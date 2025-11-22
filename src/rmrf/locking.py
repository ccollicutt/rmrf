"""
Directory locking for rmrf.

Simple TTL-based locking with exact path matching.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from rmrf.models import DirectoryLock
from rmrf.store import PlanStore


class LockError(Exception):
    """Raised when lock operations fail."""

    pass


class LockManager:
    """
    Manages directory locks to prevent concurrent operations.

    Uses simple TTL-based expiration with exact path matching.
    """

    DEFAULT_LOCK_DIR = Path("/var/lib/rmrf/locks")

    def __init__(self, lock_dir: Path | None = None, auto_create: bool = True) -> None:
        """
        Initialize lock manager.

        Args:
            lock_dir: Directory for lock files (default: /var/lib/rmrf/locks or RMRF_LOCK_DIR)
            auto_create: Automatically create directory if missing
        """
        # Check environment variable if lock_dir not provided
        if lock_dir is None:
            env_lock_dir = os.getenv("RMRF_LOCK_DIR")
            if env_lock_dir:
                lock_dir = Path(env_lock_dir)
            else:
                lock_dir = self.DEFAULT_LOCK_DIR

        self.lock_dir = lock_dir
        self.auto_create = auto_create

        if self.auto_create and not self.lock_dir.exists():
            try:
                self.lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            except OSError as e:
                raise LockError(f"Failed to create lock directory: {e}") from e

    def _get_canonical_path(self, path: Path | str) -> Path:
        """
        Get canonical absolute path.

        Args:
            path: Path to canonicalize

        Returns:
            Resolved absolute path
        """
        return Path(path).resolve()

    def _get_lock_filename(self, canonical_path: Path) -> str:
        """
        Get lock filename for a path.

        Args:
            canonical_path: Canonical path

        Returns:
            Lock filename (SHA-256 hash)
        """
        path_str = str(canonical_path)
        path_hash = hashlib.sha256(path_str.encode()).hexdigest()
        return f"{path_hash}.json"

    def _get_lock_file_path(self, canonical_path: Path) -> Path:
        """
        Get full path to lock file.

        Args:
            canonical_path: Canonical path

        Returns:
            Lock file path
        """
        filename = self._get_lock_filename(canonical_path)
        return self.lock_dir / filename

    def acquire_lock(self, path: Path | str, plan_id: str) -> DirectoryLock:
        """
        Acquire lock on directory.

        Args:
            path: Directory path to lock
            plan_id: Plan ID acquiring the lock

        Returns:
            DirectoryLock object

        Raises:
            LockError: If directory is already locked
        """
        canonical_path = self._get_canonical_path(path)
        lock_file = self._get_lock_file_path(canonical_path)

        # Check if already locked
        if lock_file.exists():
            try:
                existing_lock = self._load_lock(lock_file)
                raise LockError(
                    f"Directory {canonical_path} is locked by plan {existing_lock.plan_id} "
                    f"(locked at {existing_lock.locked_at})"
                )
            except (OSError, json.JSONDecodeError):
                # Lock file corrupted, remove it
                try:
                    lock_file.unlink()
                except OSError:
                    pass

        # Create lock
        lock = DirectoryLock(
            lock_id=f"lock-{uuid.uuid4().hex[:16]}",
            directory_path=str(canonical_path),
            plan_id=plan_id,
            locked_by_uid=os.getuid(),
            locked_at=datetime.now(timezone.utc),
        )

        # Write lock file
        try:
            if not self.lock_dir.exists():
                if self.auto_create:
                    self.lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                else:
                    raise LockError(f"Lock directory does not exist: {self.lock_dir}")

            # Atomic write using exclusive creation
            lock_json = lock.model_dump_json(indent=2)
            fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                os.write(fd, lock_json.encode())
            finally:
                os.close(fd)

        except FileExistsError:
            # Race condition - another process acquired lock
            existing_lock = self._load_lock(lock_file)
            raise LockError(
                f"Directory {canonical_path} is locked by plan {existing_lock.plan_id} "
                f"(locked at {existing_lock.locked_at})"
            ) from None
        except OSError as e:
            raise LockError(f"Failed to acquire lock for {canonical_path}: {e}") from e

        return lock

    def release_lock(self, plan_id: str) -> None:
        """
        Release lock for a plan.

        Args:
            plan_id: Plan ID to release lock for

        Raises:
            LockError: If lock not found or release fails
        """
        # Find lock file for this plan
        if not self.lock_dir.exists():
            raise LockError(f"Lock directory does not exist: {self.lock_dir}")

        for lock_file in self.lock_dir.glob("*.json"):
            try:
                lock = self._load_lock(lock_file)
                if lock.plan_id == plan_id:
                    # Found the lock, delete it
                    try:
                        lock_file.unlink()
                        return
                    except OSError as e:
                        raise LockError(f"Failed to release lock for plan {plan_id}: {e}") from e
            except (OSError, json.JSONDecodeError):
                # Skip corrupted lock files
                continue

        # Lock not found - this is OK (idempotent)
        pass

    def is_locked(self, path: Path | str) -> bool:
        """
        Check if directory is locked.

        Args:
            path: Directory path to check

        Returns:
            True if locked, False otherwise
        """
        canonical_path = self._get_canonical_path(path)
        lock_file = self._get_lock_file_path(canonical_path)

        if not lock_file.exists():
            return False

        try:
            # Lock exists - verify it's valid
            self._load_lock(lock_file)
            return True
        except (OSError, json.JSONDecodeError):
            # Corrupted lock file - remove it
            try:
                lock_file.unlink()
            except OSError:
                pass
            return False

    def get_lock_info(self, path: Path | str) -> DirectoryLock | None:
        """
        Get lock information for a directory.

        Args:
            path: Directory path

        Returns:
            DirectoryLock object if locked, None otherwise
        """
        canonical_path = self._get_canonical_path(path)
        lock_file = self._get_lock_file_path(canonical_path)

        if not lock_file.exists():
            return None

        try:
            return self._load_lock(lock_file)
        except (OSError, json.JSONDecodeError):
            # Corrupted lock file
            try:
                lock_file.unlink()
            except OSError:
                pass
            return None

    def cleanup_expired_locks(self, plan_store: PlanStore) -> int:
        """
        Remove locks for expired plans.

        Args:
            plan_store: PlanStore to check plan expiration

        Returns:
            Number of locks removed
        """
        if not self.lock_dir.exists():
            return 0

        removed = 0
        for lock_file in self.lock_dir.glob("*.json"):
            try:
                lock = self._load_lock(lock_file)

                # Check if plan exists and is expired
                if plan_store.exists(lock.plan_id):
                    plan = plan_store.load(lock.plan_id)
                    if plan.is_expired():
                        lock_file.unlink()
                        removed += 1
                else:
                    # Plan doesn't exist, remove lock
                    lock_file.unlink()
                    removed += 1

            except (OSError, json.JSONDecodeError, Exception):
                # Skip or remove corrupted locks
                try:
                    lock_file.unlink()
                    removed += 1
                except OSError:
                    pass

        return removed

    def _load_lock(self, lock_file: Path) -> DirectoryLock:
        """
        Load lock from file.

        Args:
            lock_file: Path to lock file

        Returns:
            DirectoryLock object

        Raises:
            OSError: If file cannot be read
            json.JSONDecodeError: If JSON is invalid
        """
        lock_json = lock_file.read_text()
        lock_data = json.loads(lock_json)
        return DirectoryLock(**lock_data)

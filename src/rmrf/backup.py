"""
Backup manager and rollback system.

Creates versioned backups with SHA-256 verification and rollback manifests.
"""

import hashlib
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rmrf.models import Plan, ProtectionLevel, RollbackManifest


class BackupError(Exception):
    """Raised when backup operations fail."""

    pass


class BackupManager:
    """
    Manages backup creation and rollback operations.

    Creates versioned backups in /var/lib/rmrf/backups/<env>/<date>/<plan_id>/
    """

    DEFAULT_BACKUP_ROOT = Path("/var/lib/rmrf/backups")

    def __init__(
        self,
        backup_root: Path | None = None,
    ) -> None:
        """
        Initialize backup manager.

        Args:
            backup_root: Root directory for backups (default: /var/lib/rmrf/backups or RMRF_BACKUP_ROOT)
        """
        # Check environment variable if backup_root not provided
        if backup_root is None:
            import os

            env_backup_root = os.getenv("RMRF_BACKUP_ROOT")
            if env_backup_root:
                backup_root = Path(env_backup_root)
            else:
                backup_root = self.DEFAULT_BACKUP_ROOT

        self.backup_root = backup_root

    def create_backup(
        self,
        plan: Plan,
        protection_level: ProtectionLevel,
    ) -> RollbackManifest:
        """
        Create backup for a deletion plan.

        Args:
            plan: Deletion plan
            protection_level: Protection level (for retention settings)

        Returns:
            RollbackManifest with backup metadata

        Raises:
            BackupError: If backup creation fails
        """
        if not plan.targets:
            raise BackupError("Plan has no targets to backup")

        # Create backup directory
        backup_dir = self._create_backup_directory(plan)

        # Track backed up files and symlinks
        backed_up_files: list[Path] = []
        checksums: dict[str, str] = {}
        symlinks: dict[str, str] = {}
        total_bytes = 0
        errors = plan.check_targets_exist()

        # Backup each target
        for target_str in plan.targets:
            target = Path(target_str)

            # Skip if target doesn't exist (already recorded in errors)
            # Check using lstat() which doesn't follow symlinks
            try:
                target.lstat()
            except FileNotFoundError:
                continue

            try:
                if target.is_symlink():
                    # Store symlink target (don't follow it)
                    link_target = target.readlink()
                    symlinks[str(target)] = str(link_target)
                    backed_up_files.append(target)

                elif target.is_file():
                    # Backup single file
                    self._backup_file(target, backup_dir)
                    checksum = self._calculate_checksum(target)
                    backed_up_files.append(target)
                    checksums[str(target)] = checksum
                    total_bytes += target.stat().st_size

                elif target.is_dir():
                    # Backup directory recursively (don't follow symlinks)
                    for file_path in target.rglob("*"):
                        if file_path.is_symlink():
                            # Store symlink metadata
                            try:
                                link_target = file_path.readlink()
                                symlinks[str(file_path)] = str(link_target)
                                backed_up_files.append(file_path)
                            except (OSError, PermissionError) as e:
                                errors.append((file_path, str(e)))

                        elif file_path.is_file():
                            try:
                                self._backup_file(file_path, backup_dir, base_path=target)
                                checksum = self._calculate_checksum(file_path)
                                backed_up_files.append(file_path)
                                checksums[str(file_path)] = checksum
                                total_bytes += file_path.stat().st_size
                            except (OSError, PermissionError) as e:
                                errors.append((file_path, str(e)))

            except (OSError, PermissionError) as e:
                errors.append((target, str(e)))

        # Handle backup failures based on protection level
        if errors and protection_level.require_backup:
            error_msg = f"Backup failed for {len(errors)} file(s)"
            if protection_level.name == "critical-system":
                # Critical systems abort on any backup failure
                raise BackupError(error_msg)
            # Other levels: warn but continue

        # Generate manifest
        manifest_id = (
            f"rb-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        )

        manifest = RollbackManifest(
            manifest_id=manifest_id,
            plan_id=plan.plan_id,
            environment=plan.environment,
            files=len(backed_up_files),
            total_bytes=total_bytes,
            checksums=checksums,
            symlinks=symlinks,
            targets=plan.targets,
            backup_root=str(backup_dir),
            retention_days=protection_level.retention_days,
        )

        # Save manifest to backup directory
        manifest_path = backup_dir / "rollback-manifest.json"
        manifest_path.write_text(manifest.model_dump_json(indent=2))

        return manifest

    def _create_backup_directory(self, plan: Plan) -> Path:
        """
        Create versioned backup directory.

        Args:
            plan: Deletion plan

        Returns:
            Path to created backup directory
        """
        # Structure: /var/lib/rmrf/backups/<env>/<date>/<plan_id>/
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        backup_dir = self.backup_root / plan.environment / date_str / plan.plan_id

        backup_dir.mkdir(parents=True, exist_ok=True)

        return backup_dir

    def _backup_file(
        self,
        source: Path,
        backup_dir: Path,
        base_path: Path | None = None,
    ) -> Path:
        """
        Backup a single file to backup directory.

        Args:
            source: Source file path
            backup_dir: Backup directory
            base_path: Base path for relative structure (for directories)

        Returns:
            Path to backed up file

        Raises:
            BackupError: If backup fails
        """
        try:
            # Determine destination path
            if base_path:
                # Preserve directory structure
                rel_path = source.relative_to(base_path)
                dest = backup_dir / "files" / rel_path
            else:
                # Single file backup
                dest = backup_dir / "files" / source.name

            # Create parent directories
            dest.parent.mkdir(parents=True, exist_ok=True)

            # Copy file
            shutil.copy2(source, dest)

            return dest

        except (OSError, shutil.Error) as e:
            raise BackupError(f"Failed to backup {source}: {e}") from e

    def _calculate_checksum(self, file_path: Path) -> str:
        """
        Calculate SHA-256 checksum for a file.

        Args:
            file_path: Path to file

        Returns:
            Checksum in format "sha256:..."
        """
        sha256 = hashlib.sha256()

        with open(file_path, "rb") as f:
            # Read in chunks for memory efficiency
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)

        return f"sha256:{sha256.hexdigest()}"

    def _get_backup_path(
        self,
        original_path: Path,
        targets: list[str],
        backup_dir: Path,
    ) -> Path:
        """
        Calculate backup file path from original path.

        Args:
            original_path: Original file path
            targets: List of target paths from plan
            backup_dir: Backup directory

        Returns:
            Path to backed up file

        Raises:
            BackupError: If original path is not under any target
        """
        # Try to find which target this file belongs to
        for target_str in targets:
            target = Path(target_str)
            try:
                if target.is_file() and original_path == target:
                    # Single file target
                    return backup_dir / "files" / original_path.name
                elif original_path.is_relative_to(target):
                    # File under directory target
                    rel_path = original_path.relative_to(target)
                    return backup_dir / "files" / rel_path
            except ValueError:
                # Not relative to this target, try next
                continue

        # Fallback: couldn't determine relationship, use filename
        return backup_dir / "files" / original_path.name

    def verify_backup(self, manifest: RollbackManifest) -> bool:
        """
        Verify backup integrity using checksums.

        Args:
            manifest: Rollback manifest

        Returns:
            True if all files match checksums, False otherwise
        """
        backup_dir = Path(manifest.backup_root)
        if not backup_dir.exists():
            return False

        for original_path_str, expected_checksum in manifest.checksums.items():
            # Find backed up file using targets
            original_path = Path(original_path_str)
            backed_up_file = self._get_backup_path(original_path, manifest.targets, backup_dir)

            if not backed_up_file.exists():
                return False

            # Verify checksum
            actual_checksum = self._calculate_checksum(backed_up_file)
            if actual_checksum != expected_checksum:
                return False

        return True

    def rollback(
        self,
        manifest: RollbackManifest,
        dry_run: bool = False,
    ) -> int:
        """
        Restore files from backup manifest.

        Args:
            manifest: Rollback manifest
            dry_run: If True, only simulate restoration

        Returns:
            Number of files restored

        Raises:
            BackupError: If rollback fails
        """
        backup_dir = Path(manifest.backup_root)
        if not backup_dir.exists():
            raise BackupError(f"Backup directory not found: {backup_dir}")

        restored_count = 0

        # First restore symlinks
        for original_path_str, link_target_str in manifest.symlinks.items():
            original_path = Path(original_path_str)
            link_target = Path(link_target_str)

            if not dry_run:
                # Create parent directory if needed
                original_path.parent.mkdir(parents=True, exist_ok=True)
                # Recreate symlink
                original_path.symlink_to(link_target)

            restored_count += 1

        # Then restore regular files
        for original_path_str, expected_checksum in manifest.checksums.items():
            original_path = Path(original_path_str)

            # Find backed up file using targets
            backed_up_file = self._get_backup_path(original_path, manifest.targets, backup_dir)

            if not backed_up_file.exists():
                raise BackupError(f"Backed up file not found: {backed_up_file}")

            # Verify checksum
            actual_checksum = self._calculate_checksum(backed_up_file)
            if actual_checksum != expected_checksum:
                raise BackupError(
                    f"Checksum mismatch for {backed_up_file}: "
                    f"expected {expected_checksum}, got {actual_checksum}"
                )

            if not dry_run:
                # Restore file
                original_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backed_up_file, original_path)

            restored_count += 1

        return restored_count

    def load_manifest(self, manifest_id: str, environment: str) -> RollbackManifest:
        """
        Load rollback manifest by ID.

        Args:
            manifest_id: Manifest ID
            environment: Environment name

        Returns:
            RollbackManifest

        Raises:
            BackupError: If manifest not found
        """
        # Search for manifest in environment's backup directories
        env_dir = self.backup_root / environment

        if not env_dir.exists():
            raise BackupError(f"No backups found for environment: {environment}")

        # Search through date directories
        for date_dir in sorted(env_dir.iterdir(), reverse=True):
            if not date_dir.is_dir():
                continue

            for plan_dir in date_dir.iterdir():
                if not plan_dir.is_dir():
                    continue

                manifest_path = plan_dir / "rollback-manifest.json"
                if manifest_path.exists():
                    manifest_json = manifest_path.read_text()
                    manifest = RollbackManifest.model_validate_json(manifest_json)

                    if manifest.manifest_id == manifest_id:
                        return manifest

        raise BackupError(f"Manifest not found: {manifest_id}")

    def cleanup_old_backups(
        self,
        environment: str,
        retention_days: int,
        dry_run: bool = False,
    ) -> int:
        """
        Remove backups older than retention period.

        Args:
            environment: Environment name
            retention_days: Retention period in days
            dry_run: If True, only simulate cleanup

        Returns:
            Number of backups removed
        """
        env_dir = self.backup_root / environment

        if not env_dir.exists():
            return 0

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        removed_count = 0

        for date_dir in env_dir.iterdir():
            if not date_dir.is_dir():
                continue

            try:
                # Parse date from directory name (YYYY-MM-DD)
                dir_date = datetime.strptime(date_dir.name, "%Y-%m-%d").replace(tzinfo=timezone.utc)

                if dir_date < cutoff_date:
                    if not dry_run:
                        shutil.rmtree(date_dir)
                    removed_count += 1

            except ValueError:
                # Skip directories that don't match date format
                continue

        return removed_count

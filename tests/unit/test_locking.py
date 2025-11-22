"""
Unit tests for directory locking.

Tests the LockManager class and locking behavior.
"""

import os

import pytest

from rmrf.locking import LockError, LockManager
from rmrf.models import Plan
from rmrf.store import PlanStore


class TestLockManager:
    """Test LockManager functionality."""

    def test_acquire_lock_success(self, tmp_path):
        """Test successful lock acquisition."""
        lock_dir = tmp_path / "locks"
        manager = LockManager(lock_dir=lock_dir)

        test_path = tmp_path / "test_dir"
        test_path.mkdir()
        plan_id = "plan-test-001"

        # Acquire lock
        lock = manager.acquire_lock(test_path, plan_id)

        assert lock.lock_id is not None
        assert lock.directory_path == str(test_path.resolve())
        assert lock.plan_id == plan_id
        assert lock.locked_by_uid is not None

        # Verify lock file exists
        lock_files = list(lock_dir.glob("*.json"))
        assert len(lock_files) == 1

    def test_acquire_lock_already_locked(self, tmp_path):
        """Test lock acquisition fails when already locked."""
        lock_dir = tmp_path / "locks"
        manager = LockManager(lock_dir=lock_dir)

        test_path = tmp_path / "test_dir"
        test_path.mkdir()

        # Acquire first lock
        manager.acquire_lock(test_path, "plan-001")

        # Try to acquire second lock - should fail
        with pytest.raises(LockError, match="is locked by plan"):
            manager.acquire_lock(test_path, "plan-002")

    def test_release_lock(self, tmp_path):
        """Test lock release."""
        lock_dir = tmp_path / "locks"
        manager = LockManager(lock_dir=lock_dir)

        test_path = tmp_path / "test_dir"
        test_path.mkdir()
        plan_id = "plan-test-001"

        # Acquire and release
        manager.acquire_lock(test_path, plan_id)
        manager.release_lock(plan_id)

        # Verify lock file removed
        lock_files = list(lock_dir.glob("*.json"))
        assert len(lock_files) == 0

    def test_release_lock_idempotent(self, tmp_path):
        """Test releasing non-existent lock doesn't fail."""
        lock_dir = tmp_path / "locks"
        manager = LockManager(lock_dir=lock_dir)

        # Release non-existent lock - should not raise
        manager.release_lock("plan-nonexistent")

    def test_is_locked(self, tmp_path):
        """Test is_locked check."""
        lock_dir = tmp_path / "locks"
        manager = LockManager(lock_dir=lock_dir)

        test_path = tmp_path / "test_dir"
        test_path.mkdir()

        # Not locked initially
        assert not manager.is_locked(test_path)

        # Acquire lock
        manager.acquire_lock(test_path, "plan-001")
        assert manager.is_locked(test_path)

        # Release lock
        manager.release_lock("plan-001")
        assert not manager.is_locked(test_path)

    def test_get_lock_info(self, tmp_path):
        """Test getting lock information."""
        lock_dir = tmp_path / "locks"
        manager = LockManager(lock_dir=lock_dir)

        test_path = tmp_path / "test_dir"
        test_path.mkdir()
        plan_id = "plan-test-001"

        # No lock initially
        assert manager.get_lock_info(test_path) is None

        # Acquire lock
        lock = manager.acquire_lock(test_path, plan_id)

        # Get lock info
        info = manager.get_lock_info(test_path)
        assert info is not None
        assert info.plan_id == plan_id
        assert info.lock_id == lock.lock_id

    def test_canonical_paths(self, tmp_path):
        """Test that symlinks resolve to same lock."""
        lock_dir = tmp_path / "locks"
        manager = LockManager(lock_dir=lock_dir)

        # Create real directory and symlink
        real_dir = tmp_path / "real_dir"
        real_dir.mkdir()
        symlink = tmp_path / "symlink"
        symlink.symlink_to(real_dir)

        # Lock via real path
        manager.acquire_lock(real_dir, "plan-001")

        # Check via symlink - should be locked
        assert manager.is_locked(symlink)

        # Try to lock via symlink - should fail
        with pytest.raises(LockError):
            manager.acquire_lock(symlink, "plan-002")

    def test_exact_path_only(self, tmp_path):
        """Test that nested paths are independent (exact match only)."""
        lock_dir = tmp_path / "locks"
        manager = LockManager(lock_dir=lock_dir)

        parent = tmp_path / "parent"
        child = parent / "child"
        parent.mkdir()
        child.mkdir()

        # Lock parent
        manager.acquire_lock(parent, "plan-parent")

        # Child should not be locked (exact match only)
        assert not manager.is_locked(child)

        # Should be able to lock child
        manager.acquire_lock(child, "plan-child")

        # Both should be locked now
        assert manager.is_locked(parent)
        assert manager.is_locked(child)

    def test_cleanup_expired_locks(self, tmp_path):
        """Test cleanup of locks for expired plans."""
        lock_dir = tmp_path / "locks"
        plan_dir = tmp_path / "plans"

        manager = LockManager(lock_dir=lock_dir)
        store = PlanStore(plan_dir=plan_dir)

        test_path = tmp_path / "test_dir"
        test_path.mkdir()

        # Create plan with short TTL
        from datetime import datetime, timedelta, timezone

        plan = Plan(
            plan_id="plan-test-001",
            environment="test",
            protection_level="safe-local",
            targets=[str(test_path)],
            file_count=0,
            total_bytes=0,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # Already expired
        )
        store.save(plan)

        # Acquire lock
        manager.acquire_lock(test_path, plan.plan_id)
        assert manager.is_locked(test_path)

        # Cleanup expired locks
        removed = manager.cleanup_expired_locks(store)
        assert removed == 1

        # Lock should be gone
        assert not manager.is_locked(test_path)

    def test_cleanup_locks_for_missing_plans(self, tmp_path):
        """Test cleanup removes locks for non-existent plans."""
        lock_dir = tmp_path / "locks"
        plan_dir = tmp_path / "plans"

        manager = LockManager(lock_dir=lock_dir)
        store = PlanStore(plan_dir=plan_dir)

        test_path = tmp_path / "test_dir"
        test_path.mkdir()

        # Acquire lock for non-existent plan
        manager.acquire_lock(test_path, "plan-nonexistent")

        # Cleanup should remove it
        removed = manager.cleanup_expired_locks(store)
        assert removed == 1
        assert not manager.is_locked(test_path)

    def test_lock_metadata(self, tmp_path):
        """Test that lock contains expected metadata."""
        lock_dir = tmp_path / "locks"
        manager = LockManager(lock_dir=lock_dir)

        test_path = tmp_path / "test_dir"
        test_path.mkdir()
        plan_id = "plan-test-001"

        # Acquire lock
        lock = manager.acquire_lock(test_path, plan_id)

        # Check metadata
        assert lock.lock_id.startswith("lock-")
        assert lock.directory_path == str(test_path.resolve())
        assert lock.plan_id == plan_id
        assert lock.locked_by_uid == os.getuid()  # Current user
        assert lock.locked_at is not None

    def test_corrupted_lock_file_recovery(self, tmp_path):
        """Test that corrupted lock files are handled gracefully."""
        lock_dir = tmp_path / "locks"
        manager = LockManager(lock_dir=lock_dir)

        test_path = tmp_path / "test_dir"
        test_path.mkdir()

        # Create corrupted lock file
        lock_filename = manager._get_lock_filename(manager._get_canonical_path(test_path))
        lock_file = lock_dir / lock_filename
        lock_file.write_text("invalid json{")

        # is_locked should return False and clean up
        assert not manager.is_locked(test_path)
        assert not lock_file.exists()

        # Should be able to acquire lock now
        lock = manager.acquire_lock(test_path, "plan-001")
        assert lock is not None

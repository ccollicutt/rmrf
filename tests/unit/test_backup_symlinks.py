"""Tests for symlink handling in backup system."""

from rmrf.backup import BackupManager
from rmrf.models import Plan, ProtectionLevel


def test_backup_preserves_symlinks(tmp_path):
    """Test that symlinks are preserved in backup metadata."""
    # Create source directory (separate from backup root)
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    # Create a file and a symlink
    target_file = source_dir / "target.txt"
    target_file.write_text("target content")

    symlink = source_dir / "link.txt"
    symlink.symlink_to(target_file)

    # Create plan
    plan = Plan(
        plan_id="plan-001",
        environment="dev",
        protection_level="safe-local",
        targets=[str(source_dir)],
        file_count=2,
        total_bytes=100,
    )

    # Create protection level
    protection_level = ProtectionLevel(
        name="safe-local",
        environment="dev",
        description="Test protection level",
        require_backup=True,
        retention_days=7,
    )

    # Create backup (in separate directory)
    backup_root = tmp_path / "backups"
    manager = BackupManager(backup_root=backup_root)
    manifest = manager.create_backup(plan, protection_level)

    # Verify symlink is in manifest
    assert str(symlink) in manifest.symlinks
    assert manifest.symlinks[str(symlink)] == str(target_file)

    # Verify regular file is in checksums
    assert str(target_file) in manifest.checksums

    # Verify file count includes both
    assert manifest.files == 2


def test_backup_symlink_in_directory(tmp_path):
    """Test that symlinks inside directories are preserved."""
    # Create directory with file and symlink
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    target_file = source_dir / "file.txt"
    target_file.write_text("content")

    symlink = source_dir / "link.txt"
    symlink.symlink_to(target_file)

    # Create plan
    plan = Plan(
        plan_id="plan-002",
        environment="dev",
        protection_level="safe-local",
        targets=[str(source_dir)],
        file_count=2,
        total_bytes=100,
    )

    protection_level = ProtectionLevel(
        name="safe-local",
        environment="dev",
        description="Test protection level",
        require_backup=True,
        retention_days=7,
    )

    # Create backup
    backup_root = tmp_path / "backups"
    manager = BackupManager(backup_root=backup_root)
    manifest = manager.create_backup(plan, protection_level)

    # Verify symlink is preserved
    assert str(symlink) in manifest.symlinks
    assert manifest.symlinks[str(symlink)] == str(target_file)


def test_rollback_recreates_symlinks(tmp_path):
    """Test that rollback recreates symlinks correctly."""
    # Create original structure
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    target_file = source_dir / "target.txt"
    target_file.write_text("original content")

    symlink = source_dir / "link.txt"
    symlink.symlink_to(target_file)

    # Create plan and backup
    plan = Plan(
        plan_id="plan-003",
        environment="dev",
        protection_level="safe-local",
        targets=[str(source_dir)],
        file_count=2,
        total_bytes=100,
    )

    protection_level = ProtectionLevel(
        name="safe-local",
        environment="dev",
        description="Test protection level",
        require_backup=True,
        retention_days=7,
    )

    backup_root = tmp_path / "backups"
    manager = BackupManager(backup_root=backup_root)
    manifest = manager.create_backup(plan, protection_level)

    # Delete the original files
    symlink.unlink()
    target_file.unlink()

    assert not symlink.exists()
    assert not target_file.exists()

    # Rollback
    restored_count = manager.rollback(manifest)

    # Verify both file and symlink are restored
    assert restored_count == 2
    assert target_file.exists()
    assert target_file.read_text() == "original content"
    assert symlink.exists()
    assert symlink.is_symlink()
    assert symlink.readlink() == target_file


def test_backup_absolute_symlink(tmp_path):
    """Test that absolute symlinks are preserved correctly."""
    # Create file and absolute symlink
    target_file = tmp_path / "target.txt"
    target_file.write_text("content")

    symlink_dir = tmp_path / "links"
    symlink_dir.mkdir()

    symlink = symlink_dir / "link.txt"
    symlink.symlink_to(target_file.absolute())

    # Create plan
    plan = Plan(
        plan_id="plan-004",
        environment="dev",
        protection_level="safe-local",
        targets=[str(symlink_dir)],
        file_count=1,
        total_bytes=0,
    )

    protection_level = ProtectionLevel(
        name="safe-local",
        environment="dev",
        description="Test protection level",
        require_backup=True,
        retention_days=7,
    )

    # Create backup
    backup_root = tmp_path / "backups"
    manager = BackupManager(backup_root=backup_root)
    manifest = manager.create_backup(plan, protection_level)

    # Verify absolute symlink is preserved
    assert str(symlink) in manifest.symlinks
    assert manifest.symlinks[str(symlink)] == str(target_file.absolute())

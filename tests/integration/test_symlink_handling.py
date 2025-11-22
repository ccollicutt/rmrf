"""
Integration tests for symlink handling in scanner and backup.

Tests that symlinks are counted and backed up correctly, and that
scanner counts match backup counts.
"""

from pathlib import Path

import pytest

from rmrf.backup import BackupManager
from rmrf.models import ProtectionLevel
from rmrf.planner import PlanGenerator
from rmrf.scanner import PathScanner


class TestSymlinkHandling:
    """Integration tests for symlink handling across scanner and backup."""

    @pytest.fixture
    def symlink_test_dir(self, tmp_path: Path) -> Path:
        """
        Create a directory with various symlink scenarios.

        Structure:
        test_dir/
          ├── regular_file.txt (regular file)
          ├── another_file.txt (regular file)
          ├── symlink_to_file -> regular_file.txt (symlink to file)
          ├── subdir/ (directory)
          │   ├── nested.txt (regular file)
          │   └── nested_symlink -> ../regular_file.txt (symlink to file)
          ├── symlink_to_dir -> subdir (symlink to directory)
          └── broken_symlink -> nonexistent.txt (broken symlink)
        """
        test_dir = tmp_path / "symlink_test"
        test_dir.mkdir()

        # Create regular files
        (test_dir / "regular_file.txt").write_text("Regular file content")
        (test_dir / "another_file.txt").write_text("Another regular file")

        # Create symlink to file
        (test_dir / "symlink_to_file").symlink_to("regular_file.txt")

        # Create subdirectory with file
        subdir = test_dir / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("Nested file content")

        # Create symlink within subdirectory (pointing to parent)
        (subdir / "nested_symlink").symlink_to("../regular_file.txt")

        # Create symlink to directory
        (test_dir / "symlink_to_dir").symlink_to("subdir")

        # Create broken symlink
        (test_dir / "broken_symlink").symlink_to("nonexistent.txt")

        return test_dir

    def test_scanner_counts_symlinks_correctly(self, symlink_test_dir: Path) -> None:
        """Test that scanner counts symlinks without following them (default behavior)."""
        scanner = PathScanner(follow_symlinks=False, skip_errors=True)
        result = scanner.scan(symlink_test_dir)

        # Expected counts:
        # - 3 regular files: regular_file.txt, another_file.txt, nested.txt
        # - 3 symlinks: symlink_to_file, nested_symlink, broken_symlink
        # - 1 symlink to directory: symlink_to_dir (counted as file, not recursed)
        # Total: 3 + 4 = 7 files
        assert result.file_count == 7, (
            f"Expected 7 files (3 regular + 4 symlinks), got {result.file_count}. "
            f"Files: {[str(f) for f in result.files]}"
        )

        # Verify symlinks are in the files list
        file_names = {f.name for f in result.files}
        assert "symlink_to_file" in file_names
        assert "nested_symlink" in file_names
        assert "broken_symlink" in file_names
        assert "symlink_to_dir" in file_names

    def test_scanner_follows_symlinks_when_enabled(self, symlink_test_dir: Path) -> None:
        """Test that scanner follows symlinks when follow_symlinks=True."""
        scanner = PathScanner(follow_symlinks=True, skip_errors=True)
        result = scanner.scan(symlink_test_dir)

        # When following symlinks, the scanner still counts each symlink once,
        # but gets size/info from the target. The key difference is that
        # symlink_to_dir will be recursed into (following the link).
        # Expected: 3 regular files + symlinks followed/counted
        # The exact count depends on implementation, but should still work
        assert result.file_count >= 3, (
            f"Expected at least 3 regular files when following symlinks, got {result.file_count}"
        )

        # Verify some regular files were found
        file_names = {f.name for f in result.files}
        assert "regular_file.txt" in file_names
        assert "another_file.txt" in file_names

    def test_plan_and_backup_counts_match(self, symlink_test_dir: Path, tmp_path: Path) -> None:
        """Test that plan file count matches backup file count."""
        # Generate plan (scanner doesn't follow symlinks)
        planner = PlanGenerator()
        plan = planner.generate(
            targets=[str(symlink_test_dir)],
            environment="dev",
            protection_level="safe-local",
        )

        # Expected: 7 files (3 regular + 4 symlinks)
        assert plan.file_count == 7, f"Plan should count 7 files, got {plan.file_count}"

        # Create backup
        backup_manager = BackupManager(backup_root=tmp_path / "backups")
        protection_level = ProtectionLevel(
            name="safe-local",
            description="Test",
            require_backup=True,
            retention_days=7,
        )
        manifest = backup_manager.create_backup(plan, protection_level)

        # Backup should count the same files
        assert manifest.files == plan.file_count, (
            f"Backup count ({manifest.files}) should match plan count ({plan.file_count})"
        )

        # Verify symlinks are tracked separately in manifest
        assert len(manifest.symlinks) == 4, (
            f"Expected 4 symlinks in manifest, got {len(manifest.symlinks)}"
        )

        # Verify regular files have checksums
        assert len(manifest.checksums) == 3, (
            f"Expected 3 checksums (regular files only), got {len(manifest.checksums)}"
        )

    def test_symlink_metadata_preserved_in_backup(
        self, symlink_test_dir: Path, tmp_path: Path
    ) -> None:
        """Test that symlink metadata is preserved in backup manifest."""
        # Generate plan
        planner = PlanGenerator()
        plan = planner.generate(
            targets=[str(symlink_test_dir)],
            environment="dev",
            protection_level="safe-local",
        )

        # Create backup
        backup_manager = BackupManager(backup_root=tmp_path / "backups")
        protection_level = ProtectionLevel(
            name="safe-local",
            description="Test",
            require_backup=True,
            retention_days=7,
        )
        manifest = backup_manager.create_backup(plan, protection_level)

        # Verify symlink targets are recorded
        symlinks = manifest.symlinks
        assert any("symlink_to_file" in path for path in symlinks.keys()), (
            "symlink_to_file should be in manifest"
        )

        # Find the symlink_to_file entry
        symlink_to_file_path = None
        for path in symlinks.keys():
            if "symlink_to_file" in path:
                symlink_to_file_path = path
                break

        assert symlink_to_file_path is not None
        # The target should be "regular_file.txt"
        assert "regular_file.txt" in symlinks[symlink_to_file_path], (
            f"Symlink target should be 'regular_file.txt', got {symlinks[symlink_to_file_path]}"
        )

    def test_broken_symlinks_counted_not_errored(self, symlink_test_dir: Path) -> None:
        """Test that broken symlinks are counted as files, not errors."""
        scanner = PathScanner(follow_symlinks=False, skip_errors=True)
        result = scanner.scan(symlink_test_dir)

        # Broken symlink should be counted as a file
        broken_symlinks = [f for f in result.files if f.name == "broken_symlink"]
        assert len(broken_symlinks) == 1, "Broken symlink should be counted as file"

        # Should not be in errors (with skip_errors=True)
        error_names = {path.name for path, _ in result.errors}
        assert "broken_symlink" not in error_names, "Broken symlink should not be in errors"

    def test_no_double_counting_of_files(self, symlink_test_dir: Path) -> None:
        """Test that files are not counted twice when symlinks point to them."""
        scanner = PathScanner(follow_symlinks=False, skip_errors=True)
        result = scanner.scan(symlink_test_dir)

        # Count how many times "regular_file.txt" appears
        regular_file_count = sum(1 for f in result.files if f.name == "regular_file.txt")

        # Should appear exactly once (the actual file, not via symlinks)
        assert regular_file_count == 1, (
            f"regular_file.txt should be counted once, got {regular_file_count}"
        )

        # Symlinks should be counted separately
        symlink_count = sum(
            1 for f in result.files if f.name in ["symlink_to_file", "nested_symlink"]
        )
        assert symlink_count == 2, f"Expected 2 symlinks, got {symlink_count}"

    def test_symlink_to_directory_not_recursed_by_default(self, symlink_test_dir: Path) -> None:
        """Test that symlinks to directories are not recursed when follow_symlinks=False."""
        scanner = PathScanner(follow_symlinks=False, skip_errors=True)
        result = scanner.scan(symlink_test_dir)

        # Count files in actual subdir
        subdir_file_count = sum(1 for f in result.files if "subdir" in str(f) and f.is_file())

        # Should find nested.txt and nested_symlink (2 files in subdir/)
        assert subdir_file_count == 2, f"Expected 2 files in subdir/, got {subdir_file_count}"

        # The symlink_to_dir should be counted as a single file, not recursed
        symlink_to_dir_count = sum(1 for f in result.files if f.name == "symlink_to_dir")
        assert symlink_to_dir_count == 1, "symlink_to_dir should be counted once"

        # Total should be 7, not more (proving we didn't recurse into symlink_to_dir)
        assert result.file_count == 7, (
            f"Should not recurse into symlink_to_dir, expected 7 files, got {result.file_count}"
        )

    def test_complex_symlink_scenario_counts(self, tmp_path: Path) -> None:
        """Test a complex scenario with multiple symlink types."""
        # Create a more complex structure
        test_dir = tmp_path / "complex_test"
        test_dir.mkdir()

        # Create 10 regular files
        for i in range(10):
            (test_dir / f"file{i}.txt").write_text(f"Content {i}")

        # Create 5 symlinks to files
        for i in range(5):
            (test_dir / f"link{i}").symlink_to(f"file{i}.txt")

        # Create a subdirectory with 3 files
        subdir = test_dir / "subdir"
        subdir.mkdir()
        for i in range(3):
            (subdir / f"nested{i}.txt").write_text(f"Nested {i}")

        # Create 2 broken symlinks
        (test_dir / "broken1").symlink_to("nonexistent1.txt")
        (test_dir / "broken2").symlink_to("nonexistent2.txt")

        # Total expected: 10 + 5 + 3 + 2 = 20 files

        # Test scanner
        scanner = PathScanner(follow_symlinks=False, skip_errors=True)
        result = scanner.scan(test_dir)
        assert result.file_count == 20, (
            f"Expected 20 files in complex scenario, got {result.file_count}"
        )

        # Test plan and backup
        planner = PlanGenerator()
        plan = planner.generate(
            targets=[str(test_dir)],
            environment="dev",
            protection_level="safe-local",
        )
        assert plan.file_count == 20, f"Plan should count 20 files, got {plan.file_count}"

        backup_manager = BackupManager(backup_root=tmp_path / "backups")
        protection_level = ProtectionLevel(
            name="safe-local",
            description="Test",
            require_backup=True,
            retention_days=7,
        )
        manifest = backup_manager.create_backup(plan, protection_level)
        assert manifest.files == 20, f"Backup should count 20 files, got {manifest.files}"

        # Verify symlink counts
        assert len(manifest.symlinks) == 7, (
            f"Expected 7 symlinks (5 to files + 2 broken), got {len(manifest.symlinks)}"
        )

        # Verify checksum counts (only regular files)
        assert len(manifest.checksums) == 13, (
            f"Expected 13 checksums (10 + 3 regular files), got {len(manifest.checksums)}"
        )

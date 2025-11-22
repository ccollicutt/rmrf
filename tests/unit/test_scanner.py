"""
Unit tests for rmrf.scanner.

Tests path scanning and file enumeration.
"""

from pathlib import Path

import pytest

from rmrf.scanner import PathScanner, ScanResult


class TestScanResult:
    """Tests for ScanResult class."""

    def test_empty_result(self) -> None:
        """Test empty scan result."""
        result = ScanResult()
        assert result.file_count == 0
        assert result.directory_count == 0
        assert result.total_bytes == 0
        assert len(result.errors) == 0

    def test_result_with_files(self) -> None:
        """Test scan result with files."""
        result = ScanResult()
        result.files.append(Path("/tmp/file1.txt"))
        result.files.append(Path("/tmp/file2.txt"))
        result.total_bytes = 2048

        assert result.file_count == 2
        assert result.total_bytes == 2048

    def test_result_with_directories(self) -> None:
        """Test scan result with directories."""
        result = ScanResult()
        result.directories.append(Path("/tmp/dir1"))
        result.directories.append(Path("/tmp/dir2"))

        assert result.directory_count == 2


class TestPathScanner:
    """Tests for PathScanner class."""

    def test_scanner_initialization(self) -> None:
        """Test scanner initialization with defaults."""
        scanner = PathScanner()
        assert scanner.follow_symlinks is False
        assert scanner.skip_errors is True

    def test_scanner_custom_options(self) -> None:
        """Test scanner with custom options."""
        scanner = PathScanner(follow_symlinks=True, skip_errors=False)
        assert scanner.follow_symlinks is True
        assert scanner.skip_errors is False

    def test_scan_single_file(self, tmp_path: Path) -> None:
        """Test scanning a single file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, world!")

        scanner = PathScanner()
        result = scanner.scan(test_file)

        assert result.file_count == 1
        assert result.total_bytes == len("Hello, world!")
        assert test_file in result.files

    def test_scan_empty_directory(self, tmp_path: Path) -> None:
        """Test scanning an empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        scanner = PathScanner()
        result = scanner.scan(empty_dir)

        assert result.file_count == 0
        assert result.directory_count == 1
        assert empty_dir in result.directories

    def test_scan_directory_with_files(self, tmp_path: Path) -> None:
        """Test scanning directory with files."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()

        # Create test files
        (test_dir / "file1.txt").write_text("File 1")
        (test_dir / "file2.txt").write_text("File 2")
        (test_dir / "file3.txt").write_text("File 3")

        scanner = PathScanner()
        result = scanner.scan(test_dir)

        assert result.file_count == 3
        assert result.directory_count == 1
        assert result.total_bytes == len("File 1") + len("File 2") + len("File 3")

    def test_scan_nested_directories(self, tmp_path: Path) -> None:
        """Test scanning nested directories."""
        base_dir = tmp_path / "base"
        base_dir.mkdir()

        # Create nested structure
        sub_dir1 = base_dir / "sub1"
        sub_dir1.mkdir()
        sub_dir2 = base_dir / "sub2"
        sub_dir2.mkdir()
        deep_dir = sub_dir1 / "deep"
        deep_dir.mkdir()

        # Add files at different levels
        (base_dir / "root.txt").write_text("root")
        (sub_dir1 / "sub1.txt").write_text("sub1")
        (sub_dir2 / "sub2.txt").write_text("sub2")
        (deep_dir / "deep.txt").write_text("deep")

        scanner = PathScanner()
        result = scanner.scan(base_dir)

        assert result.file_count == 4
        assert result.directory_count == 4  # base, sub1, sub2, deep
        assert result.total_bytes == len("root") + len("sub1") + len("sub2") + len("deep")

    def test_scan_nonexistent_path_skip_errors(self, tmp_path: Path) -> None:
        """Test scanning nonexistent path with skip_errors=True."""
        nonexistent = tmp_path / "does_not_exist"

        scanner = PathScanner(skip_errors=True)
        result = scanner.scan(nonexistent)

        assert result.file_count == 0
        assert len(result.errors) == 1
        assert result.errors[0][0] == nonexistent

    def test_scan_nonexistent_path_raise_errors(self, tmp_path: Path) -> None:
        """Test scanning nonexistent path with skip_errors=False."""
        nonexistent = tmp_path / "does_not_exist"

        scanner = PathScanner(skip_errors=False)

        with pytest.raises(FileNotFoundError):
            scanner.scan(nonexistent)

    def test_scan_symlink_no_follow(self, tmp_path: Path) -> None:
        """Test scanning symlink without following."""
        target_file = tmp_path / "target.txt"
        target_file.write_text("Target content")

        symlink = tmp_path / "link.txt"
        symlink.symlink_to(target_file)

        scanner = PathScanner(follow_symlinks=False)
        result = scanner.scan(symlink)

        assert result.file_count == 1
        assert symlink in result.files

    def test_scan_symlink_follow(self, tmp_path: Path) -> None:
        """Test scanning symlink with following."""
        target_file = tmp_path / "target.txt"
        target_file.write_text("Target content")

        symlink = tmp_path / "link.txt"
        symlink.symlink_to(target_file)

        scanner = PathScanner(follow_symlinks=True)
        result = scanner.scan(symlink)

        assert result.file_count == 1
        assert result.total_bytes == len("Target content")

    def test_scan_directory_with_symlinks_no_double_count(self, tmp_path: Path) -> None:
        """
        Test that symlinks in a directory are counted correctly without double-counting.

        This is a regression test for the bug where is_file() and is_dir() were
        checked before is_symlink(), causing symlinks to be followed even when
        follow_symlinks=False.
        """
        test_dir = tmp_path / "test"
        test_dir.mkdir()

        # Create a regular file
        regular_file = test_dir / "regular.txt"
        regular_file.write_text("Regular content")

        # Create a symlink to the regular file
        symlink_to_file = test_dir / "link_to_regular.txt"
        symlink_to_file.symlink_to("regular.txt")

        # Create a subdirectory with a file
        subdir = test_dir / "subdir"
        subdir.mkdir()
        nested_file = subdir / "nested.txt"
        nested_file.write_text("Nested content")

        # Create a symlink to the subdirectory
        symlink_to_dir = test_dir / "link_to_subdir"
        symlink_to_dir.symlink_to("subdir")

        # Create a broken symlink
        broken_symlink = test_dir / "broken_link"
        broken_symlink.symlink_to("nonexistent.txt")

        scanner = PathScanner(follow_symlinks=False, skip_errors=True)
        result = scanner.scan(test_dir)

        # Expected counts:
        # - 2 regular files: regular.txt, nested.txt
        # - 3 symlinks: link_to_regular.txt, link_to_subdir, broken_link
        # Total: 5 files
        assert result.file_count == 5, (
            f"Expected 5 files (2 regular + 3 symlinks), got {result.file_count}. "
            f"Files: {[str(f.name) for f in result.files]}"
        )

        # Verify no double-counting: regular.txt should appear exactly once
        regular_txt_count = sum(1 for f in result.files if f.name == "regular.txt")
        assert regular_txt_count == 1, f"regular.txt should appear once, got {regular_txt_count}"

        # Verify symlinks are in the file list
        file_names = {f.name for f in result.files}
        assert "link_to_regular.txt" in file_names, "Symlink to file should be counted"
        assert "link_to_subdir" in file_names, "Symlink to dir should be counted as file"
        assert "broken_link" in file_names, "Broken symlink should be counted"

        # Verify we didn't recurse into symlink_to_dir (only 1 subdir, not 2)
        assert result.directory_count == 2, (
            f"Should have 2 directories (test_dir and subdir), got {result.directory_count}"
        )

    def test_scan_directory_symlinks_followed_when_enabled(self, tmp_path: Path) -> None:
        """Test that symlinks in a directory are followed when follow_symlinks=True."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()

        # Create a regular file
        regular_file = test_dir / "regular.txt"
        regular_file.write_text("Regular")

        # Create a symlink to the regular file
        symlink_to_file = test_dir / "link_to_regular.txt"
        symlink_to_file.symlink_to("regular.txt")

        scanner = PathScanner(follow_symlinks=True, skip_errors=True)
        result = scanner.scan(test_dir)

        # When following symlinks, the target is scanned
        # Both the original file and the symlink resolve to the same content
        assert result.file_count >= 1
        assert result.total_bytes >= len("Regular")

    def test_scan_multiple_paths(self, tmp_path: Path) -> None:
        """Test scanning multiple paths."""
        dir1 = tmp_path / "dir1"
        dir1.mkdir()
        (dir1 / "file1.txt").write_text("File 1")

        dir2 = tmp_path / "dir2"
        dir2.mkdir()
        (dir2 / "file2.txt").write_text("File 2")

        scanner = PathScanner()
        result = scanner.scan_multiple([dir1, dir2])

        assert result.file_count == 2
        assert result.directory_count == 2
        assert result.total_bytes == len("File 1") + len("File 2")

    def test_iter_files(self, tmp_path: Path) -> None:
        """Test iterating over files."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()

        # Create test files
        (test_dir / "file1.txt").write_text("1")
        (test_dir / "file2.txt").write_text("2")
        (test_dir / "file3.txt").write_text("3")

        scanner = PathScanner()
        files = list(scanner.iter_files(test_dir))

        assert len(files) == 3
        assert all(f.is_file() for f in files)

    def test_scan_large_directory_count(self, tmp_path: Path) -> None:
        """Test scanning directory with many files."""
        test_dir = tmp_path / "large"
        test_dir.mkdir()

        # Create 100 files
        for i in range(100):
            (test_dir / f"file{i}.txt").write_text(f"Content {i}")

        scanner = PathScanner()
        result = scanner.scan(test_dir)

        assert result.file_count == 100
        assert result.directory_count == 1

    def test_scan_mixed_content(self, tmp_path: Path) -> None:
        """Test scanning directory with mixed content types."""
        test_dir = tmp_path / "mixed"
        test_dir.mkdir()

        # Files
        (test_dir / "file.txt").write_text("file")

        # Subdirectory with files
        sub_dir = test_dir / "subdir"
        sub_dir.mkdir()
        (sub_dir / "nested.txt").write_text("nested")

        # Empty subdirectory
        empty_dir = test_dir / "empty"
        empty_dir.mkdir()

        scanner = PathScanner()
        result = scanner.scan(test_dir)

        assert result.file_count == 2
        assert result.directory_count == 3  # test_dir, subdir, empty
        assert result.total_bytes == len("file") + len("nested")

    def test_scan_preserves_path_order(self, tmp_path: Path) -> None:
        """Test that scan preserves some reasonable path order."""
        test_dir = tmp_path / "ordered"
        test_dir.mkdir()

        (test_dir / "a.txt").write_text("a")
        (test_dir / "b.txt").write_text("b")
        (test_dir / "c.txt").write_text("c")

        scanner = PathScanner()
        result = scanner.scan(test_dir)

        assert result.file_count == 3
        # Files are present (order not strictly guaranteed but should be consistent)
        file_names = {f.name for f in result.files}
        assert file_names == {"a.txt", "b.txt", "c.txt"}

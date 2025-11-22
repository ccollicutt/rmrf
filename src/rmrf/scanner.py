"""
Path scanning and file enumeration.

Recursively scans directories and enumerates files for deletion planning.
"""

from collections.abc import Iterator
from pathlib import Path


class ScanResult:
    """Result of scanning a path."""

    def __init__(self) -> None:
        """Initialize scan result."""
        self.files: list[Path] = []
        self.directories: list[Path] = []
        self.total_bytes: int = 0
        self.errors: list[tuple[Path, str]] = []

    @property
    def file_count(self) -> int:
        """Get total file count."""
        return len(self.files)

    @property
    def directory_count(self) -> int:
        """Get total directory count."""
        return len(self.directories)


class PathScanner:
    """
    Scans paths and enumerates files for deletion.

    Handles symlinks, permission errors, and large directories efficiently.
    """

    def __init__(
        self,
        follow_symlinks: bool = False,
        skip_errors: bool = True,
    ) -> None:
        """
        Initialize path scanner.

        Args:
            follow_symlinks: Whether to follow symbolic links
            skip_errors: Whether to skip permission/access errors
        """
        self.follow_symlinks = follow_symlinks
        self.skip_errors = skip_errors

    def scan(self, path: Path) -> ScanResult:
        """
        Scan a path and enumerate all files.

        Args:
            path: Path to scan (file or directory)

        Returns:
            ScanResult with enumerated files and metadata
        """
        result = ScanResult()

        if not path.exists():
            if not self.skip_errors:
                raise FileNotFoundError(f"Path does not exist: {path}")
            result.errors.append((path, "Path does not exist"))
            return result

        # Check symlink FIRST before is_file() or is_dir() (which follow symlinks)
        if path.is_symlink():
            if self.follow_symlinks:
                target = path.resolve()
                return self.scan(target)
            else:
                # Treat as file for size calculation (don't follow)
                try:
                    result.files.append(path)
                    result.total_bytes += 0  # Symlinks have negligible size
                except (OSError, PermissionError) as e:
                    if not self.skip_errors:
                        raise
                    result.errors.append((path, str(e)))
            return result

        # Handle single file
        if path.is_file():
            try:
                stat = path.stat()
                result.files.append(path)
                result.total_bytes += stat.st_size
            except (OSError, PermissionError) as e:
                if not self.skip_errors:
                    raise
                result.errors.append((path, str(e)))
            return result

        # Handle directory
        if path.is_dir():
            self._scan_directory(path, result)
            return result

        return result

    def _scan_directory(self, directory: Path, result: ScanResult) -> None:
        """
        Recursively scan a directory.

        Args:
            directory: Directory to scan
            result: ScanResult to populate
        """
        try:
            # Add directory itself
            result.directories.append(directory)

            # Scan contents
            for entry in directory.iterdir():
                try:
                    # Check symlinks FIRST before is_file() or is_dir() (which follow symlinks)
                    if entry.is_symlink():
                        if self.follow_symlinks:
                            target = entry.resolve()
                            if target.is_file():
                                stat = target.stat()
                                result.files.append(entry)
                                result.total_bytes += stat.st_size
                            elif target.is_dir():
                                self._scan_directory(target, result)
                        else:
                            # Count symlink as file (don't follow)
                            result.files.append(entry)
                            result.total_bytes += 0
                    elif entry.is_file():
                        stat = entry.stat()
                        result.files.append(entry)
                        result.total_bytes += stat.st_size
                    elif entry.is_dir():
                        # Recurse into subdirectory
                        self._scan_directory(entry, result)
                except (OSError, PermissionError) as e:
                    if not self.skip_errors:
                        raise
                    result.errors.append((entry, str(e)))
        except (OSError, PermissionError) as e:
            if not self.skip_errors:
                raise
            result.errors.append((directory, str(e)))

    def scan_multiple(self, paths: list[Path]) -> ScanResult:
        """
        Scan multiple paths and combine results.

        Args:
            paths: List of paths to scan

        Returns:
            Combined ScanResult
        """
        combined = ScanResult()

        for path in paths:
            result = self.scan(path)
            combined.files.extend(result.files)
            combined.directories.extend(result.directories)
            combined.total_bytes += result.total_bytes
            combined.errors.extend(result.errors)

        return combined

    def iter_files(self, path: Path) -> Iterator[Path]:
        """
        Iterate over files in path (generator for memory efficiency).

        Args:
            path: Path to scan

        Yields:
            Path objects for each file
        """
        if path.is_file():
            yield path
            return

        if not path.is_dir():
            return

        try:
            for entry in path.rglob("*"):
                try:
                    if entry.is_file():
                        yield entry
                except (OSError, PermissionError):
                    if not self.skip_errors:
                        raise
        except (OSError, PermissionError):
            if not self.skip_errors:
                raise

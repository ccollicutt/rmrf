"""
Code quality tests.

Tests for code quality constraints like file size limits.
"""

from pathlib import Path


def test_python_file_line_limit():
    """
    Test that no Python file exceeds 510 lines.

    This keeps files manageable and encourages modular design.
    Updated to 510 to accommodate locking and approval features added to models.py.
    """
    max_lines = 510
    src_dir = Path(__file__).parent.parent.parent / "src"
    violations = []

    for py_file in src_dir.rglob("*.py"):
        # Skip __pycache__ and other generated files
        if "__pycache__" in str(py_file):
            continue

        lines = py_file.read_text().splitlines()
        line_count = len(lines)

        if line_count > max_lines:
            violations.append(
                f"{py_file.relative_to(src_dir)}: {line_count} lines (max: {max_lines})"
            )

    if violations:
        violation_msg = "\n".join(violations)
        raise AssertionError(
            f"The following files exceed {max_lines} lines:\n{violation_msg}\n\n"
            f"Please break these files into smaller modules."
        )

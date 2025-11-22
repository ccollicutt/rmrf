"""
Integration tests for closeout command.

Tests that closeout properly handles backup retention and removal.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path


def get_rmrf_command():
    """Find the rmrf command - binary or installed.

    Supports testing the PyInstaller binary by setting RMRF_BINARY_PATH
    environment variable to the path of the binary to test.
    """
    import shutil

    # Check for binary override (for testing built binary)
    if "RMRF_BINARY_PATH" in os.environ:
        binary_path = Path(os.environ["RMRF_BINARY_PATH"])
        if binary_path.exists():
            return str(binary_path)
        # If path is set but doesn't exist, raise error
        raise FileNotFoundError(
            f"RMRF_BINARY_PATH is set to '{binary_path}' but file does not exist"
        )

    # Try to find in virtual environment
    if "VIRTUAL_ENV" in os.environ:
        venv_rmrf = Path(os.environ["VIRTUAL_ENV"]) / "bin" / "rmrf"
        if venv_rmrf.exists():
            return str(venv_rmrf)

    # Try current directory structure
    project_root = Path(__file__).parent.parent.parent
    venv_rmrf = project_root / ".venv" / "bin" / "rmrf"
    if venv_rmrf.exists():
        return str(venv_rmrf)

    # Try to find in PATH
    rmrf_path = shutil.which("rmrf")
    if rmrf_path:
        return rmrf_path

    # Fallback
    return "rmrf"


RMRF_CMD = get_rmrf_command()


class TestCloseoutCommand:
    """Integration tests for closeout command."""

    def test_closeout_keeps_backup_by_default(self):
        """Test that closeout keeps backup by default (safe behavior)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            # Create directories
            plan_dir = Path(tmpdir) / "plans"
            plan_dir.mkdir()
            backup_dir = Path(tmpdir) / "backups"
            backup_dir.mkdir()
            audit_dir = Path(tmpdir) / "audit"
            audit_dir.mkdir()

            # Set environment
            env = {
                **subprocess.os.environ,
                "RM_ENVIRONMENT": '{"env":"dev","signature":"test"}',
                "RMRF_PLAN_DIR": str(plan_dir),
                "RMRF_BACKUP_ROOT": str(backup_dir),
                "RMRF_AUDIT_DIR": str(audit_dir),
            }

            # 1. Create plan
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "plan", str(test_file)],
                capture_output=True,
                text=True,
                env=env,
            )
            if result.returncode != 0:
                print(f"Plan stdout: {result.stdout}")
                print(f"Plan stderr: {result.stderr}")
            assert result.returncode == 0, f"Plan failed: {result.stderr}"
            plan_data = json.loads(result.stdout)
            plan_id = plan_data["plan_id"]

            # 2. Validate plan
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "validate", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )
            if result.returncode != 0:
                print(f"Validate stdout: {result.stdout}")
                print(f"Validate stderr: {result.stderr}")
            assert result.returncode == 0, f"Validate failed: {result.stderr}"

            # Verify plan was updated
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "show", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            plan_info = json.loads(result.stdout)
            assert plan_info["validated"] is True, "Plan should be marked as validated"

            # 3. Stage (create backup)
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "stage", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )
            if result.returncode != 0:
                print(f"Stage stdout: {result.stdout}")
                print(f"Stage stderr: {result.stderr}")
            assert result.returncode == 0, f"Stage failed: {result.stderr}"

            # Get backup path
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "show", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            plan_info = json.loads(result.stdout)
            backup_path = Path(plan_info["backup_path"])

            # Verify backup exists
            assert backup_path.exists(), "Backup should exist after staging"

            # 4. Apply (delete files)
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "apply", plan_id, "--skip-confirmation"],
                capture_output=True,
                text=True,
                env=env,
            )
            if result.returncode != 0:
                print(f"Apply stdout: {result.stdout}")
                print(f"Apply stderr: {result.stderr}")
            assert result.returncode == 0, f"Apply failed: {result.stderr}"

            # 5. Closeout (default behavior - keeps backup)
            result = subprocess.run(
                [
                    RMRF_CMD,
                    "--json-output",
                    "closeout",
                    plan_id,
                    "--comment",
                    "Testing default behavior",
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            if result.returncode != 0:
                print(f"Closeout stdout: {result.stdout}")
                print(f"Closeout stderr: {result.stderr}")
            assert result.returncode == 0, f"Closeout failed: {result.stderr}"
            closeout_data = json.loads(result.stdout)

            # Verify results
            assert closeout_data["closed_out"] is True
            assert closeout_data["backup_removed"] is False
            assert closeout_data["backup_kept"] is True

            # Verify backup still exists
            assert backup_path.exists(), "Backup should be kept by default"

    def test_closeout_removes_backup_with_flag(self):
        """Test that closeout removes backup when --remove-backup flag is used."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            # Create directories
            plan_dir = Path(tmpdir) / "plans"
            plan_dir.mkdir()
            backup_dir = Path(tmpdir) / "backups"
            backup_dir.mkdir()
            audit_dir = Path(tmpdir) / "audit"
            audit_dir.mkdir()

            # Set environment
            env = {
                **subprocess.os.environ,
                "RM_ENVIRONMENT": '{"env":"dev","signature":"test"}',
                "RMRF_PLAN_DIR": str(plan_dir),
                "RMRF_BACKUP_ROOT": str(backup_dir),
                "RMRF_AUDIT_DIR": str(audit_dir),
            }

            # 1. Create plan
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "plan", str(test_file)],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            plan_data = json.loads(result.stdout)
            plan_id = plan_data["plan_id"]

            # 2. Validate plan
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "validate", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0

            # Verify validated
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "show", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )
            plan_info = json.loads(result.stdout)
            assert plan_info["validated"] is True

            # 3. Stage (create backup)
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "stage", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0

            # Get backup path
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "show", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )
            plan_info = json.loads(result.stdout)
            backup_path = Path(plan_info["backup_path"])

            # Verify backup exists
            assert backup_path.exists(), "Backup should exist after staging"

            # 4. Apply (delete files)
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "apply", plan_id, "--skip-confirmation"],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0

            # 5. Closeout with --remove-backup flag
            result = subprocess.run(
                [
                    RMRF_CMD,
                    "--json-output",
                    "closeout",
                    plan_id,
                    "--remove-backup",
                    "--comment",
                    "Testing backup removal",
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            closeout_data = json.loads(result.stdout)

            # Verify results
            assert closeout_data["closed_out"] is True
            assert closeout_data["backup_removed"] is True
            assert closeout_data["backup_kept"] is False

            # Verify backup was removed
            assert not backup_path.exists(), "Backup should be removed with --remove-backup flag"

    def test_closeout_requires_comment(self):
        """Test that closeout requires a comment in JSON mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            # Create directories
            plan_dir = Path(tmpdir) / "plans"
            plan_dir.mkdir()
            backup_dir = Path(tmpdir) / "backups"
            backup_dir.mkdir()
            audit_dir = Path(tmpdir) / "audit"
            audit_dir.mkdir()

            # Set environment
            env = {
                **subprocess.os.environ,
                "RM_ENVIRONMENT": '{"env":"dev","signature":"test"}',
                "RMRF_PLAN_DIR": str(plan_dir),
                "RMRF_BACKUP_ROOT": str(backup_dir),
                "RMRF_AUDIT_DIR": str(audit_dir),
            }

            # Create, validate, stage, and apply
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "plan", str(test_file)],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            plan_data = json.loads(result.stdout)
            plan_id = plan_data["plan_id"]

            subprocess.run(
                [RMRF_CMD, "--json-output", "validate", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )

            subprocess.run(
                [RMRF_CMD, "--json-output", "stage", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )

            subprocess.run(
                [RMRF_CMD, "--json-output", "apply", plan_id, "--skip-confirmation"],
                capture_output=True,
                text=True,
                env=env,
            )

            # Try closeout without comment (should fail in JSON mode)
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "closeout", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode != 0, "Closeout should fail without comment in JSON mode"
            # Should error about missing comment
            output = result.stdout + result.stderr
            assert "Comment required" in output or "comment" in output.lower()

    def test_closeout_updates_plan_state(self):
        """Test that closeout properly updates plan state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            # Create directories
            plan_dir = Path(tmpdir) / "plans"
            plan_dir.mkdir()
            backup_dir = Path(tmpdir) / "backups"
            backup_dir.mkdir()
            audit_dir = Path(tmpdir) / "audit"
            audit_dir.mkdir()

            # Set environment
            env = {
                **subprocess.os.environ,
                "RM_ENVIRONMENT": '{"env":"dev","signature":"test"}',
                "RMRF_PLAN_DIR": str(plan_dir),
                "RMRF_BACKUP_ROOT": str(backup_dir),
                "RMRF_AUDIT_DIR": str(audit_dir),
            }

            # Create, validate, stage, apply
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "plan", str(test_file)],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            plan_data = json.loads(result.stdout)
            plan_id = plan_data["plan_id"]

            subprocess.run(
                [RMRF_CMD, "--json-output", "validate", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )

            subprocess.run(
                [RMRF_CMD, "--json-output", "stage", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )

            subprocess.run(
                [RMRF_CMD, "--json-output", "apply", plan_id, "--skip-confirmation"],
                capture_output=True,
                text=True,
                env=env,
            )

            # Closeout with comment
            result = subprocess.run(
                [
                    RMRF_CMD,
                    "--json-output",
                    "closeout",
                    plan_id,
                    "--comment",
                    "All went as expected",
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0

            # Check plan state
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "show", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            plan_info = json.loads(result.stdout)

            # Verify closeout fields are set
            assert plan_info["closeout_at"] is not None, "closeout_at should be set"
            assert plan_info["closeout_comment"] == "All went as expected", (
                "closeout_comment should match"
            )

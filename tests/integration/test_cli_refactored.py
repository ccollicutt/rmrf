"""
Integration tests for refactored CLI.

Tests all CLI commands, help output, and error handling.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path


# Get rmrf command path - look for it in venv or use shutil
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


class TestCLIHelpOutput:
    """Test CLI help output formatting."""

    def test_main_help_shows_epilog(self):
        """Test main help shows getting started section."""
        result = subprocess.run(
            [RMRF_CMD, "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Getting Started" in result.stdout
        assert "What is rmrf?" in result.stdout
        assert "Why it matters:" in result.stdout
        assert "Next steps:" in result.stdout
        assert "Quick Examples:" in result.stdout

    def test_plan_help_shows_examples(self):
        """Test plan command help shows examples."""
        result = subprocess.run(
            [RMRF_CMD, "plan", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Examples:" in result.stdout
        assert "rmrf plan /tmp/old-logs" in result.stdout
        assert "Common workflow:" in result.stdout

    def test_validate_help_shows_examples(self):
        """Test validate command help shows examples."""
        result = subprocess.run(
            [RMRF_CMD, "validate", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Examples:" in result.stdout
        assert "rmrf validate plan-" in result.stdout
        assert "production-ready safety rules" in result.stdout

    def test_stage_help_shows_examples(self):
        """Test stage command help shows examples."""
        result = subprocess.run(
            [RMRF_CMD, "stage", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Examples:" in result.stdout
        assert "rmrf stage plan-" in result.stdout
        assert "SHA-256" in result.stdout

    def test_apply_help_shows_examples(self):
        """Test apply command help shows examples."""
        result = subprocess.run(
            [RMRF_CMD, "apply", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Examples:" in result.stdout
        assert "Safety checks:" in result.stdout

    def test_show_help_shows_examples(self):
        """Test show command help shows examples."""
        result = subprocess.run(
            [RMRF_CMD, "show", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Examples:" in result.stdout
        assert "rmrf show plan-" in result.stdout

    def test_status_help_shows_examples(self):
        """Test status command help shows examples."""
        result = subprocess.run(
            [RMRF_CMD, "status", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Examples:" in result.stdout

    def test_rollback_help_shows_examples(self):
        """Test rollback command help shows examples."""
        result = subprocess.run(
            [RMRF_CMD, "rollback", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Examples:" in result.stdout
        assert "Warning:" in result.stdout

    def test_init_help_shows_examples(self):
        """Test init command help shows examples."""
        result = subprocess.run(
            [RMRF_CMD, "init", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Examples:" in result.stdout
        assert "rmrf preflight" in result.stdout

    def test_preflight_help_shows_examples(self):
        """Test preflight command help shows examples."""
        result = subprocess.run(
            [RMRF_CMD, "preflight", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Examples:" in result.stdout


class TestCLIErrorHandling:
    """Test CLI error handling and messages."""

    def test_plan_without_targets_shows_error(self):
        """Test plan command without targets shows helpful error."""
        result = subprocess.run(
            [RMRF_CMD, "plan"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "Missing argument" in result.stderr or "Missing argument" in result.stdout
        assert "TARGETS" in result.stderr or "TARGETS" in result.stdout

    def test_validate_without_plan_shows_error(self):
        """Test validate command without plan shows error."""
        result = subprocess.run(
            [RMRF_CMD, "validate"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_backup_without_plan_shows_error(self):
        """Test backup command without plan shows error."""
        result = subprocess.run(
            [RMRF_CMD, "backup"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_apply_without_plan_shows_error(self):
        """Test apply command without plan shows error."""
        result = subprocess.run(
            [RMRF_CMD, "apply"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_show_without_plan_shows_error(self):
        """Test show command without plan shows error."""
        result = subprocess.run(
            [RMRF_CMD, "show"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0


class TestCLICommands:
    """Test actual CLI command execution."""

    def test_init_creates_directories(self):
        """Test init command creates required directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [RMRF_CMD, "init", "--root-dir", tmpdir],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0
            assert "SUCCESS" in result.stdout
            assert "directories created successfully" in result.stdout

            # Check directories exist
            assert (Path(tmpdir) / "plans").exists()
            assert (Path(tmpdir) / "backups").exists()
            assert (Path(tmpdir) / "audit").exists()

    def test_plan_command_with_file(self):
        """Test plan command creates a plan from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            # Create temp plan directory
            plan_dir = Path(tmpdir) / "plans"
            plan_dir.mkdir()

            # Set environment
            env = {
                **subprocess.os.environ,
                "RM_ENVIRONMENT": '{"env":"dev","signature":"test"}',
                "RMRF_PLAN_DIR": str(plan_dir),
            }

            result = subprocess.run(
                [RMRF_CMD, "--json-output", "plan", str(test_file)],
                capture_output=True,
                text=True,
                env=env,
            )

            assert result.returncode == 0
            plan_data = json.loads(result.stdout)
            assert "plan_id" in plan_data
            assert plan_data["file_count"] == 1
            assert test_file.name in str(plan_data["targets"])

    def test_plan_show_workflow(self):
        """Test creating and showing a plan."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            # Create temp plan directory
            plan_dir = Path(tmpdir) / "plans"
            plan_dir.mkdir()

            # Set environment
            env = {
                **subprocess.os.environ,
                "RM_ENVIRONMENT": '{"env":"dev","signature":"test"}',
                "RMRF_PLAN_DIR": str(plan_dir),
            }

            # Create plan
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "plan", str(test_file)],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            plan_data = json.loads(result.stdout)
            plan_id = plan_data["plan_id"]

            # Show plan
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "show", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            shown_plan = json.loads(result.stdout)
            assert shown_plan["plan_id"] == plan_id

    def test_validate_command_with_plan(self):
        """Test validate command with a plan."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            # Create temp plan directory
            plan_dir = Path(tmpdir) / "plans"
            plan_dir.mkdir()

            # Set environment
            env = {
                **subprocess.os.environ,
                "RM_ENVIRONMENT": '{"env":"dev","signature":"test"}',
                "RMRF_PLAN_DIR": str(plan_dir),
            }

            # Create plan
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "plan", str(test_file)],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            plan_data = json.loads(result.stdout)
            plan_id = plan_data["plan_id"]

            # Validate plan
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "validate", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            validation_result = json.loads(result.stdout)
            assert validation_result["valid"] is True
            assert validation_result["verdict"] == "allow"

    def test_backup_command_with_plan(self):
        """Test backup command creates backup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            backup_dir = Path(tmpdir) / "backups"

            # Create temp plan directory
            plan_dir = Path(tmpdir) / "plans"
            plan_dir.mkdir()

            # Set environment
            env = {
                **subprocess.os.environ,
                "RM_ENVIRONMENT": '{"env":"dev","signature":"test"}',
                "RMRF_PLAN_DIR": str(plan_dir),
            }

            # Create plan - use json output to get plan_id
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "plan", str(test_file)],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            plan_data = json.loads(result.stdout)
            plan_id = plan_data["plan_id"]

            # Validate plan (this updates the plan in the store)
            result = subprocess.run(
                [RMRF_CMD, "validate", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0

            # Create backup (stage command) - use --json-output for easier parsing
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "stage", plan_id, "--backup-root", str(backup_dir)],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            manifest = json.loads(result.stdout)
            assert "manifest_id" in manifest
            assert manifest["files"] == 1

    def test_json_output_flag_works(self):
        """Test --json-output flag works on main command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            # Create temp plan directory
            plan_dir = Path(tmpdir) / "plans"
            plan_dir.mkdir()

            env = {
                **subprocess.os.environ,
                "RM_ENVIRONMENT": '{"env":"dev","signature":"test"}',
                "RMRF_PLAN_DIR": str(plan_dir),
            }

            result = subprocess.run(
                [RMRF_CMD, "--json-output", "plan", str(test_file)],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            # Should be valid JSON
            plan_data = json.loads(result.stdout)
            assert "plan_id" in plan_data


class TestCLIStructuredOutput:
    """Test structured output formatting."""

    def test_plan_structured_output(self):
        """Test plan command produces structured output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            # Create temp plan directory
            plan_dir = Path(tmpdir) / "plans"
            plan_dir.mkdir()

            env = {
                **subprocess.os.environ,
                "RM_ENVIRONMENT": '{"env":"dev","signature":"test"}',
                "RMRF_PLAN_DIR": str(plan_dir),
            }

            result = subprocess.run(
                [RMRF_CMD, "plan", str(test_file)],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            assert "[SUCCESS]" in result.stdout
            assert "What happened:" in result.stdout
            assert "Why it matters:" in result.stdout
            assert "Next steps:" in result.stdout

    def test_validate_structured_output(self):
        """Test validate command produces structured output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            # Create temp plan directory
            plan_dir = Path(tmpdir) / "plans"
            plan_dir.mkdir()

            env = {
                **subprocess.os.environ,
                "RM_ENVIRONMENT": '{"env":"dev","signature":"test"}',
                "RMRF_PLAN_DIR": str(plan_dir),
            }

            # Create and validate plan
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "plan", str(test_file)],
                capture_output=True,
                text=True,
                env=env,
            )
            plan_data = json.loads(result.stdout)
            plan_id = plan_data["plan_id"]

            result = subprocess.run(
                [RMRF_CMD, "validate", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            assert "[ALLOWED]" in result.stdout
            assert "What happened:" in result.stdout
            assert "Why it matters:" in result.stdout
            assert "Next steps:" in result.stdout

    def test_init_structured_output(self):
        """Test init command produces structured output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [RMRF_CMD, "init", "--root-dir", tmpdir],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0
            assert "[SUCCESS]" in result.stdout
            assert "What happened:" in result.stdout
            assert "Why it matters:" in result.stdout
            assert "Next steps:" in result.stdout

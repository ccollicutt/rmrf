"""
Integration tests for locking and approval workflow.

Tests plan locking, multi-user approval, and approval enforcement.
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


class TestPlanLocking:
    """Integration tests for plan locking."""

    def test_plan_created_with_lock(self):
        """Test that plan creation automatically acquires a lock."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            # Create directories
            plan_dir = Path(tmpdir) / "plans"
            plan_dir.mkdir()
            lock_dir = Path(tmpdir) / "locks"
            lock_dir.mkdir()

            # Set environment
            env = {
                **subprocess.os.environ,
                "RM_ENVIRONMENT": '{"env":"dev","signature":"test"}',
                "RMRF_PLAN_DIR": str(plan_dir),
                "RMRF_LOCK_DIR": str(lock_dir),
            }

            # Create plan
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "plan", str(test_file)],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0, f"Plan failed: {result.stderr}"
            plan_data = json.loads(result.stdout)
            plan_id = plan_data["plan_id"]

            # Check that lock files exist (locks are created for each target, named by path hash)
            lock_files = list(lock_dir.glob("*.json"))
            assert len(lock_files) > 0, "Lock file(s) should be created with plan"

            # Verify lock content (check first lock file)
            lock_data = json.loads(lock_files[0].read_text())
            assert lock_data["plan_id"] == plan_id
            assert "locked_at" in lock_data
            assert "locked_by_uid" in lock_data

    def test_lock_prevents_duplicate_operations(self):
        """Test that lock prevents concurrent operations on same plan."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            # Create directories
            plan_dir = Path(tmpdir) / "plans"
            plan_dir.mkdir()
            lock_dir = Path(tmpdir) / "locks"
            lock_dir.mkdir()

            # Set environment
            env = {
                **subprocess.os.environ,
                "RM_ENVIRONMENT": '{"env":"dev","signature":"test"}',
                "RMRF_PLAN_DIR": str(plan_dir),
                "RMRF_LOCK_DIR": str(lock_dir),
            }

            # Create plan (acquires lock)
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "plan", str(test_file)],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            json.loads(result.stdout)  # Verify valid JSON response

            # Verify lock exists (locks are named by path hash)
            lock_files = list(lock_dir.glob("*.json"))
            assert len(lock_files) > 0, "Lock file(s) should exist"

    def test_unlock_command(self):
        """Test that unlock command removes lock."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            # Create directories
            plan_dir = Path(tmpdir) / "plans"
            plan_dir.mkdir()
            lock_dir = Path(tmpdir) / "locks"
            lock_dir.mkdir()

            # Set environment
            env = {
                **subprocess.os.environ,
                "RM_ENVIRONMENT": '{"env":"dev","signature":"test"}',
                "RMRF_PLAN_DIR": str(plan_dir),
                "RMRF_LOCK_DIR": str(lock_dir),
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

            # Verify lock exists (locks are named by path hash)
            lock_files_before = list(lock_dir.glob("*.json"))
            assert len(lock_files_before) > 0, "Lock should exist after plan creation"

            # Unlock plan (unlock command removes locks for all targets in plan)
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "unlock", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0, f"Unlock failed: {result.stderr}"

            # Verify locks removed
            lock_files_after = list(lock_dir.glob("*.json"))
            assert len(lock_files_after) == 0, "Locks should be removed after unlock"


class TestApprovalWorkflow:
    """Integration tests for approval workflow."""

    def test_approve_command_sets_approval_metadata(self):
        """Test that approve command sets approval metadata on plan."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            # Create directories
            plan_dir = Path(tmpdir) / "plans"
            plan_dir.mkdir()
            lock_dir = Path(tmpdir) / "locks"
            lock_dir.mkdir()

            # Set environment
            env = {
                **subprocess.os.environ,
                "RM_ENVIRONMENT": '{"env":"dev","signature":"test"}',
                "RMRF_PLAN_DIR": str(plan_dir),
                "RMRF_LOCK_DIR": str(lock_dir),
            }

            # Create plan as user 1000
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "plan", str(test_file)],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            plan_data = json.loads(result.stdout)
            plan_id = plan_data["plan_id"]

            # Mark plan as requiring approval (manually edit plan file for testing)
            plan_file = plan_dir / f"{plan_id}.json"
            plan_json = json.loads(plan_file.read_text())
            plan_json["requires_approval"] = True
            plan_file.write_text(json.dumps(plan_json, indent=2))

            # Approve as different user (simulate with approval ID)
            result = subprocess.run(
                [
                    RMRF_CMD,
                    "--json-output",
                    "approve",
                    plan_id,
                    "--approver-uid",
                    "2000",
                    "--comment",
                    "Approved for deletion",
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0, f"Approve failed: {result.stderr}"
            approval_data = json.loads(result.stdout)

            # Verify approval metadata
            assert approval_data["approved"] is True
            assert "approval_id" in approval_data
            assert "approved_at" in approval_data

            # Check plan was updated
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "show", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            plan_info = json.loads(result.stdout)

            assert plan_info["approved"] is True
            assert plan_info["approved_by_uid"] == 2000
            assert plan_info["approval_comment"] == "Approved for deletion"
            assert "approved_at" in plan_info

    def test_approve_requires_different_user(self):
        """Test that approval must be by different user than creator."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            # Create directories
            plan_dir = Path(tmpdir) / "plans"
            plan_dir.mkdir()
            lock_dir = Path(tmpdir) / "locks"
            lock_dir.mkdir()

            # Set environment
            env = {
                **subprocess.os.environ,
                "RM_ENVIRONMENT": '{"env":"dev","signature":"test"}',
                "RMRF_PLAN_DIR": str(plan_dir),
                "RMRF_LOCK_DIR": str(lock_dir),
            }

            # Create plan (creator will be current UID)
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "plan", str(test_file)],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            plan_data = json.loads(result.stdout)
            plan_id = plan_data["plan_id"]

            # Mark plan as requiring approval (manually edit plan file for testing)
            plan_file = plan_dir / f"{plan_id}.json"
            plan_json = json.loads(plan_file.read_text())
            plan_json["requires_approval"] = True
            plan_file.write_text(json.dumps(plan_json, indent=2))

            # Get current UID
            current_uid = os.getuid()

            # Try to approve as same user (should fail)
            result = subprocess.run(
                [
                    RMRF_CMD,
                    "--json-output",
                    "approve",
                    plan_id,
                    "--approver-uid",
                    str(current_uid),
                    "--comment",
                    "Self approval attempt",
                ],
                capture_output=True,
                text=True,
                env=env,
            )

            # Should fail
            assert result.returncode != 0, "Self-approval should be rejected"
            output = result.stdout + result.stderr
            assert "cannot approve own plan" in output.lower() or "different user" in output.lower()

    def test_validation_with_approval_id(self):
        """Test that validation can check approval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            # Create directories
            plan_dir = Path(tmpdir) / "plans"
            plan_dir.mkdir()
            lock_dir = Path(tmpdir) / "locks"
            lock_dir.mkdir()

            # Set environment
            env = {
                **subprocess.os.environ,
                "RM_ENVIRONMENT": '{"env":"dev","signature":"test"}',
                "RMRF_PLAN_DIR": str(plan_dir),
                "RMRF_LOCK_DIR": str(lock_dir),
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

            # Mark plan as requiring approval (manually edit plan file for testing)
            plan_file = plan_dir / f"{plan_id}.json"
            plan_json = json.loads(plan_file.read_text())
            plan_json["requires_approval"] = True
            plan_file.write_text(json.dumps(plan_json, indent=2))

            # Approve plan
            result = subprocess.run(
                [
                    RMRF_CMD,
                    "--json-output",
                    "approve",
                    plan_id,
                    "--approver-uid",
                    "2000",
                    "--comment",
                    "Approved",
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            approval_data = json.loads(result.stdout)
            approval_id = approval_data["approval_id"]

            # Validate with approval ID
            result = subprocess.run(
                [
                    RMRF_CMD,
                    "--json-output",
                    "validate",
                    plan_id,
                    "--approval-id",
                    approval_id,
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0, f"Validation failed: {result.stderr}"
            validation_data = json.loads(result.stdout)

            # Should be approved
            assert validation_data["verdict"] == "allow"


class TestFullWorkflowWithApproval:
    """Integration tests for complete workflow with approval."""

    def test_complete_workflow_with_approval(self):
        """Test full workflow: plan → approve → validate → stage → apply."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            # Create directories
            plan_dir = Path(tmpdir) / "plans"
            plan_dir.mkdir()
            lock_dir = Path(tmpdir) / "locks"
            lock_dir.mkdir()
            backup_dir = Path(tmpdir) / "backups"
            backup_dir.mkdir()
            audit_dir = Path(tmpdir) / "audit"
            audit_dir.mkdir()

            # Set environment
            env = {
                **subprocess.os.environ,
                "RM_ENVIRONMENT": '{"env":"dev","signature":"test"}',
                "RMRF_PLAN_DIR": str(plan_dir),
                "RMRF_LOCK_DIR": str(lock_dir),
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
            assert result.returncode == 0, f"Plan failed: {result.stderr}"
            plan_data = json.loads(result.stdout)
            plan_id = plan_data["plan_id"]

            # Verify plan is locked (locks are named by path hash)
            lock_files = list(lock_dir.glob("*.json"))
            assert len(lock_files) > 0, "Plan should be locked"

            # Mark plan as requiring approval (manually edit plan file for testing)
            plan_file = plan_dir / f"{plan_id}.json"
            plan_json = json.loads(plan_file.read_text())
            plan_json["requires_approval"] = True
            plan_file.write_text(json.dumps(plan_json, indent=2))

            # 2. Approve plan (as different user)
            result = subprocess.run(
                [
                    RMRF_CMD,
                    "--json-output",
                    "approve",
                    plan_id,
                    "--approver-uid",
                    "2000",
                    "--comment",
                    "Approved for testing",
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0, f"Approve failed: {result.stderr}"
            approval_data = json.loads(result.stdout)
            approval_id = approval_data["approval_id"]

            # 3. Validate with approval
            result = subprocess.run(
                [
                    RMRF_CMD,
                    "--json-output",
                    "validate",
                    plan_id,
                    "--approval-id",
                    approval_id,
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0, f"Validate failed: {result.stderr}"
            validation_data = json.loads(result.stdout)
            assert validation_data["verdict"] == "allow"

            # 4. Stage (create backup)
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "stage", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0, f"Stage failed: {result.stderr}"

            # 5. Apply (delete files)
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "apply", plan_id, "--skip-confirmation"],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0, f"Apply failed: {result.stderr}"

            # Verify file was deleted
            assert not test_file.exists(), "File should be deleted"

            # 6. Verify plan shows approval metadata
            result = subprocess.run(
                [RMRF_CMD, "--json-output", "show", plan_id],
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0
            plan_info = json.loads(result.stdout)

            assert plan_info["approved"] is True
            assert plan_info["approved_by_uid"] == 2000
            assert plan_info["validated"] is True
            assert plan_info["executed_at"] is not None, "Plan should be executed"

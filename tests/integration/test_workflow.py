"""
Integration tests for rmrf full workflow.

Tests the complete lifecycle: plan → validate → backup → apply → rollback
"""

import json
from pathlib import Path

import pytest

from rmrf.environment import EnvironmentDetector
from rmrf.models import Plan
from rmrf.protection import ProtectionLevelRegistry


class TestFullWorkflow:
    """Integration tests for complete rmrf workflow."""

    @pytest.fixture
    def temp_test_dir(self, tmp_path: Path) -> Path:
        """Create a temporary directory with test files."""
        test_dir = tmp_path / "test_deletion"
        test_dir.mkdir()

        # Create some test files
        (test_dir / "file1.txt").write_text("Test file 1")
        (test_dir / "file2.txt").write_text("Test file 2")
        (test_dir / "file3.txt").write_text("Test file 3")

        # Create a subdirectory with files
        subdir = test_dir / "subdir"
        subdir.mkdir()
        (subdir / "nested1.txt").write_text("Nested file 1")
        (subdir / "nested2.txt").write_text("Nested file 2")

        return test_dir

    @pytest.fixture
    def temp_env_file(self, tmp_path: Path) -> Path:
        """Create a temporary environment file."""
        env_file = tmp_path / "test.env"
        env_data = {"env": "dev", "signature": "sha256:test"}
        env_file.write_text(json.dumps(env_data))
        return env_file

    def test_environment_and_protection_level_integration(self, temp_env_file: Path) -> None:
        """Test that environment detection integrates with protection levels."""
        # Detect environment
        detector = EnvironmentDetector(paths=[temp_env_file])
        environment = detector.detect()

        assert environment.env == "dev"

        # Get protection level for environment
        registry = ProtectionLevelRegistry(load_defaults=True)
        level = registry.get_by_environment(environment.env)

        assert level is not None
        assert level.name == "safe-local"
        assert level.require_backup is False

    def test_plan_creation_with_real_files(self, temp_test_dir: Path) -> None:
        """Test creating a plan with real files."""
        # Count files in directory
        files = list(temp_test_dir.rglob("*"))
        file_count = sum(1 for f in files if f.is_file())

        # Calculate total size
        total_bytes = sum(f.stat().st_size for f in files if f.is_file())

        # Create plan
        plan = Plan(
            plan_id="test-plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=[str(temp_test_dir)],
            file_count=file_count,
            total_bytes=total_bytes,
        )

        assert plan.file_count == 5  # 3 files + 2 nested files
        assert plan.total_bytes > 0
        assert not plan.is_expired()

    def test_plan_serialization_roundtrip(self, temp_test_dir: Path) -> None:
        """Test that plans can be saved and loaded from JSON."""
        # Create plan
        original_plan = Plan(
            plan_id="test-plan-002",
            environment="dev",
            protection_level="safe-local",
            targets=[str(temp_test_dir)],
            file_count=5,
            total_bytes=100,
        )

        # Serialize to JSON
        plan_json = original_plan.model_dump_json()

        # Deserialize from JSON
        loaded_data = json.loads(plan_json)
        loaded_plan = Plan(**loaded_data)

        # Verify
        assert loaded_plan.plan_id == original_plan.plan_id
        assert loaded_plan.environment == original_plan.environment
        assert loaded_plan.file_count == original_plan.file_count

    def test_plan_validation_with_protection_level_limits(self) -> None:
        """Test that plans respect protection level limits."""
        registry = ProtectionLevelRegistry(load_defaults=True)

        # Get critical-system level with strict limits
        critical_level = registry.get("critical-system")
        assert critical_level is not None
        assert critical_level.max_files == 1000

        # Create plan within limits
        small_plan = Plan(
            plan_id="small-plan",
            environment="prod",
            protection_level="critical-system",
            targets=["/tmp/small"],
            file_count=500,  # Within limit
            total_bytes=500_000_000,  # 500 MB, within 1 GB limit
        )

        # Check against limits
        assert small_plan.file_count <= critical_level.max_files
        assert small_plan.total_bytes <= critical_level.max_bytes

        # Create plan exceeding limits
        large_plan = Plan(
            plan_id="large-plan",
            environment="prod",
            protection_level="critical-system",
            targets=["/tmp/large"],
            file_count=2000,  # Exceeds limit
            total_bytes=2_000_000_000,  # 2 GB, exceeds limit
        )

        # Would need policy validation to reject this
        assert large_plan.file_count > critical_level.max_files
        assert large_plan.total_bytes > critical_level.max_bytes

    def test_multiple_protection_levels_for_different_environments(self) -> None:
        """Test different protection levels for different environments."""
        registry = ProtectionLevelRegistry(load_defaults=True)

        # Dev environment - permissive
        dev_level = registry.get_by_environment("dev")
        assert dev_level is not None
        assert dev_level.name == "safe-local"
        assert dev_level.require_backup is False
        assert dev_level.max_files is None  # No limit

        # Prod environment - strict
        prod_level = registry.get_by_environment("prod")
        assert prod_level is not None
        assert prod_level.name == "critical-system"
        assert prod_level.require_backup is True
        assert prod_level.max_files == 1000  # Strict limit

        # Staging environment - moderate
        staging_level = registry.get_by_environment("staging")
        assert staging_level is not None
        assert staging_level.name == "controlled-team"
        assert staging_level.require_backup is True
        assert staging_level.max_files == 10000  # Moderate limit


class TestErrorScenarios:
    """Integration tests for error handling and edge cases."""

    def test_missing_environment_aborts(self, tmp_path: Path) -> None:
        """Test that missing environment causes proper error."""
        from rmrf.environment import EnvironmentError

        nonexistent = tmp_path / "does_not_exist.env"
        detector = EnvironmentDetector(paths=[nonexistent])

        with pytest.raises(EnvironmentError) as exc_info:
            detector.detect()

        assert "Environment metadata not found" in str(exc_info.value)

    def test_plan_with_nonexistent_target(self) -> None:
        """Test creating plan with nonexistent target."""
        # This should succeed at plan creation time
        # Actual validation happens at execution time
        plan = Plan(
            plan_id="nonexistent-plan",
            environment="dev",
            protection_level="safe-local",
            targets=["/nonexistent/path"],
            file_count=0,
            total_bytes=0,
        )

        assert plan.plan_id == "nonexistent-plan"
        assert len(plan.targets) == 1

    def test_custom_protection_level_override(self, tmp_path: Path) -> None:
        """Test that custom protection levels override defaults."""
        # Create custom level YAML
        custom_yaml = tmp_path / "custom.yaml"
        custom_yaml.write_text(
            """
name: safe-local
description: Overridden safe-local
max_files: 9999
retention_days: 99
"""
        )

        # Load with custom directory
        registry = ProtectionLevelRegistry(
            levels_dir=tmp_path,
            load_defaults=True,
        )

        # Should use custom definition
        level = registry.get("safe-local")
        assert level is not None
        assert level.max_files == 9999
        assert level.retention_days == 99
        assert level.description == "Overridden safe-local"


class TestBackupWorkflow:
    """Integration tests for backup and rollback workflow (placeholder for Stage 3)."""

    def test_backup_manifest_structure(self) -> None:
        """Test backup manifest structure (to be implemented in Stage 3)."""
        from rmrf.models import RollbackManifest

        manifest = RollbackManifest(
            manifest_id="test-manifest",
            plan_id="test-plan",
            environment="dev",
            files=5,
            total_bytes=500,
            checksums={
                "/tmp/file1.txt": "sha256:abc123",
                "/tmp/file2.txt": "sha256:def456",
            },
            backup_root="/var/lib/rmrf/backups/dev/2025-11-06",
            retention_days=7,
        )

        assert manifest.manifest_id == "test-manifest"
        assert len(manifest.checksums) == 2
        assert manifest.retention_days == 7


class TestAuditWorkflow:
    """Integration tests for audit event workflow."""

    def test_audit_event_lifecycle(self) -> None:
        """Test audit events for full lifecycle."""
        from rmrf.models import AuditEvent, EventPhase, UserContext

        user = UserContext(id="test-user", role="developer")

        # Plan created event
        plan_event = AuditEvent(
            event_id="evt-001",
            phase=EventPhase.PLAN_CREATED,
            environment="dev",
            protection_level="safe-local",
            plan_id="plan-001",
            user_id=user.id,
            result="success",
            message="Plan created successfully",
        )

        # Validated event
        validated_event = AuditEvent(
            event_id="evt-002",
            phase=EventPhase.PLAN_VALIDATED,
            environment="dev",
            protection_level="safe-local",
            plan_id="plan-001",
            user_id=user.id,
            result="success",
            message="Plan validated by policy",
        )

        # Backup completed event
        backup_event = AuditEvent(
            event_id="evt-003",
            phase=EventPhase.BACKUP_COMPLETED,
            environment="dev",
            protection_level="safe-local",
            plan_id="plan-001",
            user_id=user.id,
            result="success",
            metadata={"backup_path": "/var/lib/rmrf/backups/dev"},
        )

        # Applied event
        applied_event = AuditEvent(
            event_id="evt-004",
            phase=EventPhase.APPLIED,
            environment="dev",
            protection_level="safe-local",
            plan_id="plan-001",
            user_id=user.id,
            result="success",
            message="Deletion completed successfully",
        )

        # Verify event sequence
        events = [plan_event, validated_event, backup_event, applied_event]
        assert len(events) == 4
        assert all(e.plan_id == "plan-001" for e in events)
        assert all(e.user_id == "test-user" for e in events)


class TestConfigurationIntegration:
    """Integration tests for configuration loading and merging."""

    def test_load_all_default_protection_levels(self) -> None:
        """Test that all default protection levels load correctly."""
        registry = ProtectionLevelRegistry(load_defaults=True)

        expected_levels = [
            "safe-local",
            "controlled-team",
            "guarded-ops",
            "critical-system",
            "simulation-only",
        ]

        for level_name in expected_levels:
            level = registry.get(level_name)
            assert level is not None, f"Level {level_name} should be loaded"

        assert registry.count() == 5

    def test_environment_to_level_mapping(self) -> None:
        """Test environment to protection level mapping."""
        registry = ProtectionLevelRegistry(load_defaults=True)

        mappings = {
            "dev": "safe-local",
            "staging": "controlled-team",
            "ops": "guarded-ops",
            "prod": "critical-system",
            "twin": "simulation-only",
        }

        for env, expected_level in mappings.items():
            level = registry.get_by_environment(env)
            assert level is not None
            assert level.name == expected_level

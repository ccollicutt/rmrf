"""Tests for validator self-protection against deleting rmrf infrastructure."""

from datetime import datetime, timedelta, timezone

import pytest

from rmrf.models import Plan, Verdict
from rmrf.protection import ProtectionLevel
from rmrf.validator import BuiltinValidator


@pytest.fixture
def sample_protection_level() -> ProtectionLevel:
    """Sample protection level for testing."""
    return ProtectionLevel(
        name="test-level",
        description="Test protection level",
        max_files=1000,
        max_bytes=1024 * 1024,
        require_backup=True,
        require_audit=True,
    )


@pytest.fixture
def validator() -> BuiltinValidator:
    """Validator instance."""
    return BuiltinValidator()


class TestSelfProtection:
    """Test that validator prevents deletion of rmrf infrastructure."""

    def test_denies_var_lib_rmrf_deletion(
        self, validator: BuiltinValidator, sample_protection_level: ProtectionLevel
    ) -> None:
        """Test that deleting /var/lib/rmrf is denied."""
        plan = Plan(
            plan_id="test-self-delete",
            environment="dev",
            protection_level="test-level",
            targets=["/var/lib/rmrf"],
            file_count=10,
            total_bytes=1024,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        verdict = validator.validate(plan, sample_protection_level)

        assert verdict.verdict == Verdict.DENY
        assert "Cannot delete rmrf infrastructure" in verdict.message
        assert any("/var/lib/rmrf" in reason for reason in verdict.reasons)

    def test_denies_var_lib_rmrf_subdirectory_deletion(
        self, validator: BuiltinValidator, sample_protection_level: ProtectionLevel
    ) -> None:
        """Test that deleting subdirectories of /var/lib/rmrf is denied."""
        plan = Plan(
            plan_id="test-self-delete-plans",
            environment="dev",
            protection_level="test-level",
            targets=["/var/lib/rmrf/plans"],
            file_count=10,
            total_bytes=1024,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        verdict = validator.validate(plan, sample_protection_level)

        assert verdict.verdict == Verdict.DENY
        assert "Cannot delete rmrf infrastructure" in verdict.message

    def test_denies_parent_directory_containing_rmrf(
        self, validator: BuiltinValidator, sample_protection_level: ProtectionLevel
    ) -> None:
        """Test that deleting parent directory containing rmrf is denied."""
        plan = Plan(
            plan_id="test-parent-delete",
            environment="dev",
            protection_level="test-level",
            targets=["/var/lib"],  # Contains /var/lib/rmrf
            file_count=10,
            total_bytes=1024,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        verdict = validator.validate(plan, sample_protection_level)

        assert verdict.verdict == Verdict.DENY
        assert "Cannot delete rmrf infrastructure" in verdict.message
        assert any("contains rmrf infrastructure" in reason.lower() for reason in verdict.reasons)

    def test_denies_etc_rmrf_deletion(
        self, validator: BuiltinValidator, sample_protection_level: ProtectionLevel
    ) -> None:
        """Test that deleting /etc/rmrf is denied."""
        plan = Plan(
            plan_id="test-etc-delete",
            environment="dev",
            protection_level="test-level",
            targets=["/etc/rmrf"],
            file_count=10,
            total_bytes=1024,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        verdict = validator.validate(plan, sample_protection_level)

        assert verdict.verdict == Verdict.DENY
        assert "Cannot delete rmrf infrastructure" in verdict.message

    def test_denies_custom_plan_dir_from_env(
        self,
        validator: BuiltinValidator,
        sample_protection_level: ProtectionLevel,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that deleting custom plan directory from RMRF_PLAN_DIR env is denied."""
        custom_plan_dir = "/tmp/my-plans"
        monkeypatch.setenv("RMRF_PLAN_DIR", custom_plan_dir)

        plan = Plan(
            plan_id="test-custom-plan-dir",
            environment="dev",
            protection_level="test-level",
            targets=[custom_plan_dir],
            file_count=10,
            total_bytes=1024,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        verdict = validator.validate(plan, sample_protection_level)

        assert verdict.verdict == Verdict.DENY
        assert "plan directory" in verdict.message.lower() or any(
            "plan directory" in r.lower() for r in verdict.reasons
        )

    def test_allows_safe_deletion(
        self, validator: BuiltinValidator, sample_protection_level: ProtectionLevel
    ) -> None:
        """Test that deleting unrelated directories is allowed."""
        plan = Plan(
            plan_id="test-safe-delete",
            environment="dev",
            protection_level="test-level",
            targets=["/tmp/some-random-dir"],
            file_count=10,
            total_bytes=1024,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        verdict = validator.validate(plan, sample_protection_level)

        assert verdict.verdict == Verdict.ALLOW
        assert "All safety checks passed" in verdict.reasons

    def test_multiple_targets_one_protected(
        self, validator: BuiltinValidator, sample_protection_level: ProtectionLevel
    ) -> None:
        """Test that if any target is protected, the plan is denied."""
        plan = Plan(
            plan_id="test-mixed-targets",
            environment="dev",
            protection_level="test-level",
            targets=["/tmp/safe-dir", "/var/lib/rmrf/plans"],  # Second one is protected
            file_count=10,
            total_bytes=1024,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        verdict = validator.validate(plan, sample_protection_level)

        assert verdict.verdict == Verdict.DENY
        assert "Cannot delete rmrf infrastructure" in verdict.message

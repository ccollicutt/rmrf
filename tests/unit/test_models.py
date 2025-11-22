"""
Unit tests for rmrf.models.

Tests data validation, serialization, and model behavior.
"""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from rmrf.models import (
    AuditEvent,
    Environment,
    EventPhase,
    Plan,
    PolicyVerdict,
    ProtectionLevel,
    RiskLevel,
    RiskScore,
    RollbackManifest,
    UserContext,
    Verdict,
)


class TestEnvironment:
    """Tests for Environment model."""

    def test_valid_environment(self) -> None:
        """Test creating valid environment."""
        env = Environment(env="prod", signature="sha256:abc123")
        assert env.env == "prod"
        assert env.signature == "sha256:abc123"

    def test_environment_lowercase_normalization(self) -> None:
        """Test that environment names are normalized to lowercase."""
        env = Environment(env="PROD", signature="sha256:abc123")
        assert env.env == "prod"

    def test_environment_without_signature(self) -> None:
        """Test environment can be created without signature."""
        env = Environment(env="dev")
        assert env.env == "dev"
        assert env.signature is None

    def test_empty_environment_name_rejected(self) -> None:
        """Test that empty environment name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Environment(env="")
        assert "Environment name cannot be empty" in str(exc_info.value)

    def test_whitespace_environment_name_rejected(self) -> None:
        """Test that whitespace-only environment name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Environment(env="   ")
        assert "Environment name cannot be empty" in str(exc_info.value)

    def test_environment_json_serialization(self) -> None:
        """Test environment can be serialized to JSON."""
        env = Environment(env="staging", signature="sha256:def456")
        json_data = env.model_dump_json()
        assert "staging" in json_data
        assert "sha256:def456" in json_data


class TestProtectionLevel:
    """Tests for ProtectionLevel model."""

    def test_valid_protection_level(self) -> None:
        """Test creating valid protection level."""
        level = ProtectionLevel(
            name="safe-local",
            description="Minimal restrictions",
            default_environment="dev",
            max_files=10000,
            max_bytes=1000000000,
            require_backup=False,
            require_audit=False,
            require_confirmation=False,
            retention_days=3,
        )
        assert level.name == "safe-local"
        assert level.description == "Minimal restrictions"
        assert level.max_files == 10000
        assert level.require_backup is False

    def test_protection_level_defaults(self) -> None:
        """Test protection level default values."""
        level = ProtectionLevel(
            name="test-level",
            description="Test level",
        )
        assert level.require_backup is True
        assert level.require_audit is True
        assert level.require_confirmation is False
        assert level.retention_days == 7
        assert level.allow_simulation_only is False

    def test_protection_level_name_normalized(self) -> None:
        """Test protection level name is normalized to lowercase."""
        level = ProtectionLevel(
            name="CRITICAL-SYSTEM",
            description="Critical level",
        )
        assert level.name == "critical-system"

    def test_negative_max_files_rejected(self) -> None:
        """Test that negative max_files is rejected."""
        with pytest.raises(ValidationError):
            ProtectionLevel(
                name="test",
                description="Test",
                max_files=-1,
            )

    def test_negative_retention_days_rejected(self) -> None:
        """Test that negative retention_days is rejected."""
        with pytest.raises(ValidationError):
            ProtectionLevel(
                name="test",
                description="Test",
                retention_days=-1,
            )


class TestRiskScore:
    """Tests for RiskScore model."""

    def test_valid_risk_score(self) -> None:
        """Test creating valid risk score."""
        risk = RiskScore(
            level=RiskLevel.HIGH,
            score=75,
            reasons=["Large file count", "Production environment"],
        )
        assert risk.level == RiskLevel.HIGH
        assert risk.score == 75
        assert len(risk.reasons) == 2

    def test_risk_score_bounds(self) -> None:
        """Test risk score must be between 0 and 100."""
        with pytest.raises(ValidationError):
            RiskScore(level=RiskLevel.LOW, score=-1)

        with pytest.raises(ValidationError):
            RiskScore(level=RiskLevel.CRITICAL, score=101)


class TestPlan:
    """Tests for Plan model."""

    def test_valid_plan(self) -> None:
        """Test creating valid deletion plan."""
        plan = Plan(
            plan_id="plan-123",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=10,
            total_bytes=1024,
        )
        assert plan.plan_id == "plan-123"
        assert plan.file_count == 10
        assert plan.validated is False
        assert plan.dry_run is False

    def test_plan_with_risk_score(self) -> None:
        """Test plan with risk assessment."""
        risk = RiskScore(level=RiskLevel.LOW, score=15, reasons=["Small deletion"])
        plan = Plan(
            plan_id="plan-456",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/small"],
            file_count=5,
            total_bytes=512,
            risk_score=risk,
        )
        assert plan.risk_score is not None
        assert plan.risk_score.level == RiskLevel.LOW

    def test_plan_empty_targets_rejected(self) -> None:
        """Test that plan with empty targets is rejected."""
        with pytest.raises(ValidationError):
            Plan(
                plan_id="plan-789",
                environment="dev",
                protection_level="safe-local",
                targets=[],
                file_count=0,
                total_bytes=0,
            )

    def test_plan_empty_target_path_rejected(self) -> None:
        """Test that plan with empty target path is rejected."""
        with pytest.raises(ValidationError):
            Plan(
                plan_id="plan-789",
                environment="dev",
                protection_level="safe-local",
                targets=[""],
                file_count=0,
                total_bytes=0,
            )

    def test_plan_expiration(self) -> None:
        """Test plan expiration checking."""
        # Plan with future expiration
        future_plan = Plan(
            plan_id="plan-future",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert future_plan.is_expired() is False

        # Plan with past expiration
        expired_plan = Plan(
            plan_id="plan-expired",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert expired_plan.is_expired() is True

        # Plan with no expiration
        no_expiry_plan = Plan(
            plan_id="plan-no-expiry",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
        )
        assert no_expiry_plan.is_expired() is False

    def test_plan_with_user_context(self) -> None:
        """Test plan with user information."""
        user = UserContext(id="alice", role="operator", groups=["ops", "admin"])
        plan = Plan(
            plan_id="plan-user",
            environment="prod",
            protection_level="critical-system",
            targets=["/var/log"],
            file_count=100,
            total_bytes=10000,
            user=user,
        )
        assert plan.user is not None
        assert plan.user.id == "alice"
        assert "ops" in plan.user.groups

    def test_workflow_stage_planned(self) -> None:
        """Test workflow stage for new plan."""
        plan = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
        )
        assert plan.get_workflow_stage() == "planned"

    def test_workflow_stage_validated(self) -> None:
        """Test workflow stage for validated plan."""
        plan = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
            validated=True,
        )
        assert plan.get_workflow_stage() == "validated"

    def test_workflow_stage_staged(self) -> None:
        """Test workflow stage for staged plan."""
        plan = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
            validated=True,
            backup_path="/var/lib/rmrf/backups/plan-001",
        )
        assert plan.get_workflow_stage() == "staged"

    def test_workflow_stage_applied(self) -> None:
        """Test workflow stage for applied plan."""
        plan = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
            validated=True,
            backup_path="/var/lib/rmrf/backups/plan-001",
            executed_at=datetime.now(timezone.utc),
        )
        assert plan.get_workflow_stage() == "applied"

    def test_workflow_stage_closed(self) -> None:
        """Test workflow stage for closed plan."""
        plan = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
            validated=True,
            backup_path="/var/lib/rmrf/backups/plan-001",
            executed_at=datetime.now(timezone.utc),
            closeout_at=datetime.now(timezone.utc),
        )
        assert plan.get_workflow_stage() == "closed"

    def test_workflow_stage_denied(self) -> None:
        """Test workflow stage for denied plan."""
        plan = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
            policy_verdict=PolicyVerdict(
                verdict=Verdict.DENY,
                message="Plan denied by policy",
                reasons=["Test denial reason"],
            ),
        )
        assert plan.get_workflow_stage() == "denied"

    def test_workflow_stage_approval_required(self) -> None:
        """Test workflow stage for plan requiring approval."""
        plan = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
            policy_verdict=PolicyVerdict(
                verdict=Verdict.REQUIRE_APPROVAL,
                message="Plan requires approval",
                reasons=["High risk operation"],
            ),
        )
        assert plan.get_workflow_stage() == "approval-required"

    def test_can_validate_new_plan(self) -> None:
        """Test can_validate for new plan."""
        plan = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
        )
        can_proceed, error_msg = plan.can_validate()
        assert can_proceed is True
        assert error_msg is None

    def test_can_validate_already_validated(self) -> None:
        """Test can_validate for already validated plan."""
        plan = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
            validated=True,
        )
        can_proceed, error_msg = plan.can_validate()
        assert can_proceed is False
        assert "validated" in error_msg
        assert "Next:" in error_msg

    def test_can_stage_validated_plan(self) -> None:
        """Test can_stage for validated plan."""
        plan = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
            validated=True,
        )
        can_proceed, error_msg = plan.can_stage()
        assert can_proceed is True
        assert error_msg is None

    def test_can_stage_not_validated(self) -> None:
        """Test can_stage for unvalidated plan."""
        plan = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
        )
        can_proceed, error_msg = plan.can_stage()
        assert can_proceed is False
        assert "planned" in error_msg
        assert "validate" in error_msg

    def test_can_apply_staged_plan(self) -> None:
        """Test can_apply for staged plan."""
        plan = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
            validated=True,
            backup_path="/var/lib/rmrf/backups/plan-001",
        )
        can_proceed, error_msg = plan.can_apply()
        assert can_proceed is True
        assert error_msg is None

    def test_can_apply_not_staged(self) -> None:
        """Test can_apply for validated but unstaged plan."""
        plan = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
            validated=True,
        )
        can_proceed, error_msg = plan.can_apply()
        assert can_proceed is False
        # Should suggest 'rmrf stage', not 'rmrf validate'
        assert "rmrf stage" in error_msg.lower()
        assert "rmrf validate" not in error_msg.lower()

    def test_can_apply_not_validated(self) -> None:
        """Test can_apply for unvalidated plan (planned stage)."""
        plan = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
            validated=False,
        )
        can_proceed, error_msg = plan.can_apply()
        assert can_proceed is False
        assert "validate" in error_msg.lower()
        # Should suggest 'rmrf validate', not 'rmrf stage'
        assert "rmrf validate" in error_msg.lower()
        assert "rmrf stage" not in error_msg.lower()

    def test_can_closeout_applied_plan(self) -> None:
        """Test can_closeout for applied plan."""
        plan = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
            validated=True,
            backup_path="/var/lib/rmrf/backups/plan-001",
            executed_at=datetime.now(timezone.utc),
        )
        can_proceed, error_msg = plan.can_closeout()
        assert can_proceed is True
        assert error_msg is None

    def test_can_closeout_not_applied(self) -> None:
        """Test can_closeout for unapplied plan."""
        plan = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
            validated=True,
            backup_path="/var/lib/rmrf/backups/plan-001",
        )
        can_proceed, error_msg = plan.can_closeout()
        assert can_proceed is False
        assert "staged" in error_msg
        assert "apply" in error_msg


class TestPolicyVerdict:
    """Tests for PolicyVerdict model."""

    def test_allow_verdict(self) -> None:
        """Test ALLOW verdict."""
        verdict = PolicyVerdict(
            verdict=Verdict.ALLOW,
            policy_id="small-deletion",
            reason_code="within_limits",
        )
        assert verdict.verdict == Verdict.ALLOW
        assert verdict.policy_id == "small-deletion"

    def test_deny_verdict_with_message(self) -> None:
        """Test DENY verdict with message."""
        verdict = PolicyVerdict(
            verdict=Verdict.DENY,
            policy_id="protected-path",
            reason_code="system_path",
            message="Cannot delete system directories",
        )
        assert verdict.verdict == Verdict.DENY
        assert "system directories" in verdict.message

    def test_require_approval_verdict(self) -> None:
        """Test REQUIRE_APPROVAL verdict."""
        risk = RiskScore(level=RiskLevel.HIGH, score=80)
        verdict = PolicyVerdict(
            verdict=Verdict.REQUIRE_APPROVAL,
            policy_id="large-deletion",
            reason_code="too_many_files",
            risk=risk,
        )
        assert verdict.verdict == Verdict.REQUIRE_APPROVAL
        assert verdict.risk.level == RiskLevel.HIGH


class TestRollbackManifest:
    """Tests for RollbackManifest model."""

    def test_valid_manifest(self) -> None:
        """Test creating valid rollback manifest."""
        manifest = RollbackManifest(
            manifest_id="rb-123",
            plan_id="plan-123",
            environment="prod",
            files=10,
            total_bytes=1024,
            checksums={
                "/var/log/syslog": "sha256:abc123",
                "/var/log/messages": "sha256:def456",
            },
            backup_root="/var/lib/rmrf/backups/prod/2025-11-06/plan-123",
            retention_days=30,
        )
        assert manifest.manifest_id == "rb-123"
        assert len(manifest.checksums) == 2
        assert manifest.retention_days == 30

    def test_manifest_invalid_checksum_format(self) -> None:
        """Test that checksums must be in sha256: format."""
        with pytest.raises(ValidationError) as exc_info:
            RollbackManifest(
                manifest_id="rb-invalid",
                plan_id="plan-123",
                environment="prod",
                files=1,
                total_bytes=100,
                checksums={"/test": "abc123"},  # Missing sha256: prefix
                backup_root="/tmp",
                retention_days=7,
            )
        assert "sha256:" in str(exc_info.value)


class TestAuditEvent:
    """Tests for AuditEvent model."""

    def test_valid_audit_event(self) -> None:
        """Test creating valid audit event."""
        event = AuditEvent(
            event_id="evt-123",
            phase=EventPhase.PLAN_CREATED,
            environment="dev",
            protection_level="safe-local",
            plan_id="plan-123",
            result="success",
            message="Plan created successfully",
        )
        assert event.event_id == "evt-123"
        assert event.phase == EventPhase.PLAN_CREATED
        assert event.result == "success"

    def test_audit_event_with_user(self) -> None:
        """Test audit event with user context."""
        event = AuditEvent(
            event_id="evt-456",
            phase=EventPhase.PLAN_VALIDATED,
            environment="staging",
            protection_level="controlled-team",
            user_id="bob",
            result="success",
        )
        assert event.user_id == "bob"

    def test_audit_event_with_metadata(self) -> None:
        """Test audit event with additional metadata."""
        event = AuditEvent(
            event_id="evt-789",
            phase=EventPhase.BACKUP_COMPLETED,
            environment="prod",
            protection_level="critical-system",
            result="success",
            metadata={
                "backup_path": "/var/lib/rmrf/backups/prod/2025-11-06",
                "files_backed_up": 100,
                "duration_seconds": 12.5,
            },
        )
        assert event.metadata["files_backed_up"] == 100
        assert event.metadata["duration_seconds"] == 12.5

    def test_audit_event_phases(self) -> None:
        """Test all event phase types."""
        phases = [
            EventPhase.PLAN_CREATED,
            EventPhase.PLAN_VALIDATED,
            EventPhase.BACKUP_CREATED,
            EventPhase.BACKUP_COMPLETED,
            EventPhase.DELETION_STARTED,
            EventPhase.DELETION_COMPLETED,
            EventPhase.DELETION_FAILED,
            EventPhase.APPLIED,
            EventPhase.CANCELED,
            EventPhase.ROLLBACK_COMPLETED,
            EventPhase.ROLLBACK_EXECUTED,
            EventPhase.AUTO_HALT,
        ]
        for phase in phases:
            event = AuditEvent(
                event_id=f"evt-{phase.value}",
                phase=phase,
                environment="test",
                protection_level="test",
                result="success",
            )
            assert event.phase == phase

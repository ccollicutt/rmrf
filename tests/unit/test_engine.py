"""
Unit tests for rmrf.engine.

Tests deletion engine execution and verification.
"""

from pathlib import Path

import pytest

from rmrf.audit import AuditEmitter
from rmrf.engine import DeletionEngine, DeletionError
from rmrf.locking import LockManager
from rmrf.models import EventPhase, Plan, PolicyVerdict, ProtectionLevel, Verdict


class TestDeletionEngine:
    """Tests for DeletionEngine class."""

    @pytest.fixture
    def audit_dir(self, tmp_path: Path) -> Path:
        """Create temporary audit directory."""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        return audit_dir

    @pytest.fixture
    def auditor(self, audit_dir: Path) -> AuditEmitter:
        """Create audit emitter."""
        return AuditEmitter(audit_dir=audit_dir)

    @pytest.fixture
    def lock_manager(self, tmp_path: Path) -> LockManager:
        """Create lock manager with tmp_path."""
        lock_dir = tmp_path / "locks"
        return LockManager(lock_dir=lock_dir)

    @pytest.fixture
    def engine(self, auditor: AuditEmitter, lock_manager: LockManager) -> DeletionEngine:
        """Create deletion engine."""
        return DeletionEngine(auditor=auditor, lock_manager=lock_manager, require_validation=False)

    @pytest.fixture
    def test_files(self, tmp_path: Path) -> Path:
        """Create test files for deletion."""
        test_dir = tmp_path / "test_data"
        test_dir.mkdir()

        (test_dir / "file1.txt").write_text("Content 1")
        (test_dir / "file2.txt").write_text("Content 2")
        (test_dir / "subdir").mkdir()
        (test_dir / "subdir" / "file3.txt").write_text("Content 3")

        return test_dir

    @pytest.fixture
    def safe_protection_level(self) -> ProtectionLevel:
        """Create safe protection level."""
        return ProtectionLevel(
            name="test-safe",
            description="Test safe level",
            require_backup=False,
            retention_days=7,
        )

    def test_engine_initialization(self, auditor: AuditEmitter, lock_manager: LockManager) -> None:
        """Test engine initialization."""
        engine = DeletionEngine(auditor=auditor, lock_manager=lock_manager)
        assert engine.auditor == auditor
        assert engine.require_validation is True

    def test_engine_default_auditor(self, tmp_path: Path, lock_manager: LockManager) -> None:
        """Test engine with default auditor."""
        # Create a temporary audit emitter instead of using default path
        auditor = AuditEmitter(audit_dir=tmp_path / "audit", auto_create=True)
        engine = DeletionEngine(auditor=auditor, lock_manager=lock_manager)
        assert engine.auditor is not None

    def test_execute_delete_single_file(
        self,
        engine: DeletionEngine,
        test_files: Path,
        safe_protection_level: ProtectionLevel,
    ) -> None:
        """Test deleting a single file."""
        single_file = test_files / "file1.txt"
        assert single_file.exists()

        plan = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="test-safe",
            targets=[str(single_file)],
            file_count=1,
            total_bytes=9,
            validated=True,
        )

        result = engine.execute(plan, safe_protection_level)

        assert result.success
        assert result.deleted_count == 1
        assert result.failed_count == 0
        assert not single_file.exists()

    def test_execute_delete_directory(
        self,
        engine: DeletionEngine,
        test_files: Path,
        safe_protection_level: ProtectionLevel,
    ) -> None:
        """Test deleting a directory."""
        assert test_files.exists()

        plan = Plan(
            plan_id="plan-002",
            environment="dev",
            protection_level="test-safe",
            targets=[str(test_files)],
            file_count=3,
            total_bytes=30,
            validated=True,
        )

        result = engine.execute(plan, safe_protection_level)

        assert result.success
        assert result.deleted_count == 3
        assert result.failed_count == 0
        assert not test_files.exists()

    def test_execute_dry_run(
        self,
        engine: DeletionEngine,
        test_files: Path,
        safe_protection_level: ProtectionLevel,
    ) -> None:
        """Test dry-run mode."""
        plan = Plan(
            plan_id="plan-003",
            environment="dev",
            protection_level="test-safe",
            targets=[str(test_files)],
            file_count=3,
            total_bytes=30,
            validated=True,
        )

        result = engine.execute(plan, safe_protection_level, dry_run=True)

        assert result.success
        assert result.dry_run is True
        assert result.deleted_count == 3  # Would delete 3 files
        assert result.failed_count == 0
        assert test_files.exists()  # Files still exist

    def test_execute_nonexistent_target(
        self, engine: DeletionEngine, safe_protection_level: ProtectionLevel
    ) -> None:
        """Test executing plan with nonexistent target."""
        plan = Plan(
            plan_id="plan-004",
            environment="dev",
            protection_level="test-safe",
            targets=["/nonexistent/path"],
            file_count=0,
            total_bytes=0,
            validated=True,
        )

        result = engine.execute(plan, safe_protection_level)

        assert not result.success
        assert result.deleted_count == 0
        assert result.failed_count == 1
        assert len(result.errors) == 1

    def test_execute_unvalidated_plan_requires_validation(
        self,
        auditor: AuditEmitter,
        lock_manager: LockManager,
        safe_protection_level: ProtectionLevel,
    ) -> None:
        """Test that unvalidated plan fails when validation required."""
        engine = DeletionEngine(auditor=auditor, lock_manager=lock_manager, require_validation=True)

        plan = Plan(
            plan_id="plan-005",
            environment="dev",
            protection_level="test-safe",
            targets=["/tmp/test"],
            file_count=0,
            total_bytes=0,
            validated=False,  # Not validated
        )

        with pytest.raises(DeletionError) as exc_info:
            engine.execute(plan, safe_protection_level)

        assert "must be validated" in str(exc_info.value)

    def test_execute_expired_plan(
        self,
        engine: DeletionEngine,
        safe_protection_level: ProtectionLevel,
    ) -> None:
        """Test that expired plan fails."""
        from datetime import datetime, timedelta, timezone

        plan = Plan(
            plan_id="plan-006",
            environment="dev",
            protection_level="test-safe",
            targets=["/tmp/test"],
            file_count=0,
            total_bytes=0,
            validated=True,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # Expired
        )

        with pytest.raises(DeletionError) as exc_info:
            engine.execute(plan, safe_protection_level)

        assert "expired" in str(exc_info.value).lower()

    def test_execute_simulation_only_requires_dry_run(self, engine: DeletionEngine) -> None:
        """Test that simulation-only protection level requires dry-run."""
        sim_level = ProtectionLevel(
            name="simulation-only",
            description="Simulation only",
            require_backup=False,
            retention_days=0,
        )

        plan = Plan(
            plan_id="plan-007",
            environment="dev",
            protection_level="simulation-only",
            targets=["/tmp/test"],
            file_count=0,
            total_bytes=0,
            validated=True,
            dry_run=False,  # Not dry-run
        )

        with pytest.raises(DeletionError) as exc_info:
            engine.execute(plan, sim_level)

        assert "requires dry-run" in str(exc_info.value)

    def test_execute_denied_plan(
        self, engine: DeletionEngine, safe_protection_level: ProtectionLevel
    ) -> None:
        """Test that denied plan fails."""
        plan = Plan(
            plan_id="plan-008",
            environment="dev",
            protection_level="test-safe",
            targets=["/tmp/test"],
            file_count=0,
            total_bytes=0,
            validated=True,
            policy_verdict=PolicyVerdict(verdict=Verdict.DENY, message="Denied"),
        )

        with pytest.raises(DeletionError) as exc_info:
            engine.execute(plan, safe_protection_level)

        assert "denied by policy" in str(exc_info.value).lower()

    def test_execute_requires_backup(self, engine: DeletionEngine) -> None:
        """Test that plan without backup fails when backup required."""
        strict_level = ProtectionLevel(
            name="strict",
            description="Strict level",
            require_backup=True,
            retention_days=30,
        )

        plan = Plan(
            plan_id="plan-009",
            environment="prod",
            protection_level="strict",
            targets=["/tmp/test"],
            file_count=0,
            total_bytes=0,
            validated=True,
            backup_path=None,  # No backup
        )

        with pytest.raises(DeletionError) as exc_info:
            engine.execute(plan, strict_level)

        assert "requires backup" in str(exc_info.value).lower()

    def test_audit_events_emitted(
        self,
        engine: DeletionEngine,
        test_files: Path,
        safe_protection_level: ProtectionLevel,
        auditor: AuditEmitter,
    ) -> None:
        """Test that audit events are emitted."""
        plan = Plan(
            plan_id="plan-010",
            environment="dev",
            protection_level="test-safe",
            targets=[str(test_files)],
            file_count=3,
            total_bytes=30,
            validated=True,
        )

        _result = engine.execute(plan, safe_protection_level, user_id="user123")

        # Check that events were emitted
        events = auditor.get_events(plan_id="plan-010")
        assert len(events) >= 2  # At least start and completion

        # Check event types
        event_phases = [e.phase for e in events]
        assert EventPhase.DELETION_STARTED in event_phases
        assert EventPhase.DELETION_COMPLETED in event_phases

    def test_verification_detects_failed_deletion(
        self,
        engine: DeletionEngine,
        safe_protection_level: ProtectionLevel,
    ) -> None:
        """Test that verification detects failed deletion."""
        # This test would require mocking shutil.rmtree to simulate failure
        # For now, just test the verification logic directly
        from pathlib import Path

        plan = Plan(
            plan_id="plan-011",
            environment="dev",
            protection_level="test-safe",
            targets=["/tmp/test"],
            file_count=0,
            total_bytes=0,
            validated=True,
        )

        # Create a file that will still exist after "deletion"
        test_path = Path("/tmp/test_verify")
        test_path.write_text("test")

        try:
            plan.targets = [str(test_path)]
            errors = engine._verify_deletion(plan)

            assert len(errors) == 1
            assert test_path in [e[0] for e in errors]
        finally:
            if test_path.exists():
                test_path.unlink()

    def test_audit_id_generation(self, engine: DeletionEngine) -> None:
        """Test that audit IDs are unique."""
        audit_id1 = engine._generate_audit_id()
        audit_id2 = engine._generate_audit_id()

        assert audit_id1 != audit_id2
        assert audit_id1.startswith("audit-")
        assert audit_id2.startswith("audit-")

    def test_execute_with_approval_required(
        self, engine: DeletionEngine, safe_protection_level: ProtectionLevel
    ) -> None:
        """Test that plan requiring approval fails without approval."""
        plan = Plan(
            plan_id="plan-012",
            environment="prod",
            protection_level="test-safe",
            targets=["/tmp/test"],
            file_count=0,
            total_bytes=0,
            validated=True,
            policy_verdict=PolicyVerdict(
                verdict=Verdict.REQUIRE_APPROVAL, message="Needs approval"
            ),
        )

        with pytest.raises(DeletionError) as exc_info:
            engine.execute(plan, safe_protection_level)

        assert "requires approval" in str(exc_info.value).lower()

    def test_deletion_result_attributes(
        self,
        engine: DeletionEngine,
        test_files: Path,
        safe_protection_level: ProtectionLevel,
    ) -> None:
        """Test DeletionResult attributes."""
        plan = Plan(
            plan_id="plan-013",
            environment="dev",
            protection_level="test-safe",
            targets=[str(test_files)],
            file_count=3,
            total_bytes=30,
            validated=True,
        )

        result = engine.execute(plan, safe_protection_level)

        assert hasattr(result, "audit_id")
        assert hasattr(result, "plan_id")
        assert hasattr(result, "deleted_count")
        assert hasattr(result, "failed_count")
        assert hasattr(result, "errors")
        assert hasattr(result, "success")
        assert hasattr(result, "dry_run")

        assert result.plan_id == "plan-013"
        assert result.audit_id.startswith("audit-")
        assert result.success is True
        assert result.dry_run is False

"""
Unit tests for rmrf.store.

Tests plan storage and retrieval.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from rmrf.models import Plan, Verdict
from rmrf.store import PlanStore, PlanStoreError


class TestPlanStore:
    """Tests for PlanStore class."""

    @pytest.fixture
    def plan_dir(self, tmp_path: Path) -> Path:
        """Create temporary plan directory."""
        plan_dir = tmp_path / "plans"
        plan_dir.mkdir()
        return plan_dir

    @pytest.fixture
    def store(self, plan_dir: Path) -> PlanStore:
        """Create plan store instance."""
        return PlanStore(plan_dir=plan_dir)

    @pytest.fixture
    def sample_plan(self) -> Plan:
        """Create sample plan."""
        return Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=10,
            total_bytes=1000,
        )

    def test_store_initialization(self, plan_dir: Path) -> None:
        """Test store initialization."""
        store = PlanStore(plan_dir=plan_dir)
        assert store.plan_dir == plan_dir

    def test_store_default_directory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test store with default directory."""
        # Clear any environment variable override
        monkeypatch.delenv("RMRF_PLAN_DIR", raising=False)

        store = PlanStore(auto_create=False)
        assert store.plan_dir == PlanStore.DEFAULT_PLAN_DIR

    def test_store_auto_creates_directory(self, tmp_path: Path) -> None:
        """Test that store auto-creates directory."""
        plan_dir = tmp_path / "new_plans"
        assert not plan_dir.exists()

        _store = PlanStore(plan_dir=plan_dir, auto_create=True)
        assert plan_dir.exists()

    def test_save_plan(self, store: PlanStore, sample_plan: Plan, plan_dir: Path) -> None:
        """Test saving a plan."""
        store.save(sample_plan)

        # Check that file was created
        plan_file = plan_dir / "plan-001.json"
        assert plan_file.exists()

        # Check content
        content = plan_file.read_text()
        assert "plan-001" in content
        assert "/tmp/test" in content

    def test_load_plan(self, store: PlanStore, sample_plan: Plan) -> None:
        """Test loading a plan."""
        store.save(sample_plan)
        loaded = store.load("plan-001")

        assert loaded.plan_id == "plan-001"
        assert loaded.environment == "dev"
        assert loaded.targets == ["/tmp/test"]

    def test_load_nonexistent_plan(self, store: PlanStore) -> None:
        """Test loading nonexistent plan raises error."""
        with pytest.raises(PlanStoreError) as exc_info:
            store.load("nonexistent")

        assert "not found" in str(exc_info.value).lower()

    def test_exists(self, store: PlanStore, sample_plan: Plan) -> None:
        """Test checking if plan exists."""
        assert not store.exists("plan-001")

        store.save(sample_plan)
        assert store.exists("plan-001")

    def test_delete_plan(self, store: PlanStore, sample_plan: Plan) -> None:
        """Test deleting a plan."""
        store.save(sample_plan)
        assert store.exists("plan-001")

        store.delete("plan-001")
        assert not store.exists("plan-001")

    def test_delete_nonexistent_plan(self, store: PlanStore) -> None:
        """Test deleting nonexistent plan raises error."""
        with pytest.raises(PlanStoreError) as exc_info:
            store.delete("nonexistent")

        assert "not found" in str(exc_info.value).lower()

    def test_list_plans(self, store: PlanStore) -> None:
        """Test listing all plans."""
        # Create multiple plans
        for i in range(3):
            plan = Plan(
                plan_id=f"plan-{i:03d}",
                environment="dev",
                protection_level="safe-local",
                targets=[f"/tmp/test{i}"],
                file_count=i,
                total_bytes=i * 100,
            )
            store.save(plan)

        plans = store.list()
        assert len(plans) == 3

    def test_list_plans_by_environment(self, store: PlanStore) -> None:
        """Test filtering plans by environment."""
        # Create plans in different environments
        for env in ["dev", "staging", "prod"]:
            plan = Plan(
                plan_id=f"plan-{env}",
                environment=env,
                protection_level="safe-local",
                targets=["/tmp/test"],
                file_count=1,
                total_bytes=100,
            )
            store.save(plan)

        dev_plans = store.list(environment="dev")
        assert len(dev_plans) == 1
        assert dev_plans[0].environment == "dev"

    def test_list_validated_only(self, store: PlanStore) -> None:
        """Test filtering for validated plans only."""
        # Create validated and unvalidated plans
        for i in range(2):
            plan = Plan(
                plan_id=f"plan-{i}",
                environment="dev",
                protection_level="safe-local",
                targets=["/tmp/test"],
                file_count=1,
                total_bytes=100,
                validated=(i == 0),  # Only first plan is validated
            )
            store.save(plan)

        validated = store.list(validated_only=True)
        assert len(validated) == 1
        assert validated[0].plan_id == "plan-0"

    def test_list_empty_directory(self, store: PlanStore) -> None:
        """Test listing when directory is empty."""
        plans = store.list()
        assert plans == []

    def test_list_nonexistent_directory(self, tmp_path: Path) -> None:
        """Test listing when directory doesn't exist."""
        store = PlanStore(plan_dir=tmp_path / "nonexistent", auto_create=False)
        plans = store.list()
        assert plans == []

    def test_update_plan(self, store: PlanStore, sample_plan: Plan) -> None:
        """Test updating an existing plan."""
        store.save(sample_plan)

        # Modify and update
        sample_plan.validated = True
        store.update(sample_plan)

        # Verify update
        loaded = store.load("plan-001")
        assert loaded.validated is True

    def test_update_nonexistent_plan(self, store: PlanStore, sample_plan: Plan) -> None:
        """Test updating nonexistent plan raises error."""
        with pytest.raises(PlanStoreError) as exc_info:
            store.update(sample_plan)

        assert "not found" in str(exc_info.value).lower()

    def test_mark_validated(self, store: PlanStore, sample_plan: Plan) -> None:
        """Test marking plan as validated."""
        store.save(sample_plan)
        assert not sample_plan.validated

        updated = store.mark_validated("plan-001")
        assert updated.validated is True
        assert updated.validated_at is not None

        # Verify persisted
        loaded = store.load("plan-001")
        assert loaded.validated is True

    def test_mark_validated_with_verdict(self, store: PlanStore, sample_plan: Plan) -> None:
        """Test marking plan as validated with policy verdict."""
        store.save(sample_plan)

        verdict_data = {
            "verdict": "allow",
            "message": "Approved",
            "reasons": ["Low risk"],
        }
        updated = store.mark_validated("plan-001", policy_verdict=verdict_data)

        assert updated.policy_verdict is not None
        assert updated.policy_verdict.verdict == Verdict.ALLOW

    def test_mark_staged(self, store: PlanStore, sample_plan: Plan) -> None:
        """Test marking plan as staged (backed up)."""
        store.save(sample_plan)
        assert sample_plan.backup_path is None

        updated = store.mark_staged("plan-001", "/var/lib/rmrf/backups/backup-001")
        assert updated.backup_path == "/var/lib/rmrf/backups/backup-001"

        # Verify persisted
        loaded = store.load("plan-001")
        assert loaded.backup_path == "/var/lib/rmrf/backups/backup-001"

    def test_mark_applied(self, store: PlanStore, sample_plan: Plan) -> None:
        """Test marking plan as applied (executed)."""
        store.save(sample_plan)
        assert sample_plan.executed_at is None

        updated = store.mark_applied("plan-001")
        assert updated.executed_at is not None

        # Verify persisted
        loaded = store.load("plan-001")
        assert loaded.executed_at is not None

    def test_cleanup_expired(self, store: PlanStore) -> None:
        """Test cleanup of expired plans."""
        # Create expired and valid plans
        expired_plan = Plan(
            plan_id="plan-expired",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # Expired
        )

        valid_plan = Plan(
            plan_id="plan-valid",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=1,
            total_bytes=100,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),  # Valid
        )

        store.save(expired_plan)
        store.save(valid_plan)

        # Cleanup
        removed = store.cleanup_expired()
        assert removed == 1

        # Verify only valid plan remains
        assert not store.exists("plan-expired")
        assert store.exists("plan-valid")

    def test_list_sorts_by_creation_time(self, store: PlanStore) -> None:
        """Test that list returns plans sorted by creation time (newest first)."""
        # Create plans with different timestamps
        import time

        for i in range(3):
            plan = Plan(
                plan_id=f"plan-{i}",
                environment="dev",
                protection_level="safe-local",
                targets=["/tmp/test"],
                file_count=1,
                total_bytes=100,
            )
            store.save(plan)
            time.sleep(0.01)  # Small delay to ensure different timestamps

        plans = store.list()
        # Should be in reverse order (newest first)
        assert plans[0].plan_id == "plan-2"
        assert plans[1].plan_id == "plan-1"
        assert plans[2].plan_id == "plan-0"

    def test_save_without_directory(self, tmp_path: Path, sample_plan: Plan) -> None:
        """Test saving when directory doesn't exist."""
        plan_dir = tmp_path / "missing"
        store = PlanStore(plan_dir=plan_dir, auto_create=True)

        # Should create directory and save
        store.save(sample_plan)
        assert plan_dir.exists()
        assert store.exists("plan-001")

    def test_save_without_autocreate_fails(self, tmp_path: Path, sample_plan: Plan) -> None:
        """Test saving without auto-create raises error."""
        plan_dir = tmp_path / "missing"
        store = PlanStore(plan_dir=plan_dir, auto_create=False)

        with pytest.raises(PlanStoreError) as exc_info:
            store.save(sample_plan)

        assert "does not exist" in str(exc_info.value).lower()

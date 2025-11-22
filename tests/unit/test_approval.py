"""
Unit tests for approval workflow.

Tests the approval data model and store methods.
"""

from datetime import datetime, timedelta, timezone

from rmrf.models import Plan
from rmrf.store import PlanStore


class TestApprovalWorkflow:
    """Test approval workflow functionality."""

    def test_mark_approval_required(self, tmp_path):
        """Test marking a plan as requiring approval."""
        store = PlanStore(plan_dir=tmp_path)

        # Create plan
        plan = Plan(
            plan_id="plan-test-001",
            environment="test",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=10,
            total_bytes=1000,
        )
        store.save(plan)

        # Mark as requiring approval
        updated = store.mark_approval_required(plan.plan_id)

        assert updated.requires_approval is True
        assert updated.approved is False

        # Verify persisted
        reloaded = store.load(plan.plan_id)
        assert reloaded.requires_approval is True
        assert reloaded.approved is False

    def test_mark_approved(self, tmp_path):
        """Test marking a plan as approved."""
        store = PlanStore(plan_dir=tmp_path)

        # Create plan requiring approval
        plan = Plan(
            plan_id="plan-test-001",
            environment="test",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=10,
            total_bytes=1000,
            requires_approval=True,
            approved=False,
            created_by_uid=1000,
        )
        store.save(plan)

        # Mark as approved by different user
        approver_uid = 1001
        updated = store.mark_approved(plan.plan_id, approver_uid)

        assert updated.approved is True
        assert updated.approved_by_uid == approver_uid
        assert updated.approved_at is not None

        # Verify persisted
        reloaded = store.load(plan.plan_id)
        assert reloaded.approved is True
        assert reloaded.approved_by_uid == approver_uid
        assert reloaded.approved_at is not None

    def test_approval_idempotent(self, tmp_path):
        """Test that approving already-approved plan is idempotent."""
        store = PlanStore(plan_dir=tmp_path)

        # Create and approve plan
        plan = Plan(
            plan_id="plan-test-001",
            environment="test",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=10,
            total_bytes=1000,
            requires_approval=True,
            created_by_uid=1000,
        )
        store.save(plan)

        # First approval
        store.mark_approved(plan.plan_id, 1001)
        first_approval = store.load(plan.plan_id)

        # Second approval (different user)
        store.mark_approved(plan.plan_id, 1002)
        second_approval = store.load(plan.plan_id)

        # Should update to latest approver
        assert second_approval.approved_by_uid == 1002
        assert second_approval.approved_at >= first_approval.approved_at

    def test_list_pending_approvals(self, tmp_path):
        """Test listing plans awaiting approval."""
        store = PlanStore(plan_dir=tmp_path)

        # Create various plans
        # Plan 1: Requires approval, not approved
        plan1 = Plan(
            plan_id="plan-pending-001",
            environment="test",
            protection_level="safe-local",
            targets=["/tmp/test1"],
            file_count=10,
            total_bytes=1000,
            requires_approval=True,
            approved=False,
        )
        store.save(plan1)

        # Plan 2: Requires approval, already approved
        plan2 = Plan(
            plan_id="plan-approved-001",
            environment="test",
            protection_level="safe-local",
            targets=["/tmp/test2"],
            file_count=10,
            total_bytes=1000,
            requires_approval=True,
            approved=True,
            approved_by_uid=1001,
        )
        store.save(plan2)

        # Plan 3: Doesn't require approval
        plan3 = Plan(
            plan_id="plan-no-approval-001",
            environment="test",
            protection_level="safe-local",
            targets=["/tmp/test3"],
            file_count=10,
            total_bytes=1000,
            requires_approval=False,
        )
        store.save(plan3)

        # Plan 4: Requires approval, different environment
        plan4 = Plan(
            plan_id="plan-pending-prod-001",
            environment="prod",
            protection_level="safe-local",
            targets=["/tmp/test4"],
            file_count=10,
            total_bytes=1000,
            requires_approval=True,
            approved=False,
        )
        store.save(plan4)

        # List all pending approvals
        pending = store.list_pending_approvals()
        assert len(pending) == 2
        assert plan1.plan_id in [p.plan_id for p in pending]
        assert plan4.plan_id in [p.plan_id for p in pending]

        # List pending for specific environment
        pending_test = store.list_pending_approvals(environment="test")
        assert len(pending_test) == 1
        assert pending_test[0].plan_id == plan1.plan_id

    def test_list_pending_approvals_empty(self, tmp_path):
        """Test listing pending approvals when none exist."""
        store = PlanStore(plan_dir=tmp_path)

        pending = store.list_pending_approvals()
        assert pending == []

    def test_list_pending_approvals_sorted(self, tmp_path):
        """Test that pending approvals are sorted by creation time."""
        store = PlanStore(plan_dir=tmp_path)

        # Create plans with different creation times
        now = datetime.now(timezone.utc)

        plan1 = Plan(
            plan_id="plan-001",
            created_at=now - timedelta(hours=3),
            environment="test",
            protection_level="safe-local",
            targets=["/tmp/test1"],
            file_count=10,
            total_bytes=1000,
            requires_approval=True,
            approved=False,
        )
        store.save(plan1)

        plan2 = Plan(
            plan_id="plan-002",
            created_at=now - timedelta(hours=1),
            environment="test",
            protection_level="safe-local",
            targets=["/tmp/test2"],
            file_count=10,
            total_bytes=1000,
            requires_approval=True,
            approved=False,
        )
        store.save(plan2)

        plan3 = Plan(
            plan_id="plan-003",
            created_at=now - timedelta(hours=2),
            environment="test",
            protection_level="safe-local",
            targets=["/tmp/test3"],
            file_count=10,
            total_bytes=1000,
            requires_approval=True,
            approved=False,
        )
        store.save(plan3)

        # List should be sorted oldest first
        pending = store.list_pending_approvals()
        assert len(pending) == 3
        assert pending[0].plan_id == "plan-001"  # Oldest
        assert pending[1].plan_id == "plan-003"  # Middle
        assert pending[2].plan_id == "plan-002"  # Newest


class TestPlanApprovalFields:
    """Test Plan model approval fields."""

    def test_approval_fields_defaults(self):
        """Test that approval fields have correct defaults."""
        plan = Plan(
            plan_id="plan-test-001",
            environment="test",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=10,
            total_bytes=1000,
        )

        assert plan.requires_approval is False
        assert plan.approved is None
        assert plan.approved_by_uid is None
        assert plan.approved_at is None
        assert plan.created_by_uid is None

    def test_approval_fields_set(self):
        """Test setting approval fields."""
        now = datetime.now(timezone.utc)

        plan = Plan(
            plan_id="plan-test-001",
            environment="test",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=10,
            total_bytes=1000,
            requires_approval=True,
            approved=True,
            approved_by_uid=1001,
            approved_at=now,
            created_by_uid=1000,
        )

        assert plan.requires_approval is True
        assert plan.approved is True
        assert plan.approved_by_uid == 1001
        assert plan.approved_at == now
        assert plan.created_by_uid == 1000

    def test_approval_serialization(self):
        """Test that approval fields serialize correctly."""
        now = datetime.now(timezone.utc)

        plan = Plan(
            plan_id="plan-test-001",
            environment="test",
            protection_level="safe-local",
            targets=["/tmp/test"],
            file_count=10,
            total_bytes=1000,
            requires_approval=True,
            approved=True,
            approved_by_uid=1001,
            approved_at=now,
            created_by_uid=1000,
        )

        # Serialize and deserialize
        plan_json = plan.model_dump_json()
        reloaded = Plan.model_validate_json(plan_json)

        assert reloaded.requires_approval == plan.requires_approval
        assert reloaded.approved == plan.approved
        assert reloaded.approved_by_uid == plan.approved_by_uid
        assert reloaded.approved_at == plan.approved_at
        assert reloaded.created_by_uid == plan.created_by_uid

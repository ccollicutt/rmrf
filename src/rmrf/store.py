"""
Plan storage for rmrf.

Centralized storage for deletion plans on the system.
"""

from __future__ import annotations

import builtins
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from rmrf.models import Plan


class PlanStoreError(Exception):
    """Raised when plan storage operations fail."""

    pass


class PlanStore:
    """
    Centralized storage for deletion plans.

    Plans are stored in /var/lib/rmrf/plans/{plan_id}.json
    """

    DEFAULT_PLAN_DIR = Path("/var/lib/rmrf/plans")

    def __init__(
        self,
        plan_dir: Path | None = None,
        auto_create: bool = True,
    ) -> None:
        """
        Initialize plan store.

        Args:
            plan_dir: Directory for plans (default: /var/lib/rmrf/plans or RMRF_PLAN_DIR env var)
            auto_create: Automatically create directory if missing
        """
        # Check environment variable if plan_dir not provided
        if plan_dir is None:
            env_plan_dir = os.getenv("RMRF_PLAN_DIR")
            if env_plan_dir:
                plan_dir = Path(env_plan_dir)
            else:
                plan_dir = self.DEFAULT_PLAN_DIR

        self.plan_dir = plan_dir
        self.auto_create = auto_create

        if self.auto_create and not self.plan_dir.exists():
            try:
                self.plan_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise PlanStoreError(f"Failed to create plan directory: {e}") from e

    def save(self, plan: Plan) -> None:
        """
        Save a plan to storage.

        Args:
            plan: Plan to save

        Raises:
            PlanStoreError: If save fails
        """
        plan_file = self.plan_dir / f"{plan.plan_id}.json"

        try:
            # Ensure directory exists
            if not self.plan_dir.exists():
                if self.auto_create:
                    self.plan_dir.mkdir(parents=True, exist_ok=True)
                else:
                    raise PlanStoreError(f"Plan directory does not exist: {self.plan_dir}")

            # Write plan
            plan_json = plan.model_dump_json(indent=2)
            plan_file.write_text(plan_json)

        except OSError as e:
            raise PlanStoreError(f"Failed to save plan {plan.plan_id}: {e}") from e

    def load(self, plan_id: str) -> Plan:
        """
        Load a plan from storage.

        Args:
            plan_id: Plan ID to load

        Returns:
            Plan object

        Raises:
            PlanStoreError: If plan not found or load fails
        """
        plan_file = self.plan_dir / f"{plan_id}.json"

        if not plan_file.exists():
            raise PlanStoreError(f"Plan not found: {plan_id}")

        try:
            plan_json = plan_file.read_text()
            plan_data = json.loads(plan_json)
            return Plan(**plan_data)
        except (OSError, json.JSONDecodeError) as e:
            raise PlanStoreError(f"Failed to load plan {plan_id}: {e}") from e

    def exists(self, plan_id: str) -> bool:
        """
        Check if a plan exists in storage.

        Args:
            plan_id: Plan ID to check

        Returns:
            True if plan exists
        """
        plan_file = self.plan_dir / f"{plan_id}.json"
        return plan_file.exists()

    def delete(self, plan_id: str) -> None:
        """
        Delete a plan from storage.

        Args:
            plan_id: Plan ID to delete

        Raises:
            PlanStoreError: If delete fails
        """
        plan_file = self.plan_dir / f"{plan_id}.json"

        if not plan_file.exists():
            raise PlanStoreError(f"Plan not found: {plan_id}")

        try:
            plan_file.unlink()
        except OSError as e:
            raise PlanStoreError(f"Failed to delete plan {plan_id}: {e}") from e

    def list(
        self,
        environment: str | None = None,
        validated_only: bool = False,
    ) -> list[Plan]:
        """
        List all plans in storage.

        Args:
            environment: Filter by environment
            validated_only: Only return validated plans

        Returns:
            List of plans
        """
        plans: list[Plan] = []

        if not self.plan_dir.exists():
            return plans

        try:
            for plan_file in self.plan_dir.glob("*.json"):
                try:
                    plan_json = plan_file.read_text()
                    plan_data = json.loads(plan_json)
                    plan = Plan(**plan_data)

                    # Apply filters
                    if environment and plan.environment != environment:
                        continue
                    if validated_only and not plan.validated:
                        continue

                    plans.append(plan)

                except (OSError, json.JSONDecodeError, Exception):
                    # Skip invalid plans
                    continue

        except OSError:
            # Directory access error
            pass

        # Sort by creation time (newest first)
        plans.sort(key=lambda p: p.created_at, reverse=True)

        return plans

    def update(self, plan: Plan) -> None:
        """
        Update an existing plan.

        Args:
            plan: Plan to update

        Raises:
            PlanStoreError: If plan doesn't exist or update fails
        """
        if not self.exists(plan.plan_id):
            raise PlanStoreError(f"Plan not found: {plan.plan_id}")

        self.save(plan)

    def mark_validated(
        self,
        plan_id: str,
        policy_verdict: dict | None = None,
    ) -> Plan:
        """
        Mark a plan as validated.

        Args:
            plan_id: Plan ID
            policy_verdict: Optional policy verdict data

        Returns:
            Updated plan

        Raises:
            PlanStoreError: If plan not found
        """
        plan = self.load(plan_id)
        plan.validated = True
        plan.validated_at = datetime.now(timezone.utc)

        if policy_verdict:
            from rmrf.models import PolicyVerdict

            plan.policy_verdict = PolicyVerdict(**policy_verdict)

        self.save(plan)
        return plan

    def mark_staged(
        self,
        plan_id: str,
        backup_path: str,
    ) -> Plan:
        """
        Mark a plan as staged (backed up).

        Args:
            plan_id: Plan ID
            backup_path: Path to backup

        Returns:
            Updated plan

        Raises:
            PlanStoreError: If plan not found
        """
        plan = self.load(plan_id)
        plan.backup_path = backup_path
        self.save(plan)
        return plan

    def mark_applied(
        self,
        plan_id: str,
    ) -> Plan:
        """
        Mark a plan as applied (executed).

        Args:
            plan_id: Plan ID

        Returns:
            Updated plan

        Raises:
            PlanStoreError: If plan not found
        """
        plan = self.load(plan_id)
        plan.executed_at = datetime.now(timezone.utc)
        self.save(plan)
        return plan

    def cleanup_expired(self) -> int:
        """
        Remove expired plans from storage.

        Returns:
            Number of plans removed
        """
        removed = 0

        if not self.plan_dir.exists():
            return removed

        for plan_file in self.plan_dir.glob("*.json"):
            try:
                plan_json = plan_file.read_text()
                plan_data = json.loads(plan_json)
                plan = Plan(**plan_data)

                if plan.is_expired():
                    plan_file.unlink()
                    removed += 1

            except (OSError, json.JSONDecodeError, Exception):
                # Skip invalid/inaccessible plans
                continue

        return removed

    def mark_approval_required(self, plan_id: str) -> Plan:
        """
        Mark a plan as requiring approval.

        Args:
            plan_id: Plan ID

        Returns:
            Updated plan

        Raises:
            PlanStoreError: If plan not found
        """
        plan = self.load(plan_id)
        plan.requires_approval = True
        plan.approved = False
        self.save(plan)
        return plan

    def mark_approved(self, plan_id: str, approver_uid: int, comment: str | None = None) -> Plan:
        """
        Mark a plan as approved.

        Args:
            plan_id: Plan ID
            approver_uid: User ID who approved
            comment: Optional approval comment

        Returns:
            Updated plan

        Raises:
            PlanStoreError: If plan not found
        """
        plan = self.load(plan_id)
        plan.approved = True
        plan.approved_by_uid = approver_uid
        plan.approved_at = datetime.now(timezone.utc)
        if comment:
            plan.approval_comment = comment
        self.save(plan)
        return plan

    def list_pending_approvals(self, environment: str | None = None) -> builtins.list[Plan]:
        """
        List plans awaiting approval.

        Args:
            environment: Filter by environment

        Returns:
            List of plans requiring approval
        """
        plans: list[Plan] = []

        if not self.plan_dir.exists():
            return plans

        try:
            for plan_file in self.plan_dir.glob("*.json"):
                try:
                    plan_json = plan_file.read_text()
                    plan_data = json.loads(plan_json)
                    plan = Plan(**plan_data)

                    # Filter for pending approvals
                    if not plan.requires_approval:
                        continue
                    if plan.approved:
                        continue

                    # Apply environment filter
                    if environment and plan.environment != environment:
                        continue

                    plans.append(plan)

                except (OSError, json.JSONDecodeError, Exception):
                    # Skip invalid plans
                    continue

        except OSError:
            # Directory access error
            pass

        # Sort by creation time (oldest first - needs approval soonest)
        plans.sort(key=lambda p: p.created_at)

        return plans

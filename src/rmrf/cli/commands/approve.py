"""
Approval CLI commands.

Provides commands for approving deletion plans.
"""

import json
import os
import pwd
import sys
from typing import Any

import click

from rmrf.models import AuditEvent, EventPhase
from rmrf.store import PlanStore

from ..output import log_error, log_info, log_success, print_structured_output
from ..utils import load_plan


@click.command(
    epilog="""
Examples:
  rmrf approve plan-20250107-120000-abc123    # Approve plan
  rmrf approve plan.json                      # Approve from file
  rmrf approve plan.json --comment "Reviewed" # Approve with comment
"""
)
@click.argument("plan_id_or_file")
@click.option(
    "--approver-uid",
    type=int,
    help="Approver UID (for testing - defaults to current user)",
)
@click.option(
    "--comment",
    help="Approval comment",
)
@click.pass_context
def approve(
    ctx: click.Context,
    plan_id_or_file: str,
    approver_uid: int | None,
    comment: str | None,
) -> None:
    """
    Approve a deletion plan requiring approval.

    Validates that the approver is a different user than the plan creator.
    Records approval with user ID and timestamp in the plan store.

    Accepts either a plan ID (from the plan store) or a path to a plan JSON file.

    \b
    Examples:
      rmrf approve plan-20250107-120000-abc123
      rmrf approve plan.json
    """
    json_output = ctx.obj["json_output"]

    try:
        # Load plan
        plan_obj = load_plan(plan_id_or_file)

        # Get current user (or use provided approver_uid for testing)
        current_uid = approver_uid if approver_uid is not None else os.getuid()

        # Check if plan requires approval
        if not plan_obj.requires_approval:
            if json_output:
                not_required_result: dict[str, Any] = {
                    "plan_id": plan_obj.plan_id,
                    "error": "Plan does not require approval",
                }
                click.echo(json.dumps(not_required_result, indent=2))
            else:
                log_error(f"Plan {plan_obj.plan_id} does not require approval")
            sys.exit(1)

        # Check if already approved
        if plan_obj.approved:
            approver_name = _get_username(plan_obj.approved_by_uid)
            if json_output:
                result: dict[str, Any] = {
                    "plan_id": plan_obj.plan_id,
                    "already_approved": True,
                    "approved_by_uid": plan_obj.approved_by_uid,
                    "approved_by": approver_name,
                    "approved_at": plan_obj.approved_at.isoformat()
                    if plan_obj.approved_at
                    else None,
                }
                click.echo(json.dumps(result, indent=2))
            else:
                log_info(
                    f"Plan {plan_obj.plan_id} already approved by {approver_name} "
                    f"(UID {plan_obj.approved_by_uid}) at {plan_obj.approved_at}"
                )
            sys.exit(0)

        # Validate different user
        if plan_obj.created_by_uid is not None and current_uid == plan_obj.created_by_uid:
            creator_name = _get_username(plan_obj.created_by_uid)
            if json_output:
                error_result: dict[str, Any] = {
                    "plan_id": plan_obj.plan_id,
                    "error": "Cannot approve own plan",
                    "created_by_uid": plan_obj.created_by_uid,
                    "current_uid": current_uid,
                }
                click.echo(json.dumps(error_result, indent=2))
            else:
                log_error(
                    f"Cannot approve own plan. Plan created by UID {plan_obj.created_by_uid} ({creator_name}), "
                    f"current user is UID {current_uid} (same user)"
                )
            sys.exit(1)

        # Approve plan
        try:
            # Generate approval ID if not present
            import uuid
            from datetime import datetime, timezone

            if not plan_obj.approval_id:
                plan_obj.approval_id = f"appr-{uuid.uuid4().hex[:8]}"

            store = PlanStore(auto_create=False)
            if store.exists(plan_obj.plan_id):
                # Load plan from store, update fields, and save
                store_plan = store.load(plan_obj.plan_id)
                store_plan.approval_id = plan_obj.approval_id
                store_plan.approved = True
                store_plan.approved_by_uid = current_uid
                store_plan.approved_at = datetime.now(timezone.utc)
                if comment:
                    store_plan.approval_comment = comment
                store.save(store_plan)
                plan_obj = store_plan  # Use updated plan
            else:
                # Plan not in store - update in memory only
                plan_obj.approved = True
                plan_obj.approved_by_uid = current_uid
                plan_obj.approved_at = datetime.now(timezone.utc)
                if comment:
                    plan_obj.approval_comment = comment
        except Exception as e:
            log_error(f"Failed to mark plan as approved: {e}")
            sys.exit(1)

        # Emit audit event (best effort)
        try:
            from uuid import uuid4

            from rmrf.audit import AuditEmitter

            auditor = AuditEmitter()
            timestamp = datetime.now(timezone.utc)
            event = AuditEvent(
                event_id=f"evt-{timestamp.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}",
                phase=EventPhase.APPROVAL_GRANTED,
                environment=plan_obj.environment,
                protection_level=plan_obj.protection_level,
                plan_id=plan_obj.plan_id,
                user_id=str(current_uid),
                message=f"Plan {plan_obj.plan_id} approved by UID {current_uid}",
                metadata={
                    "approver_uid": current_uid,
                    "approver_name": _get_username(current_uid),
                },
            )
            auditor.emit(event)
        except Exception:
            pass

        # Output result
        if json_output:
            success_result: dict[str, Any] = {
                "plan_id": plan_obj.plan_id,
                "approved": True,
                "approval_id": plan_obj.approval_id,
                "approved_by_uid": current_uid,
                "approved_by": _get_username(current_uid),
                "approved_at": plan_obj.approved_at.isoformat() if plan_obj.approved_at else None,
            }
            click.echo(json.dumps(success_result, indent=2))
        else:
            approver_name = _get_username(current_uid)
            log_success(f"Plan {plan_obj.plan_id} approved by {approver_name} (UID {current_uid})")
            print_structured_output(
                verdict="APPROVED",
                scenario=f"plan {plan_obj.plan_id}",
                summary="approval granted",
                what_happened=f"Plan {plan_obj.plan_id} has been approved by {approver_name} (UID {current_uid}). "
                f"The plan can now proceed to staging and execution.",
                why_it_matters="Multi-user approval ensures that critical deletion operations are reviewed by a second person, "
                "adding an important safety gate for high-risk deletions.",
                next_steps=[
                    f"Create backup: rmrf stage {plan_obj.plan_id}",
                    f"Execute deletion: rmrf apply {plan_obj.plan_id}",
                    f"View status: rmrf status --plan-id {plan_obj.plan_id}",
                ],
                additional_info={
                    "Plan ID": plan_obj.plan_id,
                    "Approved By": f"{approver_name} (UID {current_uid})",
                    "Environment": plan_obj.environment,
                },
            )

    except json.JSONDecodeError as e:
        log_error(f"Invalid JSON in plan file: {e}")
        sys.exit(1)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        sys.exit(1)


@click.command(name="list-pending-approvals")
@click.option(
    "--environment",
    help="Filter by environment",
)
@click.pass_context
def list_pending_approvals(
    ctx: click.Context,
    environment: str | None,
) -> None:
    """
    List plans awaiting approval.

    Shows all plans that require approval but have not yet been approved.

    \b
    Examples:
      rmrf list-pending-approvals
      rmrf list-pending-approvals --environment prod
    """
    json_output = ctx.obj["json_output"]

    try:
        store = PlanStore(auto_create=False)
        plans = store.list_pending_approvals(environment=environment)

        if json_output:
            result = {
                "count": len(plans),
                "plans": [
                    {
                        "plan_id": p.plan_id,
                        "created_at": p.created_at.isoformat(),
                        "created_by_uid": p.created_by_uid,
                        "created_by": _get_username(p.created_by_uid) if p.created_by_uid else None,
                        "environment": p.environment,
                        "file_count": p.file_count,
                        "total_bytes": p.total_bytes,
                        "targets": p.targets,
                    }
                    for p in plans
                ],
            }
            click.echo(json.dumps(result, indent=2))
        else:
            if not plans:
                log_info("No plans awaiting approval")
                return

            from ..output import format_bytes

            click.echo(f"\nFound {len(plans)} plan(s) awaiting approval:\n")
            for p in plans:
                creator_name = _get_username(p.created_by_uid) if p.created_by_uid else "unknown"
                click.echo(f"  • {p.plan_id}")
                click.echo(f"    Created by: {creator_name} (UID {p.created_by_uid})")
                click.echo(f"    Environment: {p.environment}")
                click.echo(f"    Files: {p.file_count} ({format_bytes(p.total_bytes)})")
                click.echo(f"    Targets: {', '.join(p.targets[:2])}")
                if len(p.targets) > 2:
                    click.echo(f"              ... and {len(p.targets) - 2} more")
                click.echo(f"    Approve: rmrf approve {p.plan_id}\n")

    except Exception as e:
        log_error(f"Failed to list pending approvals: {e}")
        sys.exit(1)


def _get_username(uid: int | None) -> str:
    """Get username from UID."""
    if uid is None:
        return "unknown"
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return f"UID-{uid}"

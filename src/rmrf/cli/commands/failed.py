"""
Mark-failed CLI command.

Provides command for marking plans as failed.
"""

import sys
from datetime import datetime, timezone

import click

from rmrf.store import PlanStore

from ..output import log_error, log_info, log_success
from ..utils import load_plan


@click.command(
    name="mark-failed",
    epilog="""\b
Examples:
  rmrf mark-failed plan-20250108-120000-abc123
  rmrf mark-failed plan-20250108-120000-abc123 --comment "Verification failed repeatedly"

Marks a plan as failed with explanation for safety tracking.
""",
)
@click.argument("plan_id")
@click.option(
    "--comment",
    "-c",
    help="Reason for failure (will prompt if not provided)",
)
@click.pass_context
def mark_failed(
    ctx: click.Context,
    plan_id: str,
    comment: str | None,
) -> None:
    """
    Mark a plan as failed.

    Records when a plan operation has failed to track failures
    and understand what went wrong. This is important for safety
    analysis and process improvement.

    \b
    Examples:
      rmrf mark-failed plan-20250108-120000-abc123
      rmrf mark-failed plan-20250108-120000-abc123 --comment "Verify failed 3 times"
    """
    json_output = ctx.obj.get("json_output", False)

    try:
        # Load plan
        plan = load_plan(plan_id)

        # Check if plan is already in a terminal state
        current_stage = plan.get_workflow_stage()
        if current_stage in ["closed", "rollback", "near-miss", "failed"]:
            log_error(f"Plan is already in terminal state: {current_stage}")
            sys.exit(1)

        # Prompt for comment if not provided
        if not comment:
            if json_output:
                log_error("Comment required in JSON mode. Use --comment flag.")
                sys.exit(1)

            click.echo("")
            click.secho("Mark Plan as Failed", bold=True, fg="red")
            click.echo("")
            click.echo(f"Plan {plan.plan_id} is at stage '{current_stage}'")
            click.echo("")
            click.echo("Please explain what failed:")
            click.echo("  - What operation failed?")
            click.echo("  - What was the error?")
            click.echo("  - Can it be retried or recovered?")
            click.echo("")

            comment = click.prompt("Failure reason", type=str)

        if not comment or not comment.strip():
            log_error("Comment cannot be empty")
            sys.exit(1)

        # Update plan as failed
        plan.failed = True
        plan.failed_at = datetime.now(timezone.utc)
        plan.failed_comment = comment.strip()

        # Save updated plan
        try:
            store = PlanStore(auto_create=False)
            if store.exists(plan.plan_id):
                store.save(plan)
                if not json_output:
                    log_success(f"Plan {plan.plan_id} marked as failed")
            else:
                if not json_output:
                    log_info("Plan not in store, but marked as failed in memory")
        except Exception as e:
            log_error(f"Could not update plan storage: {e}")
            sys.exit(1)

        # Output confirmation
        if json_output:
            import json

            result = {
                "plan_id": plan.plan_id,
                "failed": True,
                "failed_comment": plan.failed_comment,
                "failed_at": plan.failed_at.isoformat() if plan.failed_at else None,
            }
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo("")
            click.secho("✗ Plan marked as failed", fg="red", bold=True)
            click.echo(f"  Plan: {plan.plan_id}")
            click.echo(f"  Previous stage: {current_stage}")
            click.echo(f"  Reason: {plan.failed_comment}")
            click.echo("")
            click.echo("Failure tracking helps improve safety processes and identify issues.")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"Failed to mark plan as failed: {e}")
        sys.exit(1)

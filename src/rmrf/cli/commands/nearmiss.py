"""
Near-miss CLI command.

Provides command for marking abandoned plans as near-misses.
"""

import sys
from datetime import datetime, timezone

import click

from rmrf.store import PlanStore

from ..output import log_error, log_info, log_success
from ..utils import load_plan


@click.command(
    name="near-miss",
    epilog="""
Examples:
  rmrf near-miss plan-20250108-120000-abc123
  rmrf near-miss plan-20250108-120000-abc123 --comment "Plan no longer needed"

Marks a plan as abandoned with explanation for safety tracking.
""",
)
@click.argument("plan_id")
@click.option(
    "--comment",
    "-c",
    help="Reason for abandoning plan (will prompt if not provided)",
)
@click.pass_context
def near_miss(
    ctx: click.Context,
    plan_id: str,
    comment: str | None,
) -> None:
    """
    Mark a plan as abandoned (near-miss).

    Records when a plan is abandoned before completion to track near-misses
    and understand why planned deletions were not executed. This is important
    for safety analysis and process improvement.

    \b
    Examples:
      rmrf near-miss plan-20250108-120000-abc123
      rmrf near-miss plan-20250108-120000-abc123 --comment "Requirement changed"
    """
    json_output = ctx.obj.get("json_output", False)

    try:
        # Load plan
        plan = load_plan(plan_id)

        # Check if plan is already in a terminal state
        current_stage = plan.get_workflow_stage()
        if current_stage in ["closed", "rollback", "near-miss"]:
            log_error(f"Plan is already in terminal state: {current_stage}")
            sys.exit(1)

        # Prompt for comment if not provided
        if not comment:
            if json_output:
                log_error("Comment required in JSON mode. Use --comment flag.")
                sys.exit(1)

            click.echo("")
            click.secho("Near-Miss Report", bold=True, fg="yellow")
            click.echo("")
            click.echo(f"Plan {plan.plan_id} is at stage '{current_stage}'")
            click.echo("")
            click.echo("Please explain why this plan is being abandoned:")
            click.echo("  - Did requirements change?")
            click.echo("  - Was the plan created in error?")
            click.echo("  - Did circumstances change?")
            click.echo("")

            comment = click.prompt("Reason for abandoning", type=str)

        if not comment or not comment.strip():
            log_error("Comment cannot be empty")
            sys.exit(1)

        # Update plan as near-miss
        plan.near_miss = True
        plan.near_miss_at = datetime.now(timezone.utc)
        plan.near_miss_comment = comment.strip()

        # Save updated plan
        try:
            store = PlanStore(auto_create=False)
            if store.exists(plan.plan_id):
                store.save(plan)
                if not json_output:
                    log_success(f"Plan {plan.plan_id} marked as near-miss")
            else:
                if not json_output:
                    log_info("Plan not in store, but marked as near-miss in memory")
        except Exception as e:
            log_error(f"Could not update plan storage: {e}")
            sys.exit(1)

        # Output confirmation
        if json_output:
            import json

            result = {
                "plan_id": plan.plan_id,
                "near_miss": True,
                "near_miss_comment": plan.near_miss_comment,
                "near_miss_at": plan.near_miss_at.isoformat() if plan.near_miss_at else None,
            }
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo("")
            click.secho("✓ Plan marked as near-miss", fg="yellow", bold=True)
            click.echo(f"  Plan: {plan.plan_id}")
            click.echo(f"  Previous stage: {current_stage}")
            click.echo(f"  Reason: {plan.near_miss_comment}")
            click.echo("")
            click.echo("Near-miss tracking helps improve safety processes.")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"Failed to mark plan as near-miss: {e}")
        sys.exit(1)

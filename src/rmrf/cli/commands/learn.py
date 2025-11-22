"""
Learn CLI command.

Provides command for recording lessons learned and post-completion notes.
"""

import sys

import click

from rmrf.store import PlanStore

from ..output import log_error, log_info, log_success
from ..utils import load_plan


@click.command(
    epilog="""
Examples:
  rmrf learn plan-20250108-120000-abc123
  rmrf learn plan-20250108-120000-abc123 --comment "Deletion went smoothly, no issues"

Records lessons learned and operator notes for completed operations.
"""
)
@click.argument("plan_id")
@click.option(
    "--comment",
    "-c",
    help="Lessons learned comment (will prompt if not provided)",
)
@click.pass_context
def learn(
    ctx: click.Context,
    plan_id: str,
    comment: str | None,
) -> None:
    """
    Record lessons learned for a completed operation.

    Captures operator insights, observations, and notes about the deletion
    operation for future reference and continuous improvement.

    \b
    Examples:
      rmrf learn plan-20250108-120000-abc123
      rmrf learn plan-20250108-120000-abc123 --comment "Process worked well"
    """
    json_output = ctx.obj.get("json_output", False)

    try:
        # Load plan
        plan = load_plan(plan_id)

        # Prompt for comment if not provided
        if not comment:
            if json_output:
                log_error("Comment required in JSON mode. Use --comment flag.")
                sys.exit(1)

            click.echo("")
            click.secho("Record Lessons Learned", bold=True, fg="cyan")
            click.echo("")
            click.echo("Please provide insights about this deletion operation:")
            click.echo("  - What went well?")
            click.echo("  - What could be improved?")
            click.echo("  - Any observations or notes?")
            click.echo("")

            comment = click.prompt("Lessons learned", type=str)

        if not comment or not comment.strip():
            log_error("Comment cannot be empty")
            sys.exit(1)

        # Update plan with learn comment
        plan.learn_comment = comment.strip()

        # Save updated plan
        try:
            store = PlanStore(auto_create=False)
            if store.exists(plan.plan_id):
                store.save(plan)
                if not json_output:
                    log_success(f"Lessons learned recorded for plan {plan.plan_id}")
            else:
                if not json_output:
                    log_info("Plan not in store, but comment recorded in memory")
        except Exception as e:
            log_error(f"Could not update plan storage: {e}")
            sys.exit(1)

        # Output confirmation
        if json_output:
            import json

            result = {
                "plan_id": plan.plan_id,
                "learn_comment": plan.learn_comment,
            }
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo("")
            click.secho("✓ Lessons learned recorded", fg="green", bold=True)
            click.echo(f"  Plan: {plan.plan_id}")
            click.echo(f"  Comment: {plan.learn_comment}")
            click.echo("")
            click.echo("This information will help improve future operations.")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"Failed to record lessons learned: {e}")
        sys.exit(1)

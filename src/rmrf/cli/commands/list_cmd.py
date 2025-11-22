"""
List CLI commands.

Provides commands for listing plans, backups, and audit events.
"""

import json
import sys
from pathlib import Path

import click

from rmrf.store import PlanStore, PlanStoreError

from ..output import log_error, log_info, print_structured_output


@click.command(
    name="list",
    epilog="""
Examples:
  rmrf list plans                     # List all plans
  rmrf list plans --environment dev   # Filter by environment
  rmrf list plans --stage validated   # Filter by workflow stage
  rmrf list plans --stage !applied    # Exclude applied plans
  rmrf list plans --validated-only    # Only validated plans

Use --output json for machine-readable format.
""",
)
@click.argument("type", type=click.Choice(["plans"]), default="plans")
@click.option(
    "--environment",
    "-e",
    help="Filter by environment",
)
@click.option(
    "--stage",
    "-s",
    help="Filter by workflow stage (use ! to exclude, e.g., !applied)",
)
@click.option(
    "--validated-only",
    is_flag=True,
    help="Only show validated plans",
)
@click.option(
    "--plan-dir",
    type=click.Path(),
    help="Plan directory (default: /var/lib/rmrf/plans)",
)
@click.pass_context
def list_objects(
    ctx: click.Context,
    type: str,
    environment: str | None,
    stage: str | None,
    validated_only: bool,
    plan_dir: str | None,
) -> None:
    """
    List rmrf objects (plans, backups, audits).

    \b
    Examples:
      rmrf list plans
      rmrf list plans --environment dev
      rmrf list plans --stage validated
      rmrf list plans --stage !applied
      rmrf list plans --validated-only
    """
    json_output = ctx.obj["json_output"]

    if type == "plans":
        _list_plans(
            environment=environment,
            stage=stage,
            validated_only=validated_only,
            plan_dir=Path(plan_dir) if plan_dir else None,
            json_output=json_output,
        )


def _list_plans(
    environment: str | None,
    stage: str | None,
    validated_only: bool,
    plan_dir: Path | None,
    json_output: bool,
) -> None:
    """List all plans in the store."""
    try:
        # Create plan store
        store = PlanStore(plan_dir=plan_dir, auto_create=False)

        # List plans
        plans = store.list(environment=environment, validated_only=validated_only)

        # Filter by stage if specified
        if stage:
            # Check for exclusion operator
            if stage.startswith("!"):
                exclude_stage = stage[1:]
                plans = [p for p in plans if p.get_workflow_stage() != exclude_stage]
            else:
                plans = [p for p in plans if p.get_workflow_stage() == stage]

        if not plans:
            if json_output:
                click.echo(json.dumps({"plans": []}, indent=2))
            else:
                log_info("No plans found")
            return

        if json_output:
            # JSON output
            plans_data = [p.model_dump(mode="json") for p in plans]
            click.echo(json.dumps({"plans": plans_data}, indent=2))
        else:
            # Human-readable output
            click.echo(f"Found {len(plans)} plan(s)", err=True)
            click.echo("", err=True)

            # Show plans in table format
            for plan in plans:
                # Get workflow stage
                workflow_stage = plan.get_workflow_stage()

                status_markers = []
                status_markers.append(workflow_stage.upper())
                if plan.is_expired():
                    status_markers.append("EXPIRED")
                if plan.dry_run:
                    status_markers.append("DRY-RUN")

                status_str = f" [{', '.join(status_markers)}]" if status_markers else ""

                click.echo(f"Plan: {plan.plan_id}{status_str}")
                click.echo(f"  Environment: {plan.environment}")
                click.echo(f"  Protection: {plan.protection_level}")
                click.echo(f"  Files: {plan.file_count}")
                click.echo(f"  Size: {_format_bytes(plan.total_bytes)}")
                click.echo(f"  Risk: {plan.risk_score.level.value if plan.risk_score else 'N/A'}")
                click.echo(f"  Created: {plan.created_at.isoformat()}")

                if plan.expires_at:
                    expiry_status = "EXPIRED" if plan.is_expired() else "Valid"
                    click.echo(f"  Expires: {plan.expires_at.isoformat()} [{expiry_status}]")

                click.echo("")

            # Add structured summary
            print_structured_output(
                verdict="INFO",
                scenario="plan listing",
                summary=f"found {len(plans)} plan(s)",
                what_happened=f"Retrieved {len(plans)} deletion plans from store. "
                f"Plans include metadata, validation status, and backup information. "
                f"Use 'rmrf show <plan-id>' to view detailed plan information.",
                why_it_matters="Listing plans provides visibility into pending and completed deletion operations. "
                "This enables workflow management, audit review, and operational transparency. "
                "Plans can be filtered by environment and validation status for focused review.",
                next_steps=[
                    "Review individual plans: rmrf show <plan-id>",
                    "Filter by stage: rmrf list plans --stage validated",
                    "Filter by environment: Use --environment flag to narrow results",
                    "Clean up expired plans: Plans with EXPIRED status should be removed",
                    "Export to JSON: Add --output json for machine processing",
                ],
                additional_info={
                    "Total Plans": str(len(plans)),
                    "Planned": str(sum(1 for p in plans if p.get_workflow_stage() == "planned")),
                    "Validated": str(
                        sum(1 for p in plans if p.get_workflow_stage() == "validated")
                    ),
                    "Staged": str(sum(1 for p in plans if p.get_workflow_stage() == "staged")),
                    "Applied": str(sum(1 for p in plans if p.get_workflow_stage() == "applied")),
                    "Closed": str(sum(1 for p in plans if p.get_workflow_stage() == "closed")),
                    "Expired": str(sum(1 for p in plans if p.is_expired())),
                },
            )

    except PlanStoreError as e:
        log_error(f"Failed to list plans: {e}")
        sys.exit(1)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        sys.exit(1)


def _format_bytes(bytes_count: int) -> str:
    """Format bytes for human-readable output."""
    if bytes_count == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size = float(bytes_count)

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.1f} {units[unit_index]}"

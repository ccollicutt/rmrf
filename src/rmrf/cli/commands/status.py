"""
Status CLI commands.

Provides commands for viewing audit events and operation status.
"""

import json
import sys
from pathlib import Path

import click

from rmrf.audit import AuditEmitter, AuditError

from ..output import log_error, log_info, print_structured_output


@click.command(
    epilog="""
Examples:
  rmrf status audit-20250107-120000-abc123    # Show audit by ID
  rmrf status --plan-id plan-001              # Show events for plan
  rmrf status --date 2025-01-07               # Show all events for date

Use --json-output flag for machine-readable format.
"""
)
@click.argument("audit_id", required=False)
@click.option(
    "--plan-id",
    help="Filter by plan ID",
)
@click.option(
    "--date",
    help="Date in YYYY-MM-DD format (default: today)",
)
@click.option(
    "--audit-dir",
    type=click.Path(),
    help="Audit directory (default: /var/lib/rmrf/audit)",
)
@click.pass_context
def status(
    ctx: click.Context,
    audit_id: str | None,
    plan_id: str | None,
    date: str | None,
    audit_dir: str | None,
) -> None:
    """
    Show status of a deletion operation.

    Retrieves audit events for a specific operation or plan.

    \b
    Examples:
      rmrf status audit-20250107-120000-abc123
      rmrf status --plan-id plan-001
      rmrf status --date 2025-01-07
    """
    json_output = ctx.obj["json_output"]

    try:
        # Create audit emitter
        auditor = AuditEmitter(audit_dir=Path(audit_dir) if audit_dir else None, auto_create=False)

        # Get events
        events = auditor.get_events(plan_id=plan_id, audit_id=audit_id, date=date)

        if not events:
            if json_output:
                click.echo(json.dumps({"events": []}, indent=2))
            else:
                log_info("No events found")
            return

        if json_output:
            # JSON output
            events_data = [e.model_dump(mode="json") for e in events]
            click.echo(json.dumps({"events": events_data}, indent=2))
        else:
            # Human-readable output
            click.echo(f"Found {len(events)} audit event(s)", err=True)
            click.echo("", err=True)

            # Show detailed events
            for i, event in enumerate(events, 1):
                click.echo(f"[Event {i}/{len(events)}]")
                click.echo(f"  Event ID: {event.event_id}")
                click.echo(f"  Timestamp: {event.timestamp.isoformat()}")
                click.echo(f"  Phase: {event.phase.value}")

                if event.plan_id:
                    click.echo(f"  Plan ID: {event.plan_id}")
                if event.audit_id:
                    click.echo(f"  Audit ID: {event.audit_id}")
                if event.message:
                    click.echo(f"  Message: {event.message}")
                if event.user_id:
                    click.echo(f"  User: {event.user_id}")

                click.echo("")

            # Add structured summary
            latest_event = events[-1] if events else None
            if latest_event:
                scenario_name = f"audit for {plan_id or audit_id or 'unknown'}"

                # Determine phases present
                phases = {e.phase.value for e in events}
                phase_summary = ", ".join(sorted(phases))

                print_structured_output(
                    verdict="INFO",
                    scenario=scenario_name,
                    summary=f"found {len(events)} audit event(s)",
                    what_happened=f"Retrieved {len(events)} audit events covering phases: {phase_summary}. "
                    f"Latest event was {latest_event.phase.value} at {latest_event.timestamp.isoformat()}. "
                    f"Audit trail provides complete operational history for compliance and debugging.",
                    why_it_matters="Audit trails enable compliance review, debugging, and operational transparency. "
                    "Each event captures system state and actions, providing accountability for all deletion operations. "
                    "This audit-first design is a core safety feature of rmrf.",
                    next_steps=[
                        "Review event details above for complete operational history",
                        "Export to JSON for compliance records: add --json-output flag",
                        "Correlate events with system logs if investigating issues",
                    ],
                    additional_info={
                        "Total Events": str(len(events)),
                        "Phases Covered": phase_summary,
                        "Latest Phase": latest_event.phase.value,
                        **(
                            {"Latest Audit ID": latest_event.audit_id}
                            if latest_event.audit_id
                            else {}
                        ),
                    },
                    audit_id=latest_event.audit_id if latest_event.audit_id else None,
                )

    except AuditError as e:
        log_error(f"Failed to retrieve status: {e}")
        sys.exit(1)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        sys.exit(1)

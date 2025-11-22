"""
Plan-related CLI commands.

Provides commands for creating and viewing deletion plans.
"""

import json
import os
import pwd
import sys
from pathlib import Path

import click

from rmrf.environment import EnvironmentError
from rmrf.locking import LockManager
from rmrf.models import UserContext
from rmrf.planner import PlanGenerator, PlanGeneratorError
from rmrf.store import PlanStore

from ..output import (
    format_bytes,
    get_risk_color,
    log_error,
    log_info,
    log_success,
    print_structured_output,
)
from ..utils import load_plan


@click.command(
    epilog="""\b
Examples:
  rmrf plan /tmp/old-logs
  rmrf plan /tmp/file1.txt /tmp/file2.txt --output plan.json
  rmrf plan /var/log --environment prod --scenario "log rotation"

\b
Common workflow:
  1. rmrf plan /path/to/delete        # Create deletion plan
  2. rmrf validate <plan-id>          # Validate against policy
  3. rmrf stage <plan-id>             # Create backup
  4. rmrf apply <plan-id>             # Execute deletion
"""
)
@click.argument("targets", nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file for plan JSON (default: stdout)",
)
@click.option("--environment", "-e", help="Environment name (auto-detected if not specified)")
@click.option(
    "--protection-level", "-p", help="Protection level (derived from environment if not specified)"
)
@click.option("--user-id", help="User ID for audit")
@click.option("--user-role", help="User role for audit")
@click.option("--scenario", "-s", help="Scenario description")
@click.option(
    "--ttl-hours", type=int, default=24, help="Plan expiration time in hours (default: 24)"
)
@click.option("--dry-run", is_flag=True, help="Create dry-run plan (no actual deletion)")
@click.pass_context
def plan(
    ctx: click.Context,
    targets: tuple[str, ...],
    output: str | None,
    environment: str | None,
    protection_level: str | None,
    user_id: str | None,
    user_role: str | None,
    scenario: str | None,
    ttl_hours: int,
    dry_run: bool,
) -> None:
    """
    Generate a deletion plan from target paths.

    TARGETS can be files or directories. Multiple targets can be specified.

    \b
    Examples:
      rmrf plan /tmp/old-logs
      rmrf plan /tmp/file1.txt /tmp/file2.txt --output plan.json
      rmrf plan /var/log --environment prod --scenario "log rotation"
    """
    json_output = ctx.obj["json_output"]

    try:
        # Create user context if provided
        user = None
        if user_id:
            user = UserContext(id=user_id, role=user_role or "unknown")

        # Generate plan
        if not json_output:
            log_info(f"Scanning {len(targets)} target(s)...")

        generator = PlanGenerator()
        plan_obj = generator.generate(
            targets=list(targets),
            environment=environment,
            protection_level=protection_level,
            user=user,
            scenario=scenario,
            ttl_hours=ttl_hours if ttl_hours > 0 else None,
            dry_run=dry_run,
        )

        # Set created_by_uid to current user
        plan_obj.created_by_uid = os.getuid()

        # Save to plan store
        store = PlanStore()
        store.save(plan_obj)

        if not json_output:
            log_success(f"Plan saved to store: {plan_obj.plan_id}")

        # Acquire locks on all target paths (best effort - don't fail if lock unavailable)
        try:
            lock_manager = LockManager()
            for target in plan_obj.targets:
                try:
                    lock_manager.acquire_lock(Path(target), plan_obj.plan_id)
                except Exception:
                    # Lock acquisition failure on individual targets is non-fatal
                    pass
        except Exception:
            # Lock manager initialization failure is non-fatal
            pass

        # Serialize plan
        plan_json = plan_obj.model_dump_json(indent=2)

        # Output plan to file if requested
        if output:
            Path(output).write_text(plan_json)
            if not json_output:
                log_info(f"Plan also written to {output}")
        elif json_output:
            # JSON output mode: print plan
            click.echo(plan_json)

        # Human-readable summary
        if not json_output:
            # Determine risk level for narrative
            risk_desc = ""
            if plan_obj.risk_score:
                risk_desc = f" with {plan_obj.risk_score.level.value} risk"

            # Build scenario name
            scenario_name = scenario or f"deletion of {len(targets)} target(s)"

            # Structured narrative output
            print_structured_output(
                verdict="SUCCESS",
                scenario=scenario_name,
                summary="planned successfully",
                what_happened=f"Scanned {plan_obj.file_count} files totaling {format_bytes(plan_obj.total_bytes)} "
                f"across {len(targets)} target(s). Created deletion plan {plan_obj.plan_id} "
                f"for {plan_obj.environment} environment with {plan_obj.protection_level} protection{risk_desc}.",
                why_it_matters=f"This plan provides a safe, auditable deletion pathway. "
                f"The protection level enforces appropriate safety constraints for the {plan_obj.environment} environment, "
                f"and the plan must pass validation before any files can be deleted.",
                next_steps=[
                    f"Review plan details: rmrf show {plan_obj.plan_id}",
                    f"Validate against policy: rmrf validate {plan_obj.plan_id}",
                    f"Create backup: rmrf stage {plan_obj.plan_id}",
                ],
                additional_info={
                    "Plan ID": plan_obj.plan_id,
                    "Environment": plan_obj.environment,
                    "Protection Level": plan_obj.protection_level,
                    "Files": str(plan_obj.file_count),
                    "Total Size": format_bytes(plan_obj.total_bytes),
                    **(
                        {
                            "Risk": f"{plan_obj.risk_score.level.value} (score: {plan_obj.risk_score.score})"
                        }
                        if plan_obj.risk_score
                        else {}
                    ),
                },
            )

    except (PlanGeneratorError, EnvironmentError) as e:
        log_error(str(e))
        sys.exit(1)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        sys.exit(1)


@click.command(
    epilog="""
Examples:
  rmrf show plan-20250107-120000-abc123    # Show plan by ID
  rmrf show plan.json                      # Show plan from file
  rmrf show plan.json --json-output        # Output as JSON
"""
)
@click.argument("plan_id_or_file")
@click.pass_context
def show(ctx: click.Context, plan_id_or_file: str) -> None:
    """
    Display a deletion plan summary.

    Accepts either a plan ID (from the plan store) or a path to a plan JSON file.

    \b
    Examples:
      rmrf show plan-20250107-120000-abc123
      rmrf show plan.json
      rmrf show plan.json --json-output
    """
    json_output = ctx.obj["json_output"]

    try:
        # Load plan
        plan_obj = load_plan(plan_id_or_file)

        if json_output:
            # Output as JSON
            click.echo(plan_obj.model_dump_json(indent=2))
        else:
            # Human-readable output
            click.echo("═══════════════════════════════════════════════════════════")
            click.echo(f"  Deletion Plan: {plan_obj.plan_id}")
            click.echo("═══════════════════════════════════════════════════════════")
            click.echo("")

            # Plan details
            click.echo(f"Environment:       {plan_obj.environment}")
            click.echo(f"Protection Level:  {plan_obj.protection_level}")
            click.echo(f"Created:           {plan_obj.created_at.isoformat()}")

            if plan_obj.expires_at:
                status = "EXPIRED" if plan_obj.is_expired() else "Valid"
                click.echo(f"Expires:           {plan_obj.expires_at.isoformat()} [{status}]")

            click.echo("")

            # Targets
            click.echo("Targets:")
            for target in plan_obj.targets:
                click.echo(f"  • {target}")
            click.echo("")

            # Statistics
            click.echo(f"Files to delete:   {plan_obj.file_count:,}")
            click.echo(f"Total size:        {format_bytes(plan_obj.total_bytes)}")

            # Risk assessment
            if plan_obj.risk_score:
                risk_color = get_risk_color(plan_obj.risk_score.level.value)
                click.secho(
                    f"\nRisk Level:        {plan_obj.risk_score.level.value.upper()}", fg=risk_color
                )
                click.echo(f"Risk Score:        {plan_obj.risk_score.score}/100")

                if plan_obj.risk_score.reasons:
                    click.echo("\nRisk Factors:")
                    for reason in plan_obj.risk_score.reasons:
                        click.echo(f"  • {reason}")

            # Status
            click.echo("")
            if plan_obj.validated:
                click.secho("Status:            ✓ VALIDATED", fg="green")
                if plan_obj.validated_at:
                    click.echo(f"Validated at:      {plan_obj.validated_at.isoformat()}")
            else:
                click.secho("Status:            Not validated", fg="yellow")

            # Lock information
            if plan_obj.lock_id:
                click.echo("")
                click.secho("Lock:              ✓ LOCKED", fg="cyan")
                click.echo(f"Lock ID:           {plan_obj.lock_id}")

                # Try to get lock details
                try:
                    lock_manager = LockManager()
                    lock_info = lock_manager.get_lock_info(Path(plan_obj.targets[0]))
                    if lock_info:
                        try:
                            lock_owner = pwd.getpwuid(lock_info.locked_by_uid).pw_name
                        except KeyError:
                            lock_owner = f"UID-{lock_info.locked_by_uid}"
                        click.echo(
                            f"Locked by:         {lock_owner} (UID {lock_info.locked_by_uid})"
                        )
                        click.echo(f"Locked at:         {lock_info.locked_at.isoformat()}")
                except Exception:
                    pass

            # Approval information
            if plan_obj.created_by_uid is not None:
                try:
                    creator_name = pwd.getpwuid(plan_obj.created_by_uid).pw_name
                except KeyError:
                    creator_name = f"UID-{plan_obj.created_by_uid}"
                click.echo("")
                click.echo(f"Created by:        {creator_name} (UID {plan_obj.created_by_uid})")

            if plan_obj.requires_approval:
                click.echo("")
                if plan_obj.approved:
                    click.secho("Approval:          ✓ APPROVED", fg="green")
                    if plan_obj.approved_by_uid is not None:
                        try:
                            approver_name = pwd.getpwuid(plan_obj.approved_by_uid).pw_name
                        except KeyError:
                            approver_name = f"UID-{plan_obj.approved_by_uid}"
                        click.echo(
                            f"Approved by:       {approver_name} (UID {plan_obj.approved_by_uid})"
                        )
                    if plan_obj.approved_at:
                        click.echo(f"Approved at:       {plan_obj.approved_at.isoformat()}")
                else:
                    click.secho("Approval:          ⚠ PENDING", fg="yellow")
                    click.echo("Action required:   rmrf approve <plan-id>")

            if plan_obj.dry_run:
                click.secho("\nMode:              DRY-RUN (no actual deletion)", fg="blue")

            # User context
            if plan_obj.user:
                click.echo("")
                click.echo(f"User:              {plan_obj.user.id}")
                if plan_obj.user.role:
                    click.echo(f"Role:              {plan_obj.user.role}")

            # Scenario
            if plan_obj.scenario:
                click.echo("")
                click.echo(f"Scenario:          {plan_obj.scenario}")

            # Next steps section
            click.echo("")
            click.echo("═══════════════════════════════════════════════════════════")
            click.secho("Next steps:", bold=True)
            if not plan_obj.validated:
                click.echo("1. Validate against policy: rmrf validate " + plan_obj.plan_id)
                click.echo("2. Create backup: rmrf stage " + plan_obj.plan_id)
                click.echo("3. Execute deletion: rmrf apply " + plan_obj.plan_id)
            elif not plan_obj.backup_path:
                click.echo("1. Create backup: rmrf stage " + plan_obj.plan_id)
                click.echo("2. Execute deletion: rmrf apply " + plan_obj.plan_id)
            else:
                click.echo("1. Execute deletion: rmrf apply " + plan_obj.plan_id)
                click.echo("2. Monitor status: rmrf status --plan-id " + plan_obj.plan_id)
            click.echo("")

    except json.JSONDecodeError as e:
        log_error(f"Invalid JSON in plan file: {e}")
        sys.exit(1)
    except Exception as e:
        log_error(f"Error reading plan: {e}")
        sys.exit(1)

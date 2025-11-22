"""
Execution CLI commands.

Provides commands for executing validated deletion plans.
"""

import json
import sys
from pathlib import Path

import click

from rmrf.audit import AuditEmitter
from rmrf.engine import DeletionEngine, DeletionError
from rmrf.protection import ProtectionLevelRegistry
from rmrf.store import PlanStore

from ..output import format_bytes, log_error, log_info, print_structured_output
from ..utils import load_plan


@click.command(
    epilog="""
Examples:
  rmrf apply plan-20250107-120000-abc123              # Execute validated plan
  rmrf apply plan.json                                # Execute from file
  rmrf apply plan.json --dry-run                      # Simulate execution
  rmrf apply plan.json --skip-confirmation            # No prompts

Safety checks:
  - Plan must be validated (or use --skip-validation)
  - Backup required if protection level mandates it
  - Confirmation prompt shown before actual deletion
  - Complete audit trail recorded for all operations
"""
)
@click.argument("plan_id_or_file")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Simulate deletion without actually deleting files",
)
@click.option(
    "--user-id",
    help="User ID for audit trail",
)
@click.option(
    "--audit-dir",
    type=click.Path(),
    help="Audit directory (default: /var/lib/rmrf/audit)",
)
@click.option(
    "--skip-confirmation",
    is_flag=True,
    help="Skip confirmation prompts",
)
@click.pass_context
def apply(
    ctx: click.Context,
    plan_id_or_file: str,
    dry_run: bool,
    user_id: str | None,
    audit_dir: str | None,
    skip_confirmation: bool,
) -> None:
    """
    Execute a validated deletion plan.

    Accepts either a plan ID (from the plan store) or a path to a plan JSON file.
    Applies the deletion plan after all safety checks pass.
    Requires plan to be validated and backed up (if required by protection level).

    \b
    Examples:
      rmrf apply plan-20250107-120000-abc123
      rmrf apply plan.json
      rmrf apply plan.json --dry-run
      rmrf apply plan.json --user-id user123
    """
    json_output = ctx.obj["json_output"]

    try:
        # Load plan
        plan_obj = load_plan(plan_id_or_file)

        # Validate workflow order
        can_proceed, error_msg = plan_obj.can_apply()
        if not can_proceed:
            log_error(f"Cannot apply plan: {error_msg}")
            sys.exit(1)

        if not json_output:
            log_info(f"Loading plan: {plan_obj.plan_id}")

        # Get protection level
        registry = ProtectionLevelRegistry(load_defaults=True)
        protection_level = registry.require(plan_obj.protection_level)

        # Confirmation prompt for non-dry-run
        if not dry_run and not skip_confirmation:
            click.echo(f"\nYou are about to delete {plan_obj.file_count} file(s)", err=True)
            click.echo(f"Total size: {format_bytes(plan_obj.total_bytes)}", err=True)
            click.echo(f"Environment: {plan_obj.environment}", err=True)
            click.echo(f"Protection level: {plan_obj.protection_level}", err=True)

            if plan_obj.risk_score:
                click.echo(f"Risk level: {plan_obj.risk_score.level.value.upper()}", err=True)

            click.echo("", err=True)

            if not click.confirm("Do you want to proceed?"):
                log_info("Operation canceled by user")
                sys.exit(1)

        # Create audit emitter
        auditor = AuditEmitter(audit_dir=Path(audit_dir) if audit_dir else None)

        # Execute deletion
        if not json_output:
            mode_str = " (DRY-RUN)" if dry_run else ""
            log_info(f"Executing deletion{mode_str}...")

        engine = DeletionEngine(auditor=auditor, require_validation=False)
        result = engine.execute(plan_obj, protection_level, dry_run=dry_run, user_id=user_id)

        # Mark plan as applied in store (if not dry-run)
        if not dry_run and result.success:
            try:
                store = PlanStore(auto_create=False)
                if store.exists(plan_obj.plan_id):
                    store.mark_applied(plan_obj.plan_id)
                    if not json_output:
                        log_info("Plan marked as applied in store")
            except Exception:
                # Store update is best-effort, don't fail apply if it fails
                pass

        # Output result
        if json_output:
            output = {
                "audit_id": result.audit_id,
                "plan_id": result.plan_id,
                "deleted_count": result.deleted_count,
                "failed_count": result.failed_count,
                "success": result.success,
                "dry_run": result.dry_run,
            }
            if result.errors:
                output["errors"] = [{"path": str(p), "error": e} for p, e in result.errors]
            click.echo(json.dumps(output, indent=2))
        else:
            # Structured human-readable output
            scenario_name = plan_obj.scenario or f"plan {plan_obj.plan_id}"

            if result.success:
                dry_run_note = " (simulated in dry-run mode)" if result.dry_run else ""
                print_structured_output(
                    verdict="SUCCESS",
                    scenario=scenario_name,
                    summary=f"deletion executed{dry_run_note}",
                    what_happened=f"Successfully deleted {result.deleted_count} files from plan {plan_obj.plan_id} "
                    f"in {plan_obj.environment} environment. "
                    f"Operation completed with no errors{dry_run_note}. "
                    f"Full audit trail recorded under audit ID {result.audit_id}.",
                    why_it_matters="Successful deletion confirms that safety checks passed and files were removed as planned. "
                    "Complete audit trail enables compliance review and provides evidence of safe operations. "
                    + (
                        "This was a simulation - no actual files were deleted."
                        if result.dry_run
                        else "Rollback is available via backup manifest if reversal is needed."
                    ),
                    next_steps=[
                        f"Review audit trail: rmrf status {result.audit_id}",
                        "Verify deletion completed as expected",
                    ]
                    + (
                        []
                        if result.dry_run
                        else ["Rollback if needed: rmrf rollback <manifest-file>"]
                    ),
                    additional_info={
                        "Audit ID": result.audit_id,
                        "Plan ID": result.plan_id,
                        "Files Deleted": str(result.deleted_count),
                        "Environment": plan_obj.environment,
                        **({"Mode": "DRY-RUN (no actual deletion)"} if result.dry_run else {}),
                    },
                    audit_id=result.audit_id,
                )
            else:
                # Format error list
                error_list = "\n  • ".join(
                    [f"{path}: {error}" for path, error in result.errors[:5]]
                )
                if len(result.errors) > 5:
                    error_list += f"\n  • ... and {len(result.errors) - 5} more errors"

                print_structured_output(
                    verdict="ERROR",
                    scenario=scenario_name,
                    summary=f"deletion completed with {result.failed_count} error(s)",
                    what_happened=f"Attempted to delete files from plan {plan_obj.plan_id}. "
                    f"Successfully deleted {result.deleted_count} files but encountered {result.failed_count} failures. "
                    f"Partial deletion occurred - some files remain. Audit trail recorded under {result.audit_id}.",
                    why_it_matters="Partial deletion indicates potential issues with file permissions, locks, or system state. "
                    "Failed files remain on disk and may need manual intervention. "
                    "Review errors to determine if rollback or cleanup is needed.",
                    next_steps=[
                        f"Review detailed errors in audit trail: rmrf status {result.audit_id}",
                        "Check file permissions and locks on failed paths",
                        "Consider rollback: rmrf rollback <manifest-file>",
                        "Fix issues and retry with a new plan if needed",
                    ],
                    additional_info={
                        "Audit ID": result.audit_id,
                        "Plan ID": result.plan_id,
                        "Files Deleted": str(result.deleted_count),
                        "Files Failed": str(result.failed_count),
                        "Sample Errors": f"\n  • {error_list}",
                    },
                    audit_id=result.audit_id,
                )
                sys.exit(1)

    except DeletionError as e:
        log_error(f"Deletion failed: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        log_error(f"Invalid JSON in plan file: {e}")
        sys.exit(1)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        sys.exit(1)

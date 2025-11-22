"""
Closeout command - Clean up backups and close plans.

Removes backups and marks plans as closed after successful deletion.
"""

import shutil
from pathlib import Path

import click

from rmrf.audit import AuditEmitter
from rmrf.models import AuditEvent
from rmrf.store import PlanStore

from ..output import log_error, log_info, print_structured_output
from ..utils import load_plan


@click.command(
    epilog="""
Examples:
  rmrf closeout plan-20250108-120000-abc123

  # Closeout and remove backup
  rmrf closeout plan-20250108-120000-abc123 --remove-backup

  # Force closeout even if not applied
  rmrf closeout plan-20250108-120000-abc123 --force

Safety:
  - Only plans that have been applied can be closed out (use --force to override)
  - Backups are kept by default; use --remove-backup to delete
  - For automatic cleanup, use 'rmrf cleanup' with retention policy
  - Audit events are emitted for all closeout operations
"""
)
@click.argument("plan_id")
@click.option(
    "--backup-root",
    type=click.Path(exists=True),
    help="Custom backup root directory",
)
@click.option(
    "--remove-backup",
    is_flag=True,
    help="Remove backup files to reclaim disk space (default: keep backup)",
)
@click.option(
    "--force",
    is_flag=True,
    help="Force closeout even if plan was not applied",
)
@click.option(
    "--comment",
    "-c",
    help="Operator comment for closeout (will prompt if not provided)",
)
@click.pass_context
def closeout(
    ctx: click.Context,
    plan_id: str,
    backup_root: str | None,
    remove_backup: bool,
    force: bool,
    comment: str | None,
) -> None:
    """
    Close out a plan and mark deletion complete.

    After confirming a deletion was successful, use this command to:
    - Mark the plan as closed out
    - Optionally remove backup files with --remove-backup
    - Keep backup by default for safety (use cleanup for retention policy)

    \b
    Examples:
      rmrf closeout plan-20250108-120000-abc123              # Keeps backup
      rmrf closeout plan-20250108-120000-abc123 --remove-backup  # Removes backup
    """
    json_output = ctx.obj.get("json_output", False)

    try:
        # Load plan
        plan = load_plan(plan_id)

        # Validate workflow order (unless force)
        if not force:
            can_proceed, error_msg = plan.can_closeout()
            if not can_proceed:
                log_error(f"Cannot closeout plan: {error_msg}")
                raise click.Abort()

        # Prompt for comment if not provided
        if not comment:
            if json_output:
                log_error("Comment required in JSON mode. Use --comment flag.")
                raise click.Abort()

            click.echo("")
            click.secho("Closeout Comment Required", bold=True, fg="cyan")
            click.echo("")
            click.echo("Please provide a brief comment about this closeout:")
            click.echo("  - Did everything go as expected?")
            click.echo("  - Any final observations?")
            click.echo("")

            comment = click.prompt("Closeout comment", type=str)

        if not comment or not comment.strip():
            log_error("Comment cannot be empty")
            raise click.Abort()

        # Check if backup exists
        backup_path = None
        if plan.backup_path:
            backup_path = Path(plan.backup_path)
        elif backup_root:
            # Construct backup path
            backup_path = Path(backup_root) / plan.environment / plan.plan_id
        else:
            # Use default backup root
            backup_path = Path("/var/lib/rmrf/backups") / plan.environment / plan.plan_id

        backup_existed = backup_path and backup_path.exists()
        backup_removed = False

        # Remove backup only if explicitly requested
        if remove_backup and backup_existed:
            try:
                shutil.rmtree(backup_path)
                backup_removed = True
                log_info(f"Removed backup at {backup_path}")
            except Exception as e:
                log_error(f"Failed to remove backup: {e}")
                if not force:
                    raise

        # Mark plan as closed out in store
        try:
            from datetime import datetime, timezone

            store = PlanStore(auto_create=False)
            if store.exists(plan.plan_id):
                # Load, update, and save plan
                plan.closeout_at = datetime.now(timezone.utc)
                plan.closeout_comment = comment.strip()
                store.save(plan)
                log_info(f"Marked plan {plan.plan_id} as closed out")
        except Exception as e:
            log_error(f"Could not update plan storage: {e}")
            # Don't fail the command if store is unavailable

        # Emit audit event
        try:
            auditor = AuditEmitter()
            event = AuditEvent.for_closeout(
                plan=plan,
                backup_removed=backup_removed,
                keep_backup=not remove_backup,
            )
            auditor.emit(event)
        except Exception as e:
            log_error(f"Failed to emit audit event: {e}")

        # Output results
        if json_output:
            import json

            result = {
                "plan_id": plan.plan_id,
                "closed_out": True,
                "backup_removed": backup_removed,
                "backup_kept": not remove_backup or not backup_existed,
            }
            click.echo(json.dumps(result, indent=2))
        else:
            print_structured_output(
                verdict="SUCCESS",
                scenario="plan closeout",
                summary="plan closed out" + (" and backup removed" if backup_removed else ""),
                what_happened=f"Plan {plan.plan_id} has been closed out. "
                + (
                    f"Backup removed from {backup_path}."
                    if backup_removed
                    else "Backup retained."
                    if backup_existed
                    else "No backup found."
                ),
                why_it_matters="Closing out marks the deletion lifecycle as complete. "
                "Backups are kept by default for safety; use --remove-backup to reclaim "
                "disk space or rely on cleanup with retention policy. "
                "The plan record remains in storage for audit purposes.",
                next_steps=[
                    "The deletion is now complete",
                    "Backup cannot be restored"
                    if backup_removed
                    else "Backup is still available for rollback",
                    f"View audit trail: rmrf status {plan.plan_id}",
                ],
            )

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"Closeout failed: {e}")
        raise click.Abort() from e

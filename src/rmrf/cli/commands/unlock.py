"""
Unlock CLI command.

Provides command for releasing directory locks associated with a plan.
"""

import json
import sys

import click

from rmrf.locking import LockManager
from rmrf.models import AuditEvent, EventPhase

from ..output import log_error, log_info, log_success
from ..utils import load_plan


@click.command(
    epilog="""
Examples:
  rmrf unlock plan-20250108-120000-abc123

Releases all directory locks held by a plan. Useful for cleanup after
failed operations or when manually managing plan lifecycle.
"""
)
@click.argument("plan_id_or_file")
@click.pass_context
def unlock(
    ctx: click.Context,
    plan_id_or_file: str,
) -> None:
    """
    Release directory locks for a plan.

    Removes all locks associated with the specified plan, allowing
    other operations to access the locked directories.

    This is typically used for cleanup after failed operations or
    when manually managing the plan lifecycle.

    \b
    Examples:
      rmrf unlock plan-20250108-120000-abc123
      rmrf unlock plan.json
    """
    json_output = ctx.obj.get("json_output", False)

    try:
        # Load plan to get plan_id
        plan = load_plan(plan_id_or_file)
        plan_id = plan.plan_id

        # Release locks
        lock_manager = LockManager()
        lock_manager.release_lock(plan_id)

        # Update plan to clear lock_id if stored
        try:
            from rmrf.store import PlanStore

            store = PlanStore(auto_create=False)
            if store.exists(plan_id):
                stored_plan = store.load(plan_id)
                if stored_plan.lock_id:
                    stored_plan.lock_id = None
                    store.save(stored_plan)
        except Exception:
            # Best effort - don't fail if store unavailable
            pass

        # Emit audit event (best effort)
        try:
            from datetime import datetime, timezone
            from uuid import uuid4

            from rmrf.audit import AuditEmitter

            auditor = AuditEmitter()
            timestamp = datetime.now(timezone.utc)
            event = AuditEvent(
                event_id=f"evt-{timestamp.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}",
                phase=EventPhase.LOCK_RELEASED,
                environment=plan.environment,
                protection_level=plan.protection_level,
                plan_id=plan_id,
                message=f"Locks released for plan {plan_id}",
            )
            auditor.emit(event)
        except Exception:
            pass

        # Output result
        if json_output:
            result = {
                "plan_id": plan_id,
                "unlocked": True,
                "message": f"Locks released for plan {plan_id}",
            }
            click.echo(json.dumps(result, indent=2))
        else:
            log_success(f"Locks released for plan {plan_id}")
            log_info("Directories are now available for other operations")

    except Exception as e:
        if json_output:
            error_result = {
                "error": str(e),
                "unlocked": False,
            }
            click.echo(json.dumps(error_result, indent=2))
        else:
            log_error(f"Failed to release locks: {e}")
        sys.exit(1)

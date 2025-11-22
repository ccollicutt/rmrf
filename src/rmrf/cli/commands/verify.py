"""
Verification CLI command.

Provides command for verifying that deletions were successful.
"""

import sys
from pathlib import Path

import click

from rmrf.store import PlanStore

from ..output import log_error, log_info, log_success, print_structured_output
from ..utils import load_plan


@click.command(
    epilog="""
Examples:
  rmrf verify plan-20250108-120000-abc123

Verification checks that all target paths have been deleted.
Can be run multiple times to re-verify.
"""
)
@click.argument("plan_id")
@click.pass_context
def verify(
    ctx: click.Context,
    plan_id: str,
) -> None:
    """
    Verify that deletion was successful.

    Checks that all target paths specified in the plan have been deleted.
    Updates the plan with verification status and timestamp.

    \b
    Examples:
      rmrf verify plan-20250108-120000-abc123
    """
    json_output = ctx.obj.get("json_output", False)

    try:
        # Load plan
        plan = load_plan(plan_id)

        # Check if plan was applied
        if not plan.executed_at:
            log_error("Plan has not been applied yet. Cannot verify unapplied plan.")
            sys.exit(1)

        if not json_output:
            log_info(f"Verifying deletion for plan: {plan.plan_id}")
            log_info(f"Checking {len(plan.targets)} target path(s)...")

        # Check each target
        still_exists = []
        for target in plan.targets:
            target_path = Path(target)
            if target_path.exists():
                still_exists.append(target)

        # Update plan with verification results
        from datetime import datetime, timezone

        plan.verification_count += 1
        plan.last_verified_at = datetime.now(timezone.utc)
        plan.verification_passed = len(still_exists) == 0

        # Save updated plan
        try:
            store = PlanStore(auto_create=False)
            if store.exists(plan.plan_id):
                store.save(plan)
                if not json_output:
                    log_info("Plan updated with verification results")
        except Exception:
            # Store update is best-effort
            pass

        # Output results
        if json_output:
            import json

            result = {
                "plan_id": plan.plan_id,
                "verification_passed": plan.verification_passed,
                "verification_count": plan.verification_count,
                "still_exists": still_exists,
            }
            click.echo(json.dumps(result, indent=2))
        else:
            if plan.verification_passed:
                print_structured_output(
                    verdict="SUCCESS",
                    scenario=f"deletion verification for {plan.plan_id}",
                    summary="all targets deleted",
                    what_happened=f"Verified deletion of {len(plan.targets)} target path(s) from plan {plan.plan_id}. "
                    f"All targets have been successfully removed from the filesystem. "
                    f"This is verification #{plan.verification_count}.",
                    why_it_matters="Post-deletion verification confirms that the deletion operation achieved its intended effect. "
                    "This provides assurance that the safety-critical operation completed successfully and no targets remain.",
                    next_steps=[
                        f"Close out plan: rmrf closeout {plan.plan_id}",
                        f"Add lessons learned: rmrf learn {plan.plan_id}",
                        f"Review audit trail: rmrf status {plan.plan_id}",
                    ],
                    additional_info={
                        "Plan ID": plan.plan_id,
                        "Targets Checked": str(len(plan.targets)),
                        "Verification Count": str(plan.verification_count),
                        "Status": "All targets deleted",
                    },
                )
                log_success("Verification passed!")
            else:
                print_structured_output(
                    verdict="ERROR",
                    scenario=f"deletion verification for {plan.plan_id}",
                    summary=f"{len(still_exists)} target(s) still exist",
                    what_happened=f"Verified deletion of {len(plan.targets)} target path(s) from plan {plan.plan_id}. "
                    f"{len(still_exists)} target(s) still exist on the filesystem after deletion. "
                    f"This indicates the deletion operation was incomplete.",
                    why_it_matters="Failed verification indicates the deletion did not complete as expected. "
                    "Files may have been locked, permissions issues occurred, or the deletion failed partway through. "
                    "This requires investigation to determine why targets remain.",
                    next_steps=[
                        "Review which targets still exist (listed below)",
                        f"Check audit trail for errors: rmrf status {plan.plan_id}",
                        "Investigate why deletion failed",
                        "Consider rollback: rmrf rollback <manifest-file>",
                        "Or retry deletion manually",
                    ],
                    additional_info={
                        "Plan ID": plan.plan_id,
                        "Targets Checked": str(len(plan.targets)),
                        "Still Exist": str(len(still_exists)),
                        "Paths": "\n  ".join(still_exists),
                    },
                )
                sys.exit(1)

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"Verification failed: {e}")
        sys.exit(1)

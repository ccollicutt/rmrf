"""
Helper functions for the interactive shell.

Extracted from shell.py to keep file size under 500 lines.
"""

from pathlib import Path

import click

from rmrf.protection import ProtectionLevelRegistry

from ..output import log_error


def print_protection_info(environment: str) -> None:
    """Print protection level information for current environment."""
    try:
        registry = ProtectionLevelRegistry(load_defaults=True)

        # Get protection level for this environment
        level = registry.get_by_environment(environment)

        if level is None:
            # Fallback to safe-local
            level = registry.get("safe-local")
            if level is None:
                raise RuntimeError("Could not load default protection level 'safe-local'")
            click.secho(f"Protection Level: {level.name} (default)", bold=True, err=True)
        else:
            click.secho(f"Protection Level: {level.name}", bold=True, err=True)

        click.echo(f"  {level.description}", err=True)

        # Show key constraints
        constraints = []
        if level.max_files:
            constraints.append(f"max {level.max_files:,} files")
        if level.max_bytes:
            gb = level.max_bytes / (1024**3)
            constraints.append(f"max {gb:.1f} GB")
        if level.require_backup:
            constraints.append("backup required")
        if level.require_confirmation:
            constraints.append("confirmation required")
        if level.allow_simulation_only:
            constraints.append("DRY-RUN ONLY")

        if constraints:
            click.echo(f"  Constraints: {', '.join(constraints)}", err=True)

        click.echo("", err=True)

        # Show all available levels
        all_levels = registry.list_all()
        level_names = [level.name for level in all_levels]
        click.echo(f"Available protection levels: {', '.join(level_names)}", err=True)

    except Exception as e:
        log_error(f"Failed to load protection levels: {e}")

    click.echo("", err=True)


def get_next_stage(current_stage: str) -> str | None:
    """
    Get the next stage in the workflow.

    Args:
        current_stage: Current workflow stage

    Returns:
        Next stage name, or None if complete/terminal
    """
    workflow = {
        "planned": "validated",
        "validated": "staged",
        "staged": "applied",
        "applied": "verified",
        "verified": "closed",
        "closed": None,  # Terminal
        "rollback": None,  # Terminal
        "near-miss": None,  # Terminal
        "denied": None,  # Terminal - policy rejected
        "approval-required": None,  # Terminal - needs approval before proceeding
        "failed": None,  # Terminal
    }
    return workflow.get(current_stage)


def print_session_info(session_state: dict) -> None:
    """Print current session state information."""
    click.echo("")
    click.secho("Session State", bold=True, err=True)
    click.echo("", err=True)

    if session_state["plan_id"]:
        click.echo(f"  Active Plan: {session_state['plan_id']}", err=True)
        click.echo(f"  Workflow Stage: {session_state['stage'] or 'planned'}", err=True)

        # Show workflow progress
        current_stage = session_state["stage"] or "planned"

        # Define workflow stages
        normal_stages = ["planned", "validated", "staged", "applied", "verified", "closed"]
        terminal_stages = ["rollback", "near-miss", "denied", "approval-required", "failed"]

        click.echo("", err=True)
        click.echo("  Workflow Progress:", err=True)

        if current_stage in terminal_stages:
            # Show terminal state
            if current_stage in ["rollback", "failed", "denied"]:
                color = "red"
            elif current_stage == "approval-required":
                color = "yellow"
            else:
                color = "yellow"
            click.secho(f"    ! {current_stage}", fg=color, bold=True, err=True)
        else:
            # Show normal workflow
            current_idx = (
                normal_stages.index(current_stage) if current_stage in normal_stages else 0
            )

            for idx, stage in enumerate(normal_stages):
                if idx < current_idx:
                    click.secho(f"    ✓ {stage}", fg="green", err=True)
                elif idx == current_idx:
                    click.secho(f"    → {stage} (current)", fg="yellow", bold=True, err=True)
                else:
                    click.echo(f"    ○ {stage}", err=True)
    else:
        click.echo("  No active plan", err=True)
        click.echo(
            "  Use 'plan' to create one or 'set-plan <plan-id>' to track existing plan", err=True
        )

    click.echo("", err=True)


def update_session_state(session_state: dict, args: list) -> None:
    """Update session state based on executed command."""
    if not args:
        return

    command = args[0]

    # Auto-track plan creation
    if command == "plan" and len(args) > 1:
        # Plan just created - try to get the most recent plan from store
        try:
            from rmrf.store import PlanStore

            store = PlanStore(auto_create=False)
            plans = store.list()  # Returns plans sorted by created_at, newest first
            if plans:
                # First plan is the most recent
                latest_plan = plans[0]
                session_state["plan_id"] = latest_plan.plan_id
                session_state["stage"] = "planned"
                click.secho(
                    f"→ Tracking plan: {latest_plan.plan_id} [planned]",
                    fg="cyan",
                    dim=True,
                    err=True,
                )
            else:
                # No plans found in store
                click.secho(
                    "→ Plan created but not auto-tracked (use 'set-plan <id>')",
                    fg="yellow",
                    dim=True,
                    err=True,
                )
        except Exception as e:
            # Store not available, user can manually track
            click.secho(
                f"→ Could not auto-track plan: {e} (use 'set-plan <id>')",
                fg="yellow",
                dim=True,
                err=True,
            )

    # Auto-track plan operations
    elif command == "validate" and len(args) > 1:
        plan_id = extract_plan_id(args[1])
        if plan_id:
            # Load plan from store to get actual workflow stage
            # (could be validated or denied depending on policy verdict)
            try:
                from rmrf.store import PlanStore

                store = PlanStore(auto_create=False)
                plan = store.load(plan_id)
                workflow_stage = plan.get_workflow_stage()
                session_state["plan_id"] = plan_id
                session_state["stage"] = workflow_stage

                # Show appropriate message based on stage
                if workflow_stage == "denied":
                    click.secho(f"→ Plan {plan_id} denied by policy", fg="red", bold=True, err=True)
                elif workflow_stage == "approval-required":
                    click.secho(
                        f"→ Plan {plan_id} requires approval", fg="yellow", bold=True, err=True
                    )
                else:
                    click.secho(
                        f"→ Tracking plan: {plan_id} [{workflow_stage}]",
                        fg="cyan",
                        dim=True,
                        err=True,
                    )
            except Exception:
                # Don't update session state if we can't verify the plan exists
                # (command may have failed because plan doesn't exist)
                pass

    elif command == "stage" and len(args) > 1:
        plan_id = extract_plan_id(args[1])
        if plan_id:
            # Load actual plan state from store (command may have failed)
            try:
                from rmrf.store import PlanStore

                store = PlanStore(auto_create=False)
                plan = store.load(plan_id)
                workflow_stage = plan.get_workflow_stage()
                session_state["plan_id"] = plan_id
                session_state["stage"] = workflow_stage

                # Show appropriate message
                if workflow_stage == "staged":
                    click.secho(
                        f"→ Tracking plan: {plan_id} [staged]", fg="cyan", dim=True, err=True
                    )
                elif workflow_stage == "denied":
                    click.secho(f"→ Plan {plan_id} still denied", fg="red", bold=True, err=True)
            except Exception:
                # Fallback - don't update state if we can't verify
                pass

    elif command == "apply" and len(args) > 1:
        plan_id = extract_plan_id(args[1])
        if plan_id:
            # Load actual plan state from store (command may have failed)
            try:
                from rmrf.store import PlanStore

                store = PlanStore(auto_create=False)
                plan = store.load(plan_id)
                workflow_stage = plan.get_workflow_stage()
                session_state["plan_id"] = plan_id
                session_state["stage"] = workflow_stage

                # Show appropriate message
                if workflow_stage == "applied":
                    click.secho(
                        f"→ Tracking plan: {plan_id} [applied]", fg="cyan", dim=True, err=True
                    )
                    # Auto-verify after apply (unless it was a dry-run)
                    if "--dry-run" not in args:
                        click.echo("", err=True)
                        click.secho(
                            "→ Run 'verify' to check deletion success",
                            fg="cyan",
                            dim=True,
                            err=True,
                        )
                elif workflow_stage == "denied":
                    click.secho(f"→ Plan {plan_id} still denied", fg="red", bold=True, err=True)
            except Exception:
                # Fallback - don't update state if we can't verify
                pass

    elif command == "verify" and len(args) > 1:
        plan_id = extract_plan_id(args[1])
        if plan_id:
            # Load actual plan state from store
            try:
                from rmrf.store import PlanStore

                store = PlanStore(auto_create=False)
                plan = store.load(plan_id)
                workflow_stage = plan.get_workflow_stage()
                session_state["plan_id"] = plan_id
                session_state["stage"] = workflow_stage

                if workflow_stage == "verified":
                    click.secho(
                        f"→ Tracking plan: {plan_id} [verified]", fg="cyan", dim=True, err=True
                    )
            except Exception:
                pass

    elif command == "show" and len(args) > 1:
        # Viewing a plan - load actual state from store
        plan_id = extract_plan_id(args[1])
        if plan_id:
            try:
                from rmrf.store import PlanStore

                store = PlanStore(auto_create=False)
                plan = store.load(plan_id)
                workflow_stage = plan.get_workflow_stage()
                session_state["plan_id"] = plan_id
                session_state["stage"] = workflow_stage
                click.secho(
                    f"→ Tracking plan: {plan_id} [{workflow_stage}]", fg="cyan", dim=True, err=True
                )
            except Exception:
                pass

    elif command == "closeout" and len(args) > 1:
        plan_id = extract_plan_id(args[1])
        if plan_id:
            # Load actual plan state from store
            try:
                from rmrf.store import PlanStore

                store = PlanStore(auto_create=False)
                plan = store.load(plan_id)
                workflow_stage = plan.get_workflow_stage()
                session_state["plan_id"] = plan_id
                session_state["stage"] = workflow_stage

                if workflow_stage == "closed":
                    click.secho(f"→ Plan {plan_id} closed out", fg="green", dim=True, err=True)
            except Exception:
                pass

    elif command == "learn" and len(args) > 1:
        plan_id = extract_plan_id(args[1])
        if plan_id:
            click.secho(
                f"→ Lessons learned recorded for plan {plan_id}", fg="cyan", dim=True, err=True
            )

    elif command == "near-miss" and len(args) > 1:
        plan_id = extract_plan_id(args[1])
        if plan_id and session_state["plan_id"] == plan_id:
            # Plan abandoned
            session_state["stage"] = "near-miss"
            click.secho(f"→ Plan {plan_id} marked as near-miss", fg="yellow", dim=True, err=True)

    elif command == "mark-failed" and len(args) > 1:
        plan_id = extract_plan_id(args[1])
        if plan_id and session_state["plan_id"] == plan_id:
            # Plan failed
            session_state["stage"] = "failed"
            click.secho(f"→ Plan {plan_id} marked as failed", fg="red", dim=True, err=True)


def extract_plan_id(arg: str) -> str:
    """Extract plan ID from argument (could be plan ID or file path)."""
    # If it's a file path, extract just the filename
    if "/" in arg or arg.endswith(".json"):
        arg = Path(arg).stem

    # Check if it looks like a plan ID
    if arg.startswith("plan-"):
        return arg

    return arg


def print_help() -> None:
    """Print help for interactive shell."""
    click.echo("")
    click.secho("rmrf Interactive Shell - Available Commands", bold=True)
    click.echo("")

    click.secho("Core Workflow:", bold=True)
    click.echo("  plan <path>              Create deletion plan")
    click.echo("  show <plan-id>           Show plan details")
    click.echo("  list plans               List all plans")
    click.echo("  list plans --stage <s>   Filter by stage (use ! to exclude, e.g., !applied)")
    click.echo("  validate <plan-id>       Validate plan")
    click.echo("  stage <plan-id>          Stage plan (create backup)")
    click.echo("  apply <plan-id>          Execute deletion")
    click.echo("  verify <plan-id>         Verify deletion success")
    click.echo("  closeout <plan-id>       Close plan (removes backup, requires comment)")
    click.echo("  learn <plan-id>          Record lessons learned (post-completion)")
    click.echo("  rollback <manifest>      Restore from backup (requires comment)")
    click.echo("  near-miss <plan-id>      Mark abandoned plan (requires comment)")
    click.echo("  mark-failed <plan-id>    Mark plan as failed (requires comment)")
    click.echo("")

    click.secho("Status & Info:", bold=True)
    click.echo("  status <plan-id>         View audit trail")
    click.echo("  preflight                Check configuration")
    click.echo("  env                      Show environment")
    click.echo("  protection               Show protection level info")
    click.echo("  session                  Show active plan and workflow stage")
    click.echo("")

    click.secho("Maintenance:", bold=True)
    click.echo("  cleanup                  Remove old backups (uses retention policy)")
    click.echo("  cleanup --dry-run        Preview which backups would be removed")
    click.echo("  cleanup --all-environments  Clean backups for all environments")
    click.echo("")

    click.secho("Session Management:", bold=True)
    click.echo("  set-plan <plan-id>       Track an existing plan in session")
    click.echo("  clear-plan               Clear active plan from session")
    click.echo("  session                  Show session state and workflow progress")
    click.echo("")
    click.echo("  Note: Plans are automatically tracked as you work with them!")
    click.echo("  Tip: Use 'list plans' to see available plan IDs")
    click.echo("")

    click.secho("Shell Commands:", bold=True)
    click.echo("  help, ?                  Show this help")
    click.echo("  clear                    Clear screen")
    click.echo("  exit, quit, q            Exit shell")
    click.echo("  # comment                Lines starting with # are ignored")
    click.echo("")

    click.secho("Examples (Automatic Tracking):", bold=True)
    click.echo("  rmrf:dev[safe-local]")
    click.echo("  plan: (none)")
    click.echo("  > plan /tmp/old-logs --scenario 'cleanup'")
    click.echo("  → Tracking plan: plan-tmp-old-logs-20251108-abc123 [planned]")
    click.echo("")
    click.echo("  rmrf:dev[safe-local]")
    click.echo("  plan: plan-tmp-old-logs-20251108-abc123")
    click.echo("  > validate plan-tmp-old-logs-20251108-abc123")
    click.echo("  → Tracking plan: plan-tmp-old-logs-20251108-abc123 [validated]")
    click.echo("")
    click.echo("  rmrf:dev[safe-local]")
    click.echo("  plan: plan-tmp-old-logs-20251108-abc123")
    click.echo("  > stage plan-tmp-old-logs-20251108-abc123")
    click.echo("  → Tracking plan: plan-tmp-old-logs-20251108-abc123 [staged]")
    click.echo("")

    click.echo("Tips:")
    click.echo("  - Plans and workflow stages are tracked automatically!")
    click.echo("  - Press TAB to autocomplete commands and plan IDs")
    click.echo("  - Active plan ID is first in completion list")
    click.echo("  - Press Ctrl+C to cancel a running command")
    click.echo("")

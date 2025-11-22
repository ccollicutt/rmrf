"""
Interactive shell for rmrf.

Provides a REPL with persistent environment display.
"""

import shlex
import sys
from pathlib import Path

import click

from rmrf.environment import EnvironmentDetector

from ..output import log_error, log_info, print_environment_banner
from .shell_helpers import (
    get_next_stage,
    print_help,
    print_protection_info,
    print_session_info,
    update_session_state,
)


def _handle_exit_with_incomplete_plan(session_state: dict) -> None:
    """Check for incomplete plan on exit and prompt for near-miss if needed."""
    if not session_state["plan_id"]:
        return

    current_stage = session_state.get("stage")
    # Check if plan is incomplete (not in terminal state)
    if current_stage in ["closed", "rollback", "near-miss", "failed", None]:
        return

    click.echo("", err=True)
    click.secho(
        f"Warning: Active plan {session_state['plan_id']} is incomplete (stage: {current_stage})",
        fg="yellow",
        bold=True,
        err=True,
    )
    click.echo(
        "What to do? 1=Mark near-miss, 2=Delete plan, 3=Leave as-is [1]:", err=True, nl=False
    )
    choice = input(" ").strip() or "1"

    if choice == "1":
        # Mark as near-miss
        click.echo("Reason for abandoning: ", err=True, nl=False)
        comment = input().strip()

        if comment:
            try:
                from datetime import datetime, timezone

                from rmrf.store import PlanStore

                store = PlanStore(auto_create=False)
                plan = store.load(session_state["plan_id"])
                plan.near_miss = True
                plan.near_miss_at = datetime.now(timezone.utc)
                plan.near_miss_comment = comment
                store.save(plan)
                click.secho("✓ Plan marked as near-miss", fg="yellow", err=True)
            except Exception as e:
                click.secho(f"Warning: Could not mark: {e}", fg="red", err=True)

    elif choice == "2":
        # Delete plan
        try:
            from rmrf.store import PlanStore

            store = PlanStore(auto_create=False)
            store.delete(session_state["plan_id"])
            click.secho("✓ Plan deleted", fg="green", err=True)
        except Exception as e:
            click.secho(f"Warning: Could not delete: {e}", fg="red", err=True)


@click.command(
    epilog="""
Examples:
  rmrf shell                           # Enter interactive mode
  rmrf shell --environment prod        # Override environment

In shell mode (plans auto-tracked):
  rmrf:dev[safe-local]
  plan: (none)
  > plan /tmp/test
  → Tracking plan: plan-tmp-test-20251108-abc12345 [planned]

  rmrf:dev[safe-local]
  plan: plan-tmp-test-20251108-abc12345 | stage: planned
  > validate plan-tmp-test-20251108-abc12345
  → Tracking plan: plan-tmp-test-20251108-abc12345 [validated]

  rmrf:dev[safe-local]
  plan: plan-tmp-test-20251108-abc12345 | stage: validated
  > session
"""
)
@click.option(
    "--environment-override",
    "-e",
    help="Override environment detection",
)
@click.pass_context
def shell(ctx: click.Context, environment_override: str | None) -> None:
    """
    Enter interactive shell mode.

    Provides a REPL with persistent environment display and command history.
    The prompt shows current environment, protection level, and active plan/stage
    across multiple lines for easy reading. Plans are automatically tracked as
    you work through the workflow.

    \b
    Examples:
      rmrf shell

      rmrf:dev[safe-local]
      plan: (none)
      > plan /tmp/old-logs
      → Tracking plan: plan-tmp-old-logs-20251108-abc12345 [planned]

      rmrf:dev[safe-local]
      plan: plan-tmp-old-logs-20251108-abc12345 | stage: planned
      > validate plan-tmp-old-logs-20251108-abc12345
      → Tracking plan: plan-tmp-old-logs-20251108-abc12345 [validated]
    """
    from rmrf.models import Environment

    # Detect environment
    try:
        if environment_override:
            env = Environment(env=environment_override, signature=None)
        else:
            detector = EnvironmentDetector()
            env = detector.detect()
    except Exception as e:
        log_error(f"Failed to detect environment: {e}")
        sys.exit(1)

    # Print welcome
    click.clear()

    click.secho("Welcome to rmrf Interactive Shell", bold=True, err=True)
    click.echo("", err=True)

    # Environment-specific narrative
    env_name = env.env.upper()
    if env_name in ["PROD", "PRODUCTION"]:
        click.secho("You are operating in PRODUCTION.", fg="red", bold=True, err=True)
        click.echo("This is a live production environment. All deletions are permanent", err=True)
        click.echo("and can directly impact production systems and data. Stricter safety", err=True)
        click.echo("constraints are enforced, including mandatory backups, lower limits,", err=True)
        click.echo("and required confirmations. Exercise extreme caution.", err=True)
    elif env_name in ["STAGING", "STAGE", "STG"]:
        click.secho("You are operating in STAGING.", fg="yellow", bold=True, err=True)
        click.echo(
            "This is a pre-production staging environment. While not live production,", err=True
        )
        click.echo(
            "data may be shared with other teams and deletions can impact testing.", err=True
        )
        click.echo(
            "Moderate safety constraints apply. Use care when deleting shared data.", err=True
        )
    elif env_name in ["DEV", "DEVELOPMENT"]:
        click.secho("You are operating in DEVELOPMENT.", fg="green", bold=True, err=True)
        click.echo(
            "This is a development environment with relaxed constraints suitable for", err=True
        )
        click.echo(
            "local testing and experimentation. While safety features are still active,", err=True
        )
        click.echo("limits are higher to support rapid iteration.", err=True)
    else:
        click.secho(f"You are operating in {env_name}.", fg="blue", bold=True, err=True)
        click.echo("Environment-specific safety constraints will be applied based on", err=True)
        click.echo("the protection level configuration.", err=True)

    click.echo("", err=True)
    click.echo("Every deletion goes through a multi-stage workflow:", err=True)
    click.echo("  1. Plan - Scan targets and calculate risk", err=True)
    click.echo("  2. Validate - Check against protection policies", err=True)
    click.echo("  3. Backup - Create verified copies with checksums", err=True)
    click.echo("  4. Apply - Execute the deletion safely", err=True)
    click.echo("", err=True)
    click.echo("All operations in this shell are governed by the protection level", err=True)
    click.echo("for your current environment. The shell provides command history,", err=True)
    click.echo("intelligent tab completion, and persistent visibility into active", err=True)
    click.echo("constraints. Press TAB to autocomplete commands and plan IDs.", err=True)
    click.echo("", err=True)

    # Show protection level for this environment
    print_protection_info(env.env)

    click.secho("Ready to begin.", bold=True, err=True)
    click.echo("Type 'help' to see available commands or 'exit' to quit.", err=True)
    click.echo("", err=True)

    # Try to use readline for history/editing and tab completion
    try:
        import readline

        # Set up history
        histfile = Path.home() / ".rmrf_history"
        try:
            readline.read_history_file(histfile)
        except FileNotFoundError:
            pass

        import atexit

        atexit.register(readline.write_history_file, histfile)
        readline.set_history_length(1000)

        # Set up tab completion
        def completer(text: str, state: int) -> str | None:
            """Custom completer for rmrf shell - inserts active plan ID."""
            # Only return first match (state == 0)
            if state != 0:
                return None

            # Get available completions based on context
            line = readline.get_line_buffer()
            words = line.split()

            # If we're at the start or after whitespace, complete commands
            if not words or (len(words) == 1 and not line.endswith(" ")):
                commands = [
                    "plan",
                    "show",
                    "validate",
                    "stage",
                    "apply",
                    "verify",
                    "closeout",
                    "learn",
                    "near-miss",
                    "mark-failed",
                    "rollback",
                    "list",
                    "status",
                    "cleanup",
                    "preflight",
                    "env",
                    "protection",
                    "session",
                    "set-plan",
                    "clear-plan",
                    "help",
                    "clear",
                    "exit",
                ]
                matches = [cmd for cmd in commands if cmd.startswith(text)]
                return matches[0] if matches else None
            else:
                # For commands that need a plan ID, offer the active plan
                plan_id_commands = [
                    "show",
                    "validate",
                    "stage",
                    "apply",
                    "verify",
                    "closeout",
                    "learn",
                    "near-miss",
                    "mark-failed",
                ]
                if words[0] in plan_id_commands and session_state["plan_id"]:
                    plan_id = session_state["plan_id"]
                    if not text or plan_id.startswith(text):
                        return plan_id
                return None

        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")
        readline.set_completer_delims(" \t\n")  # Space/tab only (not dash)
    except ImportError:
        # readline not available (Windows)
        pass

    # Get protection level for prompt
    from rmrf.protection import ProtectionLevelRegistry

    try:
        registry = ProtectionLevelRegistry(load_defaults=True)
        protection_level = registry.get_by_environment(env.env)
        if protection_level is None:
            protection_level = registry.get("safe-local")
        protection_name = protection_level.name if protection_level else "unknown"
    except Exception:
        protection_name = "unknown"

    # Session state - track active plan and stage
    session_state = {
        "plan_id": None,
        "stage": None,  # None, 'planned', 'validated', 'staged', 'applied'
    }

    # REPL loop
    show_full_context = True
    while True:
        try:
            # Get environment color for prompt
            env_name = env.env.upper()
            if env_name in ["PROD", "PRODUCTION"]:
                prompt_color = "red"
            elif env_name in ["STAGING", "STAGE", "STG"]:
                prompt_color = "yellow"
            elif env_name in ["DEV", "DEVELOPMENT"]:
                prompt_color = "green"
            else:
                prompt_color = "blue"

            # Display context (full or abbreviated based on last command)
            if show_full_context:
                # Display context as multiple lines for readability
                # Line 1: Environment and protection level
                click.secho(
                    f"rmrf:{env.env}[{protection_name}]",
                    fg=prompt_color,
                    bold=True,
                    err=True,
                )

                # Line 2: Plan (if active)
                if session_state["plan_id"]:
                    click.secho(
                        f"plan: {session_state['plan_id']}", fg=prompt_color, dim=True, err=True
                    )

                    # Line 3: Current stage
                    current_stage = session_state["stage"] or "planned"
                    click.secho(f"current: {current_stage}", fg=prompt_color, dim=True, err=True)

                    # Line 4: Next stage
                    next_stage = get_next_stage(current_stage)
                    if next_stage:
                        click.secho(f"next: {next_stage}", fg="cyan", dim=True, err=True)
                    else:
                        # Terminal state - show appropriate message
                        if current_stage in ["denied", "failed"]:
                            click.secho("next: (blocked)", fg="red", dim=True, err=True)
                        elif current_stage == "approval-required":
                            click.secho("next: (needs approval)", fg="yellow", dim=True, err=True)
                        elif current_stage in ["rollback", "near-miss"]:
                            click.secho("next: (abandoned)", fg="yellow", dim=True, err=True)
                        else:
                            click.secho("next: (complete)", fg="green", dim=True, err=True)
                else:
                    click.secho("plan: (none)", fg=prompt_color, dim=True, err=True)
                    click.secho("next: create a plan", fg="cyan", dim=True, err=True)

            # Build prompt with ANSI color codes for readline
            # ANSI codes: \033[1m = bold, \033[0m = reset
            # Color codes: red=31, yellow=33, green=32, blue=34
            # \001 and \002 mark invisible characters for readline (prevents cursor misalignment)
            color_code = {
                "red": "31",
                "yellow": "33",
                "green": "32",
                "blue": "34",
            }[prompt_color]
            prompt_str = f"\001\033[1;{color_code}m\002> \001\033[0m\002"

            # Read command with colored prompt
            line = input(prompt_str)
            line = line.strip()

            # Skip empty lines (but don't show full context next time)
            if not line:
                show_full_context = False
                continue

            # Skip comments (lines starting with #)
            if line.startswith("#"):
                show_full_context = False
                continue

            # Reset to show full context after a real command
            show_full_context = True

            # Add to readline history (needed for piped/non-TTY input)
            try:
                readline.add_history(line)
            except NameError:
                pass  # readline not available

            # Handle special commands
            if line in ["exit", "quit", "q"]:
                _handle_exit_with_incomplete_plan(session_state)
                click.echo("Goodbye!", err=True)
                break

            if line == "clear":
                click.clear()
                print_environment_banner(env)
                continue

            if line in ["help", "?"]:
                print_help()
                continue

            if line == "env":
                print_environment_banner(env)
                print_protection_info(env.env)
                continue

            if line == "protection":
                print_protection_info(env.env)
                continue

            if line == "session":
                print_session_info(session_state)
                continue

            if line.startswith("set-plan "):
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    plan_id = parts[1]
                    # Load plan from store to get actual workflow stage
                    try:
                        from rmrf.store import PlanStore

                        store = PlanStore(auto_create=False)
                        plan = store.load(plan_id)
                        session_state["plan_id"] = plan.plan_id  # type: ignore[assignment]
                        session_state["stage"] = plan.get_workflow_stage()  # type: ignore[assignment]
                        click.secho(
                            f"→ Now tracking: {plan.plan_id} [{session_state['stage']}]",
                            fg="cyan",
                            err=True,
                        )
                    except Exception:
                        # Plan not in store - just set it manually
                        session_state["plan_id"] = plan_id  # type: ignore[assignment]
                        session_state["stage"] = None
                        click.secho(
                            f"→ Tracking: {plan_id} (stage unknown - not in store)",
                            fg="yellow",
                            err=True,
                        )
                else:
                    log_error("Usage: set-plan <plan-id>")
                continue

            if line == "clear-plan":
                session_state["plan_id"] = None
                session_state["stage"] = None
                click.secho("Cleared active plan", fg="yellow", err=True)
                continue

            # Parse command line
            try:
                args = shlex.split(line)
            except ValueError as e:
                log_error(f"Invalid command syntax: {e}")
                continue

            # Execute command by invoking the main CLI
            # Import here to avoid circular imports
            from rmrf.cli import cli

            # Prepend 'rmrf' to make it look like a full command
            full_args = args

            # Invoke the CLI with the parsed arguments
            try:
                # Create new context for this command
                with cli.make_context("rmrf", full_args, obj=ctx.obj) as cmd_ctx:
                    cli.invoke(cmd_ctx)

            except SystemExit as e:
                # Commands may call sys.exit() - don't let that exit the shell
                # Exit code 0 is success, anything else is failure
                if e.code != 0:
                    # Error already logged by the command
                    pass
            except click.ClickException as e:
                e.show()
            except click.Abort:
                log_info("Command aborted")
            except Exception as e:
                log_error(f"Command failed: {e}")
            finally:
                # Always auto-track workflow stages, even if command failed/exited
                update_session_state(session_state, args)

        except KeyboardInterrupt:
            click.echo("", err=True)
            click.echo("Use 'exit' to quit", err=True)
        except EOFError:
            click.echo("", err=True)
            _handle_exit_with_incomplete_plan(session_state)
            click.echo("Goodbye!", err=True)
            break

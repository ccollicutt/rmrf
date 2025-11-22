"""
Command-line interface for rmrf.

Provides commands for plan generation, validation, backup, and execution.
"""

import click

from rmrf import __version__

from .commands.about import about
from .commands.approve import approve, list_pending_approvals
from .commands.cleanup import cleanup
from .commands.closeout import closeout
from .commands.execute import apply
from .commands.failed import mark_failed
from .commands.learn import learn
from .commands.list_cmd import list_objects
from .commands.nearmiss import near_miss
from .commands.plan import plan, show
from .commands.setup import init, preflight
from .commands.shell import shell
from .commands.stage import rollback, stage
from .commands.status import status
from .commands.unlock import unlock
from .commands.validate import validate
from .commands.verify import verify


@click.group(
    epilog="""\b
═══════════════════════════════════════════════════════════
Getting Started
═══════════════════════════════════════════════════════════

\b
What is rmrf?
  A safety-critical deletion utility that provides policy-governed,
  reversible, and auditable alternatives to 'rm -rf'. Every deletion
  goes through validation, backup, and audit trails.

\b
Why it matters:
  Traditional rm -rf is irreversible and unauditable. rmrf adds
  safety gates: policy enforcement prevents mistakes, automatic
  backups enable recovery, and audit trails provide accountability.

\b
Next steps:
  1. Initialize directories: rmrf init
  2. Set up environment: create /etc/rmrf.env or set $RM_ENVIRONMENT
  3. Verify configuration: rmrf preflight
  4. Create a deletion plan: rmrf plan /path/to/delete
  5. Validate against policy: rmrf validate <plan-id>
  6. Stage for deletion: rmrf stage <plan-id>
  7. Execute deletion: rmrf apply <plan-id>

\b
Quick Examples:
  rmrf init                              # Setup directories
  rmrf preflight                         # Verify configuration
  rmrf shell                             # Interactive mode
  rmrf plan /tmp/old-logs --scenario "log cleanup"
  rmrf validate <plan-id>                # Built-in validation
  rmrf stage <plan-id>                   # Stage (backup) before deletion
  rmrf apply <plan-id>

\b
For detailed help on any command:
  rmrf <command> --help
"""
)
@click.version_option(version=__version__)
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--no-banner", is_flag=True, help="Suppress environment banner")
@click.pass_context
def cli(ctx: click.Context, json_output: bool, no_banner: bool) -> None:
    """
    rmrf - Safety-critical deletion utility.

    A production-safe alternative to rm -rf with policy enforcement,
    reversible deletion, and comprehensive auditing.
    """
    ctx.ensure_object(dict)
    ctx.obj["json_output"] = json_output
    ctx.obj["no_banner"] = no_banner

    # Show environment banner for all commands except shell and about
    if (
        ctx.invoked_subcommand
        and ctx.invoked_subcommand not in ["shell", "about"]
        and not no_banner
        and not json_output
    ):
        from .output import print_environment_banner

        print_environment_banner()


# Register commands
cli.add_command(about)
cli.add_command(plan)
cli.add_command(show)
cli.add_command(list_objects)
cli.add_command(validate)
cli.add_command(approve)
cli.add_command(list_pending_approvals)
cli.add_command(stage)
cli.add_command(rollback)
cli.add_command(apply)
cli.add_command(verify)
cli.add_command(closeout)
cli.add_command(learn)
cli.add_command(near_miss)
cli.add_command(mark_failed)
cli.add_command(status)
cli.add_command(cleanup)
cli.add_command(unlock)
cli.add_command(init)
cli.add_command(preflight)
cli.add_command(shell)


def main() -> None:
    """Main entry point for CLI."""
    cli(obj={})

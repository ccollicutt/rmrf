"""
Setup CLI commands.

Provides commands for initializing and verifying system configuration.
"""

import json
import os
import sys
from pathlib import Path

import click

from rmrf.environment import EnvironmentDetector, EnvironmentError
from rmrf.protection import ProtectionLevelRegistry
from rmrf.store import PlanStore

from ..output import log_error, print_structured_output


@click.command(
    epilog="""
Examples:
  rmrf init                          # Initialize in default location (/var/lib/rmrf)
  rmrf init --root-dir ~/.rmrf       # Initialize in home directory
  sudo rmrf init                     # Initialize with sudo if needed

Run 'rmrf preflight' after initialization to verify setup.
"""
)
@click.option(
    "--root-dir",
    type=click.Path(),
    default="/var/lib/rmrf",
    help="Root directory for rmrf data (default: /var/lib/rmrf)",
)
@click.pass_context
def init(ctx: click.Context, root_dir: str) -> None:
    """
    Initialize rmrf directory structure.

    Creates required directories for plans, backups, and audit logs.
    Run this after installation to set up the filesystem structure.

    \b
    Examples:
      rmrf init
      rmrf init --root-dir ~/.rmrf
    """
    json_output = ctx.obj["json_output"]
    root_path = Path(root_dir)

    try:
        created_dirs = []
        errors = []

        # Directories to create
        dirs_to_create = {
            "plans": root_path / "plans",
            "backups": root_path / "backups",
            "audit": root_path / "audit",
        }

        # Create each directory
        for name, dir_path in dirs_to_create.items():
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                # Verify it's writable
                test_file = dir_path / ".rmrf_test"
                test_file.touch()
                test_file.unlink()
                created_dirs.append(str(dir_path))
            except PermissionError:
                errors.append(f"{name}: Permission denied - {dir_path}")
            except Exception as e:
                errors.append(f"{name}: {e}")

        # Output results
        if json_output:
            result = {
                "success": len(errors) == 0,
                "root_dir": str(root_path),
                "created_dirs": created_dirs,
                "errors": errors,
            }
            click.echo(json.dumps(result, indent=2))
            sys.exit(0 if not errors else 1)
        else:
            if errors:
                # Some failures
                verdict = "ERROR"
                summary = f"failed to create {len(errors)} directory(ies)"
                what_happened = (
                    f"Attempted to initialize rmrf directories at {root_path}. "
                    f"Successfully created {len(created_dirs)} directories but encountered {len(errors)} error(s). "
                    f"Errors: {', '.join(errors)}"
                )
                why_it_matters = (
                    "Directory initialization failed due to permission issues. "
                    "rmrf needs writable directories for plans, backups, and audit logs to operate safely."
                )
                next_steps = [
                    f"Fix permissions: sudo chown -R $USER:$USER {root_path}",
                    "Or use user directory: rmrf init --root-dir ~/.rmrf",
                    "Then run: rmrf preflight to verify setup",
                ]
                additional_info = {
                    "Root Directory": str(root_path),
                    "Directories Created": str(len(created_dirs)),
                    "Errors": str(len(errors)),
                }
            else:
                # Success
                verdict = "SUCCESS"
                summary = "directories created successfully"
                what_happened = (
                    f"Initialized rmrf directory structure at {root_path}. "
                    f"Created {len(created_dirs)} directories: plans, backups, and audit. "
                    f"All directories are writable and ready for use."
                )
                why_it_matters = (
                    "Directory structure is essential for rmrf operation. "
                    "Plans store deletion metadata, backups enable rollback, "
                    "and audit logs provide complete operational history."
                )
                next_steps = [
                    "Set up environment: create /etc/rmrf.env or set $RM_ENVIRONMENT",
                    "Verify setup: rmrf preflight",
                    "Start using rmrf: rmrf plan /path/to/delete",
                ]
                additional_info = {
                    "Root Directory": str(root_path),
                    "Plans Directory": str(dirs_to_create["plans"]),
                    "Backups Directory": str(dirs_to_create["backups"]),
                    "Audit Directory": str(dirs_to_create["audit"]),
                }

            print_structured_output(
                verdict=verdict,
                scenario="directory initialization",
                summary=summary,
                what_happened=what_happened,
                why_it_matters=why_it_matters,
                next_steps=next_steps,
                additional_info=additional_info,
            )

            sys.exit(0 if not errors else 1)

    except Exception as e:
        log_error(f"Initialization failed: {e}")
        sys.exit(1)


@click.command(
    epilog="""
Examples:
  rmrf preflight                     # Check system configuration

Run this after 'rmrf init' to verify your setup is ready for use.
"""
)
@click.pass_context
def preflight(ctx: click.Context) -> None:
    """
    Check system configuration and readiness.

    Validates environment setup, directory permissions, and built-in validation.
    Run this after installation to verify rmrf is configured correctly.

    \b
    Examples:
      rmrf preflight
    """
    json_output = ctx.obj["json_output"]

    checks = []
    all_passed = True

    # Check 1: Environment Detection
    try:
        detector = EnvironmentDetector()
        env = detector.detect()
        checks.append(
            {
                "name": "Environment Detection",
                "status": "pass",
                "message": f"Detected environment: {env.env}",
                "details": f"Signature: {env.signature}",
            }
        )
    except EnvironmentError as e:
        all_passed = False
        checks.append(
            {
                "name": "Environment Detection",
                "status": "fail",
                "message": str(e),
                "details": "Create /etc/rmrf.env or set $RM_ENVIRONMENT",
            }
        )

    # Check 2: Protection Levels
    try:
        registry = ProtectionLevelRegistry(load_defaults=True)
        levels = registry.list_all()
        checks.append(
            {
                "name": "Protection Levels",
                "status": "pass",
                "message": f"Loaded {len(levels)} protection level(s)",
                "details": ", ".join([level.name for level in levels]),
            }
        )
    except Exception as e:
        all_passed = False
        checks.append(
            {
                "name": "Protection Levels",
                "status": "fail",
                "message": f"Failed to load protection levels: {e}",
                "details": "Check config/protection_levels/ directory",
            }
        )

    # Check 3: Plan Store Directory
    try:
        store = PlanStore(auto_create=True)
        store_path = store.plan_dir
        checks.append(
            {
                "name": "Plan Store",
                "status": "pass",
                "message": f"Plan store accessible at {store_path}",
                "details": f"Writable: {store_path.exists() and store_path.is_dir()}",
            }
        )
    except Exception as e:
        all_passed = False
        checks.append(
            {
                "name": "Plan Store",
                "status": "fail",
                "message": f"Plan store error: {e}",
                "details": "Check /var/lib/rmrf/plans/ permissions",
            }
        )

    # Check 4: Backup Directory
    backup_root = Path("/var/lib/rmrf/backups")
    if backup_root.exists() and backup_root.is_dir():
        checks.append(
            {
                "name": "Backup Directory",
                "status": "pass",
                "message": f"Backup directory exists at {backup_root}",
                "details": f"Writable: {os.access(backup_root, os.W_OK)}",
            }
        )
    else:
        checks.append(
            {
                "name": "Backup Directory",
                "status": "warning",
                "message": f"Backup directory not found at {backup_root}",
                "details": "Will use default location on first backup",
            }
        )

    # Check 5: Audit Directory
    audit_root = Path("/var/lib/rmrf/audit")
    if audit_root.exists() and audit_root.is_dir():
        checks.append(
            {
                "name": "Audit Directory",
                "status": "pass",
                "message": f"Audit directory exists at {audit_root}",
                "details": f"Writable: {os.access(audit_root, os.W_OK)}",
            }
        )
    else:
        checks.append(
            {
                "name": "Audit Directory",
                "status": "warning",
                "message": f"Audit directory not found at {audit_root}",
                "details": "Will use default location on first operation",
            }
        )

    # Output results
    if json_output:
        result = {
            "overall": "pass" if all_passed else "fail",
            "checks": checks,
        }
        click.echo(json.dumps(result, indent=2))
        sys.exit(0 if all_passed else 1)
    else:
        # Human-readable output
        click.echo("═══════════════════════════════════════════════════════════")
        click.echo("  rmrf Preflight Check")
        click.echo("═══════════════════════════════════════════════════════════")
        click.echo("")

        # Display each check
        pass_count = sum(1 for c in checks if c["status"] == "pass")
        warn_count = sum(1 for c in checks if c["status"] == "warning")
        fail_count = sum(1 for c in checks if c["status"] == "fail")

        for check in checks:
            if check["status"] == "pass":
                click.secho(f"✓ {check['name']}", fg="green", bold=True)
            elif check["status"] == "warning":
                click.secho(f"⚠ {check['name']}", fg="yellow", bold=True)
            else:
                click.secho(f"✗ {check['name']}", fg="red", bold=True)

            click.echo(f"  {check['message']}")
            if check["details"]:
                click.echo(f"  {check['details']}")
            click.echo("")

        # Summary with structured output
        verdict = "SUCCESS" if all_passed else "WARNING" if fail_count == 0 else "ERROR"
        scenario = "system configuration check"

        if all_passed:
            summary = "all checks passed"
            what_happened = (
                f"Completed preflight check with {pass_count} checks passing. "
                f"Environment detection, protection levels, and directory structure are properly configured. "
                f"rmrf is ready for safe deletion operations."
            )
            why_it_matters = (
                "Preflight checks ensure that rmrf has the necessary configuration and permissions to operate safely. "
                "A passing preflight check means you can proceed with confidence that deletions will be policy-governed, "
                "backed up, and audited."
            )
            next_steps = [
                "Start using rmrf: rmrf plan /path/to/delete",
                "Review protection levels: check config/protection_levels/",
                "Read quickstart guide: docs/quickstart.md",
            ]
        elif fail_count == 0:
            summary = f"{pass_count} passed, {warn_count} warnings"
            what_happened = (
                f"Preflight check completed with {warn_count} warning(s). "
                f"Core functionality is available but some optional features may not work. "
            )
            why_it_matters = (
                "Warnings don't prevent rmrf from working but may limit functionality. "
                "Optional directories will be created automatically on first use. "
            )
            next_steps = [
                "Review warnings above and address if needed",
                "Start using rmrf: rmrf plan /path/to/delete --scenario 'test'",
            ]
        else:
            summary = f"{fail_count} critical failures"
            what_happened = (
                f"Preflight check failed with {fail_count} critical error(s). "
                f"rmrf cannot operate safely without resolving these failures. "
                f"Common issues include missing environment configuration or insufficient permissions."
            )
            why_it_matters = (
                "Failed preflight checks indicate configuration problems that will prevent safe operation. "
                "Resolving these issues is essential before attempting any deletion operations."
            )
            next_steps = [
                "Fix failed checks shown above",
                'Set up environment: export RM_ENVIRONMENT=\'{"env":"dev","signature":"test"}\'',
                "Or create /etc/rmrf.env with environment configuration",
                "Run preflight again: rmrf preflight",
            ]

        print_structured_output(
            verdict=verdict,
            scenario=scenario,
            summary=summary,
            what_happened=what_happened,
            why_it_matters=why_it_matters,
            next_steps=next_steps,
            additional_info={
                "Checks Passed": str(pass_count),
                "Warnings": str(warn_count),
                "Failures": str(fail_count),
                "Total Checks": str(len(checks)),
            },
        )

        sys.exit(0 if all_passed else 1)

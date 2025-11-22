"""
Cleanup CLI command.

Provides command for removing old backups based on retention policy.
"""

import json
import sys
from pathlib import Path

import click

from rmrf.backup import BackupManager
from rmrf.environment import EnvironmentDetector
from rmrf.protection import ProtectionLevelRegistry

from ..output import log_error, log_info, print_structured_output


@click.command(
    epilog="""
Examples:
  rmrf cleanup                                    # Clean old backups in current environment
  rmrf cleanup --environment prod                 # Clean old backups in prod environment
  rmrf cleanup --retention-days 30                # Override retention period
  rmrf cleanup --dry-run                          # Show what would be removed
  rmrf cleanup --all-environments                 # Clean all environments

Cleanup removes backup directories older than the retention period defined in
the protection level for that environment. Use --dry-run to see what would be
removed before actually deleting.
"""
)
@click.option(
    "--environment",
    "-e",
    help="Environment to clean (default: current environment)",
)
@click.option(
    "--retention-days",
    type=int,
    help="Override retention period (default: from protection level)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be removed without actually deleting",
)
@click.option(
    "--all-environments",
    is_flag=True,
    help="Clean backups for all environments",
)
@click.option(
    "--backup-root",
    type=click.Path(),
    help="Backup root directory (default: /var/lib/rmrf/backups)",
)
@click.pass_context
def cleanup(
    ctx: click.Context,
    environment: str | None,
    retention_days: int | None,
    dry_run: bool,
    all_environments: bool,
    backup_root: str | None,
) -> None:
    """
    Remove old backups based on retention policy.

    Cleanup removes backup directories older than the retention period defined
    in the protection level for each environment. Use --dry-run to preview what
    would be removed before actually deleting.

    \b
    Examples:
      rmrf cleanup                          # Clean current environment
      rmrf cleanup --dry-run                # Preview cleanup
      rmrf cleanup --retention-days 30      # Override retention period
      rmrf cleanup --all-environments       # Clean all environments
    """
    json_output = ctx.obj["json_output"]

    try:
        # Initialize backup manager
        backup_manager = BackupManager(backup_root=Path(backup_root) if backup_root else None)

        # Determine which environments to clean
        if all_environments:
            # Get all environment directories
            environments_to_clean = []
            if backup_manager.backup_root.exists():
                for env_dir in backup_manager.backup_root.iterdir():
                    if env_dir.is_dir():
                        environments_to_clean.append(env_dir.name)

            if not environments_to_clean:
                if json_output:
                    click.echo(
                        json.dumps(
                            {
                                "success": True,
                                "environments_cleaned": 0,
                                "total_backups_removed": 0,
                                "message": "No environments found in backup directory",
                            },
                            indent=2,
                        )
                    )
                else:
                    log_info("No environments found in backup directory")
                sys.exit(0)
        else:
            # Single environment
            if environment:
                env_name = environment
            else:
                # Detect current environment
                detector = EnvironmentDetector()
                env = detector.detect()
                env_name = env.env

            environments_to_clean = [env_name]

        # Clean each environment
        results = []
        total_removed = 0

        for env_name in environments_to_clean:
            # Get retention days for this environment
            if retention_days is not None:
                days = retention_days
            else:
                # Get from protection level
                try:
                    registry = ProtectionLevelRegistry(load_defaults=True)
                    level = registry.get_by_environment(env_name)
                    if level:
                        days = level.retention_days
                    else:
                        # Fallback to safe-local default
                        safe_local = registry.get("safe-local")
                        days = safe_local.retention_days if safe_local else 7
                except Exception:
                    days = 7  # Default fallback

            # Perform cleanup
            removed_count = backup_manager.cleanup_old_backups(
                environment=env_name,
                retention_days=days,
                dry_run=dry_run,
            )

            total_removed += removed_count
            results.append(
                {
                    "environment": env_name,
                    "retention_days": days,
                    "backups_removed": removed_count,
                }
            )

        # Output results
        if json_output:
            output = {
                "success": True,
                "dry_run": dry_run,
                "environments_cleaned": len(environments_to_clean),
                "total_backups_removed": total_removed,
                "results": results,
            }
            click.echo(json.dumps(output, indent=2))
            sys.exit(0)
        else:
            # Human-readable output
            if dry_run:
                verdict = "INFO"
                scenario = "backup cleanup (dry-run)"
                summary = f"would remove {total_removed} backup(s)"
            else:
                verdict = "SUCCESS"
                scenario = "backup cleanup"
                summary = f"removed {total_removed} backup(s)"

            # Build what happened description
            env_descriptions = []
            for result in results:
                env_descriptions.append(
                    f"{result['environment']}: {result['backups_removed']} backup(s) "
                    f"(retention: {result['retention_days']} days)"
                )

            what_happened = (
                f"{'Analyzed' if dry_run else 'Cleaned'} backups for {len(environments_to_clean)} "
                f"environment(s): {', '.join([str(r['environment']) for r in results])}. "
            )
            if total_removed > 0:
                what_happened += f"{'Would remove' if dry_run else 'Removed'} {total_removed} backup directory(ies). "
            else:
                what_happened += "No backups exceeded retention period. "

            why_it_matters = (
                "Backup cleanup helps manage disk space by removing old backups that have "
                "exceeded their retention period. Each environment has a configured retention "
                "policy that balances storage costs with recovery needs."
            )

            if dry_run:
                next_steps = [
                    "Review the backup directories that would be removed",
                    "Run 'rmrf cleanup' without --dry-run to proceed",
                    "Or adjust retention period with --retention-days <days>",
                ]
            else:
                next_steps = [
                    "Backup cleanup complete",
                    "Run 'rmrf cleanup --dry-run' periodically to monitor old backups",
                    "Configure retention in protection levels: config/protection_levels/",
                ]

            additional_info = {
                "Environments Cleaned": str(len(environments_to_clean)),
                "Total Backups Removed": str(total_removed),
                "Dry Run": "Yes" if dry_run else "No",
            }

            # Add per-environment details
            for result in results:
                additional_info[f"{result['environment']} (retention)"] = (
                    f"{result['retention_days']} days"
                )
                additional_info[f"{result['environment']} (removed)"] = str(
                    result["backups_removed"]
                )

            print_structured_output(
                verdict=verdict,
                scenario=scenario,
                summary=summary,
                what_happened=what_happened,
                why_it_matters=why_it_matters,
                next_steps=next_steps,
                additional_info=additional_info,
            )

            sys.exit(0)

    except Exception as e:
        if json_output:
            click.echo(
                json.dumps(
                    {
                        "success": False,
                        "error": str(e),
                    },
                    indent=2,
                )
            )
        else:
            log_error(f"Cleanup failed: {e}")
        sys.exit(1)

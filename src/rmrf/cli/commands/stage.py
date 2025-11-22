"""
Stage and rollback CLI commands.

Provides commands for staging deletions (creating backups) and rolling back deletions.
"""

import json
import sys
from pathlib import Path

import click

from rmrf.backup import BackupError, BackupManager
from rmrf.models import RollbackManifest
from rmrf.protection import ProtectionLevelRegistry
from rmrf.store import PlanStore

from ..output import format_bytes, log_error, log_info, log_success, print_structured_output
from ..utils import load_plan


@click.command(
    epilog="""
Examples:
  rmrf stage plan-20250107-120000-abc123              # Stage plan (create backup)
  rmrf stage plan.json                                # Stage from file
  rmrf stage plan.json --output manifest.json         # Save manifest to file
  rmrf stage plan.json --backup-root /tmp/backups     # Custom backup location

Note: Staging creates SHA-256 verified backups. Save the manifest for rollback.
Staging must be done after validation and before apply.
"""
)
@click.argument("plan_id_or_file")
@click.option(
    "--backup-root",
    type=click.Path(),
    help="Backup root directory (default: /var/lib/rmrf/backups)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file for manifest JSON (default: stdout)",
)
@click.pass_context
def stage(
    ctx: click.Context,
    plan_id_or_file: str,
    backup_root: str | None,
    output: str | None,
) -> None:
    """
    Stage a deletion plan by creating a backup.

    Accepts either a plan ID (from the plan store) or a path to a plan JSON file.
    Copies all files specified in the plan to a versioned backup directory
    and generates a rollback manifest with SHA-256 checksums.

    Plan must be validated before staging.

    \b
    Examples:
      rmrf stage plan-20250107-120000-abc123
      rmrf stage plan.json
      rmrf stage plan.json --output manifest.json
      rmrf stage plan.json --backup-root /tmp/backups
    """
    json_output = ctx.obj["json_output"]

    try:
        # Load plan
        plan_obj = load_plan(plan_id_or_file)

        # Validate workflow order
        can_proceed, error_msg = plan_obj.can_stage()
        if not can_proceed:
            log_error(f"Cannot stage plan: {error_msg}")
            sys.exit(1)

        if not json_output:
            log_info(f"Creating backup for plan: {plan_obj.plan_id}")
            log_info(f"Backing up {plan_obj.file_count} file(s)...")

        # Get protection level
        registry = ProtectionLevelRegistry(load_defaults=True)
        protection_level = registry.require(plan_obj.protection_level)

        # Create backup
        manager = BackupManager(backup_root=Path(backup_root) if backup_root else None)
        manifest = manager.create_backup(plan_obj, protection_level)

        # Mark plan as staged in store
        try:
            store = PlanStore(auto_create=False)
            if store.exists(plan_obj.plan_id):
                # Construct backup path from manifest
                backup_path = str(manifest.backup_root)
                store.mark_staged(plan_obj.plan_id, backup_path)
                if not json_output:
                    log_info("Plan marked as staged in store")
        except Exception:
            # Store update is best-effort, don't fail backup if it fails
            pass

        # Serialize manifest
        manifest_json = manifest.model_dump_json(indent=2)

        # Output manifest
        if output:
            Path(output).write_text(manifest_json)
            if not json_output:
                log_success(f"Manifest saved to {output}")
        else:
            click.echo(manifest_json)

        # Human-readable summary using structured output
        if not json_output:
            scenario_name = plan_obj.scenario or f"plan {plan_obj.plan_id}"
            print_structured_output(
                verdict="SUCCESS",
                scenario=scenario_name,
                summary="backup completed",
                what_happened=f"Successfully backed up {manifest.files} files ({format_bytes(manifest.total_bytes)}) from plan {plan_obj.plan_id}. "
                f"All files copied to {manifest.backup_root} with SHA-256 verification. "
                f"Backup manifest {manifest.manifest_id} created with {manifest.retention_days}-day retention.",
                why_it_matters="Backup ensures complete file recovery if deletion needs to be reversed. "
                "SHA-256 checksums guarantee backup integrity and enable verification during rollback. "
                "This safety net allows confident deletion with full reversibility.",
                next_steps=[
                    "Verify backup integrity if needed (checksums in manifest)",
                    f"Execute deletion: rmrf apply {plan_obj.plan_id}",
                    f"Rollback if needed: rmrf rollback {manifest.manifest_id}",
                ],
                additional_info={
                    "Manifest ID": manifest.manifest_id,
                    "Backup Location": str(manifest.backup_root),
                    "Files Backed Up": str(manifest.files),
                    "Total Size": format_bytes(manifest.total_bytes),
                    "Retention Period": f"{manifest.retention_days} days",
                },
                audit_id=manifest.manifest_id,
            )

    except BackupError as e:
        log_error(str(e))
        sys.exit(1)
    except json.JSONDecodeError as e:
        log_error(f"Invalid JSON in plan file: {e}")
        sys.exit(1)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        sys.exit(1)


@click.command(
    epilog="""
Examples:
  rmrf rollback manifest.json              # Restore from backup
  rmrf rollback manifest.json --dry-run    # Simulate rollback
  rmrf rollback manifest.json --verify-only # Verify backup integrity only

Warning: Rollback overwrites current files. Use --verify-only first to check integrity.
"""
)
@click.argument("manifest_file", type=click.File("r"))
@click.option(
    "--backup-root",
    type=click.Path(),
    help="Backup root directory (default: /var/lib/rmrf/backups)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Simulate rollback without restoring files",
)
@click.option(
    "--verify-only",
    is_flag=True,
    help="Only verify backup integrity without restoring",
)
@click.option(
    "--comment",
    "-c",
    help="Reason for rollback (will prompt if not provided)",
)
@click.pass_context
def rollback(
    ctx: click.Context,
    manifest_file: click.File,
    backup_root: str | None,
    dry_run: bool,
    verify_only: bool,
    comment: str | None,
) -> None:
    """
    Restore files from a backup manifest.

    Reads a rollback manifest and restores all backed up files to their
    original locations with integrity verification.

    \b
    Examples:
      rmrf rollback manifest.json
      rmrf rollback manifest.json --dry-run
      rmrf rollback manifest.json --verify-only
    """
    json_output = ctx.obj["json_output"]

    try:
        # Load manifest
        manifest_data = json.load(manifest_file)  # type: ignore[arg-type]
        manifest_obj = RollbackManifest(**manifest_data)

        manager = BackupManager(backup_root=Path(backup_root) if backup_root else None)

        if verify_only:
            # Verify backup integrity
            if not json_output:
                log_info(f"Verifying backup: {manifest_obj.manifest_id}")

            is_valid = manager.verify_backup(manifest_obj)

            if json_output:
                result = {"manifest_id": manifest_obj.manifest_id, "valid": is_valid}
                click.echo(json.dumps(result, indent=2))
            else:
                if is_valid:
                    print_structured_output(
                        verdict="SUCCESS",
                        scenario=f"backup verification for {manifest_obj.manifest_id}",
                        summary="integrity verified",
                        what_happened=f"Verified backup integrity for manifest {manifest_obj.manifest_id}. "
                        f"All {manifest_obj.files} files passed SHA-256 checksum validation. "
                        f"Backup at {manifest_obj.backup_root} is intact and ready for rollback.",
                        why_it_matters="Verified backups ensure that rollback will succeed with exact file recovery. "
                        "Checksum validation confirms no corruption or tampering occurred since backup creation. "
                        "This provides confidence before executing actual restoration.",
                        next_steps=[
                            "Backup is ready - proceed with rollback if needed",
                            f"Execute rollback: rmrf rollback {manifest_file.name}",
                            "Use --dry-run to simulate rollback first",
                        ],
                        additional_info={
                            "Manifest ID": manifest_obj.manifest_id,
                            "Files Verified": str(manifest_obj.files),
                            "Backup Location": str(manifest_obj.backup_root),
                            "Status": "All checksums valid",
                        },
                    )
                else:
                    print_structured_output(
                        verdict="ERROR",
                        scenario=f"backup verification for {manifest_obj.manifest_id}",
                        summary="integrity check failed",
                        what_happened=f"Backup verification failed for manifest {manifest_obj.manifest_id}. "
                        f"One or more files failed SHA-256 checksum validation. "
                        f"Backup at {manifest_obj.backup_root} may be corrupted or incomplete.",
                        why_it_matters="Failed verification indicates backup corruption, tampering, or incomplete backup. "
                        "Rolling back from corrupted backup could restore incorrect data. "
                        "This prevents unsafe restoration that could cause data integrity issues.",
                        next_steps=[
                            "Do NOT proceed with rollback - backup is compromised",
                            f"Review backup directory: {manifest_obj.backup_root}",
                            "Check system logs for disk errors or tampering",
                            "Re-create backup from original sources if available",
                        ],
                        additional_info={
                            "Manifest ID": manifest_obj.manifest_id,
                            "Backup Location": str(manifest_obj.backup_root),
                            "Status": "CHECKSUM VALIDATION FAILED",
                        },
                    )
                    sys.exit(1)

        else:
            # Require comment for rollback (unless dry-run or verify-only)
            if not dry_run and not verify_only:
                if not comment:
                    if json_output:
                        log_error("Comment required in JSON mode. Use --comment flag.")
                        sys.exit(1)

                    click.echo("")
                    click.secho("Rollback Comment Required", bold=True, fg="yellow")
                    click.echo("")
                    click.echo("Please explain why this rollback is necessary:")
                    click.echo("  - What went wrong with the deletion?")
                    click.echo("  - Why is restoration needed?")
                    click.echo("")

                    comment = click.prompt("Rollback reason", type=str)

                if not comment or not comment.strip():
                    log_error("Comment cannot be empty")
                    sys.exit(1)

            # Perform rollback
            if not json_output:
                mode_str = " (DRY-RUN)" if dry_run else ""
                log_info(f"Rolling back: {manifest_obj.manifest_id}{mode_str}")
                log_info(f"Restoring {manifest_obj.files} file(s)...")

            restored_count = manager.rollback(manifest_obj, dry_run=dry_run)

            # Update plan with rollback info (if not dry-run)
            if not dry_run and comment:
                try:
                    from datetime import datetime, timezone

                    from rmrf.store import PlanStore

                    store = PlanStore(auto_create=False)
                    plan = store.load(manifest_obj.plan_id)
                    plan.rollback_at = datetime.now(timezone.utc)
                    plan.rollback_comment = comment.strip()
                    store.save(plan)
                except Exception:
                    # Store update is best-effort
                    pass

            if json_output:
                result = {
                    "manifest_id": manifest_obj.manifest_id,
                    "restored": restored_count,
                    "dry_run": dry_run,
                }
                click.echo(json.dumps(result, indent=2))
            else:
                dry_run_note = " (simulated in dry-run mode)" if dry_run else ""
                print_structured_output(
                    verdict="SUCCESS",
                    scenario=f"rollback from {manifest_obj.manifest_id}",
                    summary=f"restored {restored_count} files{dry_run_note}",
                    what_happened=f"Rolled back {restored_count} files from manifest {manifest_obj.manifest_id}. "
                    f"All files restored to original locations from backup at {manifest_obj.backup_root}. "
                    f"SHA-256 checksums verified for integrity{dry_run_note}. "
                    f"Deletion operation successfully reversed.",
                    why_it_matters="Successful rollback demonstrates the safety-critical reversibility of rmrf operations. "
                    "Files are restored exactly as they were before deletion, with cryptographic verification. "
                    + (
                        "This was a simulation - no actual files were restored."
                        if dry_run
                        else "This recovery capability is a core safety feature that distinguishes rmrf from rm -rf."
                    ),
                    next_steps=[
                        "Verify restored files are accessible and correct",
                        "Check application functionality if needed",
                        "Review what caused the need for rollback",
                    ]
                    + ([] if dry_run else ["Backup can be cleaned up if no longer needed"]),
                    additional_info={
                        "Manifest ID": manifest_obj.manifest_id,
                        "Files Restored": str(restored_count),
                        "Backup Location": str(manifest_obj.backup_root),
                        "Total Size": format_bytes(manifest_obj.total_bytes),
                        **({"Mode": "DRY-RUN (no actual restoration)"} if dry_run else {}),
                    },
                )

    except BackupError as e:
        log_error(str(e))
        sys.exit(1)
    except json.JSONDecodeError as e:
        log_error(f"Invalid JSON in manifest file: {e}")
        sys.exit(1)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        sys.exit(1)

"""
Deletion engine for rmrf.

Executes validated deletion plans with verification and auditing.
"""

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from rmrf.audit import AuditEmitter
from rmrf.locking import LockManager
from rmrf.models import Plan, ProtectionLevel, Verdict
from rmrf.scanner import PathScanner


class DeletionError(Exception):
    """Raised when deletion operations fail."""

    pass


class DeletionResult:
    """Result of a deletion operation."""

    def __init__(
        self,
        audit_id: str,
        plan_id: str,
        deleted_count: int,
        failed_count: int,
        errors: list[tuple[Path, str]],
        dry_run: bool = False,
    ) -> None:
        """
        Initialize deletion result.

        Args:
            audit_id: Unique audit ID for this operation
            plan_id: Plan ID that was executed
            deleted_count: Number of files successfully deleted
            failed_count: Number of files that failed to delete
            errors: List of (path, error_message) tuples
            dry_run: Whether this was a dry run
        """
        self.audit_id = audit_id
        self.plan_id = plan_id
        self.deleted_count = deleted_count
        self.failed_count = failed_count
        self.errors = errors
        self.dry_run = dry_run
        self.success = failed_count == 0


class DeletionEngine:
    """
    Executes validated deletion plans.

    Performs actual file deletion with verification and auditing.
    """

    def __init__(
        self,
        auditor: AuditEmitter | None = None,
        require_validation: bool = True,
        lock_manager: LockManager | None = None,
    ) -> None:
        """
        Initialize deletion engine.

        Args:
            auditor: Audit emitter (default: creates new one)
            require_validation: Require plans to be validated before execution
            lock_manager: Lock manager (default: creates new one)
        """
        self.auditor = auditor or AuditEmitter()
        self.require_validation = require_validation
        self.lock_manager = lock_manager or LockManager()
        self.scanner = PathScanner(skip_errors=False)

    def execute(
        self,
        plan: Plan,
        protection_level: ProtectionLevel,
        dry_run: bool = False,
        user_id: str | None = None,
    ) -> DeletionResult:
        """
        Execute deletion plan.

        Args:
            plan: Validated deletion plan
            protection_level: Protection level configuration
            dry_run: If True, simulate deletion without actually deleting
            user_id: User ID for audit trail

        Returns:
            DeletionResult with operation details

        Raises:
            DeletionError: If execution fails or plan is invalid
        """
        # Validate prerequisites
        self._validate_plan(plan, protection_level)

        # Generate audit ID
        audit_id = self._generate_audit_id()

        # Emit start event
        self.auditor.emit_deletion_started(plan.plan_id, audit_id, user_id)

        try:
            # Check approval if required
            if plan.requires_approval and not plan.approved:
                raise DeletionError(
                    f"Plan {plan.plan_id} requires approval before execution. "
                    "Run: rmrf approve <plan-id>"
                )

            # Execute deletion
            deleted_count = 0
            failed_count = 0
            errors: list[tuple[Path, str]] = []

            # Check for missing targets first
            missing_targets = plan.check_targets_exist()
            if missing_targets:
                errors.extend(missing_targets)
                failed_count += len(missing_targets)

            for target_str in plan.targets:
                target = Path(target_str)

                # Skip if already recorded as missing
                if not target.exists():
                    continue

                # Delete target
                if target.is_file():
                    # Delete single file
                    try:
                        if not dry_run:
                            target.unlink()
                        deleted_count += 1
                    except (OSError, PermissionError) as e:
                        errors.append((target, str(e)))
                        failed_count += 1

                elif target.is_dir():
                    # Delete directory recursively
                    try:
                        if not dry_run:
                            shutil.rmtree(target)
                        # Count files that would be/were deleted
                        if dry_run:
                            scan_result = self.scanner.scan(target)
                            deleted_count += len(scan_result.files)
                        else:
                            # Already deleted, use plan count
                            deleted_count += plan.file_count
                    except (OSError, PermissionError) as e:
                        errors.append((target, str(e)))
                        failed_count += 1

            # Verify deletion (if not dry run)
            if not dry_run:
                verification_errors = self._verify_deletion(plan)
                if verification_errors:
                    for path, error in verification_errors:
                        errors.append((path, f"Verification failed: {error}"))
                    failed_count += len(verification_errors)

            # Create result
            result = DeletionResult(
                audit_id=audit_id,
                plan_id=plan.plan_id,
                deleted_count=deleted_count,
                failed_count=failed_count,
                errors=errors,
                dry_run=dry_run,
            )

            # Emit completion/failure event
            if result.success:
                self.auditor.emit_deletion_completed(plan.plan_id, audit_id, deleted_count, user_id)
            else:
                error_summary = f"{failed_count} files failed to delete"
                self.auditor.emit_deletion_failed(plan.plan_id, audit_id, error_summary, user_id)

            return result

        except Exception as e:
            # Emit failure event
            self.auditor.emit_deletion_failed(plan.plan_id, audit_id, str(e), user_id)
            raise DeletionError(f"Deletion execution failed: {e}") from e

        finally:
            # Always release lock after execution (success or failure)
            try:
                self.lock_manager.release_lock(plan.plan_id)
            except Exception:
                # Don't fail if lock release fails - log but continue
                pass

    def _validate_plan(self, plan: Plan, protection_level: ProtectionLevel) -> None:
        """
        Validate plan before execution.

        Args:
            plan: Deletion plan
            protection_level: Protection level

        Raises:
            DeletionError: If validation fails
        """
        # Check if validation is required
        if self.require_validation and not plan.validated:
            raise DeletionError("Plan must be validated before execution")

        # Check expiration
        if plan.is_expired():
            raise DeletionError("Plan has expired")

        # Check dry-run for simulation-only level
        if protection_level.name == "simulation-only" and not plan.dry_run:
            raise DeletionError("Simulation-only protection level requires dry-run mode")

        # Check policy verdict if present
        if plan.policy_verdict:
            if plan.policy_verdict.verdict == Verdict.DENY:
                raise DeletionError("Plan was denied by policy")
            if plan.policy_verdict.verdict == Verdict.REQUIRE_APPROVAL:
                # Check if approval exists (stub for MVP)
                if not hasattr(plan, "approval_id") or not plan.approval_id:
                    raise DeletionError("Plan requires approval before execution")

        # Check backup if required
        if protection_level.require_backup and not plan.backup_path:
            raise DeletionError(
                f"Protection level {protection_level.name} requires backup before deletion"
            )

    def _verify_deletion(self, plan: Plan) -> list[tuple[Path, str]]:
        """
        Verify that deletion completed successfully.

        Args:
            plan: Deletion plan

        Returns:
            List of (path, error) tuples for verification failures
        """
        errors: list[tuple[Path, str]] = []

        for target_str in plan.targets:
            target = Path(target_str)

            # Target should no longer exist
            if target.exists():
                errors.append((target, "Target still exists after deletion"))

        return errors

    def _generate_audit_id(self) -> str:
        """Generate unique audit ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"audit-{timestamp}-{uuid.uuid4().hex[:8]}"

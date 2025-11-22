"""
Audit event emitter for rmrf.

Emits structured audit events to JSON log files.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from rmrf.models import AuditEvent, EventPhase


class AuditError(Exception):
    """Raised when audit operations fail."""

    pass


class AuditEmitter:
    """
    Emits audit events to structured log files.
    """

    DEFAULT_AUDIT_DIR = Path("/var/lib/rmrf/audit")

    def __init__(
        self,
        audit_dir: Path | None = None,
        auto_create: bool = True,
    ) -> None:
        """
        Initialize audit emitter.

        Args:
            audit_dir: Directory for audit logs (default: /var/lib/rmrf/audit or RMRF_AUDIT_DIR)
            auto_create: Automatically create audit directory if missing
        """
        # Check environment variable if audit_dir not provided
        if audit_dir is None:
            import os

            env_audit_dir = os.getenv("RMRF_AUDIT_DIR")
            if env_audit_dir:
                audit_dir = Path(env_audit_dir)
            else:
                audit_dir = self.DEFAULT_AUDIT_DIR

        self.audit_dir = audit_dir
        self.auto_create = auto_create

        if self.auto_create and not self.audit_dir.exists():
            try:
                self.audit_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise AuditError(f"Failed to create audit directory: {e}") from e

    def emit(self, event: AuditEvent) -> None:
        """
        Emit an audit event.

        Args:
            event: Audit event to emit

        Raises:
            AuditError: If event emission fails
        """
        # Determine log file based on date
        date_str = event.timestamp.strftime("%Y-%m-%d")
        log_file = self.audit_dir / f"rmrf-{date_str}.jsonl"

        try:
            # Serialize event as JSON line
            event_json = event.model_dump_json()

            # Append to log file (create if doesn't exist)
            with open(log_file, "a") as f:
                f.write(event_json + "\n")

        except OSError as e:
            raise AuditError(f"Failed to write audit event: {e}") from e

    def emit_plan_created(
        self,
        plan_id: str,
        environment: str,
        protection_level: str,
        file_count: int,
        total_bytes: int,
        user_id: str | None = None,
    ) -> None:
        """Emit plan creation event."""
        event = AuditEvent(
            event_id=self._generate_event_id(),
            phase=EventPhase.PLAN_CREATED,
            plan_id=plan_id,
            environment=environment,
            protection_level=protection_level,
            message=f"Deletion plan created: {file_count} files, {total_bytes} bytes",
            user_id=user_id,
        )
        self.emit(event)

    def emit_plan_validated(
        self,
        plan_id: str,
        verdict: str,
        message: str | None = None,
        user_id: str | None = None,
    ) -> None:
        """Emit plan validation event."""
        event = AuditEvent(
            event_id=self._generate_event_id(),
            phase=EventPhase.PLAN_VALIDATED,
            plan_id=plan_id,
            message=message or f"Plan validation: {verdict}",
            user_id=user_id,
            metadata={"verdict": verdict},
        )
        self.emit(event)

    def emit_backup_created(
        self,
        plan_id: str,
        manifest_id: str,
        file_count: int,
        backup_root: str,
        user_id: str | None = None,
    ) -> None:
        """Emit backup creation event."""
        event = AuditEvent(
            event_id=self._generate_event_id(),
            phase=EventPhase.BACKUP_CREATED,
            plan_id=plan_id,
            message=f"Backup created: {file_count} files to {backup_root}",
            user_id=user_id,
            metadata={"manifest_id": manifest_id, "backup_root": backup_root},
        )
        self.emit(event)

    def emit_deletion_started(
        self,
        plan_id: str,
        audit_id: str,
        user_id: str | None = None,
    ) -> None:
        """Emit deletion start event."""
        event = AuditEvent(
            event_id=self._generate_event_id(),
            phase=EventPhase.DELETION_STARTED,
            plan_id=plan_id,
            audit_id=audit_id,
            message="Deletion execution started",
            user_id=user_id,
        )
        self.emit(event)

    def emit_deletion_completed(
        self,
        plan_id: str,
        audit_id: str,
        deleted_count: int,
        user_id: str | None = None,
    ) -> None:
        """Emit deletion completion event."""
        event = AuditEvent(
            event_id=self._generate_event_id(),
            phase=EventPhase.DELETION_COMPLETED,
            plan_id=plan_id,
            audit_id=audit_id,
            message=f"Deletion completed: {deleted_count} files deleted",
            user_id=user_id,
            metadata={"deleted_count": deleted_count},
        )
        self.emit(event)

    def emit_deletion_failed(
        self,
        plan_id: str,
        audit_id: str,
        error: str,
        user_id: str | None = None,
    ) -> None:
        """Emit deletion failure event."""
        event = AuditEvent(
            event_id=self._generate_event_id(),
            phase=EventPhase.DELETION_FAILED,
            plan_id=plan_id,
            audit_id=audit_id,
            message=f"Deletion failed: {error}",
            user_id=user_id,
            metadata={"error": error},
        )
        self.emit(event)

    def emit_rollback_completed(
        self,
        plan_id: str,
        manifest_id: str,
        restored_count: int,
        user_id: str | None = None,
    ) -> None:
        """Emit rollback completion event."""
        event = AuditEvent(
            event_id=self._generate_event_id(),
            phase=EventPhase.ROLLBACK_COMPLETED,
            plan_id=plan_id,
            message=f"Rollback completed: {restored_count} files restored",
            user_id=user_id,
            metadata={"manifest_id": manifest_id, "restored_count": restored_count},
        )
        self.emit(event)

    def get_events(
        self,
        plan_id: str | None = None,
        audit_id: str | None = None,
        date: str | None = None,
    ) -> list[AuditEvent]:
        """
        Retrieve audit events.

        Args:
            plan_id: Filter by plan ID
            audit_id: Filter by audit ID
            date: Date in YYYY-MM-DD format (default: today)

        Returns:
            List of matching audit events
        """
        if not date:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        log_file = self.audit_dir / f"rmrf-{date}.jsonl"

        if not log_file.exists():
            return []

        events: list[AuditEvent] = []

        try:
            with open(log_file) as f:
                for line in f:
                    if line.strip():
                        event_data = json.loads(line)
                        event = AuditEvent(**event_data)

                        # Apply filters
                        if plan_id and event.plan_id != plan_id:
                            continue
                        if audit_id and event.audit_id != audit_id:
                            continue

                        events.append(event)

        except (OSError, json.JSONDecodeError) as e:
            raise AuditError(f"Failed to read audit events: {e}") from e

        return events

    def _generate_event_id(self) -> str:
        """Generate unique event ID."""
        from uuid import uuid4

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"evt-{timestamp}-{uuid4().hex[:8]}"

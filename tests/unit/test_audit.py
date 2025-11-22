"""
Unit tests for rmrf.audit.

Tests audit event emission and retrieval.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from rmrf.audit import AuditEmitter, AuditError
from rmrf.models import AuditEvent, EventPhase


class TestAuditEmitter:
    """Tests for AuditEmitter class."""

    @pytest.fixture
    def audit_dir(self, tmp_path: Path) -> Path:
        """Create temporary audit directory."""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        return audit_dir

    @pytest.fixture
    def emitter(self, audit_dir: Path) -> AuditEmitter:
        """Create audit emitter instance."""
        return AuditEmitter(audit_dir=audit_dir)

    def test_emitter_initialization(self, audit_dir: Path) -> None:
        """Test audit emitter initialization."""
        emitter = AuditEmitter(audit_dir=audit_dir)
        assert emitter.audit_dir == audit_dir

    def test_emitter_default_directory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test audit emitter with default directory."""
        # Clear any environment variable override
        monkeypatch.delenv("RMRF_AUDIT_DIR", raising=False)

        emitter = AuditEmitter(auto_create=False)
        assert emitter.audit_dir == AuditEmitter.DEFAULT_AUDIT_DIR

    def test_emitter_auto_creates_directory(self, tmp_path: Path) -> None:
        """Test that emitter auto-creates directory."""
        audit_dir = tmp_path / "new_audit"
        assert not audit_dir.exists()

        _emitter = AuditEmitter(audit_dir=audit_dir, auto_create=True)
        assert audit_dir.exists()

    def test_emit_event(self, emitter: AuditEmitter, audit_dir: Path) -> None:
        """Test emitting an audit event."""
        event = AuditEvent(
            event_id="test-event-001",
            phase=EventPhase.PLAN_CREATED,
            plan_id="plan-001",
            message="Test event",
        )

        emitter.emit(event)

        # Check that log file was created
        date_str = event.timestamp.strftime("%Y-%m-%d")
        log_file = audit_dir / f"rmrf-{date_str}.jsonl"
        assert log_file.exists()

        # Check content
        content = log_file.read_text()
        assert "test-event-001" in content
        assert "plan-001" in content

    def test_emit_multiple_events(self, emitter: AuditEmitter, audit_dir: Path) -> None:
        """Test emitting multiple events."""
        events = [
            AuditEvent(
                event_id=f"event-{i}",
                phase=EventPhase.PLAN_CREATED,
                plan_id="plan-001",
                message=f"Event {i}",
            )
            for i in range(3)
        ]

        for event in events:
            emitter.emit(event)

        # Check that all events were written
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = audit_dir / f"rmrf-{date_str}.jsonl"

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_emit_plan_created(self, emitter: AuditEmitter, audit_dir: Path) -> None:
        """Test emitting plan creation event."""
        emitter.emit_plan_created(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            file_count=10,
            total_bytes=1000,
            user_id="user123",
        )

        # Verify event was written
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = audit_dir / f"rmrf-{date_str}.jsonl"
        assert log_file.exists()

        # Parse and verify
        event_data = json.loads(log_file.read_text())
        assert event_data["phase"] == "plan_created"
        assert event_data["plan_id"] == "plan-001"
        assert event_data["user_id"] == "user123"

    def test_emit_plan_validated(self, emitter: AuditEmitter) -> None:
        """Test emitting plan validation event."""
        emitter.emit_plan_validated(plan_id="plan-001", verdict="allow", message="Plan approved")

        events = emitter.get_events(plan_id="plan-001")
        assert len(events) == 1
        assert events[0].phase == EventPhase.PLAN_VALIDATED

    def test_emit_backup_created(self, emitter: AuditEmitter) -> None:
        """Test emitting backup creation event."""
        emitter.emit_backup_created(
            plan_id="plan-001",
            manifest_id="manifest-001",
            file_count=10,
            backup_root="/var/lib/rmrf/backups",
        )

        events = emitter.get_events(plan_id="plan-001")
        assert len(events) == 1
        assert events[0].phase == EventPhase.BACKUP_CREATED

    def test_emit_deletion_started(self, emitter: AuditEmitter) -> None:
        """Test emitting deletion start event."""
        emitter.emit_deletion_started(plan_id="plan-001", audit_id="audit-001", user_id="user123")

        events = emitter.get_events(audit_id="audit-001")
        assert len(events) == 1
        assert events[0].phase == EventPhase.DELETION_STARTED

    def test_emit_deletion_completed(self, emitter: AuditEmitter) -> None:
        """Test emitting deletion completion event."""
        emitter.emit_deletion_completed(plan_id="plan-001", audit_id="audit-001", deleted_count=10)

        events = emitter.get_events(audit_id="audit-001")
        assert len(events) == 1
        assert events[0].phase == EventPhase.DELETION_COMPLETED

    def test_emit_deletion_failed(self, emitter: AuditEmitter) -> None:
        """Test emitting deletion failure event."""
        emitter.emit_deletion_failed(
            plan_id="plan-001", audit_id="audit-001", error="Permission denied"
        )

        events = emitter.get_events(audit_id="audit-001")
        assert len(events) == 1
        assert events[0].phase == EventPhase.DELETION_FAILED

    def test_emit_rollback_completed(self, emitter: AuditEmitter) -> None:
        """Test emitting rollback completion event."""
        emitter.emit_rollback_completed(
            plan_id="plan-001", manifest_id="manifest-001", restored_count=10
        )

        events = emitter.get_events(plan_id="plan-001")
        assert len(events) == 1
        assert events[0].phase == EventPhase.ROLLBACK_COMPLETED

    def test_get_events_by_plan_id(self, emitter: AuditEmitter) -> None:
        """Test retrieving events by plan ID."""
        # Emit multiple events
        emitter.emit_plan_created(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            file_count=10,
            total_bytes=1000,
        )
        emitter.emit_plan_created(
            plan_id="plan-002",
            environment="dev",
            protection_level="safe-local",
            file_count=20,
            total_bytes=2000,
        )

        # Get events for plan-001
        events = emitter.get_events(plan_id="plan-001")
        assert len(events) == 1
        assert events[0].plan_id == "plan-001"

    def test_get_events_by_audit_id(self, emitter: AuditEmitter) -> None:
        """Test retrieving events by audit ID."""
        emitter.emit_deletion_started(plan_id="plan-001", audit_id="audit-001", user_id="user123")
        emitter.emit_deletion_completed(plan_id="plan-001", audit_id="audit-001", deleted_count=10)
        emitter.emit_deletion_started(plan_id="plan-002", audit_id="audit-002", user_id="user123")

        # Get events for audit-001
        events = emitter.get_events(audit_id="audit-001")
        assert len(events) == 2
        assert all(e.audit_id == "audit-001" for e in events)

    def test_get_events_no_matches(self, emitter: AuditEmitter) -> None:
        """Test retrieving events when no matches."""
        events = emitter.get_events(plan_id="nonexistent")
        assert events == []

    def test_get_events_missing_log_file(self, emitter: AuditEmitter) -> None:
        """Test retrieving events when log file doesn't exist."""
        events = emitter.get_events(date="2020-01-01")
        assert events == []

    def test_event_id_generation(self, emitter: AuditEmitter) -> None:
        """Test that event IDs are unique."""
        event_id1 = emitter._generate_event_id()
        event_id2 = emitter._generate_event_id()

        assert event_id1 != event_id2
        assert event_id1.startswith("evt-")
        assert event_id2.startswith("evt-")

    def test_json_lines_format(self, emitter: AuditEmitter, audit_dir: Path) -> None:
        """Test that events are written in JSON lines format."""
        # Emit multiple events
        for i in range(3):
            emitter.emit_plan_created(
                plan_id=f"plan-{i}",
                environment="dev",
                protection_level="safe-local",
                file_count=i,
                total_bytes=i * 100,
            )

        # Check format
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = audit_dir / f"rmrf-{date_str}.jsonl"

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 3

        # Each line should be valid JSON
        for line in lines:
            data = json.loads(line)
            assert "event_id" in data
            assert "phase" in data
            assert "plan_id" in data

    def test_emit_with_write_error(self, tmp_path: Path) -> None:
        """Test handling of write errors."""
        # Create read-only directory
        audit_dir = tmp_path / "readonly"
        audit_dir.mkdir()
        audit_dir.chmod(0o444)

        emitter = AuditEmitter(audit_dir=audit_dir)
        event = AuditEvent(
            event_id="test-event",
            phase=EventPhase.PLAN_CREATED,
            plan_id="plan-001",
            message="Test",
        )

        with pytest.raises(AuditError) as exc_info:
            emitter.emit(event)

        assert "Failed to write audit event" in str(exc_info.value)

        # Clean up
        audit_dir.chmod(0o755)

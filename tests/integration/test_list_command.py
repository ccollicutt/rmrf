"""
Integration tests for list command.

Tests the list command with real plan storage.
"""

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rmrf.models import Plan, RiskLevel, RiskScore
from rmrf.store import PlanStore

# Get path to rmrf binary
RMRF_BIN = Path(__file__).parent.parent.parent / ".venv" / "bin" / "rmrf"


class TestListCommand:
    """Test list command integration."""

    def test_list_plans_empty_store(self, tmp_path: Path) -> None:
        """Test listing plans from empty store."""
        plan_dir = tmp_path / "plans"
        plan_dir.mkdir()

        result = subprocess.run(
            [str(RMRF_BIN), "list", "plans", "--plan-dir", str(plan_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "No plans found" in result.stderr

    def test_list_plans_with_plans(self, tmp_path: Path) -> None:
        """Test listing plans with multiple plans in store."""
        plan_dir = tmp_path / "plans"
        plan_dir.mkdir()

        # Create some test plans
        store = PlanStore(plan_dir=plan_dir)

        plan1 = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test1"],
            file_count=5,
            total_bytes=1024,
            risk_score=RiskScore(level=RiskLevel.LOW, score=15, reasons=["Small"]),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        plan2 = Plan(
            plan_id="plan-002",
            environment="prod",
            protection_level="critical-system",
            targets=["/tmp/test2"],
            file_count=100,
            total_bytes=10240,
            validated=True,
            risk_score=RiskScore(level=RiskLevel.MEDIUM, score=45, reasons=["Medium"]),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
        )

        store.save(plan1)
        store.save(plan2)

        # List all plans
        result = subprocess.run(
            [str(RMRF_BIN), "list", "plans", "--plan-dir", str(plan_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Found 2 plan(s)" in result.stderr
        assert "plan-001" in result.stdout
        assert "plan-002" in result.stdout
        assert "dev" in result.stdout
        assert "prod" in result.stdout

    def test_list_plans_filter_by_environment(self, tmp_path: Path) -> None:
        """Test filtering plans by environment."""
        plan_dir = tmp_path / "plans"
        plan_dir.mkdir()

        store = PlanStore(plan_dir=plan_dir)

        plan1 = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test1"],
            file_count=5,
            total_bytes=1024,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        plan2 = Plan(
            plan_id="plan-002",
            environment="prod",
            protection_level="critical-system",
            targets=["/tmp/test2"],
            file_count=100,
            total_bytes=10240,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
        )

        store.save(plan1)
        store.save(plan2)

        # Filter by dev environment
        result = subprocess.run(
            [str(RMRF_BIN), "list", "plans", "--environment", "dev", "--plan-dir", str(plan_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Found 1 plan(s)" in result.stderr
        assert "plan-001" in result.stdout
        assert "plan-002" not in result.stdout

    def test_list_plans_validated_only(self, tmp_path: Path) -> None:
        """Test filtering only validated plans."""
        plan_dir = tmp_path / "plans"
        plan_dir.mkdir()

        store = PlanStore(plan_dir=plan_dir)

        plan1 = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test1"],
            file_count=5,
            total_bytes=1024,
            validated=False,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        plan2 = Plan(
            plan_id="plan-002",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test2"],
            file_count=100,
            total_bytes=10240,
            validated=True,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
        )

        store.save(plan1)
        store.save(plan2)

        # Filter validated only
        result = subprocess.run(
            [str(RMRF_BIN), "list", "plans", "--validated-only", "--plan-dir", str(plan_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Found 1 plan(s)" in result.stderr
        assert "plan-002" in result.stdout
        assert "plan-001" not in result.stdout
        assert "VALIDATED" in result.stdout

    def test_list_plans_json_output(self, tmp_path: Path) -> None:
        """Test JSON output format."""
        import json

        plan_dir = tmp_path / "plans"
        plan_dir.mkdir()

        store = PlanStore(plan_dir=plan_dir)

        plan1 = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test1"],
            file_count=5,
            total_bytes=1024,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        store.save(plan1)

        # Get JSON output
        result = subprocess.run(
            [str(RMRF_BIN), "--json-output", "list", "plans", "--plan-dir", str(plan_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        # Parse JSON
        data = json.loads(result.stdout)
        assert "plans" in data
        assert len(data["plans"]) == 1
        assert data["plans"][0]["plan_id"] == "plan-001"
        assert data["plans"][0]["environment"] == "dev"

    def test_list_plans_shows_status_badges(self, tmp_path: Path) -> None:
        """Test that list shows status badges correctly."""
        plan_dir = tmp_path / "plans"
        plan_dir.mkdir()

        store = PlanStore(plan_dir=plan_dir)

        # Plan with backup (will show as STAGED)
        plan1 = Plan(
            plan_id="plan-001",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test1"],
            file_count=5,
            total_bytes=1024,
            validated=True,
            backup_path="/var/lib/rmrf/backups/dev/2025-01-01/plan-001",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        # Expired plan
        plan2 = Plan(
            plan_id="plan-002",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test2"],
            file_count=5,
            total_bytes=1024,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # Expired
        )

        # Dry-run plan
        plan3 = Plan(
            plan_id="plan-003",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test3"],
            file_count=5,
            total_bytes=1024,
            dry_run=True,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        # Validated plan (no backup yet)
        plan4 = Plan(
            plan_id="plan-004",
            environment="dev",
            protection_level="safe-local",
            targets=["/tmp/test4"],
            file_count=5,
            total_bytes=1024,
            validated=True,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        store.save(plan1)
        store.save(plan2)
        store.save(plan3)
        store.save(plan4)

        result = subprocess.run(
            [str(RMRF_BIN), "list", "plans", "--plan-dir", str(plan_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "VALIDATED" in result.stdout  # plan4
        assert "STAGED" in result.stdout  # plan1
        assert "EXPIRED" in result.stdout  # plan2
        assert "DRY-RUN" in result.stdout  # plan3

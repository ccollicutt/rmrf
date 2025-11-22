"""
Unit tests for rmrf.planner.

Tests plan generation and risk scoring.
"""

import json
from pathlib import Path

import pytest

from rmrf.locking import LockManager
from rmrf.models import ProtectionLevel, RiskLevel, UserContext
from rmrf.planner import PlanGenerator, PlanGeneratorError, RiskScorer


class TestRiskScorer:
    """Tests for RiskScorer class."""

    def test_zero_files_low_risk(self) -> None:
        """Test that zero files is low risk."""
        scorer = RiskScorer()
        risk = scorer.score(file_count=0, total_bytes=0)

        assert risk.level == RiskLevel.LOW
        assert risk.score == 0
        assert "No files" in risk.reasons[0]

    def test_small_deletion_low_risk(self) -> None:
        """Test that small deletions are low risk."""
        scorer = RiskScorer()
        risk = scorer.score(file_count=10, total_bytes=1024)

        assert risk.level == RiskLevel.LOW
        assert risk.score < 30

    def test_moderate_deletion_medium_risk(self) -> None:
        """Test that moderate deletions are medium risk."""
        scorer = RiskScorer()
        risk = scorer.score(file_count=500, total_bytes=500 * 1024 * 1024)  # 500 MB

        assert risk.level in [RiskLevel.MEDIUM, RiskLevel.HIGH]
        assert 30 <= risk.score < 85

    def test_large_deletion_high_risk(self) -> None:
        """Test that large deletions are high risk."""
        scorer = RiskScorer()
        risk = scorer.score(file_count=5000, total_bytes=5 * 1024 * 1024 * 1024)  # 5 GB

        assert risk.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        assert risk.score >= 60

    def test_very_large_deletion_critical_risk(self) -> None:
        """Test that very large deletions are critical risk."""
        scorer = RiskScorer()
        risk = scorer.score(file_count=10000, total_bytes=20 * 1024 * 1024 * 1024)  # 20 GB

        assert risk.level == RiskLevel.CRITICAL
        assert risk.score >= 85

    def test_exceeds_protection_level_file_limit(self) -> None:
        """Test risk when exceeding protection level file limit."""
        level = ProtectionLevel(
            name="test",
            description="Test level",
            max_files=100,
        )

        scorer = RiskScorer()
        risk = scorer.score(file_count=200, total_bytes=1024, protection_level=level)

        assert "Exceeds protection level file limit" in " ".join(risk.reasons)
        assert risk.score > scorer.score(file_count=200, total_bytes=1024).score

    def test_exceeds_protection_level_size_limit(self) -> None:
        """Test risk when exceeding protection level size limit."""
        level = ProtectionLevel(
            name="test",
            description="Test level",
            max_bytes=1024 * 1024,  # 1 MB
        )

        scorer = RiskScorer()
        risk = scorer.score(
            file_count=10,
            total_bytes=10 * 1024 * 1024,
            protection_level=level,  # 10 MB
        )

        assert "Exceeds protection level size limit" in " ".join(risk.reasons)

    def test_risk_score_capped_at_100(self) -> None:
        """Test that risk score never exceeds 100."""
        level = ProtectionLevel(
            name="test",
            description="Test level",
            max_files=1,
            max_bytes=1,
        )

        scorer = RiskScorer()
        risk = scorer.score(
            file_count=100000,
            total_bytes=100 * 1024 * 1024 * 1024,  # 100 GB
            protection_level=level,
        )

        assert risk.score <= 100

    def test_risk_reasons_descriptive(self) -> None:
        """Test that risk reasons are descriptive."""
        scorer = RiskScorer()
        risk = scorer.score(file_count=150, total_bytes=200 * 1024 * 1024)  # 200 MB

        assert len(risk.reasons) > 0
        assert all(isinstance(r, str) for r in risk.reasons)


class TestPlanGenerator:
    """Tests for PlanGenerator class."""

    @pytest.fixture
    def temp_test_files(self, tmp_path: Path) -> Path:
        """Create temporary test files."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()

        (test_dir / "file1.txt").write_text("Test file 1")
        (test_dir / "file2.txt").write_text("Test file 2")
        (test_dir / "file3.txt").write_text("Test file 3")

        return test_dir

    @pytest.fixture
    def mock_env_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Create mock environment file."""
        env_file = tmp_path / "test.env"
        env_data = {"env": "dev", "signature": "sha256:test"}
        env_file.write_text(json.dumps(env_data))

        # Set environment variable to use this file
        monkeypatch.setenv("RM_ENVIRONMENT", json.dumps(env_data))

        return env_file

    @pytest.fixture
    def lock_manager(self, tmp_path: Path) -> LockManager:
        """Create a LockManager with tmp_path for testing."""
        lock_dir = tmp_path / "locks"
        return LockManager(lock_dir=lock_dir)

    def test_generator_initialization(self, lock_manager) -> None:
        """Test plan generator initialization with defaults."""
        generator = PlanGenerator(lock_manager=lock_manager)

        assert generator.environment_detector is not None
        assert generator.protection_registry is not None
        assert generator.scanner is not None
        assert generator.risk_scorer is not None

    def test_generate_plan_from_single_file(
        self, temp_test_files: Path, mock_env_file: Path, lock_manager: LockManager
    ) -> None:
        """Test generating plan from a single file."""
        single_file = temp_test_files / "file1.txt"

        generator = PlanGenerator(lock_manager=lock_manager)
        plan = generator.generate(targets=[str(single_file)])

        assert plan.plan_id.startswith("plan-")
        assert plan.file_count == 1
        assert plan.total_bytes > 0
        assert plan.environment == "dev"
        assert plan.protection_level == "safe-local"
        assert not plan.validated
        assert not plan.is_expired()

    def test_generate_plan_from_directory(
        self, temp_test_files: Path, mock_env_file: Path, lock_manager
    ) -> None:
        """Test generating plan from a directory."""
        generator = PlanGenerator(lock_manager=lock_manager)
        plan = generator.generate(targets=[str(temp_test_files)])

        assert plan.file_count == 3
        assert plan.total_bytes > 0
        assert plan.risk_score is not None
        assert plan.risk_score.level == RiskLevel.LOW

    def test_generate_plan_with_explicit_environment(
        self, temp_test_files: Path, lock_manager
    ) -> None:
        """Test generating plan with explicit environment."""
        generator = PlanGenerator(lock_manager=lock_manager)
        plan = generator.generate(
            targets=[str(temp_test_files)],
            environment="staging",
        )

        assert plan.environment == "staging"
        assert plan.protection_level == "controlled-team"

    def test_generate_plan_with_explicit_protection_level(
        self, temp_test_files: Path, mock_env_file: Path, lock_manager: LockManager
    ) -> None:
        """Test generating plan with explicit protection level."""
        generator = PlanGenerator(lock_manager=lock_manager)
        plan = generator.generate(
            targets=[str(temp_test_files)],
            protection_level="critical-system",
        )

        assert plan.protection_level == "critical-system"

    def test_generate_plan_with_user_context(
        self, temp_test_files: Path, mock_env_file: Path, lock_manager: LockManager
    ) -> None:
        """Test generating plan with user context."""
        user = UserContext(id="test-user", role="developer", groups=["dev-team"])

        generator = PlanGenerator(lock_manager=lock_manager)
        plan = generator.generate(targets=[str(temp_test_files)], user=user)

        assert plan.user is not None
        assert plan.user.id == "test-user"
        assert plan.user.role == "developer"

    def test_generate_plan_with_scenario(
        self, temp_test_files: Path, mock_env_file: Path, lock_manager
    ) -> None:
        """Test generating plan with scenario description."""
        generator = PlanGenerator(lock_manager=lock_manager)
        plan = generator.generate(
            targets=[str(temp_test_files)],
            scenario="Cleanup old test files",
        )

        assert plan.scenario == "Cleanup old test files"

    def test_generate_plan_with_custom_ttl(
        self, temp_test_files: Path, mock_env_file: Path, lock_manager: LockManager
    ) -> None:
        """Test generating plan with custom TTL."""
        generator = PlanGenerator(lock_manager=lock_manager)
        plan = generator.generate(targets=[str(temp_test_files)], ttl_hours=48)

        assert plan.expires_at is not None
        assert not plan.is_expired()

    def test_generate_plan_with_no_expiration(
        self, temp_test_files: Path, mock_env_file: Path, lock_manager: LockManager
    ) -> None:
        """Test generating plan with no expiration."""
        generator = PlanGenerator(lock_manager=lock_manager)
        plan = generator.generate(targets=[str(temp_test_files)], ttl_hours=None)

        assert plan.expires_at is None
        assert not plan.is_expired()

    def test_generate_dry_run_plan(
        self, temp_test_files: Path, mock_env_file: Path, lock_manager
    ) -> None:
        """Test generating dry-run plan."""
        generator = PlanGenerator(lock_manager=lock_manager)
        plan = generator.generate(targets=[str(temp_test_files)], dry_run=True)

        assert plan.dry_run is True

    def test_generate_multiple_targets(
        self, tmp_path: Path, mock_env_file: Path, lock_manager
    ) -> None:
        """Test generating plan with multiple targets."""
        dir1 = tmp_path / "dir1"
        dir1.mkdir()
        (dir1 / "file1.txt").write_text("File 1")

        dir2 = tmp_path / "dir2"
        dir2.mkdir()
        (dir2 / "file2.txt").write_text("File 2")

        generator = PlanGenerator(lock_manager=lock_manager)
        plan = generator.generate(targets=[str(dir1), str(dir2)])

        assert len(plan.targets) == 2
        assert plan.file_count == 2

    def test_generate_from_paths_convenience(
        self, temp_test_files: Path, mock_env_file: Path, lock_manager: LockManager
    ) -> None:
        """Test generate_from_paths convenience method."""
        generator = PlanGenerator(lock_manager=lock_manager)
        plan = generator.generate_from_paths(str(temp_test_files))

        assert plan.file_count == 3
        assert len(plan.targets) == 1

    def test_generate_no_targets_raises_error(self, mock_env_file: Path, lock_manager) -> None:
        """Test that generating plan with no targets raises error."""
        generator = PlanGenerator(lock_manager=lock_manager)

        with pytest.raises(PlanGeneratorError) as exc_info:
            generator.generate(targets=[])

        assert "At least one target" in str(exc_info.value)

    def test_generate_nonexistent_protection_level_raises_error(
        self, temp_test_files: Path, mock_env_file: Path, lock_manager: LockManager
    ) -> None:
        """Test that invalid protection level raises error."""
        from rmrf.protection import ProtectionLevelError

        generator = PlanGenerator(lock_manager=lock_manager)

        with pytest.raises(ProtectionLevelError):
            generator.generate(
                targets=[str(temp_test_files)],
                protection_level="nonexistent-level",
            )

    def test_generate_plan_includes_risk_score(
        self, temp_test_files: Path, mock_env_file: Path, lock_manager: LockManager
    ) -> None:
        """Test that generated plan includes risk score."""
        generator = PlanGenerator(lock_manager=lock_manager)
        plan = generator.generate(targets=[str(temp_test_files)])

        assert plan.risk_score is not None
        assert isinstance(plan.risk_score.level, RiskLevel)
        assert 0 <= plan.risk_score.score <= 100
        assert len(plan.risk_score.reasons) > 0

    def test_plan_serialization(
        self, temp_test_files: Path, mock_env_file: Path, lock_manager
    ) -> None:
        """Test that generated plan can be serialized to JSON."""
        generator = PlanGenerator(lock_manager=lock_manager)
        plan = generator.generate(targets=[str(temp_test_files)])

        # Serialize
        plan_json = plan.model_dump_json()

        # Deserialize
        from rmrf.models import Plan

        loaded_data = json.loads(plan_json)
        loaded_plan = Plan(**loaded_data)

        assert loaded_plan.plan_id == plan.plan_id
        assert loaded_plan.file_count == plan.file_count

    def test_large_directory_risk_scoring(
        self, tmp_path: Path, mock_env_file: Path, lock_manager
    ) -> None:
        """Test risk scoring for large directory."""
        large_dir = tmp_path / "large"
        large_dir.mkdir()

        # Create 1000 files
        for i in range(1000):
            (large_dir / f"file{i}.txt").write_text(f"Content {i}")

        generator = PlanGenerator(lock_manager=lock_manager)
        plan = generator.generate(targets=[str(large_dir)])

        assert plan.file_count == 1000
        assert plan.risk_score.level in [RiskLevel.MEDIUM, RiskLevel.HIGH]

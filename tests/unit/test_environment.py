"""
Unit tests for rmrf.environment.

Tests environment detection and validation.
"""

import json
from pathlib import Path

import pytest

from rmrf.environment import EnvironmentDetector, EnvironmentError
from rmrf.models import Environment


class TestEnvironmentDetector:
    """Tests for EnvironmentDetector class."""

    def test_detect_from_env_variable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test detecting environment from environment variable."""
        env_data = json.dumps({"env": "prod", "signature": "sha256:abc123"})
        monkeypatch.setenv("RM_ENVIRONMENT", env_data)

        detector = EnvironmentDetector()
        environment = detector.detect()

        assert environment.env == "prod"
        assert environment.signature == "sha256:abc123"

    def test_detect_from_file(self, tmp_path: Path) -> None:
        """Test detecting environment from file."""
        env_file = tmp_path / "test.env"
        env_data = {"env": "staging", "signature": "sha256:def456"}
        env_file.write_text(json.dumps(env_data))

        detector = EnvironmentDetector(paths=[env_file])
        environment = detector.detect()

        assert environment.env == "staging"
        assert environment.signature == "sha256:def456"

    def test_env_variable_takes_precedence(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that environment variable takes precedence over files."""
        # Create file with one environment
        env_file = tmp_path / "test.env"
        file_data = {"env": "dev", "signature": "sha256:file"}
        env_file.write_text(json.dumps(file_data))

        # Set environment variable with different environment
        env_var_data = json.dumps({"env": "prod", "signature": "sha256:env"})
        monkeypatch.setenv("TEST_ENV", env_var_data)

        detector = EnvironmentDetector(env_var="TEST_ENV", paths=[env_file])
        environment = detector.detect()

        # Should use environment variable value
        assert environment.env == "prod"
        assert environment.signature == "sha256:env"

    def test_checks_multiple_paths_in_order(self, tmp_path: Path) -> None:
        """Test that detector checks multiple paths in order."""
        file1 = tmp_path / "first.env"
        file2 = tmp_path / "second.env"

        # Only create second file
        file2_data = {"env": "ops", "signature": "sha256:second"}
        file2.write_text(json.dumps(file2_data))

        detector = EnvironmentDetector(paths=[file1, file2])
        environment = detector.detect()

        # Should find second file
        assert environment.env == "ops"

    def test_missing_environment_raises_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that missing environment raises EnvironmentError."""
        # Ensure environment variable is not set
        monkeypatch.delenv("RM_ENVIRONMENT", raising=False)

        # Use non-existent paths
        nonexistent = tmp_path / "does_not_exist.env"

        detector = EnvironmentDetector(paths=[nonexistent])

        with pytest.raises(EnvironmentError) as exc_info:
            detector.detect()

        assert "Environment metadata not found" in str(exc_info.value)
        assert "does_not_exist.env" in str(exc_info.value)

    def test_invalid_json_continues_to_next_path(self, tmp_path: Path) -> None:
        """Test that invalid JSON in first file causes check of next file."""
        file1 = tmp_path / "invalid.env"
        file2 = tmp_path / "valid.env"

        # First file has invalid JSON
        file1.write_text("{invalid json")

        # Second file is valid
        file2_data = {"env": "dev", "signature": "sha256:valid"}
        file2.write_text(json.dumps(file2_data))

        detector = EnvironmentDetector(paths=[file1, file2])
        environment = detector.detect()

        # Should successfully parse second file
        assert environment.env == "dev"

    def test_invalid_json_in_env_variable_raises_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that invalid JSON in environment variable raises error."""
        monkeypatch.setenv("RM_ENVIRONMENT", "{invalid json")

        detector = EnvironmentDetector()

        with pytest.raises(EnvironmentError) as exc_info:
            detector.detect()

        assert "Invalid JSON" in str(exc_info.value)

    def test_missing_required_fields_raises_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that missing required fields raises error."""
        # Missing 'env' field
        env_data = json.dumps({"signature": "sha256:abc123"})
        monkeypatch.setenv("RM_ENVIRONMENT", env_data)

        detector = EnvironmentDetector()

        with pytest.raises(EnvironmentError) as exc_info:
            detector.detect()

        assert "Invalid environment metadata" in str(exc_info.value)

    def test_environment_without_signature(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test environment can be detected without signature."""
        env_data = json.dumps({"env": "dev"})
        monkeypatch.setenv("RM_ENVIRONMENT", env_data)

        detector = EnvironmentDetector()
        environment = detector.detect()

        assert environment.env == "dev"
        assert environment.signature is None

    def test_environment_name_normalized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that environment name is normalized to lowercase."""
        env_data = json.dumps({"env": "PRODUCTION"})
        monkeypatch.setenv("RM_ENVIRONMENT", env_data)

        detector = EnvironmentDetector()
        environment = detector.detect()

        assert environment.env == "production"

    def test_verify_signature_with_valid_format(self) -> None:
        """Test signature verification with valid format."""
        detector = EnvironmentDetector()
        env = Environment(env="prod", signature="sha256:abc123")

        assert detector.verify_signature(env) is True

    def test_verify_signature_with_invalid_format(self) -> None:
        """Test signature verification with invalid format."""
        detector = EnvironmentDetector()
        env = Environment(env="prod", signature="invalid_format")

        # Should fail for invalid format
        assert detector.verify_signature(env) is False

    def test_verify_signature_without_signature(self) -> None:
        """Test signature verification when no signature present."""
        detector = EnvironmentDetector()
        env = Environment(env="dev")

        # Should pass when no signature
        assert detector.verify_signature(env) is True

    def test_whitespace_trimmed_from_file(self, tmp_path: Path) -> None:
        """Test that whitespace is trimmed from file content."""
        env_file = tmp_path / "whitespace.env"
        env_data = {"env": "dev"}
        # Add extra whitespace
        env_file.write_text(f"\n\n  {json.dumps(env_data)}  \n\n")

        detector = EnvironmentDetector(paths=[env_file])
        environment = detector.detect()

        assert environment.env == "dev"

    def test_custom_env_variable_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test using custom environment variable name."""
        env_data = json.dumps({"env": "custom"})
        monkeypatch.setenv("CUSTOM_ENV_VAR", env_data)

        detector = EnvironmentDetector(env_var="CUSTOM_ENV_VAR")
        environment = detector.detect()

        assert environment.env == "custom"

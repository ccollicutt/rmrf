"""
Unit tests for rmrf.protection.

Tests protection level loading and registry.
"""

from pathlib import Path

import pytest

from rmrf.models import ProtectionLevel
from rmrf.protection import ProtectionLevelError, ProtectionLevelRegistry


class TestProtectionLevelRegistry:
    """Tests for ProtectionLevelRegistry class."""

    def test_load_builtin_levels(self) -> None:
        """Test that built-in protection levels are loaded."""
        registry = ProtectionLevelRegistry(load_defaults=True)

        # Should have 5 default levels
        assert registry.count() == 5

        # Check specific levels
        assert registry.get("safe-local") is not None
        assert registry.get("controlled-team") is not None
        assert registry.get("guarded-ops") is not None
        assert registry.get("critical-system") is not None
        assert registry.get("simulation-only") is not None

    def test_builtin_level_properties(self) -> None:
        """Test properties of built-in levels."""
        registry = ProtectionLevelRegistry(load_defaults=True)

        # Safe-Local level
        safe_local = registry.get("safe-local")
        assert safe_local is not None
        assert safe_local.name == "safe-local"
        assert safe_local.default_environment == "dev"
        assert safe_local.require_backup is False
        assert safe_local.retention_days == 3

        # Critical-System level
        critical = registry.get("critical-system")
        assert critical is not None
        assert critical.name == "critical-system"
        assert critical.default_environment == "prod"
        assert critical.require_backup is True
        assert critical.require_confirmation is True
        assert critical.retention_days == 30
        assert critical.max_files == 1000

    def test_get_by_environment(self) -> None:
        """Test looking up protection level by environment."""
        registry = ProtectionLevelRegistry(load_defaults=True)

        # Should map environments to levels
        dev_level = registry.get_by_environment("dev")
        assert dev_level is not None
        assert dev_level.name == "safe-local"

        prod_level = registry.get_by_environment("prod")
        assert prod_level is not None
        assert prod_level.name == "critical-system"

        staging_level = registry.get_by_environment("staging")
        assert staging_level is not None
        assert staging_level.name == "controlled-team"

    def test_get_nonexistent_level(self) -> None:
        """Test getting non-existent level returns None."""
        registry = ProtectionLevelRegistry(load_defaults=True)
        assert registry.get("does-not-exist") is None

    def test_get_by_nonexistent_environment(self) -> None:
        """Test getting by non-existent environment returns None."""
        registry = ProtectionLevelRegistry(load_defaults=True)
        assert registry.get_by_environment("unknown-env") is None

    def test_require_existing_level(self) -> None:
        """Test require() returns level for existing name."""
        registry = ProtectionLevelRegistry(load_defaults=True)
        level = registry.require("safe-local")
        assert level.name == "safe-local"

    def test_require_nonexistent_level_raises_error(self) -> None:
        """Test require() raises error for non-existent level."""
        registry = ProtectionLevelRegistry(load_defaults=True)

        with pytest.raises(ProtectionLevelError) as exc_info:
            registry.require("does-not-exist")

        assert "not found" in str(exc_info.value)
        assert "does-not-exist" in str(exc_info.value)

    def test_list_names(self) -> None:
        """Test listing all level names."""
        registry = ProtectionLevelRegistry(load_defaults=True)
        names = registry.list_names()

        assert len(names) == 5
        assert "safe-local" in names
        assert "critical-system" in names
        # Should be sorted
        assert names == sorted(names)

    def test_list_all(self) -> None:
        """Test listing all levels."""
        registry = ProtectionLevelRegistry(load_defaults=True)
        levels = registry.list_all()

        assert len(levels) == 5
        assert all(isinstance(level, ProtectionLevel) for level in levels)

    def test_register_custom_level(self) -> None:
        """Test registering a custom protection level."""
        registry = ProtectionLevelRegistry(load_defaults=False)

        custom = ProtectionLevel(
            name="custom-level",
            description="Custom protection level",
            default_environment="custom",
        )

        registry.register(custom)

        assert registry.count() == 1
        assert registry.get("custom-level") == custom
        assert registry.get_by_environment("custom") == custom

    def test_load_from_yaml_file(self, tmp_path: Path) -> None:
        """Test loading protection level from YAML file."""
        yaml_file = tmp_path / "custom.yaml"
        yaml_content = """
name: custom-strict
description: Custom strict level
default_environment: custom
max_files: 500
require_backup: true
require_audit: true
retention_days: 60
"""
        yaml_file.write_text(yaml_content)

        registry = ProtectionLevelRegistry(
            levels_dir=tmp_path,
            load_defaults=False,
        )

        assert registry.count() == 1
        level = registry.get("custom-strict")
        assert level is not None
        assert level.max_files == 500
        assert level.retention_days == 60

    def test_load_from_directory(self, tmp_path: Path) -> None:
        """Test loading multiple YAML files from directory."""
        # Create multiple YAML files
        (tmp_path / "level1.yaml").write_text(
            """
name: level-one
description: First level
"""
        )
        (tmp_path / "level2.yml").write_text(
            """
name: level-two
description: Second level
"""
        )

        registry = ProtectionLevelRegistry(
            levels_dir=tmp_path,
            load_defaults=False,
        )

        assert registry.count() == 2
        assert registry.get("level-one") is not None
        assert registry.get("level-two") is not None

    def test_custom_levels_override_defaults(self, tmp_path: Path) -> None:
        """Test that custom levels can override default levels."""
        yaml_file = tmp_path / "override.yaml"
        yaml_content = """
name: safe-local
description: Overridden safe-local level
max_files: 9999
retention_days: 99
"""
        yaml_file.write_text(yaml_content)

        registry = ProtectionLevelRegistry(
            levels_dir=tmp_path,
            load_defaults=True,
        )

        # Should have overridden the default
        level = registry.get("safe-local")
        assert level is not None
        assert level.description == "Overridden safe-local level"
        assert level.max_files == 9999
        assert level.retention_days == 99

    def test_invalid_yaml_file_continues_loading(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test that invalid YAML file doesn't stop loading other files."""
        # Create one invalid and one valid file
        (tmp_path / "invalid.yaml").write_text("invalid: yaml: content:")
        (tmp_path / "valid.yaml").write_text(
            """
name: valid-level
description: Valid level
"""
        )

        registry = ProtectionLevelRegistry(
            levels_dir=tmp_path,
            load_defaults=False,
        )

        # Should have loaded the valid file
        assert registry.count() == 1
        assert registry.get("valid-level") is not None

        # Should have printed warning about invalid file
        captured = capsys.readouterr()
        assert "Warning" in captured.out
        assert "invalid.yaml" in captured.out

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        """Test that non-existent directory doesn't cause error."""
        nonexistent = tmp_path / "does_not_exist"

        # Should not raise error
        registry = ProtectionLevelRegistry(
            levels_dir=nonexistent,
            load_defaults=False,
        )

        assert registry.count() == 0

    def test_case_insensitive_lookup(self) -> None:
        """Test that level lookup is case-insensitive."""
        registry = ProtectionLevelRegistry(load_defaults=True)

        # Should find level regardless of case
        assert registry.get("safe-local") is not None
        assert registry.get("SAFE-LOCAL") is not None
        assert registry.get("Safe-Local") is not None

    def test_environment_lookup_case_insensitive(self) -> None:
        """Test that environment lookup is case-insensitive."""
        registry = ProtectionLevelRegistry(load_defaults=True)

        # Should find level regardless of environment case
        assert registry.get_by_environment("prod") is not None
        assert registry.get_by_environment("PROD") is not None
        assert registry.get_by_environment("Prod") is not None

    def test_simulation_only_level(self) -> None:
        """Test simulation-only protection level."""
        registry = ProtectionLevelRegistry(load_defaults=True)

        sim_level = registry.get("simulation-only")
        assert sim_level is not None
        assert sim_level.allow_simulation_only is True
        assert sim_level.default_environment == "twin"

    def test_yaml_file_with_all_fields(self, tmp_path: Path) -> None:
        """Test loading YAML file with all possible fields."""
        yaml_file = tmp_path / "complete.yaml"
        yaml_content = """
name: complete-level
description: Level with all fields
default_environment: complete
max_files: 1234
max_bytes: 5678
require_backup: false
require_audit: false
require_confirmation: true
retention_days: 42
allow_simulation_only: true
"""
        yaml_file.write_text(yaml_content)

        registry = ProtectionLevelRegistry(
            levels_dir=tmp_path,
            load_defaults=False,
        )

        level = registry.get("complete-level")
        assert level is not None
        assert level.max_files == 1234
        assert level.max_bytes == 5678
        assert level.require_backup is False
        assert level.require_confirmation is True
        assert level.retention_days == 42
        assert level.allow_simulation_only is True

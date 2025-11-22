"""
Protection level management and loading.

Loads protection levels from YAML files and provides registry.
"""

from pathlib import Path

import yaml

from rmrf.models import ProtectionLevel


class ProtectionLevelError(Exception):
    """Raised when protection level cannot be loaded or found."""

    pass


class ProtectionLevelRegistry:
    """
    Registry for protection levels.

    Loads levels from YAML files and provides lookup by name or environment.
    """

    DEFAULT_LEVELS_DIR = Path("/etc/rmrf/protection_levels.d")

    def __init__(
        self,
        levels_dir: Path | None = None,
        load_defaults: bool = True,
    ) -> None:
        """
        Initialize protection level registry.

        Args:
            levels_dir: Directory containing YAML level definitions
            load_defaults: Whether to load default protection levels
        """
        self.levels_dir = levels_dir if levels_dir is not None else self.DEFAULT_LEVELS_DIR
        self._levels: dict[str, ProtectionLevel] = {}
        self._env_mapping: dict[str, str] = {}

        if load_defaults:
            self._load_builtin_levels()

        if self.levels_dir.exists():
            self._load_from_directory(self.levels_dir)

    def _load_builtin_levels(self) -> None:
        """Load built-in default protection levels."""
        defaults = [
            ProtectionLevel(
                name="safe-local",
                description="Minimal restrictions; rollback optional",
                default_environment="dev",
                max_files=None,
                max_bytes=None,
                require_backup=False,
                require_audit=False,
                require_confirmation=False,
                retention_days=3,
                allow_simulation_only=False,
            ),
            ProtectionLevel(
                name="controlled-team",
                description="Rollback required; one confirmation",
                default_environment="staging",
                max_files=10000,
                max_bytes=10 * 1024 * 1024 * 1024,  # 10 GB
                require_backup=True,
                require_audit=True,
                require_confirmation=True,
                retention_days=7,
                allow_simulation_only=False,
            ),
            ProtectionLevel(
                name="guarded-ops",
                description="Approval workflow; audit required",
                default_environment="ops",
                max_files=5000,
                max_bytes=5 * 1024 * 1024 * 1024,  # 5 GB
                require_backup=True,
                require_audit=True,
                require_confirmation=True,
                retention_days=14,
                allow_simulation_only=False,
            ),
            ProtectionLevel(
                name="critical-system",
                description="Dual confirmation; backup + audit required",
                default_environment="prod",
                max_files=1000,
                max_bytes=1 * 1024 * 1024 * 1024,  # 1 GB
                require_backup=True,
                require_audit=True,
                require_confirmation=True,
                retention_days=30,
                allow_simulation_only=False,
            ),
            ProtectionLevel(
                name="simulation-only",
                description="Dry-run only; no actual deletion",
                default_environment="twin",
                max_files=None,
                max_bytes=None,
                require_backup=True,
                require_audit=True,
                require_confirmation=False,
                retention_days=7,
                allow_simulation_only=True,
            ),
        ]

        for level in defaults:
            self.register(level)

    def _load_from_directory(self, directory: Path) -> None:
        """
        Load protection levels from YAML files in directory.

        Args:
            directory: Directory containing *.yaml files
        """
        if not directory.is_dir():
            return

        for yaml_file in directory.glob("*.yaml"):
            try:
                self._load_from_file(yaml_file)
            except Exception as e:
                # Log warning but continue loading other files
                print(f"Warning: Failed to load {yaml_file}: {e}")

        for yml_file in directory.glob("*.yml"):
            try:
                self._load_from_file(yml_file)
            except Exception as e:
                print(f"Warning: Failed to load {yml_file}: {e}")

    def _load_from_file(self, file_path: Path) -> None:
        """
        Load protection level from YAML file.

        Args:
            file_path: Path to YAML file

        Raises:
            ProtectionLevelError: If file cannot be parsed
        """
        try:
            with open(file_path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ProtectionLevelError(f"Invalid YAML in {file_path}: {e}") from e
        except OSError as e:
            raise ProtectionLevelError(f"Cannot read {file_path}: {e}") from e

        if not isinstance(data, dict):
            raise ProtectionLevelError(f"Expected dict in {file_path}, got {type(data)}")

        try:
            level = ProtectionLevel(**data)
            self.register(level)
        except Exception as e:
            raise ProtectionLevelError(f"Invalid protection level in {file_path}: {e}") from e

    def register(self, level: ProtectionLevel) -> None:
        """
        Register a protection level.

        Args:
            level: ProtectionLevel to register
        """
        self._levels[level.name] = level

        # Map environment to level if specified
        if level.default_environment:
            self._env_mapping[level.default_environment] = level.name

    def get(self, name: str) -> ProtectionLevel | None:
        """
        Get protection level by name.

        Args:
            name: Protection level name

        Returns:
            ProtectionLevel or None if not found
        """
        return self._levels.get(name.lower())

    def get_by_environment(self, env: str) -> ProtectionLevel | None:
        """
        Get protection level by environment name.

        Args:
            env: Environment name

        Returns:
            ProtectionLevel or None if no mapping exists
        """
        level_name = self._env_mapping.get(env.lower())
        if level_name:
            return self.get(level_name)
        return None

    def require(self, name: str) -> ProtectionLevel:
        """
        Get protection level by name, raising error if not found.

        Args:
            name: Protection level name

        Returns:
            ProtectionLevel

        Raises:
            ProtectionLevelError: If level not found
        """
        level = self.get(name)
        if level is None:
            raise ProtectionLevelError(
                f"Protection level '{name}' not found. "
                f"Available levels: {', '.join(self.list_names())}"
            )
        return level

    def list_names(self) -> list[str]:
        """
        List all registered protection level names.

        Returns:
            List of level names
        """
        return sorted(self._levels.keys())

    def list_all(self) -> list[ProtectionLevel]:
        """
        List all registered protection levels.

        Returns:
            List of ProtectionLevel objects
        """
        return [self._levels[name] for name in self.list_names()]

    def count(self) -> int:
        """
        Get count of registered protection levels.

        Returns:
            Number of levels
        """
        return len(self._levels)

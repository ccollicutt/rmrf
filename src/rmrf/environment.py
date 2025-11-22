"""
Environment detection and verification.

Reads environment metadata from files or environment variables.
"""

import json
import os
from pathlib import Path

from rmrf.models import Environment


class EnvironmentError(Exception):
    """Raised when environment cannot be determined or verified."""

    pass


class EnvironmentDetector:
    """
    Detects and validates the current environment.

    Reads from (in order of precedence):
    1. $RM_ENVIRONMENT environment variable
    2. /etc/rmrf.env
    3. /etc/system.env
    """

    DEFAULT_PATHS = [
        Path("/etc/rmrf.env"),
        Path("/etc/system.env"),
    ]

    def __init__(
        self,
        env_var: str = "RM_ENVIRONMENT",
        paths: list[Path] | None = None,
    ) -> None:
        """
        Initialize environment detector.

        Args:
            env_var: Environment variable name to check
            paths: List of file paths to check (defaults to DEFAULT_PATHS)
        """
        self.env_var = env_var
        self.paths = paths if paths is not None else self.DEFAULT_PATHS

    def detect(self) -> Environment:
        """
        Detect and validate environment.

        Returns:
            Environment object with metadata

        Raises:
            EnvironmentError: If environment cannot be determined
        """
        # Try environment variable first
        env_value = os.environ.get(self.env_var)
        if env_value:
            return self._parse_environment(env_value, source=f"${self.env_var}")

        # Try each file path
        for path in self.paths:
            if path.exists():
                try:
                    content = path.read_text().strip()
                    return self._parse_environment(content, source=str(path))
                except (OSError, EnvironmentError):
                    # Continue to next path on error
                    continue

        # No valid environment found
        raise EnvironmentError(
            f"Environment metadata not found. Checked:\n"
            f"  - ${self.env_var}\n"
            + "\n".join(f"  - {p}" for p in self.paths)
            + "\n\nrmrf requires valid environment metadata to operate safely."
        )

    def _parse_environment(self, content: str, source: str) -> Environment:
        """
        Parse environment JSON string.

        Args:
            content: JSON string with environment metadata
            source: Source description for error messages

        Returns:
            Validated Environment object

        Raises:
            EnvironmentError: If parsing or validation fails
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise EnvironmentError(
                f"Invalid JSON in environment metadata from {source}: {e}"
            ) from e

        try:
            return Environment(**data)
        except Exception as e:
            raise EnvironmentError(f"Invalid environment metadata from {source}: {e}") from e

    def verify_signature(self, environment: Environment) -> bool:
        """
        Verify environment signature (placeholder for future implementation).

        Args:
            environment: Environment to verify

        Returns:
            True if signature is valid or not present
        """
        # TODO: Implement Ed25519 signature verification
        # For now, just check if signature is present and formatted correctly
        if environment.signature:
            if not environment.signature.startswith("sha256:"):
                return False
        return True

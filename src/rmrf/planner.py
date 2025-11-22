"""
Plan generation and risk scoring.

Creates deletion plans from targets with risk assessment.
"""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from rmrf.environment import EnvironmentDetector
from rmrf.locking import LockManager
from rmrf.models import Plan, ProtectionLevel, RiskLevel, RiskScore, UserContext
from rmrf.protection import ProtectionLevelRegistry
from rmrf.scanner import PathScanner


class PlanGeneratorError(Exception):
    """Raised when plan generation fails."""

    pass


class RiskScorer:
    """
    Calculates risk scores for deletion plans.

    Risk is based on:
    - File count
    - Total size
    - Protection level limits
    - Path sensitivity
    """

    # Risk thresholds
    LOW_RISK_FILES = 100
    MEDIUM_RISK_FILES = 1000
    HIGH_RISK_FILES = 5000

    LOW_RISK_BYTES = 100 * 1024 * 1024  # 100 MB
    MEDIUM_RISK_BYTES = 1024 * 1024 * 1024  # 1 GB
    HIGH_RISK_BYTES = 10 * 1024 * 1024 * 1024  # 10 GB

    def score(
        self,
        file_count: int,
        total_bytes: int,
        protection_level: ProtectionLevel | None = None,
    ) -> RiskScore:
        """
        Calculate risk score for a deletion plan.

        Args:
            file_count: Number of files to delete
            total_bytes: Total size in bytes
            protection_level: Protection level (for limit comparison)

        Returns:
            RiskScore with level, numeric score, and reasons
        """
        reasons: list[str] = []
        score = 0

        # Score based on file count
        if file_count == 0:
            score += 0
            reasons.append("No files to delete")
        elif file_count < self.LOW_RISK_FILES:
            score += 10
            reasons.append("Small file count")
        elif file_count < self.MEDIUM_RISK_FILES:
            score += 30
            reasons.append("Moderate file count")
        elif file_count < self.HIGH_RISK_FILES:
            score += 50
            reasons.append("Large file count")
        else:
            score += 70
            reasons.append("Very large file count")

        # Score based on total size
        if total_bytes == 0:
            score += 0
        elif total_bytes < self.LOW_RISK_BYTES:
            score += 5
            reasons.append("Small total size")
        elif total_bytes < self.MEDIUM_RISK_BYTES:
            score += 15
            reasons.append("Moderate total size")
        elif total_bytes < self.HIGH_RISK_BYTES:
            score += 25
            reasons.append("Large total size")
        else:
            score += 35
            reasons.append("Very large total size")

        # Check against protection level limits
        if protection_level:
            if protection_level.max_files and file_count > protection_level.max_files:
                score += 20
                reasons.append(
                    f"Exceeds protection level file limit ({protection_level.max_files})"
                )

            if protection_level.max_bytes and total_bytes > protection_level.max_bytes:
                score += 20
                reasons.append(
                    f"Exceeds protection level size limit ({protection_level.max_bytes} bytes)"
                )

        # Determine risk level
        if score == 0:
            level = RiskLevel.LOW
        elif score < 30:
            level = RiskLevel.LOW
        elif score < 60:
            level = RiskLevel.MEDIUM
        elif score < 85:
            level = RiskLevel.HIGH
        else:
            level = RiskLevel.CRITICAL

        # Cap score at 100
        score = min(score, 100)

        return RiskScore(level=level, score=score, reasons=reasons)


class PlanGenerator:
    """
    Generates deletion plans from target paths.

    Combines scanning, risk scoring, and plan creation.
    """

    def __init__(
        self,
        environment_detector: EnvironmentDetector | None = None,
        protection_registry: ProtectionLevelRegistry | None = None,
        scanner: PathScanner | None = None,
        risk_scorer: RiskScorer | None = None,
        lock_manager: LockManager | None = None,
    ) -> None:
        """
        Initialize plan generator.

        Args:
            environment_detector: Environment detector (creates default if None)
            protection_registry: Protection level registry (creates default if None)
            scanner: Path scanner (creates default if None)
            risk_scorer: Risk scorer (creates default if None)
            lock_manager: Lock manager (creates default if None)
        """
        self.environment_detector = environment_detector or EnvironmentDetector()
        self.protection_registry = protection_registry or ProtectionLevelRegistry(
            load_defaults=True
        )
        self.scanner = scanner or PathScanner(skip_errors=True)
        self.risk_scorer = risk_scorer or RiskScorer()
        self.lock_manager = lock_manager or LockManager()

    def generate(
        self,
        targets: list[str],
        environment: str | None = None,
        protection_level: str | None = None,
        user: UserContext | None = None,
        scenario: str | None = None,
        ttl_hours: int | None = 24,
        dry_run: bool = False,
    ) -> Plan:
        """
        Generate a deletion plan from target paths.

        Args:
            targets: List of paths to delete
            environment: Environment name (auto-detected if None)
            protection_level: Protection level name (derived from env if None)
            user: User context
            scenario: Scenario description
            ttl_hours: Plan expiration time in hours (None for no expiration)
            dry_run: Whether this is a dry-run plan

        Returns:
            Complete Plan object

        Raises:
            PlanGeneratorError: If plan generation fails
        """
        if not targets:
            raise PlanGeneratorError("At least one target must be specified")

        # Detect environment if not provided
        if environment is None:
            try:
                env = self.environment_detector.detect()
                environment = env.env
            except Exception as e:
                raise PlanGeneratorError(f"Failed to detect environment: {e}") from e

        # Determine protection level
        if protection_level is None:
            level = self.protection_registry.get_by_environment(environment)
            if level is None:
                # Fall back to safe-local if no mapping exists
                level = self.protection_registry.require("safe-local")
            protection_level = level.name
        else:
            level = self.protection_registry.require(protection_level)

        # Scan all targets
        target_paths = [Path(t) for t in targets]
        scan_result = self.scanner.scan_multiple(target_paths)

        # Calculate risk score
        risk_score = self.risk_scorer.score(
            file_count=scan_result.file_count,
            total_bytes=scan_result.total_bytes,
            protection_level=level,
        )

        # Generate plan ID with target descriptor
        target_desc = self._generate_target_descriptor(targets)
        date_stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        plan_id = f"plan-{target_desc}-{date_stamp}-{uuid.uuid4().hex[:8]}"

        # Calculate expiration
        expires_at = None
        if ttl_hours is not None:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

        # Create plan
        plan = Plan(
            plan_id=plan_id,
            environment=environment,
            protection_level=protection_level,
            targets=targets,
            file_count=scan_result.file_count,
            total_bytes=scan_result.total_bytes,
            risk_score=risk_score,
            user=user,
            scenario=scenario,
            expires_at=expires_at,
            dry_run=dry_run,
        )

        # Acquire lock on first target directory (canonical path)
        # This prevents concurrent operations on the same directory
        try:
            first_target = Path(targets[0])
            lock = self.lock_manager.acquire_lock(first_target, plan_id)
            plan.lock_id = lock.lock_id
        except Exception as e:
            # Lock acquisition failed - clean up and raise
            raise PlanGeneratorError(f"Failed to acquire lock: {e}") from e

        return plan

    def _generate_target_descriptor(self, targets: list[str]) -> str:
        """
        Generate a short, filesystem-safe descriptor from targets.

        Args:
            targets: List of target paths

        Returns:
            Sanitized descriptor string (max 30 chars)
        """
        if not targets:
            return "empty"

        # Use first target for single target, or summarize for multiple
        if len(targets) == 1:
            target = targets[0]
        else:
            # Multiple targets - use count
            return f"{len(targets)}-targets"

        # Extract meaningful part of path
        path = Path(target)

        # Use last 2 path components for depth, or just name if short path
        parts = path.parts
        if len(parts) >= 2:
            # Take last 2 parts: /var/log/old-logs -> log-old-logs
            desc = "-".join(parts[-2:])
        else:
            # Just the name
            desc = path.name or "root"

        # Sanitize: keep only alphanumeric, dash, underscore
        desc = "".join(c if c.isalnum() or c in "-_" else "-" for c in desc)

        # Remove leading/trailing dashes and collapse multiple dashes
        desc = "-".join(filter(None, desc.split("-")))

        # Limit length
        if len(desc) > 30:
            desc = desc[:30].rstrip("-")

        # Ensure we have something
        return desc if desc else "target"

    def generate_from_paths(
        self,
        *paths: str,
        **kwargs: Any,
    ) -> Plan:
        """
        Generate plan from paths (convenience method).

        Args:
            *paths: Variable number of path strings
            **kwargs: Additional arguments passed to generate()

        Returns:
            Plan object
        """
        return self.generate(targets=list(paths), **kwargs)

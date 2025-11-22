"""
Built-in validation logic for deletion plans.

Implements the same validation rules as the OPA policy (policies/deletion.rego)
but with pure Python logic. This provides robust validation without requiring
an external OPA server.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

from rmrf.models import Plan, PolicyVerdict, ProtectionLevel, RiskLevel, Verdict


class BuiltinValidator:
    """
    Built-in policy validator that implements deletion safety rules.

    This validator replicates the logic from policies/deletion.rego to provide
    production-ready validation without requiring OPA.
    """

    # Protected paths that rmrf should never delete
    PROTECTED_PATHS = [
        "/var/lib/rmrf",  # Main rmrf data directory
        "/etc/rmrf",  # Configuration directory
    ]

    def validate(
        self,
        plan: Plan,
        protection_level: ProtectionLevel,
        approval_id: str | None = None,
    ) -> PolicyVerdict:
        """
        Validate a deletion plan against built-in safety rules.

        Args:
            plan: The deletion plan to validate
            protection_level: Protection level configuration
            approval_id: Optional approval ID if pre-approved

        Returns:
            PolicyVerdict with allow/deny/require_approval decision

        Validation Rules (from deletion.rego):
        0. Must not target rmrf's own infrastructure
        1. Plan must not be expired
        2. Must not exceed protection level limits
        3. Critical risk requires approval
        4. Production with medium+ risk requires approval
        5. High risk in production requires approval
        """
        reasons: list[str] = []

        # Check 0: Self-protection - do not delete rmrf infrastructure
        self_deletion = self._check_self_deletion(plan)
        if self_deletion:
            return PolicyVerdict(
                verdict=Verdict.DENY,
                message="Cannot delete rmrf infrastructure",
                reasons=self_deletion,
            )

        # Check 1: Plan expiration
        if self._is_expired(plan):
            return PolicyVerdict(
                verdict=Verdict.DENY,
                message="Deletion plan has expired",
                reasons=["Plan has expired and can no longer be executed"],
            )

        # Check 2: Protection level limits
        limit_violations = self._check_protection_limits(plan, protection_level)
        if limit_violations:
            reasons.extend(limit_violations)
            return PolicyVerdict(
                verdict=Verdict.DENY,
                message=f"Deletion exceeds protection level limits for {plan.protection_level}",
                reasons=reasons,
            )

        # Check 3: Critical risk always requires approval
        if plan.risk_score and plan.risk_score.level == RiskLevel.CRITICAL:
            if not approval_id:
                reasons.append("Risk level is CRITICAL")
                return PolicyVerdict(
                    verdict=Verdict.REQUIRE_APPROVAL,
                    message="Critical risk deletions require approval",
                    reasons=reasons,
                )

        # Check 4: High risk in production requires approval
        if (
            plan.risk_score
            and plan.risk_score.level == RiskLevel.HIGH
            and plan.environment == "prod"
        ):
            if not approval_id:
                reasons.append("High risk deletion in production environment")
                return PolicyVerdict(
                    verdict=Verdict.REQUIRE_APPROVAL,
                    message="High risk production deletions require approval",
                    reasons=reasons,
                )

        # Check 5: Production with medium+ risk requires approval (unless dry-run)
        if (
            plan.environment == "prod"
            and plan.risk_score
            and plan.risk_score.level in [RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
            and not plan.dry_run
        ):
            if not approval_id:
                risk_level_str = plan.risk_score.level.value.upper()
                reasons.append(f"Production deletion with {risk_level_str} risk requires review")
                return PolicyVerdict(
                    verdict=Verdict.REQUIRE_APPROVAL,
                    message="Production deletions with medium+ risk require review",
                    reasons=reasons,
                )

        # All checks passed
        reasons.append("All safety checks passed")
        reasons.append(f"Environment: {plan.environment}")
        reasons.append(f"Protection level: {plan.protection_level}")
        if plan.risk_score:
            reasons.append(f"Risk: {plan.risk_score.level.value}")

        return PolicyVerdict(
            verdict=Verdict.ALLOW,
            message="Deletion plan approved by built-in validation",
            reasons=reasons,
        )

    def _is_expired(self, plan: Plan) -> bool:
        """Check if plan has expired."""
        if not plan.expires_at:
            return False

        now = datetime.now(timezone.utc)
        return now > plan.expires_at

    def _check_protection_limits(self, plan: Plan, protection_level: ProtectionLevel) -> list[str]:
        """
        Check if plan exceeds protection level limits.

        Returns list of violation reasons (empty if no violations).
        """
        violations: list[str] = []

        # Check max_files limit
        if protection_level.max_files is not None:
            if plan.file_count > protection_level.max_files:
                violations.append(
                    f"File count ({plan.file_count:,}) exceeds limit "
                    f"({protection_level.max_files:,})"
                )

        # Check max_bytes limit
        if protection_level.max_bytes is not None:
            if plan.total_bytes > protection_level.max_bytes:
                violations.append(
                    f"Total size ({plan.total_bytes:,} bytes) exceeds limit "
                    f"({protection_level.max_bytes:,} bytes)"
                )

        return violations

    def _check_self_deletion(self, plan: Plan) -> list[str]:
        """
        Check if plan targets rmrf's own infrastructure.

        Returns list of reasons if self-deletion detected (empty if safe).
        """
        violations: list[str] = []

        for target_str in plan.targets:
            target = Path(target_str).resolve()

            # Check each protected path
            for protected_str in self.PROTECTED_PATHS:
                protected = Path(protected_str).resolve()

                # Check if target is the protected path or inside it
                try:
                    if target == protected or protected in target.parents:
                        violations.append(
                            f"Target '{target}' would delete rmrf infrastructure at '{protected}'"
                        )
                    # Check if target is a parent of protected path (would contain it)
                    elif target in protected.parents:
                        violations.append(
                            f"Target '{target}' contains rmrf infrastructure at '{protected}'"
                        )
                except (ValueError, OSError):
                    # Path operations can fail for non-existent paths, skip
                    pass

            # Also check for plan directory from environment variable
            plan_dir_env = os.getenv("RMRF_PLAN_DIR")
            if plan_dir_env:
                plan_dir = Path(plan_dir_env).resolve()
                try:
                    if target == plan_dir or plan_dir in target.parents:
                        violations.append(
                            f"Target '{target}' would delete active plan directory at '{plan_dir}'"
                        )
                    elif target in plan_dir.parents:
                        violations.append(
                            f"Target '{target}' contains active plan directory at '{plan_dir}'"
                        )
                except (ValueError, OSError):
                    pass

        return violations

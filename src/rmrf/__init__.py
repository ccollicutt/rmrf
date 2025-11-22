"""
rmrf - Safety-Critical Deletion Utility

A production-safe alternative to `rm -rf` with policy enforcement,
reversible deletion, and comprehensive auditing.
"""

__version__ = "0.1.22"
__author__ = "Curtis"

from rmrf.audit import AuditEmitter, AuditError
from rmrf.backup import BackupError, BackupManager
from rmrf.engine import DeletionEngine, DeletionError
from rmrf.environment import EnvironmentDetector, EnvironmentError
from rmrf.models import (
    AuditEvent,
    Environment,
    EventPhase,
    Plan,
    PolicyVerdict,
    ProtectionLevel,
    RiskLevel,
    RiskScore,
    RollbackManifest,
    UserContext,
    Verdict,
)
from rmrf.planner import PlanGenerator, PlanGeneratorError, RiskScorer
from rmrf.protection import ProtectionLevelError, ProtectionLevelRegistry
from rmrf.scanner import PathScanner, ScanResult
from rmrf.store import PlanStore, PlanStoreError

__all__ = [
    # Models
    "AuditEvent",
    "Environment",
    "EventPhase",
    "Plan",
    "PolicyVerdict",
    "ProtectionLevel",
    "RiskLevel",
    "RiskScore",
    "RollbackManifest",
    "UserContext",
    "Verdict",
    # Environment
    "EnvironmentDetector",
    "EnvironmentError",
    # Protection
    "ProtectionLevelError",
    "ProtectionLevelRegistry",
    # Scanner
    "PathScanner",
    "ScanResult",
    # Planner
    "PlanGenerator",
    "PlanGeneratorError",
    "RiskScorer",
    # Backup
    "BackupManager",
    "BackupError",
    # Engine
    "DeletionEngine",
    "DeletionError",
    # Audit
    "AuditEmitter",
    "AuditError",
    # Store
    "PlanStore",
    "PlanStoreError",
    # Metadata
    "__version__",
    "__author__",
]

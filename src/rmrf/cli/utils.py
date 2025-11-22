"""
CLI utility functions.

Provides helper functions for common CLI operations.
"""

import json
from pathlib import Path

import click

from rmrf.models import Plan
from rmrf.store import PlanStore, PlanStoreError


def load_plan(plan_id_or_path: str, store: PlanStore | None = None) -> Plan:
    """
    Load a plan from either store (by ID) or file (by path).

    Args:
        plan_id_or_path: Plan ID (e.g. "plan-20250107-120000-abc123") or file path (e.g. "plan.json")
        store: Optional PlanStore instance (created if None)

    Returns:
        Plan object

    Raises:
        click.ClickException: If plan cannot be loaded
    """
    # Check if it's a file path
    path = Path(plan_id_or_path)
    if path.exists() and path.is_file():
        try:
            plan_data = json.loads(path.read_text())
            return Plan(**plan_data)
        except (OSError, json.JSONDecodeError, Exception) as e:
            raise click.ClickException(f"Failed to load plan from file: {e}") from e

    # Try loading from store
    if store is None:
        store = PlanStore(auto_create=False)

    try:
        return store.load(plan_id_or_path)
    except PlanStoreError as e:
        raise click.ClickException(f"Failed to load plan: {e}") from e

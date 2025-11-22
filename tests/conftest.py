"""
Pytest configuration for rmrf tests.

Sets up test environment and fixtures.
"""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment(tmp_path_factory):
    """
    Set up test environment for all tests.

    Configures environment variables to use temporary directories
    instead of system directories that require permissions.
    """
    # Create a session-wide temp directory for test infrastructure
    tmpdir = tmp_path_factory.mktemp("rmrf-test-session")

    # Set lock directory to temp location
    lock_dir = tmpdir / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    os.environ["RMRF_LOCK_DIR"] = str(lock_dir)

    # Set plan directory to temp location
    plan_dir = tmpdir / "plans"
    plan_dir.mkdir(parents=True, exist_ok=True)
    os.environ["RMRF_PLAN_DIR"] = str(plan_dir)

    # Set backup directory to temp location
    backup_dir = tmpdir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    os.environ["RMRF_BACKUP_DIR"] = str(backup_dir)

    # Set audit directory to temp location
    audit_dir = tmpdir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    os.environ["RMRF_AUDIT_DIR"] = str(audit_dir)

    yield

    # Cleanup happens automatically when pytest cleans up tmp_path_factory

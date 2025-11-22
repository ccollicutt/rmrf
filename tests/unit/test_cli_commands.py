"""
Unit tests for CLI command completeness.

Ensures all expected commands are registered and available.
"""

import click.testing

from rmrf.cli import cli


class TestCLICommandCompleteness:
    """Test that all expected CLI commands are registered."""

    def test_all_workflow_commands_exist(self):
        """Test that all workflow commands are registered."""
        # Core workflow commands
        workflow_commands = [
            "plan",
            "show",
            "validate",
            "stage",
            "apply",
            "verify",
            "closeout",
            "rollback",
        ]

        registered = [cmd.name for cmd in cli.commands.values()]

        for cmd in workflow_commands:
            assert cmd in registered, f"Workflow command '{cmd}' is not registered"

    def test_all_approval_commands_exist(self):
        """Test that approval workflow commands are registered."""
        approval_commands = [
            "approve",
            "list-pending-approvals",
            "unlock",
        ]

        registered = [cmd.name for cmd in cli.commands.values()]

        for cmd in approval_commands:
            assert cmd in registered, f"Approval command '{cmd}' is not registered"

    def test_all_management_commands_exist(self):
        """Test that management commands are registered."""
        management_commands = [
            "list",
            "status",
            "cleanup",
            "learn",
            "near-miss",
            "mark-failed",
        ]

        registered = [cmd.name for cmd in cli.commands.values()]

        for cmd in management_commands:
            assert cmd in registered, f"Management command '{cmd}' is not registered"

    def test_all_setup_commands_exist(self):
        """Test that setup commands are registered."""
        setup_commands = [
            "init",
            "preflight",
            "shell",
            "about",
        ]

        registered = [cmd.name for cmd in cli.commands.values()]

        for cmd in setup_commands:
            assert cmd in registered, f"Setup command '{cmd}' is not registered"

    def test_minimum_command_count(self):
        """Test that we have the expected minimum number of commands."""
        # This catches accidental removal of commands
        registered = list(cli.commands.keys())

        # We expect at least 20 commands
        assert len(registered) >= 20, (
            f"Expected at least 20 commands, but only found {len(registered)}: {registered}"
        )

    def test_commands_have_help_text(self):
        """Test that all commands have help text."""
        for name, cmd in cli.commands.items():
            assert cmd.help is not None or cmd.callback.__doc__ is not None, (
                f"Command '{name}' has no help text"
            )

    def test_workflow_commands_accept_plan_id(self):
        """Test that workflow commands accept plan_id argument."""
        # Commands that should accept plan_id as first argument
        plan_id_commands = [
            "show",
            "validate",
            "stage",
            "apply",
            "verify",
            "closeout",
            "rollback",
            "approve",
            "unlock",
            "learn",
            "near-miss",
            "mark-failed",
        ]

        for cmd_name in plan_id_commands:
            cmd = cli.commands.get(cmd_name)
            assert cmd is not None, f"Command '{cmd_name}' not found"

            # Check that command has at least one argument (plan_id)
            params = [p for p in cmd.params if isinstance(p, click.Argument)]
            assert len(params) >= 1, f"Command '{cmd_name}' should accept plan_id argument"

    def test_no_duplicate_command_names(self):
        """Test that there are no duplicate command names."""
        names = [cmd.name for cmd in cli.commands.values()]
        duplicates = [name for name in names if names.count(name) > 1]

        assert not duplicates, f"Duplicate command names found: {set(duplicates)}"

    def test_command_names_are_kebab_case(self):
        """Test that multi-word commands use kebab-case."""
        for name in cli.commands.keys():
            # Should not contain underscores (use hyphens instead)
            assert "_" not in name, (
                f"Command '{name}' should use kebab-case (hyphens), not underscores"
            )
            # Should be lowercase
            assert name == name.lower(), f"Command '{name}' should be lowercase"

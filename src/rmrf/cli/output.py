"""
Output utilities for CLI.

Provides logging functions and structured output formatting.
"""

import click

from rmrf.environment import EnvironmentDetector
from rmrf.models import Environment


# Simple log printer (following python.md best practices)
def log_info(msg: str) -> None:
    """Print info message."""
    click.echo(f"[INFO] {msg}", err=True)


def log_success(msg: str) -> None:
    """Print success message."""
    click.secho(f"✓ {msg}", fg="green", err=True)


def log_error(msg: str) -> None:
    """Print error message."""
    click.secho(f"✗ {msg}", fg="red", err=True)


def log_warning(msg: str) -> None:
    """Print warning message."""
    click.secho(f"! {msg}", fg="yellow", err=True)


def print_structured_output(
    verdict: str,
    scenario: str,
    summary: str,
    what_happened: str,
    why_it_matters: str,
    next_steps: list[str],
    audit_id: str | None = None,
    additional_info: dict[str, str] | None = None,
) -> None:
    """
    Print structured, human-readable output with narrative context.

    Args:
        verdict: Status (e.g., "SUCCESS", "ALLOWED", "DENIED", "ERROR")
        scenario: Scenario name/description
        summary: Brief summary of outcome
        what_happened: 1-2 sentences explaining event and outcome
        why_it_matters: 1-2 sentences linking outcome to system safety
        next_steps: List of concrete actions for the user
        audit_id: Optional audit event ID
        additional_info: Optional dict of additional key-value info to display
    """
    # Verdict line with color based on status
    verdict_color = (
        "green"
        if verdict in ["SUCCESS", "ALLOWED", "SAFE"]
        else "red"
        if verdict in ["ERROR", "DENIED", "BLOCKED"]
        else "yellow"
        if verdict in ["WARNING", "REQUIRES_APPROVAL"]
        else "blue"
    )

    click.secho(f"[{verdict}]", fg=verdict_color, bold=True, nl=False)
    click.echo(f" — Scenario '{scenario}' {summary}")
    click.echo()

    # What happened section
    click.secho("What happened:", bold=True)
    click.echo(what_happened)
    click.echo()

    # Why it matters section
    click.secho("Why it matters:", bold=True)
    click.echo(why_it_matters)
    click.echo()

    # Additional information (optional)
    if additional_info:
        for key, value in additional_info.items():
            click.echo(f"{key}: {value}")
        click.echo()

    # Next steps section
    click.secho("Next steps:", bold=True)
    for i, step in enumerate(next_steps, 1):
        click.echo(f"{i}. {step}")
    click.echo()

    # Audit record if available
    if audit_id:
        click.echo(f"Audit record: audit:{audit_id}")
        click.echo()


def format_bytes(bytes_val: int) -> str:
    """Format bytes as human-readable string."""
    val = float(bytes_val)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if val < 1024.0:
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{val:.1f} PB"


def get_risk_color(risk_level: str) -> str:
    """Get color for risk level."""
    colors = {
        "low": "green",
        "medium": "yellow",
        "high": "red",
        "critical": "red",
    }
    return colors.get(risk_level.lower(), "white")


def print_environment_banner(environment: Environment | None = None, force: bool = False) -> None:
    """
    Print environment indicator.

    Shows current environment with color coding:
    - dev: green
    - staging: yellow
    - prod: RED BOLD
    - test/ci: blue
    - unknown: magenta

    Args:
        environment: Environment object (auto-detects if None)
        force: Always print even if detection fails
    """
    if environment is None:
        try:
            detector = EnvironmentDetector()
            environment = detector.detect()
        except Exception:
            if not force:
                return
            # Fallback to unknown
            environment = Environment(env="unknown", signature=None)

    env_name = environment.env.upper()

    # Determine color based on environment
    if env_name in ["PROD", "PRODUCTION"]:
        color = "red"
        bold = True
    elif env_name in ["STAGING", "STAGE", "STG"]:
        color = "yellow"
        bold = True
    elif env_name in ["DEV", "DEVELOPMENT"]:
        color = "green"
        bold = False
    elif env_name in ["TEST", "CI", "TESTING"]:
        color = "blue"
        bold = False
    else:
        color = "magenta"
        bold = True

    # Print simple environment line
    click.secho(f"Environment: {env_name}", fg=color, bold=bold, err=True)
    click.echo(err=True)

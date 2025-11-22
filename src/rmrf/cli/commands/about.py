"""
About command - man page style documentation.

Shows comprehensive information about rmrf.
"""

from pathlib import Path

import click


@click.command()
@click.pass_context
def about(ctx: click.Context) -> None:
    """
    Display comprehensive information about rmrf.

    Shows architecture, workflow, safety features, and usage patterns
    in a man-page style format.
    """
    # Read about text from file
    about_file = Path(__file__).parent / "about.txt"
    about_text = about_file.read_text()

    click.echo("")
    click.echo(about_text)

"""
Command-line interface for rmrf.

This module provides backward compatibility by importing from the new CLI structure.
"""

from rmrf.cli import cli, main

__all__ = ["cli", "main"]

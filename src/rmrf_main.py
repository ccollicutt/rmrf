#!/usr/bin/env python3
"""
PyInstaller entry point for rmrf binary.

This minimal entry point imports the CLI main function and serves as the
entry point for PyInstaller when building the standalone binary executable.
"""

import sys

from rmrf.cli import main

if __name__ == "__main__":
    sys.exit(main())

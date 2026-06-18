"""
Script for quick testing of the cli during development.

You must run it like so in the **root directory** -> python scripts/test_cli.py
"""
import sys
sys.path.insert(0, ".")

import typer
from cine_cli.cli.__main__ import cine_cli

if __name__ == "__main__":
    typer.run(cine_cli)
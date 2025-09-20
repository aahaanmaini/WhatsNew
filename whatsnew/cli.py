"""Command line interface for whatsnew."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="whatsnew",
        description="Generate concise, user-facing changelogs from git activity.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"whatsnew {__version__}",
        help="Show the version and exit.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output the changelog in JSON format (placeholder).",
    )
    parser.add_argument(
        "--md",
        action="store_true",
        help="Output the changelog in Markdown format (placeholder).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the whatsnew CLI."""
    parser = build_parser()
    parser.parse_args(argv)
    # Placeholder message until summarization is implemented.
    parser.exit(0, "whatsnew: changelog generation coming soon.\n")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())

"""Command line interface for whatsnew."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import get_config
from .utils.dates import (
    RangeResolutionError,
    resolve_range_request,
    summarize_range_request,
)


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

    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--json",
        dest="output_format",
        action="store_const",
        const="json",
        help="Output the changelog in JSON format.",
    )
    output_group.add_argument(
        "--md",
        dest="output_format",
        action="store_const",
        const="markdown",
        help="Output the changelog in Markdown format.",
    )

    parser.add_argument(
        "--no-code",
        dest="include_code_hunks",
        action="store_false",
        default=None,
        help="Disable sending code hunks to the summarizer.",
    )
    parser.add_argument(
        "--include-internal",
        dest="include_internal",
        action="store_true",
        default=None,
        help="Include internal-only changes in the output.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Explicitly set the repository root (defaults to auto-detect).",
    )

    range_group = parser.add_argument_group("Range selection")
    range_group.add_argument(
        "--tag",
        dest="tag",
        help="Generate notes since the specified tag (exclusive).",
    )
    range_group.add_argument(
        "--from-sha",
        dest="from_sha",
        help="Start commit SHA for the range.",
    )
    range_group.add_argument(
        "--to-sha",
        dest="to_sha",
        help="End commit SHA for the range (defaults to HEAD).",
    )
    range_group.add_argument(
        "--since-date",
        dest="since_date",
        help="Earliest commit date (ISO 8601).",
    )
    range_group.add_argument(
        "--until-date",
        dest="until_date",
        help="Latest commit date (ISO 8601).",
    )
    range_group.add_argument(
        "--window",
        dest="window",
        help="Time window to include (e.g. 7d, 24h).",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the whatsnew CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    overrides = _collect_cli_overrides(args)
    config = get_config(repo_root=args.repo_root, cli_overrides=overrides)

    try:
        range_request = resolve_range_request(vars(args), config.data)
    except RangeResolutionError as exc:
        parser.error(str(exc))

    output_format = config.data.get("output", {}).get("format", "terminal")
    range_summary = summarize_range_request(range_request)
    parser.exit(
        0,
        "whatsnew: changelog generation coming soon "
        f"(output={output_format}, range={range_summary}).\n",
    )


def _collect_cli_overrides(args: argparse.Namespace) -> dict:
    overrides: dict = {}
    if args.output_format:
        overrides.setdefault("output", {})["format"] = args.output_format

    if args.include_code_hunks is not None:
        overrides["include_code_hunks"] = args.include_code_hunks

    if args.include_internal is not None:
        overrides["drop_internal"] = not args.include_internal

    return overrides


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())

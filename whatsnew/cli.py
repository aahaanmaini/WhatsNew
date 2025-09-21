"""Command line interface for whatsnew."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import get_config
from .ingest.collect import collect_changes
from .outputs.json_out import build_json_payload
from .outputs.md_out import build_markdown
from .outputs.terminal import render_terminal
from .summarize.map_step import run_map_step
from .summarize.provider import provider_from_config
from .summarize.reduce_step import run_reduce_step
from .utils.dates import RangeResolutionError, resolve_range_request


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

    try:
        changes = collect_changes(config, range_request)
    except Exception as exc:  # pragma: no cover - runtime dependency
        parser.error(f"Failed to collect git changes: {exc}")

    provider = provider_from_config(config.data)
    map_items = run_map_step(config, changes, provider=provider)
    reduce_result = run_reduce_step(config, map_items)

    summary = reduce_result.to_dict()
    summary.update(
        {
            "repository": changes.get("repository", {}),
            "range": changes.get("range", {}),
            "commits": changes.get("commits", []),
            "prs": changes.get("prs", []),
        }
    )
    summary["meta"].update(
        {
            "commit_count": len(changes.get("commits", [])),
            "pr_count": len(changes.get("prs", [])),
            "model": provider.default_model,
        }
    )
    summary["id"] = reduce_result.generated_at

    output_format = config.data.get("output", {}).get("format", "terminal")
    if args.output_format:
        output_format = args.output_format

    payload = build_json_payload(summary)

    if output_format == "json":
        parser.exit(0, json.dumps(payload, indent=2) + "\n")
    if output_format == "markdown":
        parser.exit(0, build_markdown(summary) + "\n")

    output_text = render_terminal(summary)
    parser.exit(0, output_text + "\n")


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

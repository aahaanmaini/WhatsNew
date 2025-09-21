"""Command line interface for whatsnew."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Sequence

from . import __version__
from .config import get_config
from .ingest.collect import collect_changes
from .outputs.json_out import build_json_payload
from .outputs.md_out import build_markdown
from .outputs.terminal import render_terminal
from .publish import (
    PublishError,
    PublishResult,
    PreviewError,
    PreviewResult,
    preview_publish,
    publish_summary,
)
from .summarize.map_step import run_map_step
from .summarize.provider import provider_from_config
from .summarize.reduce_step import run_reduce_step
from .utils.dates import RangeResolutionError, resolve_range_request


def add_common_arguments(parser: argparse.ArgumentParser, *, include_range_tag: bool) -> None:
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
    if include_range_tag:
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

    parser.set_defaults(
        output_format=None,
        include_code_hunks=None,
        include_internal=None,
        tag=None,
        from_sha=None,
        to_sha=None,
        since_date=None,
        until_date=None,
        window=None,
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

    add_common_arguments(parser, include_range_tag=True)

    subparsers = parser.add_subparsers(dest="command")

    publish_parser = subparsers.add_parser(
        "publish",
        help="Publish changelog artifacts to the gh-pages branch.",
    )
    add_common_arguments(publish_parser, include_range_tag=False)
    publish_parser.add_argument(
        "--tag",
        dest="publish_tag",
        help="Release tag to write under data/releases/.",
    )
    publish_parser.add_argument(
        "--message",
        dest="publish_message",
        help="Override the publish commit message.",
    )
    publish_parser.add_argument(
        "--force-publish",
        action="store_true",
        dest="force_publish",
        help="Allow publishing even if the repository is private.",
    )
    publish_parser.add_argument(
        "--preview",
        action="store_true",
        dest="publish_preview",
        help="Preview changes instead of pushing them.",
    )

    preview_parser = subparsers.add_parser(
        "preview",
        help="Preview the gh-pages changes that would be published.",
    )
    add_common_arguments(preview_parser, include_range_tag=False)
    preview_parser.add_argument(
        "--tag",
        dest="publish_tag",
        help="Release tag to preview under data/releases/.",
    )
    preview_parser.add_argument(
        "--message",
        dest="publish_message",
        help="Commit message that would be used during publish.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the whatsnew CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    overrides = _collect_cli_overrides(args)
    config = get_config(repo_root=args.repo_root, cli_overrides=overrides)
    try:
        summary = _generate_summary(args, config)
    except RangeResolutionError as exc:
        parser.error(str(exc))
    except Exception as exc:  # pragma: no cover - runtime dependency
        parser.error(f"Failed to collect git changes: {exc}")

    command = getattr(args, "command", None)

    if command == "publish":
        return _handle_publish(parser, args, config, summary)
    if command == "preview":
        return _handle_preview(parser, args, config, summary)

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


def _generate_summary(args: argparse.Namespace, config: WhatsNewConfig) -> dict:
    range_request = resolve_range_request(vars(args), config.data)
    changes = collect_changes(config, range_request)
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
    meta = summary.setdefault("meta", {})
    meta.update(
        {
            "commit_count": len(changes.get("commits", [])),
            "pr_count": len(changes.get("prs", [])),
            "model": provider.default_model,
        }
    )
    summary["id"] = reduce_result.generated_at

    return summary


def _handle_publish(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    config: WhatsNewConfig,
    summary: dict,
) -> int:
    tag = getattr(args, "publish_tag", None)
    message = getattr(args, "publish_message", None)
    summary = _stamp_release_metadata(summary, tag)
    if getattr(args, "publish_preview", False):
        try:
            result = preview_publish(config, summary, tag=tag, message=message)
        except PreviewError as exc:
            parser.error(str(exc))
        _print_preview_result(result)
        return 0

    try:
        result = publish_summary(
            config,
            summary,
            tag=tag,
            message=message,
            force=getattr(args, "force_publish", False),
        )
    except PublishError as exc:
        parser.error(str(exc))
    _print_publish_success(result)
    return 0


def _handle_preview(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    config: WhatsNewConfig,
    summary: dict,
) -> int:
    tag = getattr(args, "publish_tag", None)
    message = getattr(args, "publish_message", None)
    summary = _stamp_release_metadata(summary, tag)
    try:
        result = preview_publish(config, summary, tag=tag, message=message)
    except PreviewError as exc:
        parser.error(str(exc))
    _print_preview_result(result)
    return 0


def _print_publish_success(result: PublishResult) -> None:
    lines = [
        f"Published changelog to branch {result.branch}.",
        f"Commit: {result.commit_sha}",
        f"Message: {result.message}",
        "Files:",
    ]
    for path in result.paths:
        lines.append(f"  - {path.as_posix()}")
    print("\n".join(lines))


def _print_preview_result(result: PreviewResult) -> None:
    lines = [f"Branch: {result.branch}", "Files that would be written:"]
    for path in result.files:
        lines.append(f"  - {path.as_posix()}")
    lines.append(f"Commit message: {result.commit_message}")
    lines.append("Diff preview:")
    for diff in result.diffs:
        lines.append(f"--- {diff.path.as_posix()} ---")
        lines.append(diff.diff or "(no changes)")
    print("\n".join(lines))


def _stamp_release_metadata(summary: dict, tag: str | None) -> dict:
    if tag:
        summary["tag"] = tag
        summary.setdefault("meta", {})["tag"] = tag
    released_at = datetime.now(timezone.utc).isoformat()
    summary["released_at"] = released_at
    summary.setdefault("meta", {})["released_at"] = released_at
    return summary


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())

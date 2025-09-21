"""Terminal renderer for whatsnew summaries."""

from __future__ import annotations

import textwrap
from typing import Any, Dict, Mapping

try:  # pragma: no cover - optional dependency
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError:  # pragma: no cover - optional dependency
    Console = None  # type: ignore
    Panel = None  # type: ignore
    Table = None  # type: ignore

from .json_out import build_json_payload


def render_terminal(summary: Mapping[str, Any], *, use_rich: bool = True) -> str:
    """Return a string representation suitable for terminal output."""

    payload = build_json_payload(summary)
    if use_rich and Console and Table and Panel:
        return _render_with_rich(payload)
    return _render_plain_text(payload)


def _render_with_rich(payload: Mapping[str, Any]) -> str:
    console = Console(record=True)
    repo = payload.get("repo", "?")
    range_info = payload.get("range", {})
    header = f"[bold]whatsnew[/bold] · {repo} · {range_info.get('summary', '')}"

    stats = payload.get("stats", {})
    provenance = payload.get("provenance", {})
    stats_line = f"commits={stats.get('commits')}, prs={stats.get('prs')}"
    prov_line = f"generated_by={provenance.get('generated_by')} model={provenance.get('model')}"

    console.print(Panel.fit(header, border_style="magenta"))
    console.print(f"[dim]{stats_line} | {prov_line}[/dim]")

    table = Table(show_header=True, header_style="bold cyan", box=None, expand=True)
    table.add_column("Section", style="bold")
    table.add_column("Summary")
    for section in payload.get("sections", []):
        title = section.get("title", "")
        entries = section.get("items", []) or []
        if not entries:
            continue
        for item in entries:
            refs = ", ".join(item.get("refs", []))
            text = item.get("summary", "")
            if refs:
                text = f"{text} ([dim]{refs}[/dim])"
            table.add_row(title, text)
            title = ""
    if not table.rows:
        table.add_row("No changes", "All changes were internal this period.")
    console.print(table)
    return console.export_text(styles=True)


def _render_plain_text(payload: Mapping[str, Any]) -> str:
    lines: list[str] = []
    repo = payload.get("repo", "?")
    range_info = payload.get("range", {})
    header = f"whatsnew · {repo} · {range_info.get('summary', '')}"
    lines.append(header.strip())
    lines.append("".join("-" for _ in header))

    sections = payload.get("sections", []) or []
    if not sections:
        lines.append("No user-visible changes in this range.")
    for section in sections:
        title = section.get("title", "")
        entries = section.get("items", []) or []
        if not entries:
            continue
        lines.append(f"\n{title}")
        for item in entries:
            refs = ", ".join(item.get("refs", []))
            summary_text = item.get("summary", "")
            bullet = f"- {summary_text}"
            if refs:
                bullet += f" ({refs})"
            lines.append(textwrap.fill(bullet, width=88, subsequent_indent="  "))

    stats = payload.get("stats", {})
    provenance = payload.get("provenance", {})
    lines.append(
        "\n" + f"Stats: commits={stats.get('commits')} prs={stats.get('prs')} | Model: {provenance.get('model')}"
    )
    return "\n".join(lines)

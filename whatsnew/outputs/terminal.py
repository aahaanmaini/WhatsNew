"""Terminal renderer for whatsnew summaries."""

from __future__ import annotations

import textwrap
from typing import Any, Dict, Mapping

try:  # pragma: no cover - optional dependency
    from rich.console import Console
    from rich.table import Table
except ImportError:  # pragma: no cover - optional dependency
    Console = None  # type: ignore
    Table = None  # type: ignore


def render_terminal(summary: Mapping[str, Any], *, use_rich: bool = True) -> str:
    """Return a string representation suitable for terminal output."""

    if use_rich and Console and Table:
        return _render_with_rich(summary)
    return _render_plain_text(summary)


def _render_with_rich(summary: Mapping[str, Any]) -> str:
    console = Console(record=True)
    repo = summary.get("repository", {})
    range_info = summary.get("range", {})
    console.print(
        f"[bold]whatsnew[/bold] · {repo.get('owner','?')}/{repo.get('name','?')} · {range_info.get('summary','')}"
    )
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Section", style="bold")
    table.add_column("Summary")
    for section in summary.get("sections", []):
        title = section.get("title", "")
        for item in section.get("items", []):
            refs = ", ".join(item.get("refs", []))
            text = item.get("summary", "")
            if refs:
                text = f"{text} ([dim]{refs}[/dim])"
            table.add_row(title, text)
            title = ""
    if not table.rows:
        table.add_row("No changes", "All changes were internal this period.")
    console.print(table)
    meta = summary.get("meta", {})
    dropped = meta.get("dropped_internal", 0)
    if dropped:
        console.print(f"[dim]{dropped} internal updates hidden[/dim]")
    return console.export_text(styles=True)


def _render_plain_text(summary: Mapping[str, Any]) -> str:
    lines = []
    repo = summary.get("repository", {})
    range_info = summary.get("range", {})
    header = f"whatsnew · {repo.get('owner','?')}/{repo.get('name','?')} · {range_info.get('summary','')}"
    lines.append(header.strip())
    lines.append("".join("-" for _ in header))
    sections = summary.get("sections", [])
    if not sections:
        lines.append("No user-visible changes in this range.")
    for section in sections:
        title = section.get("title", "")
        if not section.get("items"):
            continue
        lines.append(f"\n{title}")
        for item in section.get("items", []):
            refs = ", ".join(item.get("refs", []))
            summary_text = item.get("summary", "")
            bullet = f"- {summary_text}"
            if refs:
                bullet += f" ({refs})"
            lines.append(textwrap.fill(bullet, width=88, subsequent_indent="  "))
    meta = summary.get("meta", {})
    dropped = meta.get("dropped_internal", 0)
    if dropped:
        lines.append(f"\n({dropped} internal updates hidden)")
    return "\n".join(lines)

"""Markdown writer derived from the canonical JSON output."""

from __future__ import annotations

from typing import Mapping

from .json_out import build_json_payload


def build_markdown(summary: Mapping[str, object]) -> str:
    payload = build_json_payload(summary)
    lines: list[str] = []
    lines.append(f"# whatsnew for {payload['repo']}")
    range_summary = payload["range"].get("summary")
    if range_summary:
        lines.append(f"_Range: {range_summary}_")
    lines.append("")

    sections = payload.get("sections", [])
    if not sections:
        lines.append("No user-visible changes in this range.")
        return "\n".join(lines)

    for section in sections:
        title = section.get("title")
        items = section.get("items", []) or []
        if not items:
            continue
        lines.append(f"## {title}")
        for item in items:
            summary_text = item.get("summary", "")
            refs = ", ".join(item.get("refs", []))
            entry = summary_text
            if refs:
                entry += f" ({refs})"
            lines.append(f"- {entry}")
        lines.append("")

    stats = payload.get("stats", {})
    provenance = payload.get("provenance", {})
    meta_line_parts = []
    commits = stats.get("commits")
    prs = stats.get("prs")
    if commits is not None or prs is not None:
        meta_line_parts.append(f"Stats: commits={commits}, prs={prs}")
    model = provenance.get("model")
    if model:
        meta_line_parts.append(f"Model: {model}")
    if meta_line_parts:
        lines.append("\n" + " | ".join(meta_line_parts))

    return "\n".join(lines).strip()

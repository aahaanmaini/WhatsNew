"""Canonical JSON writer for whatsnew summaries."""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Mapping

from .. import __version__


def build_json_payload(summary: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a canonical JSON payload following the v1 schema."""

    repo = summary.get("repository", {})
    range_info = summary.get("range", {})
    raw_sections = summary.get("sections", [])
    sections = []
    for section in raw_sections:
        items = []
        for item in section.get("items", []) or []:
            labels = item.get("labels") or []
            refs = item.get("refs") or []
            items.append(
                {
                    "summary": item.get("summary", ""),
                    "refs": refs,
                    "labels": labels,
                }
            )
        sections.append(
            {
                "title": section.get("title", ""),
                "items": items,
            }
        )
    meta = summary.get("meta", {})

    repo_full = _format_repo(repo)
    timestamp = summary.get("id") or _iso_now()
    released_at = summary.get("released_at") or meta.get("released_at") or timestamp
    tag = summary.get("tag") or meta.get("tag")
    stats = {
        "commits": meta.get("commit_count", len(summary.get("commits", []))),
        "prs": meta.get("pr_count", len(summary.get("prs", []))),
    }

    provenance = {
        "generated_by": f"whatsnew@{__version__}",
        "model": meta.get("model", "fallback"),
    }

    range_payload = {
        "mode": range_info.get("mode"),
        "summary": range_info.get("summary"),
        "from": range_info.get("start_ref"),
        "to": range_info.get("end_ref"),
    }

    result = {
        "id": timestamp,
        "repo": repo_full,
        "range": range_payload,
        "released_at": released_at,
        "stats": stats,
        "sections": sections,
        "provenance": provenance,
    }
    if tag:
        result["tag"] = tag
    return result


def _format_repo(repo: Mapping[str, Any]) -> str:
    owner = repo.get("owner") or "?"
    name = repo.get("name") or "?"
    return f"{owner}/{name}"


def _iso_now() -> str:
    return dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat()

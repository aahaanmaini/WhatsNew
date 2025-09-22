"""Prompt builders for map and reduce summarization steps."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Mapping

MAP_SYSTEM_PROMPT = (
    "You write concise changelog blurbs that clearly state what changed."
)
MAP_JSON_SCHEMA: Dict[str, Any] = {
    "name": "MapSummary",
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "class": {
            "type": "string",
            "enum": [
                "feature",
                "fix",
                "perf",
                "docs",
                "security",
                "breaking",
                "internal",
            ],
        },
        "visibility": {
            "type": "string",
            "enum": ["user-visible", "internal"],
        },
        "refs": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["summary", "class", "visibility", "refs"],
}

REDUCE_SYSTEM_PROMPT = """You produce crisp Stripe-style public changelogs."""
REDUCE_JSON_SCHEMA: Dict[str, Any] = {
    "name": "ReduceSummary",
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "summary": {"type": "string"},
                                "refs": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["summary", "refs"],
                        },
                    },
                },
                "required": ["title", "items"],
            },
        }
    },
    "required": ["sections"],
}


def build_map_user_prompt(context: Mapping[str, Any]) -> str:
    """Return the user prompt for the map step given context data."""

    context_json = json.dumps(context, indent=2, sort_keys=True)
    return (
        "Given this change context (title, body, labels, linked issues, file paths, diff stats, and selected code hunks),\n"
        "- Write ONE short sentence (<=18 words) that states the actual change.\n"
        "- Do not copy commit or PR titles verbatim; synthesize the core change instead.\n"
        "- Classify one of: feature, fix, improvement, internal.\n"
        "- Set visibility to internal only if the change has no external effect.\n"
        "Return JSON: {\"summary\":\"...\", \"class\":\"feature|fix|improvement|internal\", \"visibility\":\"user-visible|internal\", \"refs\":[...]}.\n"
        "\nchange context:\n"
        f"{context_json}\n"
    )


def build_reduce_user_prompt(items: Iterable[Mapping[str, Any]], section_order: List[str]) -> str:
    """Return the reduce-step user prompt."""

    payload = {
        "section_order": section_order,
        "items": list(items),
    }
    data_json = json.dumps(payload, indent=2, sort_keys=True)
    return (
        "Aggregate these mini-summaries into sections: Features, Fixes, Improvements.\n"
        "- Merge related items into a single bullet with combined refs.\n"
        "- Limit each section to the 5 most important bullets.\n"
        "- Skip internal-only work.\n"
        "- Keep bullets short (<=18 words).\n"
        "Return JSON in schema: {\"sections\":[{\"title\":\"Features\",\"items\":[{\"summary\":\"...\",\"refs\":[...]}, ...]}, ...]}.\n"
        "\nmini-summaries:\n"
        f"{data_json}\n"
    )

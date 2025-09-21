"""Reduce step for aggregating mini-summaries into sections."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping

from ..config import WhatsNewConfig
from .map_step import MapItem

DEFAULT_SECTION_ORDER = [
    "Breaking changes",
    "Features",
    "Fixes",
    "Performance",
    "Security",
    "Docs",
]

CLASS_TO_SECTION = {
    "breaking": "Breaking changes",
    "feature": "Features",
    "fix": "Fixes",
    "perf": "Performance",
    "security": "Security",
    "docs": "Docs",
    "internal": "Internal",
}

CLASS_LABELS = {
    "breaking": "Breaking change",
    "feature": "Feature",
    "fix": "Fix",
    "perf": "Improvement",
    "security": "Security",
    "docs": "Docs",
    "internal": "Internal",
}


@dataclass(slots=True)
class ReduceResult:
    sections: List[Dict[str, Any]]
    dropped_internal: int
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sections": self.sections,
            "meta": {
                "generated_at": self.generated_at,
                "dropped_internal": self.dropped_internal,
            },
        }


def run_reduce_step(config: WhatsNewConfig, items: Iterable[MapItem]) -> ReduceResult:
    """Aggregate map-step results into ordered sections."""

    section_order = _resolve_section_order(config)
    visible_items: List[MapItem] = []
    dropped_internal = 0

    for item in items:
        if item.visibility == "internal" and item.classification not in {"perf", "security"}:
            dropped_internal += 1
            continue
        visible_items.append(item)

    deduped = _dedupe_items(visible_items)
    buckets: Dict[str, List[Dict[str, Any]]] = {section: [] for section in section_order}

    for item in deduped:
        section = CLASS_TO_SECTION.get(item.classification, "Fixes")
        if section not in buckets:
            buckets[section] = []
        label = CLASS_LABELS.get(item.classification, item.classification.title())
        buckets[section].append(
            {
                "summary": item.summary,
                "refs": item.refs,
                "labels": [label],
            }
        )

    for section, section_items in buckets.items():
        section_items.sort(key=lambda entry: (_score_refs(entry["refs"]), entry["summary"].lower()))

    ordered_sections: List[Dict[str, Any]] = []
    for section in section_order:
        entries = buckets.get(section, [])
        if not entries:
            continue
        ordered_sections.append({"title": section, "items": entries})

    generated_at = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat()
    return ReduceResult(
        sections=ordered_sections,
        dropped_internal=dropped_internal,
        generated_at=generated_at,
    )


def _resolve_section_order(config: WhatsNewConfig) -> List[str]:
    configured = config.data.get("section_order") if isinstance(config.data, Mapping) else None
    if isinstance(configured, list) and configured:
        return [str(section) for section in configured]
    return list(DEFAULT_SECTION_ORDER)


def _dedupe_items(items: Iterable[MapItem]) -> List[MapItem]:
    seen: Dict[tuple, MapItem] = {}
    ordered: List[MapItem] = []
    for item in items:
        key = (tuple(sorted(item.refs)), item.summary.lower())
        if key in seen:
            continue
        seen[key] = item
        ordered.append(item)
    return ordered


def _score_refs(refs: List[str]) -> tuple:
    primary = -len(refs)
    ref_text = ",".join(refs)
    return (primary, ref_text)

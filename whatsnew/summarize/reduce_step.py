"""Reduce step for aggregating mini-summaries into sections."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping

from ..config import WhatsNewConfig
from .map_step import MapItem

DEFAULT_SECTION_ORDER = [
    "Features",
    "Fixes",
    "Improvements",
]

CLASS_TO_SECTION = {
    "feature": "Features",
    "fix": "Fixes",
    "improvement": "Improvements",
}

CLASS_LABELS = {
    "feature": "Feature",
    "fix": "Fix",
    "improvement": "Improvement",
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
        normalized_class = _normalize_classification(item.classification)
        if normalized_class == "internal" or item.visibility == "internal":
            dropped_internal += 1
            continue
        visible_items.append(_replace_classification(item, normalized_class))

    deduped = _dedupe_items(visible_items)
    buckets: Dict[str, List[MapItem]] = {section: [] for section in section_order}

    for item in deduped:
        section = CLASS_TO_SECTION.get(item.classification, "Improvements")
        if section not in buckets:
            buckets[section] = []
        buckets[section].append(item)

    for section, section_items in buckets.items():
        section_items.sort(key=_section_sort_key)

    ordered_sections: List[Dict[str, Any]] = []
    for section in section_order:
        section_items = buckets.get(section, [])
        if not section_items:
            continue
        limited_items = section_items[:MAX_ITEMS_PER_SECTION]
        entries: List[Dict[str, Any]] = []
        for item in limited_items:
            label = CLASS_LABELS.get(item.classification, item.classification.title())
            entries.append(
                {
                    "summary": item.summary,
                    "refs": item.refs,
                    "labels": [label],
                }
            )
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
    seen: set[tuple[str, str]] = set()
    ordered: List[MapItem] = []
    for item in items:
        summary_key = _normalize_summary(item.summary)
        key = (item.classification, summary_key)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return ordered


def _normalize_summary(summary: str) -> str:
    return " ".join(summary.lower().split())


def _section_sort_key(item: MapItem) -> tuple:
    pr_priority = 0 if item.source_type == "pull_request" else 1
    ref_priority = -len(item.refs)
    return (pr_priority, ref_priority, _normalize_summary(item.summary))


def _normalize_classification(classification: str) -> str:
    value = (classification or "").lower()
    mapping = {
        "perf": "improvement",
        "performance": "improvement",
        "docs": "improvement",
        "documentation": "improvement",
        "security": "improvement",
        "breaking": "improvement",
    }
    return mapping.get(value, value)


def _replace_classification(item: MapItem, classification: str) -> MapItem:
    if item.classification == classification:
        return item
    return MapItem(
        source_id=item.source_id,
        source_type=item.source_type,
        summary=item.summary,
        classification=classification,
        visibility=item.visibility,
        refs=item.refs,
        metadata=item.metadata,
    )
MAX_ITEMS_PER_SECTION = 5

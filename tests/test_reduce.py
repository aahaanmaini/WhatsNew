from __future__ import annotations

from pathlib import Path

from whatsnew.config import WhatsNewConfig
from whatsnew.summarize.map_step import MapItem
from whatsnew.summarize.reduce_step import run_reduce_step


def make_item(summary: str, classification: str, visibility: str = "user-visible", ref: str = "abc123") -> MapItem:
    return MapItem(
        source_id=ref,
        source_type="commit",
        summary=summary,
        classification=classification,
        visibility=visibility,
        refs=[ref],
        metadata={"sha": ref},
    )


def test_reduce_deduplicates_by_summary_and_refs():
    config = WhatsNewConfig(repo_root=Path("."), data={}, config_path=None)
    items = [
        make_item("Feat: add onboarding flow", "feature", ref="aaa111"),
        make_item("Feat: add onboarding flow", "feature", ref="aaa111"),
        make_item("Fix: handle bug", "fix", ref="bbb222"),
        make_item("Internal cleanup", "internal", visibility="internal", ref="ccc333"),
    ]

    result = run_reduce_step(config, items)
    sections = {section["title"]: section for section in result.sections}

    assert "Features" in sections
    assert len(sections["Features"]["items"]) == 1
    assert sections["Features"]["items"][0]["summary"] == "Feat: add onboarding flow"

    assert "Fixes" in sections
    assert len(sections["Fixes"]["items"]) == 1

    # Internal-only change should be dropped by default
    assert "Internal" not in sections or not sections["Internal"]["items"]

from __future__ import annotations

import json

from pathlib import Path


def normalise_payload(data: dict) -> dict:
    data = dict(data)
    data.pop("id", None)
    data.pop("released_at", None)
    data.pop("tag", None)
    data.pop("provenance", None)

    sections = []
    for section in data.get("sections", []):
        items = []
        for item in section.get("items", []):
            items.append(
                {
                    "summary": item.get("summary"),
                    "refs": [],
                    "labels": item.get("labels", []),
                }
            )
        sections.append({"title": section.get("title"), "items": items})
    data["sections"] = sections
    return data


def test_golden_summary(run_cli):
    result = run_cli("--json")
    actual = json.loads(result.stdout)
    golden_path = Path(__file__).resolve().parent / "golden" / "summary.json"
    expected = json.loads(golden_path.read_text(encoding="utf-8"))

    actual_norm = normalise_payload(actual)
    expected_norm = normalise_payload(expected)
    assert actual_norm == expected_norm

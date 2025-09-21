"""Map step for summarizing individual commits or pull requests."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping

from ..cache import CacheStore
from ..config import WhatsNewConfig
from ..summarize.provider import ProviderResponse, SummarizationProvider, provider_from_config
from .prompts import MAP_JSON_SCHEMA, MAP_SYSTEM_PROMPT, build_map_user_prompt

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MapItem:
    """Resulting mini-summary for a unit (commit or PR)."""

    source_id: str
    source_type: str
    summary: str
    classification: str
    visibility: str
    refs: List[str]
    metadata: Dict[str, Any]


def run_map_step(
    config: WhatsNewConfig,
    changes: Mapping[str, Any],
    *,
    provider: SummarizationProvider | None = None,
) -> List[MapItem]:
    """Execute the map step returning mini-summaries for each change unit."""

    provider = provider or provider_from_config(config.data)
    cache = CacheStore(config.repo_root)

    commits_data: List[Mapping[str, Any]] = list(changes.get("commits", []))
    prs_data: List[Mapping[str, Any]] = list(changes.get("prs", []))
    issues_data: List[Mapping[str, Any]] = list(changes.get("issues", []))
    files = list(changes.get("files", []))
    snippets = list(changes.get("snippets", []))

    issue_lookup = {issue.get("number"): issue for issue in issues_data if issue.get("number")}

    map_items: List[MapItem] = []

    for pr in prs_data:
        number = pr.get("number")
        if number is None:
            continue
        refs = [f"PR#{number}"]
        linked_issues = _linked_issues_from_body(pr.get("body", ""), issue_lookup)
        context = {
            "type": "pull_request",
            "number": number,
            "title": pr.get("title", ""),
            "body": pr.get("body", ""),
            "labels": pr.get("labels", []),
            "refs": refs,
            "issues": linked_issues,
            "files": files,
            "snippets": snippets,
        }
        cache_key = f"pr:{number}"
        item = _summarize_unit(
            provider,
            cache,
            cache_key,
            context,
            metadata={"number": number, "type": "pull_request"},
        )
        if item:
            map_items.append(item)

    for commit in commits_data:
        sha = commit.get("sha")
        if not sha:
            continue
        refs = [sha[:7]]
        linked_issues = _linked_issues_from_body(commit.get("message", ""), issue_lookup)
        context = {
            "type": "commit",
            "sha": sha,
            "message": commit.get("message", ""),
            "author": commit.get("author", {}),
            "refs": refs,
            "issues": linked_issues,
            "files": files,
            "snippets": [snippet for snippet in snippets if snippet.get("sha") == sha] or snippets[:2],
        }
        cache_key = f"commit:{sha}"
        metadata = {
            "sha": sha,
            "type": "commit",
            "date": commit.get("date"),
        }
        item = _summarize_unit(provider, cache, cache_key, context, metadata=metadata)
        if item:
            map_items.append(item)

    return map_items


def _summarize_unit(
    provider: SummarizationProvider,
    cache: CacheStore,
    cache_key: str,
    context: Mapping[str, Any],
    *,
    metadata: Dict[str, Any],
) -> MapItem | None:
    payload = {
        "context": context,
    }

    def generator() -> Mapping[str, Any]:
        system_prompt = MAP_SYSTEM_PROMPT
        user_prompt = build_map_user_prompt(context)
        response: ProviderResponse = provider.generate(
            model=provider.default_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=MAP_JSON_SCHEMA,
        )
        result = _sanitize_map_payload(response.payload, context)
        return {
            "mini_summary": json.dumps(result, sort_keys=True),
            "model": response.model,
        }

    entry = cache.get_or_generate(cache_key, payload, generator)
    try:
        data = json.loads(entry.mini_summary)
    except json.JSONDecodeError:
        logger.warning("Invalid cached summary for %s; regenerating", cache_key)
        cache.invalidate(cache_key)
        return _summarize_unit(provider, cache, cache_key, context, metadata=metadata)

    summary = str(data.get("summary", "")).strip()
    if not summary:
        return None
    classification = str(data.get("class", "feature"))
    visibility = str(data.get("visibility", "user-visible"))
    refs = [str(ref) for ref in data.get("refs", context.get("refs", []))]

    return MapItem(
        source_id=cache_key,
        source_type=context.get("type", "commit"),
        summary=summary,
        classification=classification,
        visibility=visibility,
        refs=refs,
        metadata=metadata,
    )


def _sanitize_map_payload(payload: Mapping[str, Any], context: Mapping[str, Any]) -> Dict[str, Any]:
    summary = str(payload.get("summary") or context.get("title") or context.get("message") or "")
    summary = summary.strip()
    if not summary:
        summary = "Change"

    classification = str(payload.get("class") or "feature").lower()
    if classification not in {"feature", "fix", "perf", "docs", "security", "breaking", "internal"}:
        classification = "feature"

    visibility = str(payload.get("visibility") or "user-visible").lower()
    if visibility not in {"user-visible", "internal"}:
        visibility = "user-visible"

    refs = payload.get("refs") or context.get("refs") or []
    refs_list = [str(ref) for ref in refs]

    return {
        "summary": summary,
        "class": classification,
        "visibility": visibility,
        "refs": refs_list,
    }


def _linked_issues_from_body(text: str, issues: Mapping[int, Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    numbers: List[int] = []
    for token in text.split():
        if token.startswith("#") and token[1:].isdigit():
            numbers.append(int(token[1:]))
    result: List[Mapping[str, Any]] = []
    for number in numbers:
        issue = issues.get(number)
        if issue:
            result.append(issue)
    return result

"""Summarization provider abstractions."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Mapping

from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    from openai import OpenAI  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None  # type: ignore


@dataclass(slots=True)
class ProviderResponse:
    """Normalized result from a summarization provider."""

    model: str
    payload: Dict[str, Any]


class SummarizationProvider:
    """Abstract provider interface."""

    name: str = "base"
    default_model: str = "gpt-4o-mini"

    def generate(
        self,
        *,
        model: str | None,
        system_prompt: str,
        user_prompt: str,
        json_schema: Mapping[str, Any] | None = None,
    ) -> ProviderResponse:
        raise NotImplementedError


class OpenAIProvider(SummarizationProvider):
    """Implementation backed by OpenAI's Responses API."""

    name = "openai"

    def __init__(self, api_key: str, default_model: str | None = None) -> None:
        if OpenAI is None:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "openai package is not installed. Install openai to use OpenAIProvider."
            )
        self._client = OpenAI(api_key=api_key)
        if default_model:
            self.default_model = default_model

    def generate(
        self,
        *,
        model: str | None,
        system_prompt: str,
        user_prompt: str,
        json_schema: Mapping[str, Any] | None = None,
    ) -> ProviderResponse:
        effective_model = model or self.default_model
        schema = json_schema or {}
        response = self._execute_with_retry(
            effective_model,
            system_prompt,
            user_prompt,
            schema,
        )
        content = response.output[0].content[0].text  # type: ignore[attr-defined]
        payload = json.loads(content)
        return ProviderResponse(model=effective_model, payload=payload)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def _execute_with_retry(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema: Mapping[str, Any],
    ):
        response_format = {"type": "json_object"}
        if schema:
            response_format = {"type": "json_schema", "json_schema": schema}
        return self._client.responses.create(  # type: ignore[attr-defined]
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=response_format,
        )


class FallbackProvider(SummarizationProvider):
    """Heuristic provider used when no external model is configured."""

    name = "fallback"
    default_model = "fallback"

    def generate(
        self,
        *,
        model: str | None,
        system_prompt: str,
        user_prompt: str,
        json_schema: Mapping[str, Any] | None = None,
    ) -> ProviderResponse:
        del system_prompt, json_schema  # unused
        try:
            context = json.loads(user_prompt.split("change context:", 1)[1].strip())
        except Exception:  # pragma: no cover - defensive
            context = {}
        summary = _fallback_summary(context)
        payload = {
            "summary": summary["summary"],
            "class": summary["class"],
            "visibility": summary["visibility"],
            "refs": summary["refs"],
        }
        return ProviderResponse(model=model or self.default_model, payload=payload)


def provider_from_config(config: Mapping[str, Any]) -> SummarizationProvider:
    """Return an appropriate provider based on configuration."""

    credentials = config.get("credentials", {}) if isinstance(config, Mapping) else {}
    api_key = credentials.get("openai_api_key") if isinstance(credentials, Mapping) else None
    provider_cfg = config.get("provider", {}) if isinstance(config, Mapping) else {}
    model = provider_cfg.get("model") if isinstance(provider_cfg, Mapping) else None

    if api_key:
        try:
            provider = OpenAIProvider(api_key, default_model=model)
            return provider
        except Exception as exc:  # pragma: no cover - optional dependency missing
            logger.warning("Falling back to heuristic provider: %s", exc)
    else:
        logger.info("OPENAI_API_KEY not set; using fallback summarization provider.")

    provider = FallbackProvider()
    if model:
        provider.default_model = model
    return provider


def _fallback_summary(context: Mapping[str, Any]) -> Dict[str, Any]:
    title = str(context.get("title") or context.get("message") or "Change")
    title_clean = title.strip().rstrip(".")

    labels = [label.lower() for label in context.get("labels", []) if isinstance(label, str)]
    body = str(context.get("body") or "")
    refs = context.get("refs", []) or []

    classification = _classify_from_labels(title_clean, body, labels)
    visibility = "user-visible" if classification != "internal" else "internal"

    summary = title_clean
    if not summary:
        summary = "Update"
    if not summary[0].isupper():
        summary = summary.capitalize()

    return {
        "summary": summary,
        "class": classification,
        "visibility": visibility,
        "refs": refs,
    }


def _classify_from_labels(title: str, body: str, labels: list[str]) -> str:
    text = f"{title}\n{body}".lower()
    if any("break" in label for label in labels) or "breaking" in text:
        return "breaking"
    if any(label in {"feature", "enhancement", "feat"} for label in labels) or "feature" in text:
        return "feature"
    if any(label in {"bug", "fix"} for label in labels) or "fix" in text or "bug" in text:
        return "fix"
    if "doc" in text or any("doc" in label for label in labels):
        return "docs"
    if "perf" in text or any("perf" in label for label in labels):
        return "perf"
    if "security" in text or any("security" in label for label in labels):
        return "security"
    if "refactor" in text or any(label in {"chore", "internal"} for label in labels):
        return "internal"
    return "feature"

"""Filesystem-backed cache for per-item summaries."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CacheEntry:
    """Represents a cached summarization result."""

    input_fingerprint: str
    mini_summary: str
    model: str | None
    timestamp: str

    def to_dict(self) -> dict:
        return {
            "input_fingerprint": self.input_fingerprint,
            "mini_summary": self.mini_summary,
            "model": self.model,
            "timestamp": self.timestamp,
        }


class CacheStore:
    """JSON cache stored under `.whatsnew/cache/` inside the repo root."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = Path(repo_root or Path.cwd())
        self.cache_dir = self.repo_root / ".whatsnew" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_or_generate(
        self,
        key: str,
        input_payload: Mapping[str, Any],
        generator_fn: Callable[[], Mapping[str, Any]],
    ) -> CacheEntry:
        """Return cached data or generate, store, and return new data."""

        fingerprint = _fingerprint(input_payload)
        existing = self._read_entry(key)
        if existing and existing.input_fingerprint == fingerprint:
            logger.debug("Cache hit for %s", key)
            return existing

        logger.debug("Cache miss for %s", key)
        generated = generator_fn()
        if not isinstance(generated, Mapping):
            raise TypeError("generator_fn must return a mapping with mini_summary and model fields")

        mini_summary = str(generated.get("mini_summary", ""))
        if not mini_summary:
            raise ValueError("generator_fn must provide a non-empty mini_summary")
        model = generated.get("model")
        if model is not None:
            model = str(model)

        timestamp = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat()
        entry = CacheEntry(
            input_fingerprint=fingerprint,
            mini_summary=mini_summary,
            model=model,
            timestamp=timestamp,
        )
        self._write_entry(key, entry)
        return entry


    def invalidate(self, key: str) -> None:
        """Remove a cached entry if it exists."""
        path = self._path_for_key(key)
        try:
            path.unlink()
        except FileNotFoundError:
            return

    def _read_entry(self, key: str) -> CacheEntry | None:
        path = self._path_for_key(key)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:  # pragma: no cover - corrupted cache
            logger.warning("Failed to read cache entry %s: %s", path, exc)
            return None
        return CacheEntry(
            input_fingerprint=str(payload.get("input_fingerprint", "")),
            mini_summary=str(payload.get("mini_summary", "")),
            model=payload.get("model"),
            timestamp=str(payload.get("timestamp", "")),
        )

    def _write_entry(self, key: str, entry: CacheEntry) -> None:
        path = self._path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    def _path_for_key(self, key: str) -> Path:
        filename = key if key.endswith(".json") else f"{key}.json"
        return self.cache_dir / filename


def _fingerprint(payload: Mapping[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

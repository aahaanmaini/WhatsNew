"""Configuration loading helpers for whatsnew."""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, TYPE_CHECKING

try:  # pragma: no cover - exercised at runtime
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - optional dependency in dev env
    yaml = None  # type: ignore

if TYPE_CHECKING:  # pragma: no cover - typing helpers
    import yaml as _yaml

CONFIG_FILE_NAMES = ("whatsnew.config.yml", "whatsnew.config.yaml")

DEFAULT_CONFIG: Dict[str, Any] = {
    "tone": "stripe",
    "default_range": "since-tag",
    "date_window_days": 7,
    "include_code_hunks": True,
    "drop_internal": True,
    "section_order": [
        "Features",
        "Fixes",
        "Performance",
        "Docs",
        "Security",
        "Breaking changes",
    ],
    "publish": {
        "branch": "gh-pages",
        "paths": {
            "latest": "data/latest.json",
            "releases": "data/releases",
        },
    },
    "site": {
        "title": "",
        "logo": "",
        "accent": "#635bff",
    },
    "output": {
        "format": "terminal",
    },
    "credentials": {
        "openai_api_key": None,
        "github_token": None,
    },
}


@dataclass(slots=True)
class WhatsNewConfig:
    """In-memory representation of CLI configuration."""

    repo_root: Path
    data: Dict[str, Any]
    config_path: Path | None = None

    def get(self, key: str, default: Any | None = None) -> Any:
        return self.data.get(key, default)


def get_config(
    repo_root: Path | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
    config_path: str | Path | None = None,
) -> WhatsNewConfig:
    """Return the effective configuration for the CLI execution."""

    resolved_root = repo_root or _discover_repo_root(Path.cwd())

    merged: Dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
    file_config, config_file = _load_file_config(resolved_root, config_path)
    if file_config:
        merged = _deep_merge(merged, file_config)

    env_overrides = _environment_overrides()
    if env_overrides:
        merged = _deep_merge(merged, env_overrides)

    if cli_overrides:
        merged = _deep_merge(merged, cli_overrides)

    return WhatsNewConfig(repo_root=resolved_root, data=merged, config_path=config_file)


def _discover_repo_root(start: Path) -> Path:
    """Find the repository root by walking up until a `.git` directory appears."""
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current


def _load_file_config(root: Path, explicit: str | Path | None) -> tuple[Dict[str, Any], Path | None]:
    if explicit:
        location = (Path(explicit) if Path(explicit).is_absolute() else root / explicit).resolve()
        if not location.is_file():
            raise FileNotFoundError(f"Configuration file not found: {location}")
        return _read_config_file(location), location

    for name in CONFIG_FILE_NAMES:
        location = root / name
        if location.is_file():
            return _read_config_file(location), location
    return {}, None


def _read_config_file(location: Path) -> Dict[str, Any]:
    text = location.read_text(encoding="utf-8")
    if yaml is None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:  # pragma: no cover - fallback path
            raise RuntimeError(
                "PyYAML is required to read configuration files with YAML syntax. "
                "Either install PyYAML or provide JSON content."
            ) from exc
    else:
        data = yaml.safe_load(text)  # type: ignore[union-attr]
    if not isinstance(data, dict):
        return {}
    return data


def _environment_overrides() -> Dict[str, Any]:
    overrides: Dict[str, Any] = {}
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        overrides.setdefault("credentials", {})["openai_api_key"] = api_key
    gh_token = os.environ.get("GH_TOKEN")
    if gh_token:
        overrides.setdefault("credentials", {})["github_token"] = gh_token
    return overrides


def _deep_merge(original: Dict[str, Any], update: Mapping[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = copy.deepcopy(original)
    for key, value in update.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, Mapping)
        ):
            result[key] = _deep_merge(result[key], value)  # type: ignore[arg-type]
        else:
            result[key] = value
    return result

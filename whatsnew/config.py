"""Configuration loading helpers for whatsnew."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml


CONFIG_FILE_NAMES = ("whatsnew.config.yml", "whatsnew.config.yaml")


@dataclass(slots=True)
class WhatsNewConfig:
    """In-memory representation of CLI configuration."""

    raw: Dict[str, Any]


def load_config(start_dir: Path | None = None) -> WhatsNewConfig | None:
    """Load configuration data if a config file is present."""
    base_dir = start_dir or Path.cwd()

    for name in CONFIG_FILE_NAMES:
        candidate = base_dir / name
        if candidate.is_file():
            data = yaml.safe_load(candidate.read_text()) or {}
            return WhatsNewConfig(raw=data)

    return None

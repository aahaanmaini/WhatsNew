"""Preview gh-pages publishing without writing to the repository."""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

try:  # pragma: no cover - optional dependency
    import git  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    git = None  # type: ignore

from ..config import WhatsNewConfig
from ..git.repo import open_repository
from ..outputs.json_out import build_json_payload
from .gh_pages import PublishConfig, _default_message


@dataclass(slots=True)
class PreviewDiff:
    path: Path
    diff: str


@dataclass(slots=True)
class PreviewResult:
    branch: str
    files: List[Path]
    diffs: List[PreviewDiff]
    commit_message: str


class PreviewError(RuntimeError):
    """Raised when a preview cannot be generated."""


def preview_publish(
    config: WhatsNewConfig,
    summary: dict,
    *,
    tag: str | None = None,
    message: str | None = None,
) -> PreviewResult:
    """Produce the diffs that would be written to gh-pages."""

    if git is None:  # pragma: no cover - runtime guard
        raise PreviewError("GitPython is required for previews. Install gitpython to continue.")

    repo = open_repository(config.repo_root)
    payload = build_json_payload(summary)
    publish_cfg = PublishConfig.from_config(config)

    target_files: Dict[Path, str] = {}
    latest_content = _to_json(payload)
    target_files[publish_cfg.latest_path] = latest_content
    if tag:
        target_files[publish_cfg.release_path(tag)] = latest_content

    diffs: List[PreviewDiff] = []
    written: List[Path] = []
    for rel_path, new_content in target_files.items():
        written.append(rel_path)
        old_content = _read_branch_file(repo, publish_cfg.branch, rel_path)
        diff = _make_diff(old_content, new_content, publish_cfg.branch, rel_path)
        diffs.append(PreviewDiff(path=rel_path, diff=diff))

    commit_message = message or _default_message(tag, payload)
    return PreviewResult(
        branch=publish_cfg.branch,
        files=written,
        diffs=diffs,
        commit_message=commit_message,
    )


def _to_json(payload: dict) -> str:
    return json.dumps(payload, indent=2) + "\n"


def _read_branch_file(repo: "git.Repo", branch: str, path: Path) -> str:
    git_path = f"{branch}:{path.as_posix()}"
    try:
        return repo.git.show(git_path)
    except git.GitCommandError:
        return ""


def _make_diff(old: str, new: str, branch: str, path: Path) -> str:
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    diff_iter = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"{branch}:{path.as_posix()}",
        tofile=f"new:{path.as_posix()}",
        lineterm="",
    )
    return "\n".join(diff_iter)

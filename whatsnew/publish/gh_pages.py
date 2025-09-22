"""Publish changelog artifacts to a gh-pages branch."""

from __future__ import annotations

import contextlib
import json
import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

try:  # pragma: no cover - optional dependency
    import git  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    git = None  # type: ignore

try:  # pragma: no cover - optional dependency
    import requests
except ImportError:  # pragma: no cover - optional dependency
    requests = None  # type: ignore

from ..config import WhatsNewConfig
from ..git.repo import describe_repository, open_repository
from ..outputs.json_out import build_json_payload

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PublishConfig:
    branch: str
    latest_path: Path
    releases_dir: Path

    @classmethod
    def from_config(cls, config: WhatsNewConfig) -> "PublishConfig":
        publish_cfg = config.data.get("publish", {}) if isinstance(config.data, dict) else {}
        branch = publish_cfg.get("branch", "gh-pages")
        paths = publish_cfg.get("paths", {}) if isinstance(publish_cfg, dict) else {}
        latest = paths.get("latest", "data/latest.json")
        releases = paths.get("releases", "data/releases")
        base = config.repo_root
        return cls(
            branch=branch,
            latest_path=Path(latest),
            releases_dir=Path(releases),
        )

    def release_path(self, tag: str) -> Path:
        filename = f"{tag}.json" if not tag.endswith(".json") else tag
        return self.releases_dir / filename


@dataclass(slots=True)
class PublishResult:
    branch: str
    paths: List[Path]
    commit_sha: str
    message: str


class PublishError(RuntimeError):
    """Raised when publishing cannot proceed."""


def publish_summary(
    config: WhatsNewConfig,
    summary: dict,
    *,
    tag: str | None = None,
    message: str | None = None,
    force: bool = False,
) -> PublishResult:
    """Write changelog artifacts and push them to the gh-pages branch."""

    if git is None:  # pragma: no cover - runtime guard
        raise PublishError("GitPython is required for publishing. Install gitpython to continue.")

    repo = open_repository(config.repo_root)
    repo_meta = describe_repository(config.repo_root)
    publish_cfg = PublishConfig.from_config(config)
    payload = build_json_payload(summary)

    if _is_private_repo(repo_meta, config) and not force:
        raise PublishError(
            "Publishing to gh-pages is disabled for private repositories. Pass --force-publish to override."
        )

    with _temporary_worktree(repo, publish_cfg.branch) as worktree:
        wt_repo = git.Repo(worktree)
        files_written = _write_artifacts(wt_repo, publish_cfg, payload, tag)
        if not wt_repo.is_dirty(untracked_files=True):
            raise PublishError("No changes detected for publishing.")

        commit_message = message or _default_message(tag, payload)
        wt_repo.git.add(all=True)
        wt_repo.index.commit(commit_message)

        push_args: list[str] = ["origin", publish_cfg.branch]
        token = config.data.get("credentials", {}).get("github_token") if isinstance(config.data, dict) else None
        if token and repo_meta.remote_url and repo_meta.remote_url.startswith("https://"):
            push_url = _inject_token(repo_meta.remote_url, token)
            wt_repo.git.push(push_url, publish_cfg.branch)
        else:
            wt_repo.git.push(*push_args)

        commit_sha = wt_repo.head.commit.hexsha

    return PublishResult(
        branch=publish_cfg.branch,
        paths=files_written,
        commit_sha=commit_sha,
        message=commit_message,
    )


def _write_artifacts(
    wt_repo: "git.Repo",
    publish_cfg: PublishConfig,
    payload: dict,
    tag: str | None,
) -> List[Path]:
    worktree_root = Path(wt_repo.working_tree_dir or ".")
    files: List[Path] = []

    _ensure_parents(worktree_root, publish_cfg.latest_path)
    latest_path = worktree_root / publish_cfg.latest_path
    latest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    files.append(publish_cfg.latest_path)

    if tag:
        release_path = publish_cfg.release_path(tag)
        _ensure_parents(worktree_root, release_path)
        (worktree_root / release_path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        files.append(release_path)

    nojekyll = worktree_root / ".nojekyll"
    if not nojekyll.exists():
        nojekyll.write_text("", encoding="utf-8")
        files.append(Path(".nojekyll"))

    if tag:
        index_rel = _update_release_index(worktree_root, publish_cfg, payload, tag)
        if index_rel:
            files.append(index_rel)

    return files


def _ensure_parents(root: Path, relative: Path) -> None:
    (root / relative).parent.mkdir(parents=True, exist_ok=True)


def _default_message(tag: str | None, payload: dict) -> str:
    if tag:
        return f"Publish changelog for {tag}"
    range_summary = payload.get("range", {}).get("summary", "latest changes")
    return f"Publish changelog for {range_summary}".strip()


@contextlib.contextmanager
def _temporary_worktree(repo: "git.Repo", branch: str) -> Iterable[Path]:
    temp_dir = Path(tempfile.mkdtemp(prefix="whatsnew-gh-"))
    try:
        if branch in repo.heads:
            repo.git.worktree("add", str(temp_dir), branch)
        else:
            repo.git.worktree("add", "--detach", str(temp_dir))
            wt_repo = git.Repo(temp_dir)
            wt_repo.git.checkout("--orphan", branch)
            (temp_dir / ".nojekyll").write_text("", encoding="utf-8")
            wt_repo.git.add(".nojekyll")
            wt_repo.index.commit("Initialize gh-pages branch")
            wt_repo.git.branch("-M", branch)
        yield temp_dir
    finally:
        try:
            repo.git.worktree("remove", "--force", str(temp_dir))
        except git.GitCommandError:
            pass
        shutil.rmtree(temp_dir, ignore_errors=True)


def _inject_token(remote_url: str, token: str) -> str:
    if "@" in remote_url:
        return remote_url
    if remote_url.startswith("https://"):
        return remote_url.replace("https://", f"https://x-access-token:{token}@", 1)
    return remote_url


def _is_private_repo(repo_meta, config: WhatsNewConfig) -> bool:
    indicator = config.data.get("publish", {}).get("private", False) if isinstance(config.data, dict) else False
    if indicator:
        return True
    if not repo_meta.owner or not repo_meta.name:
        return False
    token = config.data.get("credentials", {}).get("github_token") if isinstance(config.data, dict) else None
    if not token or requests is None:
        return False
    api_url = f"https://api.github.com/repos/{repo_meta.owner}/{repo_meta.name}"
    try:
        response = requests.get(api_url, headers={"Authorization": f"Bearer {token}"}, timeout=5)
        if response.status_code >= 400:
            return False
        data = response.json()
        return bool(data.get("private", False))
    except Exception:
        logger.debug("Unable to determine repository visibility; assuming public.")
        return False


def _update_release_index(
    root: Path,
    publish_cfg: PublishConfig,
    payload: dict,
    tag: str | None,
) -> Path | None:
    entry = _build_index_entry(publish_cfg, payload, tag)
    if entry is None:
        return None
    index_rel = publish_cfg.releases_dir / "index.json"
    _ensure_parents(root, index_rel)
    index_path = root / index_rel
    existing_text = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    merged = _merge_index_entries(existing_text, entry)
    index_path.write_text(merged, encoding="utf-8")
    return index_rel


def _build_index_entry(
    publish_cfg: PublishConfig,
    payload: dict,
    tag: str | None,
) -> dict | None:
    released_at = payload.get("released_at") or payload.get("id")
    if not released_at:
        return None
    label = payload.get("label") or tag or ("latest" if not tag else tag)
    entry = {
        "tag": tag,
        "label": label,
        "released_at": released_at,
        "range": payload.get("range", {}),
        "stats": payload.get("stats", {}),
        "path": (
            publish_cfg.release_path(tag).as_posix()
            if tag
            else publish_cfg.latest_path.as_posix()
        ),
    }
    return entry


def _merge_index_entries(existing_text: str, new_entry: dict) -> str:
    try:
        entries = json.loads(existing_text) if existing_text else []
    except json.JSONDecodeError:
        entries = []
    if not isinstance(entries, list):
        entries = []
    label = new_entry.get("label")
    entries = [entry for entry in entries if entry.get("label") != label]
    entries.append(new_entry)
    entries.sort(key=lambda entry: entry.get("released_at", ""), reverse=True)
    return json.dumps(entries, indent=2) + "\n"

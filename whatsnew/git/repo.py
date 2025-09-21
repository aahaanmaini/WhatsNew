"""Git repository helpers for whatsnew ingestion."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

try:  # pragma: no cover - optional dependency, enforced at runtime
    import git  # type: ignore
except ImportError:  # pragma: no cover - optional dependency, enforced at runtime
    git = None  # type: ignore

from ..utils.dates import RangeMode, RangeRequest

_SEMVER_RE = re.compile(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-+].*)?$")


@dataclass(slots=True)
class RepositoryMetadata:
    """Metadata describing the current git repository."""

    root: Path
    remote_url: str | None
    owner: str | None
    name: str | None
    default_branch: str | None


@dataclass(slots=True)
class CommitInfo:
    """Normalized commit data used by downstream summarization."""

    sha: str
    parent_shas: list[str]
    author_name: str
    author_email: str
    committed_datetime: dt.datetime
    message: str

    def to_dict(self) -> dict:
        return {
            "sha": self.sha,
            "parents": self.parent_shas,
            "author": {
                "name": self.author_name,
                "email": self.author_email,
            },
            "date": self.committed_datetime.astimezone(dt.timezone.utc).isoformat(),
            "message": self.message,
        }


@dataclass(slots=True)
class CommitRange:
    """Collection of commits along with the resolved boundaries."""

    commits: List[CommitInfo]
    mode: RangeMode
    start_ref: str | None
    end_ref: str
    fallback_used: bool


class GitDependencyError(RuntimeError):
    """Raised when GitPython is unavailable in the execution environment."""


def open_repository(root: Path | None = None) -> "git.Repo":
    """Open the git repository at *root* (default: auto-discover)."""

    if git is None:  # pragma: no cover - runtime guard
        raise GitDependencyError(
            "GitPython is required for whatsnew ingestion. Install gitpython to continue."
        )

    root = root or _discover_repo_root(Path.cwd())
    return git.Repo(root, search_parent_directories=True)


def describe_repository(root: Path | None = None) -> RepositoryMetadata:
    """Return repository metadata for the repo rooted at *root*."""

    repo = open_repository(root)
    actual_root = Path(repo.working_tree_dir or Path.cwd()).resolve()
    remote_url = _get_remote_url(repo)
    owner, name = _split_remote(remote_url) if remote_url else (None, None)
    default_branch = _get_default_branch(repo)
    return RepositoryMetadata(
        root=actual_root,
        remote_url=remote_url,
        owner=owner,
        name=name,
        default_branch=default_branch,
    )


def list_tags(repo: "git.Repo") -> list[str]:
    """Return repository tags sorted in descending semantic/lexicographic order."""

    tag_names = [tag.name for tag in repo.tags]
    return sorted(tag_names, key=_tag_sort_key, reverse=True)


def get_commit_range(repo: "git.Repo", request: RangeRequest) -> CommitRange:
    """Fetch commits matching the specified *request*."""

    commits: list = []
    start_ref: str | None = None
    fallback_used = False

    if request.mode is RangeMode.SINCE_SPECIFIC_TAG:
        if not request.tag:
            raise ValueError("Tag-based range requested without a tag value")
        start_ref = request.tag
        commits = list(repo.iter_commits(f"{request.tag}..HEAD"))
    elif request.mode is RangeMode.SINCE_LAST_TAG:
        tags = list_tags(repo)
        if tags:
            start_ref = tags[0]
            commits = list(repo.iter_commits(f"{start_ref}..HEAD"))
        else:
            fallback_used = True
            commits = _commits_with_window(repo, _days_to_delta(request.fallback_window_days))
    elif request.mode is RangeMode.SHA_RANGE:
        end_ref = request.to_sha or "HEAD"
        start_ref = request.from_sha
        rev_range = f"{request.from_sha}..{end_ref}" if request.from_sha else end_ref
        commits = list(repo.iter_commits(rev_range))
    elif request.mode is RangeMode.DATE_RANGE:
        since = request.since.isoformat() if request.since else None
        until = request.until.isoformat() if request.until else None
        commits = list(repo.iter_commits("HEAD", since=since, until=until))
        if not commits and request.fallback_window_days:
            fallback_used = True
            commits = _commits_with_window(repo, _days_to_delta(request.fallback_window_days))
    elif request.mode is RangeMode.WINDOW:
        commits = _commits_with_window(repo, request.window)
    else:  # pragma: no cover - defensive
        commits = list(repo.iter_commits("HEAD"))

    commit_infos = [_normalize_commit(commit) for commit in reversed(commits)]
    return CommitRange(
        commits=commit_infos,
        mode=request.mode,
        start_ref=start_ref,
        end_ref=request.to_sha or "HEAD",
        fallback_used=fallback_used,
    )


def _normalize_commit(commit: "git.Commit") -> CommitInfo:
    committed_dt = commit.committed_datetime
    if committed_dt.tzinfo is None:
        committed_dt = committed_dt.replace(tzinfo=dt.timezone.utc)
    return CommitInfo(
        sha=commit.hexsha,
        parent_shas=[parent.hexsha for parent in commit.parents],
        author_name=commit.author.name,
        author_email=getattr(commit.author, "email", ""),
        committed_datetime=committed_dt.astimezone(dt.timezone.utc),
        message=commit.message.strip(),
    )


def _commits_with_window(repo: "git.Repo", window: dt.timedelta | None) -> list:
    if window is None:
        return list(repo.iter_commits("HEAD"))
    since_dt = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc) - window
    since = since_dt.isoformat()
    return list(repo.iter_commits("HEAD", since=since))


def _days_to_delta(days: int | None) -> dt.timedelta | None:
    if days is None:
        return None
    return dt.timedelta(days=days)


def _discover_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current


def _get_remote_url(repo: "git.Repo") -> str | None:
    try:
        origin = repo.remotes.origin
    except (AttributeError, IndexError):
        return None
    urls = list(origin.urls)
    return urls[0] if urls else None


def _split_remote(remote_url: str) -> tuple[str | None, str | None]:
    if remote_url.startswith("git@"):  # git@github.com:owner/repo.git
        _, path = remote_url.split(":", 1)
    elif remote_url.startswith("https://") or remote_url.startswith("http://"):
        path = remote_url.split("://", 1)[1]
        path = path.split("/", 1)[1]
    else:
        path = remote_url

    path = path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return None, None


def _get_default_branch(repo: "git.Repo") -> str | None:
    try:
        ref = repo.git.symbolic_ref("refs/remotes/origin/HEAD")
        return ref.split("/")[-1]
    except Exception:  # pragma: no cover - depends on repo config
        pass
    try:
        return repo.active_branch.name
    except Exception:  # pragma: no cover - detached head or bare repo
        return None


def _tag_sort_key(tag_name: str) -> tuple[int, int, int, str]:
    match = _SEMVER_RE.match(tag_name)
    if not match:
        return (0, 0, 0, tag_name)
    major = int(match.group(1)) if match.group(1) else 0
    minor = int(match.group(2)) if match.group(2) else 0
    patch = int(match.group(3)) if match.group(3) else 0
    return (major, minor, patch, tag_name)

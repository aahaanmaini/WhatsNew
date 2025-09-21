"""Diff extraction helpers for whatsnew ingestion."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence

try:  # pragma: no cover - optional dependency, enforced at runtime
    import git  # type: ignore
except ImportError:  # pragma: no cover - optional dependency, enforced at runtime
    git = None  # type: ignore

logger = logging.getLogger(__name__)

_ALLOWED_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".go",
    ".rs",
    ".java",
    ".rb",
    ".cs",
    ".hpp",
    ".h",
    ".c",
    ".md",
    ".yml",
    ".yaml",
    ".json",
    ".proto",
    ".graphql",
    ".sql",
}

_SKIP_PATTERNS = (
    "vendor/",
    "node_modules/",
    "generated/",
)

_SKIP_SUFFIXES = (
    ".lock",
    ".min.js",
    ".min.css",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
)

_PRIORITY_PATH_SEGMENTS = ("api/", "public/", "cli/", "docs/", "schema/")

_NULL_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


@dataclass(slots=True)
class FileStat:
    path: str
    additions: int
    deletions: int

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "adds": self.additions,
            "dels": self.deletions,
        }


@dataclass(slots=True)
class Snippet:
    path: str
    sha: str
    hunk: str

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "sha": self.sha,
            "hunk": self.hunk,
        }


def collect_commit_diffs(
    repo: "git.Repo",
    shas: Sequence[str],
    *,
    max_hunks_per_item: int = 2,
    char_budget: int = 4000,
) -> tuple[List[FileStat], List[Snippet]]:
    """Return file stats and curated hunks for the provided commit SHAs."""

    if git is None:  # pragma: no cover - runtime guard
        raise RuntimeError("GitPython is required for diff collection. Install gitpython to continue.")

    aggregated_stats: Dict[str, FileStat] = {}
    snippets: List[Snippet] = []
    remaining_budget = char_budget

    for sha in shas:
        try:
            commit = repo.commit(sha)
        except Exception as exc:  # pragma: no cover - depends on repo state
            logger.warning("Unable to load commit %s: %s", sha, exc)
            continue

        _merge_stats(aggregated_stats, commit.stats.files)
        parent = commit.parents[0] if commit.parents else None
        diff_index = commit.diff(parent, create_patch=True) if parent else commit.diff(_NULL_TREE, create_patch=True)

        candidate_hunks: List[tuple[float, str, str]] = []
        for diff in diff_index:
            path = diff.b_path or diff.a_path
            if not path or not _should_include_path(path):
                continue
            patch_bytes = diff.diff
            if not patch_bytes:
                continue
            if isinstance(patch_bytes, bytes):
                patch_text = patch_bytes.decode("utf-8", errors="ignore")
            else:
                patch_text = str(patch_bytes)
            for hunk in _extract_hunks(patch_text):
                score = _score_hunk(path, hunk)
                candidate_hunks.append((score, path, hunk))

        if not candidate_hunks:
            continue

        candidate_hunks.sort(key=lambda item: item[0], reverse=True)
        for _, path, hunk in candidate_hunks[:max_hunks_per_item]:
            if remaining_budget <= 0:
                break
            snippet_text = hunk.strip()
            text_len = len(snippet_text)
            if text_len > remaining_budget:
                snippet_text = snippet_text[: max(remaining_budget - 1, 0)] + ("…" if remaining_budget > 0 else "")
                text_len = len(snippet_text)
            snippets.append(Snippet(path=path, sha=sha, hunk=snippet_text))
            remaining_budget -= text_len

    files = sorted(aggregated_stats.values(), key=lambda fs: fs.path)
    snippets_sorted = sorted(snippets, key=lambda sn: (sn.path, sn.sha))
    return files, snippets_sorted


def _merge_stats(target: Dict[str, FileStat], stats: Mapping[str, Mapping[str, int]]) -> None:
    for path, data in stats.items():
        if not _should_include_path(path):
            continue
        adds = int(data.get("insertions", 0))
        dels = int(data.get("deletions", 0))
        if path in target:
            entry = target[path]
            entry.additions += adds
            entry.deletions += dels
        else:
            target[path] = FileStat(path=path, additions=adds, deletions=dels)


def _extract_hunks(patch_text: str) -> List[str]:
    hunks: List[str] = []
    current: List[str] = []
    for line in patch_text.splitlines():
        if line.startswith("@@"):
            if current:
                hunks.append("\n".join(current))
                current = []
            current.append(line)
        elif current:
            current.append(line)
    if current:
        hunks.append("\n".join(current))
    return hunks


def _should_include_path(path: str) -> bool:
    lowered = path.lower()
    if any(segment in lowered for segment in _SKIP_PATTERNS):
        return False
    if any(lowered.endswith(suffix) for suffix in _SKIP_SUFFIXES):
        return False
    if path.endswith("/"):
        return False
    suffix = _suffix(path)
    return suffix in _ALLOWED_SUFFIXES


def _suffix(path: str) -> str:
    idx = path.rfind(".")
    return path[idx:].lower() if idx != -1 else ""


def _score_hunk(path: str, hunk: str) -> float:
    score = 0.0
    if any(segment in path for segment in _PRIORITY_PATH_SEGMENTS):
        score += 1.0
    if re.search(r"^\+.*(def |class |function |export )", hunk, flags=re.MULTILINE):
        score += 1.5
    if re.search(r"^@@.*(public|export|class|function)", hunk, flags=re.MULTILINE):
        score += 0.5
    score += min(len(hunk), 500) / 1000.0
    return score

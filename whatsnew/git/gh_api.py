"""GitHub API helper utilities."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence, Set

import requests

logger = logging.getLogger(__name__)

_ISSUE_REF_RE = re.compile(r"#(?P<number>\d+)")


@dataclass(slots=True)
class PullRequestInfo:
    """Lightweight representation of a GitHub pull request."""

    number: int
    title: str
    body: str
    labels: List[str]
    merged: bool
    state: str
    url: str
    merge_commit_sha: str | None
    head_ref: str | None
    base_ref: str | None

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "title": self.title,
            "body": self.body,
            "labels": self.labels,
            "merged": self.merged,
            "state": self.state,
            "url": self.url,
            "merge_commit_sha": self.merge_commit_sha,
            "head_ref": self.head_ref,
            "base_ref": self.base_ref,
        }


@dataclass(slots=True)
class IssueInfo:
    """Lightweight representation of a GitHub issue."""

    number: int
    title: str
    body: str
    labels: List[str]
    state: str
    url: str

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "title": self.title,
            "body": self.body,
            "labels": self.labels,
            "state": self.state,
            "url": self.url,
        }


class GitHubClient:
    """Minimal GitHub REST API client with token support."""

    def __init__(
        self,
        owner: str,
        repo: str,
        *,
        token: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.owner = owner
        self.repo = repo
        self.base_url = f"https://api.github.com/repos/{owner}/{repo}"
        self._session = session or requests.Session()
        self._token = token or os.environ.get("GH_TOKEN")

    def fetch_pulls_for_commits(self, shas: Sequence[str]) -> Dict[str, List[PullRequestInfo]]:
        """Return pull requests associated with each commit SHA."""

        results: Dict[str, List[PullRequestInfo]] = {}
        for sha in shas:
            try:
                pulls = self._request(
                    "GET",
                    f"/commits/{sha}/pulls",
                    headers={"Accept": "application/vnd.github.groot-preview+json"},
                )
            except requests.RequestException as exc:  # pragma: no cover - network dependent
                logger.warning("Failed to fetch pull requests for %s: %s", sha, exc)
                continue

            pr_infos: List[PullRequestInfo] = []
            for payload in pulls or []:
                pr_infos.append(_pull_from_payload(payload))
            if pr_infos:
                results[sha] = pr_infos
        return results

    def fetch_pull(self, number: int) -> PullRequestInfo | None:
        try:
            payload = self._request("GET", f"/pulls/{number}")
        except requests.RequestException as exc:  # pragma: no cover - network dependent
            logger.warning("Failed to fetch PR #%s: %s", number, exc)
            return None
        if not payload:
            return None
        return _pull_from_payload(payload)

    def fetch_issues(self, numbers: Iterable[int]) -> Dict[int, IssueInfo]:
        results: Dict[int, IssueInfo] = {}
        for number in numbers:
            try:
                payload = self._request("GET", f"/issues/{number}")
            except requests.RequestException as exc:  # pragma: no cover - network dependent
                logger.warning("Failed to fetch issue #%s: %s", number, exc)
                continue
            if not payload:
                continue
            if "pull_request" in payload:
                # Skip PRs returned from the issues endpoint.
                continue
            results[number] = _issue_from_payload(payload)
        return results

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> dict | list | None:
        url = f"{self.base_url}{path}"
        request_headers = {
            "Accept": "application/vnd.github+json",
        }
        if headers:
            request_headers.update(headers)
        if self._token:
            request_headers["Authorization"] = f"Bearer {self._token}"

        response = self._session.request(method, url, headers=request_headers, timeout=10)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        if not response.content:
            return None
        return response.json()


def extract_issue_numbers(*texts: str) -> Set[int]:
    """Extract issue numbers referenced as #123 from given texts."""

    numbers: Set[int] = set()
    for text in texts:
        if not text:
            continue
        for match in _ISSUE_REF_RE.finditer(text):
            numbers.add(int(match.group("number")))
    return numbers


def _pull_from_payload(payload: Mapping[str, object]) -> PullRequestInfo:
    labels = [item.get("name", "") for item in payload.get("labels", [])]  # type: ignore[arg-type]
    return PullRequestInfo(
        number=int(payload.get("number", 0)),
        title=str(payload.get("title", "")),
        body=str(payload.get("body") or ""),
        labels=[label for label in labels if label],
        merged=bool(payload.get("merged", False)),
        state=str(payload.get("state", "open")),
        url=str(payload.get("html_url", "")),
        merge_commit_sha=str(payload.get("merge_commit_sha") or "") or None,
        head_ref=str(payload.get("head", {}).get("ref", "")) or None,  # type: ignore[index]
        base_ref=str(payload.get("base", {}).get("ref", "")) or None,  # type: ignore[index]
    )


def _issue_from_payload(payload: Mapping[str, object]) -> IssueInfo:
    labels = [item.get("name", "") for item in payload.get("labels", [])]  # type: ignore[arg-type]
    return IssueInfo(
        number=int(payload.get("number", 0)),
        title=str(payload.get("title", "")),
        body=str(payload.get("body") or ""),
        labels=[label for label in labels if label],
        state=str(payload.get("state", "open")),
        url=str(payload.get("html_url", "")),
    )

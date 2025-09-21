"""Entry point for gathering git and GitHub data for summarization."""

from __future__ import annotations

import logging
from typing import Dict, List

from ..config import WhatsNewConfig
from ..git.diffs import collect_commit_diffs
from ..git.gh_api import GitHubClient, PullRequestInfo, extract_issue_numbers
from ..git.repo import CommitRange, describe_repository, get_commit_range, open_repository
from ..utils.dates import RangeRequest, summarize_range_request

logger = logging.getLogger(__name__)


def collect_changes(config: WhatsNewConfig, range_request: RangeRequest) -> Dict[str, object]:
    """Collect commits, PRs, issues, and diffs for the requested range."""

    repo = open_repository(config.repo_root)
    repo_meta = describe_repository(config.repo_root)

    commit_range = get_commit_range(repo, range_request)
    commit_dicts = [commit.to_dict() for commit in commit_range.commits]
    commit_shas = [commit.sha for commit in commit_range.commits]

    include_code = bool(config.data.get("include_code_hunks", True))
    file_stats: List[dict]
    snippets: List[dict]
    if commit_shas:
        stats, snippet_objs = collect_commit_diffs(
            repo,
            commit_shas,
            max_hunks_per_item=2,
            char_budget=4000,
        )
        file_stats = [entry.to_dict() for entry in stats]
        snippets = [entry.to_dict() for entry in snippet_objs] if include_code else []
    else:
        file_stats = []
        snippets = []

    prs: List[dict] = []
    issues: List[dict] = []
    if repo_meta.owner and repo_meta.name and commit_shas:
        token = config.data.get("credentials", {}).get("github_token")
        try:
            gh_client = GitHubClient(repo_meta.owner, repo_meta.name, token=token)
            pr_map = _fetch_pull_requests(gh_client, commit_shas)
            prs = [pr.to_dict() for pr in pr_map.values()]
            issues = _fetch_linked_issues(gh_client, pr_map, commit_range)
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning("GitHub API requests failed: %s", exc)

    return {
        "repository": {
            "root": str(repo_meta.root),
            "owner": repo_meta.owner,
            "name": repo_meta.name,
            "default_branch": repo_meta.default_branch,
            "remote_url": repo_meta.remote_url,
        },
        "range": {
            "mode": range_request.mode.value,
            "summary": summarize_range_request(range_request),
            "start_ref": commit_range.start_ref,
            "end_ref": commit_range.end_ref,
            "fallback_used": commit_range.fallback_used,
        },
        "commits": commit_dicts,
        "prs": prs,
        "issues": issues,
        "files": file_stats,
        "snippets": snippets,
    }


def _fetch_pull_requests(
    gh_client: GitHubClient,
    commit_shas: List[str],
) -> Dict[int, PullRequestInfo]:
    mapping: Dict[int, PullRequestInfo] = {}
    sha_to_prs = gh_client.fetch_pulls_for_commits(commit_shas)
    for pr_list in sha_to_prs.values():
        for pr in pr_list:
            mapping[pr.number] = pr
    return mapping


def _fetch_linked_issues(
    gh_client: GitHubClient,
    prs: Dict[int, PullRequestInfo],
    commit_range: CommitRange,
) -> List[dict]:
    issue_numbers = set()
    for pr in prs.values():
        issue_numbers.update(extract_issue_numbers(pr.title, pr.body))
    for commit in commit_range.commits:
        issue_numbers.update(extract_issue_numbers(commit.message))

    if not issue_numbers:
        return []

    issues = gh_client.fetch_issues(issue_numbers)
    return [issue.to_dict() for issue in issues.values()]

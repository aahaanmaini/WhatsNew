from __future__ import annotations

import os
import subprocess
from pathlib import Path

import git
import pytest


@pytest.fixture(autouse=True)
def clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure external providers don't interfere with tests."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)


@pytest.fixture
def sample_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_dir = tmp_path / "repo"
    repo = git.Repo.init(repo_dir)
    writer = repo.config_writer()
    writer.set_value("user", "name", "Test User")
    writer.set_value("user", "email", "test@example.com")
    writer.release()

    def commit(message: str, content: str) -> None:
        path = repo_dir / "CHANGELOG.md"
        path.write_text(content, encoding="utf-8")
        repo.index.add(["CHANGELOG.md"])
        repo.index.commit(message)

    (repo_dir / "CHANGELOG.md").write_text("seed", encoding="utf-8")
    repo.index.add(["CHANGELOG.md"])
    repo.index.commit("chore: initial commit")
    repo.create_tag("v0.1.0")

    commit("feat: add onboarding flow", "feature work")
    commit("fix: handle empty input", "fix work")
    commit("docs: update quickstart", "docs work")

    if "origin" not in [remote.name for remote in repo.remotes]:
        repo.create_remote("origin", "https://github.com/example/whatsnew-test.git")

    monkeypatch.chdir(repo_dir)
    return repo_dir


@pytest.fixture
def run_cli(sample_repo: Path):
    def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{Path(__file__).resolve().parents[1]}:{env.get('PYTHONPATH', '')}".rstrip(":")
        cmd = [os.sys.executable, "-m", "whatsnew.cli", *args]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check,
            env=env,
        )

    return _run

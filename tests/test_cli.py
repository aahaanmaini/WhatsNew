from __future__ import annotations

import json

import pytest


def test_cli_json_output(run_cli):
    result = run_cli("--json")
    payload = json.loads(result.stdout)
    assert payload["repo"] == "example/whatsnew-test"
    assert payload["stats"]["commits"] == 3
    assert any(section["items"] for section in payload["sections"])


def test_cli_markdown_output(run_cli):
    result = run_cli("--md")
    assert "# whatsnew for example/whatsnew-test" in result.stdout


def test_cli_preview_command(run_cli):
    result = run_cli("preview", check=False)
    assert result.returncode == 0
    assert "Branch:" in result.stdout


def test_cli_invalid_flag_combo(run_cli):
    result = run_cli("--tag", "v0.1.0", "--window", "7d", check=False)
    assert result.returncode != 0
    assert "mutually exclusive" in result.stderr

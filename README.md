# whatsnew

Generate concise, user-facing changelogs straight from git history.

## Quickstart

```bash
pipx install --editable .
whatsnew --help
```

### Optional provider dependencies

- OpenAI: `pip install openai`
- Cerebras: `pip install cerebras-cloud-sdk`

## GitHub Action

This repository ships with a ready-to-use workflow at `.github/workflows/whatsnew.yml` that:

- Runs on every `v*` tag push
- Generates JSON/Markdown changelog artifacts for the tag
- Publishes the results to the `gh-pages` branch via `whatsnew publish`

### Required secrets

- `OPENAI_API_KEY` (optional but recommended for high-quality summaries)
- `CEREBRAS_API_KEY` (set if you prefer the Cerebras Inference API)
- `GITHUB_TOKEN` is provided automatically by GitHub Actions and used for pushing to `gh-pages`

Once those secrets are configured in your repository settings, pushing a tag such as `v1.2.3` will build the release notes and publish them to GitHub Pages.

### Release labels

You can assign friendly names to releases:

```bash
whatsnew publish --tag v0.2.0 --label "Autumn 2024 Release"
```

The publish command records the label in `data/releases/index.json` and the individual release file so the frontend can display it instead of the raw tag name. You can also define defaults in `whatsnew.config.yml` under `publish.label` (single value) or `publish.labels.<tag>` (per-tag overrides).

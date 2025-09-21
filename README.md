# whatsnew

Generate concise, user-facing changelogs straight from git history.

## Quickstart

```bash
pipx install --editable .
whatsnew --help
```

## GitHub Action

This repository ships with a ready-to-use workflow at `.github/workflows/whatsnew.yml` that:

- Runs on every `v*` tag push
- Generates JSON/Markdown changelog artifacts for the tag
- Publishes the results to the `gh-pages` branch via `whatsnew publish`

### Required secrets

- `OPENAI_API_KEY` (optional but recommended for high-quality summaries)
- `GITHUB_TOKEN` is provided automatically by GitHub Actions and used for pushing to `gh-pages`

Once those secrets are configured in your repository settings, pushing a tag such as `v1.2.3` will build the release notes and publish them to GitHub Pages.

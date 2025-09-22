# whatsnew

Generate crisp, developer-facing changelogs directly from Git. `whatsnew` analyzes commits, pull requests, issues, file paths, and curated diff hunks, runs them through an LLM map→reduce pipeline, and publishes the results to GitHub Pages so teams always know what shipped.

View the public changelog explorer at **[https://whatsnew-cli.vercel.app](https://whatsnew-cli.vercel.app)**. Push a release with `whatsnew publish` and the site updates instantly.

---

## Why WhatsNew?

- **Automate release notes** – stop combing through commits or copy/pasting PR descriptions.
- **LLM-assisted summaries** – choose OpenAI or Cerebras; fall back to a heuristic summarizer offline.
- **Accurate tag ranges** – `whatsnew publish --tag vX.Y.Z` automatically diff the previous tag → `vX.Y.Z`.
- **Friendly release labels** – surface human-readable names in the frontend (`--label`, config defaults, or per-tag overrides).
- **Zero-flag defaults** – running `whatsnew` just works, summarizing since the last tag (fallback: 7-day window).
- **Rich outputs** – pretty terminal rendering, canonical JSON, Markdown, and a `gh-pages` artifact layout consumed by the hosted viewer.
- **Repeatable** – the golden snapshot + comprehensive tests keep summaries stable across upgrades.

---

## Installation

```bash
pip install whatsnew
```

The package targets Python ≥ 3.10 and bundles the optional OpenAI + Cerebras SDKs so you can swap providers without extra installs. Prefer pipx? Try `pipx install whatsnew`.

---

## Quickstart

```bash
# summarize since the last release tag (fallback: 7-day window)
whatsnew

# JSON or Markdown snapshots to stdout
whatsnew --json
whatsnew --md

# publish a weekly changelog (no tag, friendly label)
whatsnew publish --window 7d --label "Week 37"

# publish an actual tagged release (previous tag → v0.2.0)
git tag v0.2.0 && git push origin v0.2.0
whatsnew publish --tag v0.2.0 --label "Autumn 2024 Release"

# preview publish writes
whatsnew preview --tag v0.2.0

# environment diagnostics
whatsnew check
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `whatsnew` | Summarize the default range (last tag → HEAD, fallback 7-day window). |
| `whatsnew publish [flags]` | Write `data/latest.json`, optionally `data/releases/<tag>.json`, commit to `gh-pages`, and push. |
| `whatsnew preview [flags]` | Same as publish but prints diffs (no writes). |
| `whatsnew release --tag TAG [flags]` | Render the snapshot for `TAG` to stdout. |
| `whatsnew check` | Validate Git remotes, tokens, and provider configuration. |

Tag-aware commands automatically convert `--tag vX.Y.Z` into the correct range (previous tag → `vX.Y.Z`).

---

## Flags & Options

### Global flags (available on all commands)

| Flag | Description |
|------|-------------|
| `--json` | Emit canonical JSON to stdout. |
| `--md` | Emit Markdown to stdout. |
| `--no-code` | Skip sending code hunks to the summarizer. |
| `--include-internal` | Include internal-only changes. |
| `--drop-internal` | Explicitly drop internal changes (default). |
| `--repo-root PATH` | Override repo auto-detection. |
| `--log-level {debug,info,warning,error}` | Adjust logging verbosity. |
| `--config PATH` | Load a specific `whatsnew.config.yml`. |
| `--private` | Prefer the Cerebras provider when both APIs are configured. |

### Range selection flags (mutually exclusive)

| Flag | Description |
|------|-------------|
| `--tag TAG` | Release tag. For publish/preview/release this labels the changelog and sets the range to previous tag → `TAG`. |
| `--from-sha SHA` / `--to-sha SHA` | Explicit commit boundaries. |
| `--since-date ISO` / `--until-date ISO` | Date-bounded ranges (ISO 8601). |
| `--window [Nd|Nw|Nh]` | Sliding window (e.g. `7d`, `14d`, `24h`). |

### Publish/Preview/Release flags

| Flag | Description |
|------|-------------|
| `--label "Name"` | Friendly release name surfaced in JSON + changelog viewer. |
| `--message ".."` | Custom publish commit message. |
| `--force-publish` | Push even if the repo is private (overrides safety checks). |
| `--dry-run` | Run the workflow without writing or pushing.

---

## Configuration

Optional `whatsnew.config.yml` at the repo root:

```yaml
publish:
  branch: gh-pages
  paths:
    latest: data/latest.json
    releases: data/releases
  label: "Weekly Digest"           # default label when --label is omitted
  labels:
    v1.0.0: "Spring 2024 Release" # per-tag overrides
credentials:
  openai_api_key: ${OPENAI_API_KEY}
  cerebras_api_key: ${CEREBRAS_API_KEY}
```

Order of precedence: defaults → config file → environment (`OPENAI_API_KEY`, `CEREBRAS_API_KEY`, `GH_TOKEN`, etc.) → CLI flags.

---

## Providers

`whatsnew` routes summarization through a provider abstraction:

- **OpenAI** – default provider. Set `OPENAI_API_KEY` and optionally `provider.model` in config.
- **Cerebras Inference API** – set `CEREBRAS_API_KEY`. Large context support (default `qwen-3-32b`, override via `provider.model`). Use `--private` when both keys exist to prefer Cerebras.
- **Fallback** – deterministic heuristics when no API keys are present or the provider fails.

Retries are handled with exponential backoff via `tenacity`.

---

## Publishing Flow & Release Labels

1. **Range resolution**
   - `whatsnew publish --tag v0.2.0` resolves commits from the previous tag (or first commit) to `v0.2.0`.
   - The resolved range is recorded in `summary.meta` (`from_tag`, `to_tag`, `from_sha`, `to_sha`) and emitted in the JSON payload.
2. **Label propagation**
   - Supply `--label "Autumn 2024"` or configure `publish.label / publish.labels.v0.2.0`.
   - The label populates `meta.label` and the top-level `label` in JSON so the frontend can display it.
3. **Artifacts**
   - `data/latest.json` – always updated (captures the label when no tag is present).
   - `data/releases/<tag>.json` – generated when `--tag` is supplied.
   - `data/releases/index.json` – release index (tag, label, released_at, range, stats, path), updated only for tagged publishes.

---

## Artifact Layout

```
root
├── data
│   ├── latest.json              # current release (may include label but no tag)
│   └── releases
│       ├── index.json           # array of tagged releases (label, tag, released_at, path)
│       └── v0.2.0.json          # tagged release snapshot
└── ...
```

---

## GitHub Action

`whatsnew` ships with a ready-to-use workflow (see `.github/workflows/whatsnew.yml`). It triggers on tag pushes, installs the package, and runs `whatsnew publish --tag "$GITHUB_REF_NAME"`. Ensure `OPENAI_API_KEY` or `CEREBRAS_API_KEY` (optional) and `GITHUB_TOKEN` (automatic) are available in repo secrets.

---

## Changelog Viewer

Published releases are rendered by **https://whatsnew-cli.vercel.app**:

```
https://whatsnew-cli.vercel.app/<owner>/<repo>
```

- `latest.json` drives the default view.
- `releases/index.json` powers the release timeline.
- Each entry includes `label` (friendly name) and `path` for the detail view.
- The site fetches directly from `gh-pages`, so publish updates appear immediately.

Frontend integration tips:

```ts
// Fetch releases
const releases: ReleaseEntry[] = await fetch('/data/releases/index.json').then(res => res.json());

const name = (entry: ReleaseEntry) => entry.label || entry.tag || 'Latest';
const detail = await fetch(entry.path).then(res => res.json()); // includes top-level "label"
```

---

## Development

```bash
pip install -e .
python -m pytest

# optional linting
pip install ruff mypy
ruff check .
mypy whatsnew
```

Key modules:

- `whatsnew/config.py` – layered config loader supporting overrides.
- `whatsnew/git/` – tag discovery, range resolution, diff helpers.
- `whatsnew/summarize/` – map/reduce pipeline, prompts, provider integration.
- `whatsnew/outputs/` – canonical JSON schema, Markdown, rich terminal renderer.
- `whatsnew/publish/` – preview/publish workflows and release index maintenance.
- `tests/` – unit tests, cli smoke tests, golden snapshot.

Contributions welcome—open a PR after running `python -m pytest`.

---

## License

MIT © WhatsNew Maintainers

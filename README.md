# What’s New?

Generate crisp, developer-facing changelogs straight from Git. 

`whatsnew` scans commits/PRs/issues + high-signal diff hunks, runs a disciplined LLM **map → reduce** summarization, and (optionally) publishes to gh-pages so your public viewer updates instantly.

---

## 🚀 Quickstart

**1) Install (Python ≥ 3.10)**  
```bash
pip install whatsnew
```

**2) Set environment variables (use what you have)**

```bash
# choose one provider (or both)
export OPENAI_API_KEY=sk-...           
# or
export CEREBRAS_API_KEY=...            

# recommended so PR/issue context is rich (public/private):
export GH_TOKEN=ghp_...                
```

**3) Run commands**

```bash
# summarize since last tag (fallback: 7-day window)
whatsnew

# force a time window
whatsnew --window 14d

# preview what would be written to gh-pages
whatsnew preview --window 14d

# publish latest (no tag) — updates data/latest.json
whatsnew publish --window 14d --label "Week 37"

# publish a tagged release (prev tag → v0.2.0) and update releases/v0.2.0.json
git tag v0.2.0 && git push origin v0.2.0
whatsnew publish --tag v0.2.0 --label "Autumn 2024"
```

**4) View it publicly** 

👉 Visit [https://whatsnew-cli.vercel.app](https://whatsnew-cli.vercel.app).  
The homepage will guide you to the correct project.

---

## ⭐ Key Features

* **One-command changelog** — `whatsnew` “just works” with smart defaults (last tag → `HEAD`, fallback window).
* **Works with your keys** — bring your own `OPENAI_API_KEY` or `CEREBRAS_API_KEY`; offline fallback uses heuristics.
* **Deep context** — commit messages, PRs, linked issues, file paths, and curated diff hunks (privacy toggle `--no-code`).
* **Concise sections** — enforces short, action-led blurbs and caps each section at 5 bullets to stay readable.
* **Tag-aware releases** — `whatsnew publish --tag vX.Y.Z` diffs previous tag → `vX.Y.Z` and writes release JSON.
* **Preview before publish** — `whatsnew preview` shows exactly which files/commits would land on `gh-pages`.
* **CI-ready** — ship on tag push with a tiny GitHub Action.
* **Zero-backend viewer** — public Next.js site reads JSON from `gh-pages`; updates as soon as you push.
* **Caching built-in** — per-commit summaries are cached to avoid re-calling the provider for unchanged history.
* **Retries with clear messaging** — automatic retries on provider/API errors with actionable logs.

<details>
<summary><b>Example GitHub Action</b></summary>

```yaml
name: publish-changelog
on: { push: { tags: ['v*'] } }
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install whatsnew
      - name: Publish changelog
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}   # or CEREBRAS_API_KEY
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: whatsnew publish --tag "${GITHUB_REF_NAME}"
```

</details>

---

## 🧰 CLI Commands

| Command                              | Description                                                                                      |
| ------------------------------------ | ------------------------------------------------------------------------------------------------ |
| `whatsnew`                           | Summarize the default range (last tag → HEAD, fallback 7-day window).                            |
| `whatsnew publish [flags]`           | Write `data/latest.json`, optionally `data/releases/<tag>.json`, commit to `gh-pages`, and push. |
| `whatsnew preview [flags]`           | Same as publish but prints diffs (no writes).                                                    |
| `whatsnew release --tag TAG [flags]` | Render the snapshot for `TAG` to stdout.                                                         |
| `whatsnew check`                     | Validate Git remotes, tokens, and provider configuration.                                        |

---

## 🚩 Flags & Options

### Global flags (available on all commands)

| Flag                                     | Description                                                 |
| ---------------------------------------- | ----------------------------------------------------------- |
| `--json`                                 | Emit canonical JSON to stdout.                              |
| `--md`                                   | Emit Markdown to stdout.                                    |
| `--no-code`                              | Skip sending code hunks to the summarizer.                  |
| `--include-internal`                     | Include internal-only changes.                              |
| `--drop-internal`                        | Explicitly drop internal changes (default).                 |
| `--repo-root PATH`                       | Override repo auto-detection.                               |
| `--log-level {debug,info,warning,error}` | Adjust logging verbosity.                                   |
| `--config PATH`                          | Load a specific `whatsnew.config.yml`.                      |
| `--private`                              | Prefer the Cerebras provider when both APIs are configured. |

### Range selection flags (mutually exclusive)

| Flag                                    | Description                                                                                                    |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `--tag TAG`                             | Release tag. For publish/preview/release this labels the changelog and sets the range to previous tag → `TAG`. |
| `--from-sha SHA` / `--to-sha SHA`       | Explicit commit boundaries.                                                                                    |
| `--since-date ISO` / `--until-date ISO` | Date-bounded ranges (ISO 8601).                                                                                |
| `--window [Nd \| Nw \| Nh]`             | Sliding window (e.g. `7d`, `14d`, `24h`).                                                                     |

### Publish/Preview/Release flags

| Flag              | Description                                                 |
| ----------------- | ----------------------------------------------------------- |
| `--label "Name"`  | Friendly release name surfaced in JSON + changelog viewer.  |
| `--message ".."`  | Custom publish commit message.                              |
| `--force-publish` | Push even if the repo is private (overrides safety checks). |
| `--dry-run`       | Run the workflow without writing or pushing.                |

---

## 💡 Design Decisions

<details>
<summary><b>CLI-first, GitHub-only integration</b></summary>
We optimized for developer flow: run in any local repo or CI without wiring web UIs or databases. Git is the single source of truth, and GitHub is the highest-leverage incremental context (PRs, issues, tags). This keeps setup minimal and adoption friction near zero.
</details>

<details>
<summary><b>Range selection: “since last tag” by default, plus windows/dates</b></summary>
Releases map naturally to tags, so the default is previous tag → `HEAD`. For teams without tags or for interim digests, you can specify windows (`--window 14d`) or dates. This mirrors how devs actually think about shipping: either “the new release” or “what happened this week.”
</details>

<details>
<summary><b>Ground truth from files and hunks; PRs/issues as context</b></summary>
Commit messages alone are noisy. We classify by where changes occurred (paths, extensions) and select high-signal diff hunks (API/CLI/UI/docs). PR/issue text is used to clarify intent, but we don’t trust it blindly.
</details>

<details>
<summary><b>Map → Reduce with concision guarantees</b></summary>
Each change (PR or standalone commit) gets one short, user-impact bullet (Map). A Reduce pass dedupes near-duplicates and caps each section at 5 items. This scales to large ranges while keeping the final output readable.
</details>

<details>
<summary><b>Preview before publish; atomic publish to <code>gh-pages</code></b></summary>
`whatsnew preview` renders the exact file diffs and commit message without writing. `whatsnew publish` creates/updates the `gh-pages` branch (orphan safe), writes `data/latest.json` and `data/releases/<tag>.json`, and pushes a single commit—simple to audit and roll back.
</details>

<details>
<summary><b>Zero-backend viewer</b></summary>
The Next.js site reads JSON directly from `gh-pages` (or GitHub Pages). No infra, no auth for public repos, instant updates on push. For private repos, you can mirror JSON to a public artifacts repo from CI.
</details>

<details>
<summary><b>Caching & retries</b></summary>
We cache per-unit summaries, so reruns don’t re-call the LLM unnecessarily. On provider/API errors, retries are handled with exponential backoff (via `tenacity`). This keeps runs deterministic and fast without surprising costs.
</details>

---

## 🤖 AI Tools Used

- **ChatGPT**: Brainstorm and talk through product decisions  
- **Codex/Cursor**: Implementation assistance

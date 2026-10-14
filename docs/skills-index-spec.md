# agent-skills-index: spec for Claude Code session

## Purpose
A repo that tracks GitHub starred repos (bbrewington) and maps them to skills stored in this repo. When a tracked upstream repo changes, or a new star is detected, a GitHub Actions workflow opens a PR for review.

## Current state
Implemented and running. The workflow has run weekly since 2026-07-13 and opens PRs against `tracked.yml`. `tracked:` is still empty; all starred repos are `stubs:`. Remaining work is listed at the bottom.

## Repo structure
```
agent-skills-index/
  tracked.yml                   - single source of truth: config + bot-written state
  scripts/
    sync_stars.py                - sync + discover modes
    gen_pr_body.py                - renders changes.yaml into PR markdown
  .github/workflows/sync.yml     - scheduled + manual trigger workflow
  pyproject.toml / uv.lock       - dependencies (uv)
  CLAUDE.md, TODO.md, docs/
  .gitignore
  README.md
```

## Key design decisions (from grilling session)

1. No separate `index/` directory with one file per repo. Everything lives in `tracked.yml`.
2. Single file, two sections:
   - `tracked:` - human-authored config (`repo`, `skill`, `notes`, `watch_paths`) plus a bot-written `state:` block (`latest_sha`, `pushed_at`, `indexed_at`, `last_changed_at`, `description`, `language`, `topics`, `license`, `stargazers_count`)
   - `stubs:` - auto-discovered stars not yet linked to a skill, same shape but `skill`/`notes`/`watch_paths` are `null`
3. YAML everywhere, not JSON, for consistency (`tracked.yml`, `changes.yaml`).
4. All bot writes go through a PR, never committed directly to main.
5. Branch naming: `agent-skills-index/update-<ISO datetime, no separators>`, e.g. `agent-skills-index/update-20250602T080012` (UTC, `date -u +%Y%m%dT%H%M%S`).

## Two modes (in `sync_stars.py`)

- `--mode sync` - for each `tracked:` entry, fetch repo meta + latest commit SHA (scoped to `watch_paths` if set), compare against `state.latest_sha`, update state if changed.
- `--mode discover` - add any repo not in `tracked:` or `stubs:` as a new stub. Scoped to the `agent-skills` star list (slug in `STAR_LIST`, fetched via GraphQL) so unrelated stars are ignored; with no `STAR_LIST` it uses every star via the REST starred endpoint. `--prune-stubs` removes stubs outside the list (never `tracked:`).
- `--mode all` (default) runs both in one pass.
- `--dry-run` skips writing `tracked.yml` (still writes `changes.yaml` for inspection).
- Exit code 1 if any changes/new stars found, 0 otherwise (drives the workflow's PR step).

## Workflow (`.github/workflows/sync.yml`)

- Trigger: weekly cron (Mon 08:00 UTC) + `workflow_dispatch` with a `dry_run` boolean input.
- Steps: checkout -> setup uv (Python 3.14) -> `uv sync --locked` -> run `sync_stars.py --mode all` -> if changed, generate PR body via `gen_pr_body.py` -> create branch (ISO datetime name) -> commit `tracked.yml` -> `gh pr create` with title showing counts, e.g. `chore(index): skills index update 2025-06-02 (3 updated, 5 new stars)` -> label `agent-skills-index`.
- Dry run uploads `changes.yaml` as a workflow artifact instead of opening a PR.
- Needs secret `SKILLS_INDEX_TOKEN`: a fine-grained PAT with contents: write, pull requests: write, metadata: read, scoped to this repo (prefilled creation link in README Setup). Original design assumed a classic PAT with `read:user` was required for `GET /users/{user}/starred`; with a fine-grained token, verify via a dry run that discover still lists stars and fall back to classic (`repo` + `read:user`) if not.

## Remaining work

Done (originally open): repo init and push, PAT/secret, discover mode against the real API, state bootstrap, header-comment preservation (`extract_header`), rate-limit warning in the PR body, end-to-end PR flow test, first large discover PR.

Open:

0. Verify star-list scoping in Actions: run the workflow with `dry_run` (GraphQL is blocked from Claude Code sessions, so this has only been tested with mocks), check `changes.yaml`, then run once with `prune_stubs` to drop out-of-list stubs.
1. Decide the real `tracked:` list and skill paths (currently `tracked: []`; the 4 placeholders were removed).
2. Triage the stub backlog (286 as of 2026-10-14) and decide whether unreviewed weekly PRs should be closed or merged.
3. Token expiry: `SKILLS_INDEX_TOKEN` expired once (runs failing at checkout, 2026-10-05 to 2026-10-12). Now a 365 day fine-grained PAT; track its expiry date.

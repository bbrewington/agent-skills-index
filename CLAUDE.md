# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Tracks GitHub starred repos (bbrewington) and maps them to skills stored in this repo. When a tracked upstream repo changes, or a new star is detected, a GitHub Actions workflow is meant to open a PR for review.

## Commands

Dependency management is via `uv` (see `pyproject.toml` / `uv.lock`):

```
uv sync
```

Run the sync script (mutates `tracked.yml`, writes a `changes.yaml` summary):

```
uv run python scripts/sync_stars.py --mode all|sync|discover [--dry-run] [--output changes.yaml]
```

- `--mode sync` checks each `adopt`/`watch` entry for upstream SHA changes (scoped to `skill_or_plugin_paths` if set).
- `--mode discover` adds unseen repos as stubs. With `STAR_LIST` (or `--star-list`) set to comma-separated star list slug(s), it only considers repos in those lists (GraphQL); otherwise it considers every star.
- `--prune-stubs` (requires a star list) removes stubs that are not in the list. Entries with a verdict are never pruned.
- `--mode all` (default) runs both.
- `--dry-run` skips writing `tracked.yml` but still writes `changes.yaml`.
- Requires env var `GITHUB_TOKEN` (fine-grained PAT owned by the starred user; if `GET /users/{user}/starred` returns nothing or 403, use a classic PAT with `read:user`). `GITHUB_USER` defaults to `bbrewington`. `STAR_LIST` is `agent-skills,ai-helpers-and-reference` in the workflow.
- Exit code is `1` if anything changed, `0` if nothing did, `2` if `tracked.yml` fails validation. CI then applies the PR policy (see Architecture).

Render a PR body from a `changes.yaml`:

```
uv run python scripts/gen_pr_body.py --input changes.yaml --output pr_body.md
```

Tests and lint (dev deps: pytest, ruff; config in `pyproject.toml`):

```
uv run pytest
uv run ruff check .
```

Tests live in `tests/` and stub out the GitHub API; nothing hits the network. `.github/workflows/ci.yml` runs both on every pull request.

## Architecture

`tracked.yml` is the single source of truth: one `repos:` list. A stub is an entry with `verdict: null`; curated repos have `verdict` of `adopt`, `watch` or `skip` (vocabulary in `CONTEXT.md`).

- Human-authored fields: `repo`, `verdict`, `use_contexts`, `notes`, `skill_or_plugin_paths`. The bot never writes these on an existing entry; new stubs get them as `null`.
- Bot-written `state:` (`latest_sha`, `pushed_at`, `indexed_at`, `last_changed_at`, `description`, `language`, `topics`, `license`, `stargazers_count`).
- `use_contexts` tags must exist in `use-contexts.yml`. `sync_stars.py` exits 2 on an unknown tag or verdict, and `tests/test_sync_stars.py::test_committed_tracked_yml_is_valid` fails CI.

`scripts/sync_stars.py` is the only writer of `tracked.yml`. It does a full `yaml.safe_load` / `yaml.dump` round-trip on every run, but `extract_header` re-prepends the leading comment block afterward, so the header documenting the config/state field split survives. Other comments in the file would not.

`scripts/gen_pr_body.py` reads the `changes.yaml` emitted by `sync_stars.py` and renders a Markdown PR body with two sections: tracked repos with upstream changes (plus a review checklist), and newly discovered stars grouped by language.

CI is `.github/workflows/sync.yml`: weekly cron (Mon 08:00 UTC) + `workflow_dispatch` (with `dry_run` and `prune_stubs` inputs). It runs `sync_stars.py --mode all`, then `scripts/pr_policy.py` decides what to do (see the PR policy below). Dry runs upload `changes.yaml` as an artifact instead. Actions are pinned to commit SHAs. It needs a secret `SKILLS_INDEX_TOKEN` (fine-grained PAT: contents write, pull requests write, metadata read, scoped to this repo, 365 day expiry; creation link in README Setup).

PR policy: at most one open bot PR (label `agent-skills-index`, branch `agent-skills-index/update-<ISO datetime, no separators>`, e.g. `agent-skills-index/update-20250602T080012`). If one is open, the run starts from that branch's `tracked.yml` (after merging main in), pushes to it, and refreshes its title and body (the new body is appended as a dated section). If none is open, a PR is opened only when the diff holds something a human decides on: today, upstream changes to curated repos (#22, #24 and #25 add changelog entries, suggestions and flags to that check in `pr_policy.needs_decision`). New and pruned stubs never open a PR alone; they ride along on the next one. If merging main into the PR branch conflicts, the run stops without touching the branch. Any failed run opens or comments on a `sync-failure` issue (using the workflow's own token, `issues: write`). A `concurrency` group serialises runs.

If the checkout step fails with `fatal: could not read Username for 'https://github.com'`, the `SKILLS_INDEX_TOKEN` secret has expired or been revoked (this caused the failed runs of 2026-10-05 and 2026-10-12). Regenerate the PAT (README Setup has a prefilled link) and update the secret.

`docs/skills-index-spec.md` has the full design rationale and a running list of remaining work — check it for context before making structural changes.

## Known gotchas

- GraphQL (used for star lists) is blocked from Claude Code cloud sessions, so list fetching can only be verified in Actions (use `dry_run`), not locally in a session. It is covered by mocked tests only. The fine-grained PAT's access to `user.lists` was verified in Actions on 2026-10-14.
- `get_starred_repos` in `scripts/sync_stars.py` bails out early once `X-RateLimit-Remaining < 10`. It returns a `rate_limited` flag, written to `changes.yaml` as `discover_rate_limited`, and `gen_pr_body.py` renders a warning in the PR body when it is set.
- Weekly PRs accumulate unreviewed stubs if not merged or closed; no entry has a verdict yet, so everything is a stub.

## Agent skills

### Issue tracker

Issues live in GitHub Issues for bbrewington/agent-skills-index (via `gh`). See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the default five-label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

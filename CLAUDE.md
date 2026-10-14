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

- `--mode sync` checks each `tracked:` entry for upstream SHA changes.
- `--mode discover` fetches the full starred list and adds unseen repos as `stubs:`.
- `--mode all` (default) runs both.
- `--dry-run` skips writing `tracked.yml` but still writes `changes.yaml`.
- Requires env var `GITHUB_TOKEN` (fine-grained PAT owned by the starred user; if `GET /users/{user}/starred` returns nothing or 403, use a classic PAT with `read:user`). `GITHUB_USER` defaults to `bbrewington`.
- Exit code is `1` if anything changed, `0` otherwise (this drives whether CI opens a PR).

Render a PR body from a `changes.yaml`:

```
uv run python scripts/gen_pr_body.py --input changes.yaml --output pr_body.md
```

Tests and lint (dev deps: pytest, ruff; config in `pyproject.toml`):

```
uv run pytest
uv run ruff check .
```

Tests live in `tests/` and stub out the GitHub API; nothing hits the network. CI does not run them yet.

## Architecture

`tracked.yml` is the single source of truth, with two sections:

- `tracked:` — repos explicitly wired to a skill. Fields `repo`, `skill`, `notes`, `watch_paths` are human-authored; `state:` (`latest_sha`, `pushed_at`, `indexed_at`, `last_changed_at`, `description`, `language`, `topics`, `license`, `stargazers_count`) is bot-written by `sync_stars.py`.
- `stubs:` — auto-discovered stars not yet linked to a skill, same shape but with `skill`/`notes`/`watch_paths` set to `null`.

`scripts/sync_stars.py` is the only writer of `tracked.yml`. It does a full `yaml.safe_load` / `yaml.dump` round-trip on every run, but `extract_header` re-prepends the leading comment block afterward, so the header documenting the config/state field split survives. Other comments in the file would not.

`scripts/gen_pr_body.py` reads the `changes.yaml` emitted by `sync_stars.py` and renders a Markdown PR body with two sections: tracked repos with upstream changes (plus a review checklist), and newly discovered stars grouped by language.

CI is `.github/workflows/sync.yml`: weekly cron (Mon 08:00 UTC) + `workflow_dispatch` (with a `dry_run` input). It runs `sync_stars.py --mode all`, and if the exit code is 1, renders a PR body and opens a PR via `gh pr create` on a branch named `agent-skills-index/update-<ISO datetime, no separators>` (e.g. `agent-skills-index/update-20250602T080012`) with label `agent-skills-index`. Dry runs upload `changes.yaml` as an artifact instead. Actions are pinned to commit SHAs. It needs a secret `SKILLS_INDEX_TOKEN` (fine-grained PAT: contents write, pull requests write, metadata read, scoped to this repo, 365 day expiry; creation link in README Setup).

If the checkout step fails with `fatal: could not read Username for 'https://github.com'`, the `SKILLS_INDEX_TOKEN` secret has expired or been revoked (this caused the failed runs of 2026-10-05 and 2026-10-12). Regenerate the PAT (README Setup has a prefilled link) and update the secret.

`docs/skills-index-spec.md` has the full design rationale and a running list of remaining work — check it for context before making structural changes.

## Known gotchas

- `get_starred_repos` in `scripts/sync_stars.py` bails out early once `X-RateLimit-Remaining < 10`. It returns a `rate_limited` flag, written to `changes.yaml` as `discover_rate_limited`, and `gen_pr_body.py` renders a warning in the PR body when it is set.
- Weekly PRs accumulate unreviewed stubs if not merged or closed; `tracked:` is currently empty and everything is a stub.

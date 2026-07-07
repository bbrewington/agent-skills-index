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
- Requires env var `GITHUB_TOKEN` (PAT with `read:user` scope — must belong to the starred user, since `GET /users/{user}/starred` requires it). `GITHUB_USER` defaults to `bbrewington`.
- Exit code is `1` if anything changed, `0` otherwise (this drives whether CI opens a PR).

Render a PR body from a `changes.yaml`:

```
uv run python scripts/gen_pr_body.py --input changes.yaml --output pr_body.md
```

There is no test suite or lint configuration in this repo yet.

## Architecture

`tracked.yml` is the single source of truth, with two sections:

- `tracked:` — repos explicitly wired to a skill. Fields `repo`, `skill`, `notes`, `watch_paths` are human-authored; `state:` (`latest_sha`, `pushed_at`, `indexed_at`, `last_changed_at`, `description`, `language`, `topics`, `license`, `stargazers_count`) is bot-written by `sync_stars.py`.
- `stubs:` — auto-discovered stars not yet linked to a skill, same shape but with `skill`/`notes`/`watch_paths` set to `null`.

`scripts/sync_stars.py` is the only writer of `tracked.yml`. It does a full `yaml.safe_load` / `yaml.dump` round-trip on every run — **this does not preserve the leading comment block** at the top of `tracked.yml` that documents the config/state field split. That's a known open issue (see `docs/skills-index-spec.md`): either move that documentation into README-only, or have the script read the file as raw text and re-prepend the header after dumping.

`scripts/gen_pr_body.py` reads the `changes.yaml` emitted by `sync_stars.py` and renders a Markdown PR body with two sections: tracked repos with upstream changes (plus a review checklist), and newly discovered stars grouped by language.

The intended CI wiring (`.github/workflows/sync.yml`) is **not yet implemented**. Per the design in `docs/skills-index-spec.md`, it should run on a weekly cron + `workflow_dispatch`, invoke `sync_stars.py --mode all`, and if anything changed, generate a PR body and open a PR via `gh pr create` on a branch named `agent-skills-index/update-<ISO datetime, no separators>` (e.g. `agent-skills-index/update-20250602T080012`). It needs a secret `SKILLS_INDEX_TOKEN` with `contents:write`, `pull-requests:write`, and `read:user`.

`docs/skills-index-spec.md` has the full design rationale and a running list of remaining work — check it for context before making structural changes.

## Known gotchas

- `get_starred_repos` in `scripts/sync_stars.py` bails out early once `X-RateLimit-Remaining < 10`, which can silently truncate discovery on a large star backlog.

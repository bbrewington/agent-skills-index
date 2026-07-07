# agent-skills-index: spec for Claude Code session

## Purpose
A repo that tracks GitHub starred repos (bbrewington) and maps them to skills stored in this repo. When a tracked upstream repo changes, or a new star is detected, a GitHub Actions workflow opens a PR for review.

## Current state
Scaffold already built and available as a zip in the prior conversation (`agent-skills-index.zip`). Needs to be unpacked into a real git repo, tested end-to-end with actual GitHub API access, and pushed.

## Repo structure
```
agent-skills-index/
  tracked.yml                   - single source of truth: config + bot-written state
  scripts/
    sync_stars.py                - sync + discover modes
    gen_pr_body.py                - renders changes.yaml into PR markdown
  .github/workflows/sync.yml     - scheduled + manual trigger workflow
  requirements.txt
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
- `--mode discover` - fetch full starred list via GitHub API, add any repo not in `tracked:` or `stubs:` as a new stub.
- `--mode all` (default) runs both in one pass.
- `--dry-run` skips writing `tracked.yml` (still writes `changes.yaml` for inspection).
- Exit code 1 if any changes/new stars found, 0 otherwise (drives the workflow's PR step).

## Workflow (`.github/workflows/sync.yml`)

- Trigger: weekly cron (Mon 08:00 UTC) + `workflow_dispatch` with a `dry_run` boolean input.
- Steps: checkout -> setup Python -> install deps -> run `sync_stars.py --mode all` -> if changed, generate PR body via `gen_pr_body.py` -> create branch (ISO datetime name) -> commit `tracked.yml` -> `gh pr create` with title showing counts, e.g. `chore(index): skills index update 2025-06-02 (3 updated, 5 new stars)` -> label `agent-skills-index`.
- Dry run uploads `changes.yaml` as a workflow artifact instead of opening a PR.
- Needs secret `SKILLS_INDEX_TOKEN`: a PAT with `contents: write`, `pull-requests: write`, and `read:user` (the starred-repos endpoint requires the token belong to the starred user, i.e. bbrewington's own PAT - a repo-scoped fine-grained token alone won't work for `GET /users/{user}/starred`).

## Remaining work / open items to pick up in Claude Code

1. Unzip and init git repo. Set remote, initial commit, push to GitHub.
2. Create the PAT with the right scopes and add as `SKILLS_INDEX_TOKEN` secret.
3. Test discover mode against real API access - prior dry runs got 403s from a sandboxed environment's network allowlist (not a code bug, just that sandbox blocking `api.github.com` broadly). Confirm real requests to `/users/bbrewington/starred` and `/repos/{owner}/{repo}` work as expected with a live token.
4. Bootstrap `tracked.yml` state by running the workflow once manually (or `python scripts/sync_stars.py --mode all` locally with `GITHUB_TOKEN` set) to populate initial `state:` blocks for the 4 seeded `tracked:` entries.
5. Decide on real `tracked:` list. The current 4 entries (dbt-core, dbt-utils, snowflake-connector-python, fivetran_connector_sdk) are placeholders - replace/expand based on actual starred repos worth explicit tracking, and actual skill paths once they exist in this repo.
6. First discover run will populate `stubs:` with everything else currently starred - expect a large first PR. Consider whether to seed `stubs:` manually beforehand to avoid a huge initial diff, or just let it happen once and review.
7. Verify YAML round-tripping. `yaml.dump` with `sort_keys=False` should preserve section order, but comments in `tracked.yml` (the header docblock) will likely get stripped on the first bot write since `sync_stars.py` re-serializes the whole file via `yaml.safe_load`/`yaml.dump`. Decide if that's acceptable or if the header should be re-injected after dump (e.g. read/prepend a static comment block before writing).
8. Consider rate limiting for large star lists - `get_starred_repos` currently bails early if `X-RateLimit-Remaining < 10`, which could silently truncate discovery on a big backlog. May want pagination logging or a warning surfaced in the PR body itself.
9. Test the full PR flow once with a real dummy change (e.g. manually edit a `state.latest_sha` value in `tracked.yml` to something stale) to confirm branch creation, commit, and `gh pr create` all work correctly in Actions.

## Known gotcha to flag in Claude Code

The header comment block at the top of `tracked.yml` (explaining the config vs state fields) will not survive a bot-driven `yaml.dump` rewrite unless the script explicitly preserves it. Worth deciding early whether to:

- move that documentation into README.md only, or
- have `sync_stars.py` read the file as raw text, extract/preserve the leading comment block, and re-prepend it after dumping the updated YAML body.

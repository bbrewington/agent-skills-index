# agent-skills-index

Tracks GitHub starred repos and maps them to skills in this repo.

When an upstream repo changes, or when a new star is detected, a PR is automatically opened against `tracked.yml`.

## How it works

```
tracked.yml                  - single source of truth: config + bot-written state
scripts/
  sync_stars.py              - sync + discover modes; mutates tracked.yml state blocks
  gen_pr_body.py             - renders changes.yaml into a Markdown PR description
.github/workflows/sync.yml   - runs weekly (Mon 08:00 UTC); opens PR when anything changes
```

### tracked.yml structure

```yaml
tracked:
  - repo: dbt-labs/dbt-core
    skill: skills/dbt/core/SKILL.md      # human-authored
    notes: "dbt core framework"          # human-authored
    watch_paths:                         # human-authored (optional)
      - core/dbt/
      - CHANGELOG.md
    state:                               # bot-written
      latest_sha: abc1234...
      pushed_at: "2025-06-01T12:00:00Z"
      indexed_at: "2025-06-01T08:00:00Z"
      last_changed_at: "2025-06-01T08:00:00Z"
      description: ...                   # also: language, topics, license, stargazers_count

stubs:
  - repo: some/new-star                  # auto-added by discover mode
    skill: null
    notes: null
    watch_paths: null
    state:
      latest_sha: def5678...
      indexed_at: "2025-06-02T08:00:00Z"
```

`tracked:` entries are repos you've explicitly wired to a skill. `stubs:` are
newly discovered stars with no skill linked yet - they show up in the PR body
for you to triage.

### Two modes, one job

`--mode all` (default) runs both:

- **sync** - for each `tracked:` entry, checks whether the latest commit SHA
  (optionally scoped to `watch_paths`) has moved since `state.latest_sha`.
- **discover** - adds any repo not already in `tracked:` or `stubs:` as a new
  stub entry. With `STAR_LIST` set (the workflow uses `agent-skills`, the slug of
  [your GitHub star list](https://github.com/stars/bbrewington/lists/agent-skills)),
  only repos in that list are considered, fetched via the GraphQL API. Without it,
  every starred repo is considered.

### Branch naming

Branches are named `agent-skills-index/update-<ISO datetime>`, e.g.:
`agent-skills-index/update-20250602T080012`

## Setup

0. Install dependencies with `uv sync` (Python 3.14).
1. [Create a fine-grained PAT](https://github.com/settings/personal-access-tokens/new?name=agent-skills-index-sync&target_name=bbrewington&expires_in=365&contents=write&pull_requests=write&metadata=read) with the permissions prefilled
   (contents: write, pull requests: write, metadata: read; 365 day expiry).
   On the token page, set repository access to only `bbrewington/agent-skills-index`.
2. Add it as secret `SKILLS_INDEX_TOKEN` (Settings -> Secrets and variables -> Actions),
   and note its expiry date.
3. Populate the `tracked:` section of `tracked.yml`.
4. Trigger the workflow manually once to bootstrap `state:` blocks.

## Promoting a stub to tracked

Move the entry from `stubs:` to `tracked:` and fill in the config fields:

```yaml
tracked:
  - repo: some/new-star
    skill: skills/category/skill-name/SKILL.md
    notes: "Why this is tracked"
    watch_paths: null
    state:
      # leave existing state block as-is
      latest_sha: def5678...
```

## Workflow dispatch

The `dry_run` input runs the full check without writing `tracked.yml` or opening
a PR - uploads `changes.yaml` as a workflow artifact instead.

The `prune_stubs` input (one-off cleanup) removes stubs that are not in the star
list. `tracked:` entries are never removed. Removed repos are listed in the PR
body. Run it with `dry_run` first and check `pruned_stubs` in `changes.yaml`.

## Troubleshooting

If a run fails in the Checkout step with `could not read Username for
'https://github.com'`, `SKILLS_INDEX_TOKEN` has expired or been revoked.
Regenerate the PAT, update the secret, and re-run the workflow.

To regenerate, follow Setup steps 1 and 2 again (same prefilled link), then re-run the workflow.

Fine-grained tokens have no `read:user` scope. After rotating, run the workflow
with `dry_run` enabled and confirm discover mode still lists your stars; if it
doesn't, use a classic PAT with `repo` and `read:user` instead.

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
- **discover** - fetches the full star list; adds any repo not already in
  `tracked:` or `stubs:` as a new stub entry.

### Branch naming

Branches are named `agent-skills-index/update-<ISO datetime>`, e.g.:
`agent-skills-index/update-20250602T080012`

## Setup

1. Create a PAT with `contents: write` and `pull-requests: write` on this repo,
   plus `read:user` scope for the starred-repos API (must be your own token).
2. Add it as secret `SKILLS_INDEX_TOKEN`.
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

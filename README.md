# agent-skills-index

Tracks GitHub starred repos and maps them to skills in this repo.

When an upstream repo changes, or when a new star is detected, a PR is automatically opened against `tracked.yml`.

## How it works

```
tracked.yml                  - single source of truth: one list of repos, human fields + bot-written state
use-contexts.yml             - controlled vocabulary for `use_contexts` tags
scripts/
  sync_stars.py              - sync + discover modes; mutates tracked.yml
  gen_pr_body.py             - renders changes.yaml into a Markdown PR description
.github/workflows/sync.yml   - runs weekly (Mon 08:00 UTC); keeps at most one open bot PR
.github/workflows/ci.yml     - pytest + ruff on pull requests
```

### tracked.yml structure

One list, `repos:`. A **stub** is an entry with `verdict: null`; a **curated repo**
has a verdict (`adopt`, `watch` or `skip`). See `CONTEXT.md` for the vocabulary.

```yaml
repos:
  - repo: dbt-labs/dbt-core
    verdict: adopt                       # human-authored: adopt | watch | skip | null
    use_contexts: [data-engineering]     # human-authored: tags from use-contexts.yml
    notes: "dbt core framework"          # human-authored
    skill_or_plugin_paths:               # human-authored (optional; null = whole repo)
      - skills/dbt
    state:                               # bot-written
      latest_sha: abc1234...
      pushed_at: "2025-06-01T12:00:00Z"
      indexed_at: "2025-06-01T08:00:00Z"
      last_changed_at: "2025-06-01T08:00:00Z"
      description: ...                   # also: language, topics, license, stargazers_count

  - repo: some/new-star                  # a stub, auto-added by discover mode
    verdict: null
    use_contexts: null
    notes: null
    skill_or_plugin_paths: null
    state:
      latest_sha: def5678...
      indexed_at: "2025-06-02T08:00:00Z"
```

The bot only writes bot-owned fields: `state:`, new stubs, removal of stubs that
left the star list(s), and the files under `generated/`. It never changes
`verdict`, `use_contexts`, `notes` or `skill_or_plugin_paths` on an existing entry.
A `skip` entry stays in the file so the repo never comes back as a stub.

Bot state beyond the fields above: `changelog_sha` / `changelog_at` / `known_tags`
(the last-seen marker for the changelog), `tree_sha` (the upstream head last scanned
for skill/plugin paths) and `flags` (`archived`, `renamed:<new name>`, `gone`).

### Generated files

The bot commits plain markdown (no build step), in the same PR as `tracked.yml`:

- [`generated/INDEX.md`](generated/INDEX.md) - curated repos grouped by use-context,
  with verdict, notes, paths and flags, plus the stub list. Do not edit it. To
  regenerate it after editing `tracked.yml` by hand: `uv run python scripts/render.py`.
- [`generated/changelog/`](generated/changelog/) - one `YYYY-MM.md` per month,
  newest first: releases, new tags and commits touching each repo's
  `skill_or_plugin_paths`, one entry per repo per run with a compare link. Merge
  commits are skipped and `adopt` repos are listed above `watch`.

`sync_stars.py` exits with code 2 (and CI's pytest fails) if an entry has an
unknown `verdict` or a `use_contexts` tag that is not in `use-contexts.yml`. Add
the tag to that file first.

### Two modes, one job

`--mode all` (default) runs both:

- **sync** - for each `adopt` or `watch` entry: flags it if the upstream is
  archived, renamed or gone (never auto-removed); then reports releases, new tags and
  commits touching `skill_or_plugin_paths` since the last-seen SHA. The first sync
  after a verdict only sets a baseline and reports nothing. It also suggests
  skill/plugin paths found in the upstream file tree (one Git Trees call per repo,
  skipped while the head SHA is unchanged) that are not yet listed, checks them
  against the agentskills.io / Claude Code rules, and flags listed paths that are
  neither. Stubs get the path suggestions too, without the compliance check.
  Suggestions never touch your fields.
- **discover** - adds any repo not already in `repos:` as a new stub. With `STAR_LIST` set (comma-separated list slugs; the workflow uses
  `agent-skills,ai-helpers-and-reference`, from
  [your GitHub star lists](https://github.com/stars/bbrewington/lists)),
  only repos in those lists are considered, fetched via the GraphQL API. Without it,
  every starred repo is considered.

### PR policy

- **At most one open bot PR.** If one is open, each run starts from its branch (with
  main merged in), pushes to it, and refreshes its title and body (new runs are
  appended as a dated section). Merge or close it to start a fresh one.
- **A new PR opens only when there is something to decide**, today an upstream
  change to a curated repo. New and pruned stubs alone never open a PR; they ride
  along on the next one.
- **Merge conflict:** if main can't be merged into the PR branch, the run stops and
  leaves the branch alone.
- **Failures:** any failed run opens (or comments on) an issue labelled
  `sync-failure` with the run link and the token-rotation steps.

Branches are named `agent-skills-index/update-<ISO datetime>`, e.g.:
`agent-skills-index/update-20250602T080012`

## Setup

0. Install dependencies with `uv sync` (Python 3.14).
1. [Create a fine-grained PAT](https://github.com/settings/personal-access-tokens/new?name=agent-skills-index-sync&target_name=bbrewington&expires_in=365&contents=write&pull_requests=write&metadata=read) with the permissions prefilled
   (contents: write, pull requests: write, metadata: read; 365 day expiry).
   On the token page, set repository access to only `bbrewington/agent-skills-index`.
2. Add it as secret `SKILLS_INDEX_TOKEN` (Settings -> Secrets and variables -> Actions),
   and note its expiry date (current token: about 2027-10-14).
3. Review stubs in `tracked.yml` (see below).
4. Trigger the workflow manually once to bootstrap `state:` blocks.

## Reviewing a stub

Edit the entry in place: set `verdict`, and fill in the other human fields.

```yaml
  - repo: some/new-star
    verdict: watch
    use_contexts: [software-engineering]
    notes: "Why this is worth following"
    skill_or_plugin_paths: [skills/skill-name]
    state:
      # leave existing state block as-is
      latest_sha: def5678...
```

## Workflow dispatch

The `dry_run` input runs the full check without writing `tracked.yml` or opening
a PR - uploads `changes.yaml` as a workflow artifact instead.

The `update_changelog` input (default off) controls whether changelog entries are
recorded and last-seen SHAs advance. Scheduled runs always record. With it off, the
run reports what it would record (`unrecorded` in `changes.yaml`) and advances
nothing.

Stubs that are not in the star list(s) are pruned on every run (entries with a
verdict are never removed); they are listed in the PR body and in `pruned_stubs`
in `changes.yaml`.

## Troubleshooting

If a run fails in the Checkout step with `could not read Username for
'https://github.com'`, `SKILLS_INDEX_TOKEN` has expired or been revoked.
Regenerate the PAT, update the secret, and re-run the workflow.

To regenerate, follow Setup steps 1 and 2 again (same prefilled link), then re-run the workflow.

Fine-grained tokens have no `read:user` scope. After rotating, run the workflow
with `dry_run` enabled and confirm discover mode still lists your stars; if it
doesn't, use a classic PAT with `repo` and `read:user` instead.

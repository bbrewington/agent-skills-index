# TODO

Tasking space for `agent-skills-index` setup. Ordered so each item only depends on ones above it — work top to bottom.

- [ ] Resolve the `skills-index` vs `agent-skills-index` naming mismatch: `docs/skills-index-spec.md` says branch prefix `agent-skills-index/update-...` and PR label `agent-skills-index`, but `.github/workflows/sync.yml` still hardcodes `skills-index/update-...` and `--label skills-index`. Pick one and make the other match.
- [ ] Apply the GHA-001 security review fix to `sync.yml`: pin `actions/checkout`, `astral-sh/setup-uv`, and `actions/upload-artifact` to full commit SHAs (not floating tags), and/or add `persist-credentials: false` to the checkout step. (Single-token design confirmed — no token split needed.)
- [ ] Decide and implement the `tracked.yml` header-comment preservation fix in `sync_stars.py` (currently a full `yaml.safe_load`/`yaml.dump` round-trip strips the leading comment block) — do this before the first real bot write so the header isn't lost immediately.
- [ ] Decide whether to surface a rate-limit warning in the PR body (`get_starred_repos` currently bails silently once `X-RateLimit-Remaining < 10`, which could truncate discovery on a large star backlog).
- [ ] Commit and push the scaffolded files (`CLAUDE.md`, `scripts/`, `tracked.yml`, `.github/workflows/sync.yml`, `docs/`, `.claude/`) to `agent-skills-index` now that the above are settled.
- [ ] Create the GitHub label used by `gh pr create --label ...` in the `agent-skills-index` repo (name must match whatever was decided in the first item).
- [x] Create the `SKILLS_INDEX_TOKEN` PAT (classic, `repo` + `read:user` scopes) and add it as a repo secret.
- [ ] Decide the real `tracked:` list — replace the 4 placeholder entries (dbt-core, dbt-utils, snowflake-connector-python, fivetran_connector_sdk) with actual starred repos worth explicit tracking, once real skill paths exist.
- [ ] Decide how to handle the first large `discover`-mode PR (everything currently starred and not yet tracked will show up as `stubs:` at once) — pre-seed `stubs:` manually to shrink the diff, or let it happen once and review.
- [ ] Test `discover` mode against the real GitHub API (`--dry-run` first) — prior attempts hit a sandboxed environment's network allowlist blocking `api.github.com`.
- [ ] Bootstrap `tracked.yml`'s `state:` blocks with a real run (`uv run python scripts/sync_stars.py --mode all`, or trigger the workflow manually) now that the token and tracked list are in place.
- [ ] End-to-end test of the full PR flow: manually stale a `state.latest_sha` value, trigger the workflow, and confirm branch creation, commit, and `gh pr create` all work in Actions.

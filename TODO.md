# TODO

Open items for `agent-skills-index`. Setup, workflow, token, header preservation, rate-limit warning, and e2e testing are done.

- [ ] Verify star-list scoping in Actions: run the workflow with `dry_run` (and `prune_stubs`) and check `changes.yaml` (`new_stars`, `pruned_stubs`). If the fine-grained PAT cannot read `user.lists`, switch to a classic PAT with `read:user`.
- [ ] Then run once with `prune_stubs` to remove out-of-list stubs, and re-count the stubs before chunk review.
- [ ] Decide the real `tracked:` list (currently empty) and wire entries to skill paths once they exist.
- [ ] Triage the stubs in chunks by use-context (cloud/data platforms, software vendors, software engineering, data engineering, content creation, ...). Weekly PRs #6-#16 were closed unmerged.
- [ ] Track `SKILLS_INDEX_TOKEN` expiry (it lapsed 2026-10-05 to 2026-10-12, failing runs at checkout).
- [x] Add a test suite / lint config (pytest + ruff).
- [ ] Run pytest and ruff in CI (the sync workflow does not, and there is no PR-check workflow).

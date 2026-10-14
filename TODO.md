# TODO

Open items for `agent-skills-index`. Setup, workflow, token, header preservation, rate-limit warning, and e2e testing are done.

- [ ] Decide the real `tracked:` list (currently empty) and wire entries to skill paths once they exist.
- [ ] Triage the stub backlog (286 as of 2026-10-14) and decide how to handle unreviewed weekly PRs (PRs #6-#16 were closed unmerged).
- [ ] Track `SKILLS_INDEX_TOKEN` expiry (it lapsed 2026-10-05 to 2026-10-12, failing runs at checkout).
- [x] Add a test suite / lint config (pytest + ruff).
- [ ] Run pytest and ruff in CI (the sync workflow does not, and there is no PR-check workflow).

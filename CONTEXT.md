# Agent Skills Index

A personal library of agent skills, fed by upstream GitHub repos that the owner stars and then reviews. It exists so the owner has one place to see which upstream repos are worth following and what changed in them.

## Language

**Star list**:
A named GitHub star list on the owner's profile (e.g. `agent-skills`) used to flag a repo as potentially useful. The index may read from more than one star list.
_Avoid_: Bookmark, collection

**Stub**:
A repo that has entered the index from a star list but has no verdict yet.
_Avoid_: Candidate, pending repo

**Curated repo**:
A repo the owner has reviewed, annotated with notes, and given a verdict.
_Avoid_: Reviewed repo, tracked repo

**Verdict**:
The owner's decision on a reviewed repo: `adopt`, `watch`, or `skip`. A `skip` repo stays recorded so it never returns as a stub.
_Avoid_: Status, rating

**Adopt**:
A verdict meaning the owner uses the repo's skills. The index records pointers to the upstream skill paths (or plugin), never copies of the skills.
_Avoid_: Vendor, import

**Use-context**:
A tag naming the kind of work a curated repo helps with (e.g. data engineering, cloud/data platforms, content creation). A repo may carry several.
_Avoid_: Category, topic (topic means a GitHub topic)

**Skill or plugin path**:
A path inside a curated repo that holds either a skill (per agentskills.io) or a plugin (per Anthropic's plugin spec). A curated repo has one or more.
_Avoid_: Skill path, watch path

**Upstream change**:
Something new in a curated repo worth reporting in the changelog: a release or tag, or a commit touching a skill or plugin path. Repos that ship straight from the default branch with no tags or releases only have path commits.
_Avoid_: Update, release (a release is one kind of upstream change)

**Changelog**:
The single page listing upstream changes across `adopt` and `watch` repos, newest first.
_Avoid_: Feed, digest

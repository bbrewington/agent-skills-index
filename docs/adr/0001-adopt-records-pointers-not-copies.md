---
status: accepted
---
# Adopting a repo records pointers to upstream paths, not copies

This repo's purpose is a skills library, but an `adopt` verdict stores only the upstream repo, its skill or plugin paths and the owner's notes. Skills are never vendored into this repo. Upstream stays the source of truth, which is what lets the changelog watch those same paths for changes, and avoids drift and merge work against copies that plugin installs already make unnecessary.

## Considered Options

- **Vendored copy with drift detection:** rejected for the maintenance cost above.
- **Per-repo choice of pointer or copy:** deferred. It can be added later without changing existing entries.

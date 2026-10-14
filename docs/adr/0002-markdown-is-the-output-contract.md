---
status: accepted
---
# The bot's output is committed markdown; the site renderer is deferred

The bot writes `generated/INDEX.md` and `generated/changelog/YYYY-MM.md`, which GitHub renders without any build step. A static site generator, if wanted, is a replaceable layer built from those files. MkDocs Material was the obvious choice, but it reaches end of life on 2026-11-05 and its successor (Zensical) was not yet confirmed mature, so committing to a renderer now would mean migrating almost immediately.

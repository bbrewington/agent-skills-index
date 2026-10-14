# Detecting skills and plugins in GitHub repos

Researched 2026-10-14 from first-party docs. Every claim carries its source URL. Anything not confirmed is marked UNVERIFIED.

## 1. agentskills.io specification

Source for this whole section: https://agentskills.io/specification

- A skill is a directory containing at minimum `SKILL.md`. Optional dirs `scripts/`, `references/`, `assets/` are conventions; any other files are allowed.
- `SKILL.md` must have YAML frontmatter followed by Markdown.
- Required frontmatter: `name` and `description`.
  - `name`: 1-64 chars; unicode lowercase alphanumerics and `-`; no leading or trailing `-`; no `--`; **must match the parent directory name**.
  - `description`: 1-1024 chars, non-empty.
- Optional frontmatter: `license`, `compatibility` (1-500 chars), `metadata` (string-to-string map), `allowed-tools` (space-separated string, experimental).
- Recommendation, not a rule: keep `SKILL.md` under 500 lines.
- Reference validator: `skills-ref validate ./my-skill` (https://github.com/agentskills/agentskills/tree/main/skills-ref). It checks frontmatter validity and naming conventions.

Claude Code differences (https://code.claude.com/docs/en/skills):
- Claude Code treats all frontmatter as optional. `name` defaults to the directory name. `description` is recommended; if omitted, the first line of the body is used.
- Spec-portable fields are `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`. Fields such as `when_to_use`, `disable-model-invocation`, `context`, `hooks` and `paths` are Claude Code-only.
- Consequence: "valid for Claude Code" is weaker than "agentskills.io compliant". The bot should report spec compliance separately.

## 2. Claude Code plugins and marketplaces

### Plugin layout and manifest
Source: https://code.claude.com/docs/en/plugins-reference

- Manifest path is `.claude-plugin/plugin.json`. **The manifest is optional.** Without it, Claude Code loads components from the standard layout, and the plugin name comes from the marketplace entry or directory name.
- When a manifest exists, `name` is the only required field. Validator warnings cover non-kebab-case names and a missing `version`, `description` or `author`.
- All components live at the plugin root, **not** inside `.claude-plugin/`. Defaults:

| Component | Default location |
|---|---|
| Skills | `skills/<name>/SKILL.md` |
| Commands | `commands/*.md` (flat; "prefer skills") |
| Agents | `agents/*.md` |
| Hooks | `hooks/hooks.json` (wrapped in a top-level `"hooks"` key) |
| MCP | `.mcp.json` |
| LSP | `.lsp.json` |
| Output styles | `output-styles/` |
| Workflows | `workflows/` |
| Themes | `themes/` |
| Monitors | `monitors/monitors.json` |
| Executables | `bin/` |
| Settings | `settings.json` |

- A plugin with `SKILL.md` at its root, no `skills/` dir and no `skills` key loads as a single-skill plugin.
- The manifest `skills` key may point at other dirs and adds to `skills/`. `commands` and `agents` replace their defaults.
- Reserved plugin names: starts with `claude-`, `anthropic-`, `anthropics-` or `cc-plugin-`, or is exactly `claude`, `anthropic`, `claude-code` and similar. These are validator errors.
- Validator: `claude plugin validate ./my-plugin` (`--strict` turns warnings into failures).

### Other skill locations (not plugins)
Source: https://code.claude.com/docs/en/skills
- Project skills: `.claude/skills/<name>/SKILL.md`; nested `<subdir>/.claude/skills/...`; personal `~/.claude/skills/...`; legacy `.claude/commands/<name>.md`.

### Marketplace manifest
Sources: https://code.claude.com/docs/en/plugins/marketplace-reference and https://code.claude.com/docs/en/plugin-marketplaces

- Path is `.claude-plugin/marketplace.json`. The relative-path root is the dir containing `.claude-plugin/`.
- Required top-level fields: `name`, `owner` (object, with `owner.name` required) and `plugins` (array). Optional: `description`, `version`, `metadata.pluginRoot`, `$schema`.
- Each plugin entry requires `name` and `source`. An entry also accepts every `plugin.json` field plus `category`, `tags`, `strict` (default `true`), `dependencies` and others.
- `source` is a string or an object:

| Type | Form | Fields |
|---|---|---|
| Relative path | string starting with `./` (or a bare name under `metadata.pluginRoot`); no `..` | none |
| `github` | `{source:"github", repo:"o/r"}` | `ref`, `sha` optional |
| `url` | any git URL | `url`, `ref`, `sha` |
| `git-subdir` | repo subdirectory | `url`, `path`, `ref`, `sha` |
| `npm` | npm package | `package`, `version`, `registry` |
| `archive` | zip over HTTPS | `url`, `sha256` |
| `command` | directory printed by a command | `command`, `timeout`, `mode` |

- `sha` is a full 40-char commit SHA.
- If the plugin has no `plugin.json`, the marketplace entry serves as its manifest. For remote (non-relative) sources, users see only the entry fields before install.
- Marketplace names reserved for Anthropic include `agent-skills` and `anthropic-agent-skills`.
- Validator: `claude plugin validate ./my-marketplace`. It does not catch a missing relative source directory or fetch errors; those appear at install time.

## 3. Other signals

| Signal | Source | Detect? |
|---|---|---|
| `**/SKILL.md` | https://agentskills.io/specification | **Yes, primary.** Shared by Claude Code, Codex, Cursor and Gemini. |
| `.claude-plugin/plugin.json` | https://code.claude.com/docs/en/plugins-reference | **Yes.** |
| `.claude-plugin/marketplace.json` | https://code.claude.com/docs/en/plugins/marketplace-reference | **Yes.** Lists plugins by `source`, so it is a pointer to other repos and paths. |
| `.cursor-plugin/plugin.json` (only `name` required; `skills/`, `rules/*.mdc`, `mcp.json`) | https://cursor.com/docs/plugins | **Yes, cheap.** |
| `.cursor-plugin/marketplace.json` | https://cursor.com/docs/plugins | Yes, same query. |
| Codex: root `plugin.json` (portable, `$schema` agent-plugins.org) or `.codex-plugin/plugin.json` (compat fallback); skills in `skills/<n>/SKILL.md` | https://developers.openai.com/codex/plugins/build | **Yes.** |
| `.agents/plugins/marketplace.json` (Codex repo-scoped marketplace; legacy `.claude-plugin/marketplace.json` also read) | https://developers.openai.com/codex/plugins/build | **Yes.** |
| `gemini-extension.json` (`name`, `version`, `description` required; `skills/`, `commands/*.toml`, `agents/`, `hooks/`, `GEMINI.md`) | https://geminicli.com/docs/extensions/reference/ | **Yes.** Classify as an extension. |
| `.claude/skills/*/SKILL.md` | https://code.claude.com/docs/en/skills | Covered by `SKILL.md`; label as "project skill, not distributable plugin". |
| `.mcp.json`, `hooks/hooks.json`, `agents/*.md` alone | https://code.claude.com/docs/en/plugins-reference | **No.** Weak signal; common in ordinary repos. Use only as a corroborating signal inside a confirmed plugin. |
| `commands/*.md`, `GEMINI.md`, `CLAUDE.md`, `AGENTS.md` alone | n/a | No. Too noisy. |

Root `plugin.json` alone is too generic to treat as Codex-specific. Require the `$schema` to contain `agent-plugins.org` (UNVERIFIED whether that is the only discriminator).

## 4. GitHub APIs

### REST code search (`GET /search/code`)
Source: https://docs.github.com/en/rest/search/search#search-code, https://docs.github.com/en/search-github/searching-on-github/searching-code (the "legacy code search" page the REST API uses)

- Requires authentication.
- Rate limit is 10 requests/minute (other search endpoints: 30/min), separate `code_search` category in `GET /rate_limit` (https://docs.github.com/en/rest/rate-limit/rate-limit).
- Query limits: at most 256 characters (excluding operators/qualifiers) and at most five AND/OR/NOT operators. Language-only queries are invalid.
- Max 100 results per page. `incomplete_results=true` is returned on timeout.
- Only the default branch is indexed. Files over 384 KB are not searchable.
- Repos with 500,000 or more files are not searchable.
- Forks are searchable only if they have more stars than the parent.
- Repos with no activity or search hits in the last year are not searchable.
- `path:` and `filename:` qualifiers are documented for legacy search (searching-code page above), and AND/OR/NOT are documented for the REST endpoint (five-operator limit).
- The new code search syntax page (https://docs.github.com/en/search-github/github-code-search/understanding-github-code-search-syntax) documents OR/AND/NOT and `path:` but does not say it applies to the REST API. **Treat REST as legacy syntax.**
- The "1,000 results max" cap is commonly cited, but not confirmed from the pages fetched: UNVERIFIED.
- Whether `OR` with `filename:` behaves reliably in legacy REST search: UNVERIFIED. Test empirically.
- Fine-grained PAT support for `/search/code`: UNVERIFIED. The endpoint page fetched does not mention token types, and `/search/code` is absent from the fine-grained PAT permissions table (https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens). Test before depending on it.
- Code search is not suited to "scan these N known repos": it results in per-repo queries (`repo:o/r filename:SKILL.md`) at 10/min, so 500 repos takes 50 min or more. It also misses non-default branches, large repos and dormant repos.

### Git Trees API (`GET /repos/{o}/{r}/git/trees/{sha}?recursive=1`)
Sources: https://docs.github.com/en/rest/git/trees#get-a-tree, https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api

- Limit is 100,000 entries and 7 MB with `recursive`. If `truncated` is true the list is incomplete.
- Cost is one GET, 1 point under secondary limits, drawn from the primary core limit of 5,000 requests/hour for PAT/App users. `GITHUB_TOKEN` in Actions gets 1,000/hour per repo (rate-limits page above).
- Secondary limits: 100 concurrent requests, 900 points/min for REST.
- Permissions page lists the tree endpoint under repository permission "Contents: read" (https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens). Public-repo access without that permission: UNVERIFIED for this endpoint.
- Fallback when `truncated`: walk non-recursively per directory, or use `GET /repos/{o}/{r}/contents/{path}` (same Contents:read permission per the permissions page).

### Recommendation
Use the Git Trees API per repo. Per repo, one call for the default-branch SHA (or `GET /repos/{o}/{r}` metadata, which `sync_stars.py` already fetches) plus one tree call: about 2 calls per repo, so 500 repos is about 1,000 requests. This is well under 5,000/hour and needs no 10/min throttle. It is exact (full tree, not an index), covers any repo size up to the truncation limit, and works for fine-grained PATs via Contents:read. Skip the tree call when `pushed_at` and the SHA are unchanged. Use code search, if at all, only for discovering unstarred repos, with the PAT caveat above.

---

## (a) Path patterns for the discovery query

Apply as regexes over the recursive tree's blob paths (not as search queries):

```
(^|/)SKILL\.md$                              # skill (agentskills.io)
(^|/)\.claude-plugin/plugin\.json$           # Claude Code plugin
(^|/)\.claude-plugin/marketplace\.json$      # Claude Code marketplace
(^|/)\.cursor-plugin/plugin\.json$           # Cursor plugin
(^|/)\.cursor-plugin/marketplace\.json$      # Cursor marketplace
(^|/)\.codex-plugin/plugin\.json$            # Codex plugin (compat)
^\.agents/plugins/marketplace\.json$         # Codex marketplace
^plugin\.json$                               # Codex portable (confirm $schema)
^gemini-extension\.json$                     # Gemini extension
```

If the tree is `truncated`, fall back to directory-by-directory listing of `/`, `skills/`, `.claude/skills/`, `.claude-plugin/`, `.agents/`, `.cursor-plugin/`.

## (b) Classification rules

1. **Plugin (Claude Code)**: `.claude-plugin/plugin.json` exists at dir D. Also a plugin: a dir D named by a `.claude-plugin/marketplace.json` entry `source` (relative path, `git-subdir.path`, or `github.repo` root) even with no manifest. D is the plugin root. Its skills are `D/skills/*/SKILL.md`, plus any dirs named in the manifest `skills` key.
2. **Marketplace**: `.claude-plugin/marketplace.json` at dir M. Record each entry's `name` and `source`, and queue the targets: `github.repo` becomes a new repo to track; `git-subdir` or relative `./path` becomes a plugin at that path. Fetch and parse the JSON (blob via Contents API) to resolve `source`.
3. **Standalone skill**: a `SKILL.md` whose parent dir is not already inside a plugin root from rules 1 or 2. Sub-label: under `.claude/skills/` is a project skill, otherwise a distributable skill. Repo-root `SKILL.md` with no `skills/` and no manifest is a single-skill repo, which Claude Code also loads as a single-skill plugin.
4. **Other-agent plugin**: `.cursor-plugin/plugin.json`, `.codex-plugin/plugin.json`, a Codex-schema root `plugin.json`, or `gemini-extension.json`. Record the format; treat their `skills/*/SKILL.md` as skills using rule 3.
5. **Non-compliant (agentskills.io)**, per https://agentskills.io/specification:
   - `SKILL.md` has missing or unparsable YAML frontmatter.
   - `name` or `description` is missing.
   - `name` is over 64 chars, has uppercase or invalid characters, starts or ends with `-`, or contains `--`.
   - `name` does not equal the parent directory name.
   - `description` is empty or over 1,024 chars.
   - `compatibility` is over 500 chars.
   - `metadata` is not a string-to-string map.
   - File is named `skill.md` or any variant other than `SKILL.md` (UNVERIFIED whether the spec is case-sensitive; the spec only ever writes `SKILL.md`).
   - Validate by running `skills-ref validate <dir>`, or by reimplementing these checks.
6. **Non-compliant (Claude Code)**, per https://code.claude.com/docs/en/plugins-reference and the marketplace reference:
   - `plugin.json` is not valid JSON or has no `name`.
   - Components are placed inside `.claude-plugin/` instead of at the plugin root.
   - Manifest paths do not start with `./` or contain `..`.
   - `hooks/hooks.json` lacks the top-level `"hooks"` wrapper.
   - Plugin name uses a reserved prefix.
   - `marketplace.json` lacks `name`, `owner` or `plugins`, or an entry lacks `name` or `source`.
   - A relative `source` lacks `./` or contains `..`.
   - Duplicate entry names.
   - Best done by running `claude plugin validate` in CI (UNVERIFIED that it is installable in the bot's runner); otherwise reimplement the checks above.
7. **Not a signal**: `.mcp.json`, `hooks/`, `agents/`, `commands/`, `CLAUDE.md` or `AGENTS.md` without rules 1-4 matching.

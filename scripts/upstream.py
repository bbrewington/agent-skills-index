"""
upstream.py

What the sync learns about a curated or starred upstream repo: whether it was archived, renamed
or deleted; what changed since the last-seen SHA (the changelog); and which skill or plugin paths
it holds that the owner has not listed (suggestions). Everything here reads from GitHub through
`ghapi.get`; callers decide what to write.
"""

import json
import re
from urllib.parse import quote

import ghapi
import yaml

MAX_KNOWN_TAGS = 50
MAX_COMPLIANCE_FETCHES = 20
MAX_SHALLOW_SUBDIRS = 50


def _json(response):
    return response.json() if response.status_code == 200 else None


# -----------------------------------------------------------------------
# Flags: archived, renamed, gone
# -----------------------------------------------------------------------

def repo_flags(repo: str, meta: dict) -> list[str]:
    flags = []
    if meta.get("archived"):
        flags.append("archived")
    full_name = meta.get("full_name")
    if full_name and full_name.lower() != repo.lower():
        flags.append(f"renamed:{full_name}")
    return flags


def fetch_repo(repo: str) -> tuple[dict | None, list[str]]:
    """(metadata, flags). A deleted repo returns (None, ["gone"]). GitHub redirects renames, which shows
    up as a different `full_name`."""
    r = ghapi.get(f"/repos/{repo}")
    if r.status_code in (404, 410):
        return None, ["gone"]
    r.raise_for_status()
    meta = r.json()
    return meta, repo_flags(repo, meta)


# -----------------------------------------------------------------------
# Changelog: releases, tags and path commits since the last-seen SHA
# -----------------------------------------------------------------------

def head_commit(repo: str) -> dict | None:
    r = ghapi.get(f"/repos/{repo}/commits", {"per_page": 1})
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    return {"sha": data[0]["sha"], "date": data[0]["commit"]["committer"]["date"]}


def all_tags(repo: str) -> list[str]:
    return [t["name"] for t in _json(ghapi.get(f"/repos/{repo}/tags", {"per_page": 100})) or []]


def new_releases(repo: str, since: str) -> list[dict]:
    data = _json(ghapi.get(f"/repos/{repo}/releases", {"per_page": 30})) or []
    return [
        {"tag": r["tag_name"], "name": r.get("name") or r["tag_name"], "url": r["html_url"]}
        for r in data
        if not r.get("draft") and (r.get("published_at") or "") > since
    ]


def path_commits(repo: str, paths: list[str] | None, since: str, last_sha: str) -> list[dict]:
    """Non-merge commits touching `paths` (the whole repo when None) after `since`, excluding the last-seen SHA."""
    found: dict[str, dict] = {}
    for path in paths or [None]:
        params = {"per_page": 100, "since": since} | ({"path": path} if path else {})
        for c in _json(ghapi.get(f"/repos/{repo}/commits", params)) or []:
            if c["sha"] == last_sha or len(c.get("parents", [])) > 1 or c["sha"] in found:
                continue
            found[c["sha"]] = {
                "sha": c["sha"],
                "message": c["commit"]["message"].splitlines()[0] if c["commit"]["message"] else "",
                "url": c["html_url"],
            }
    return list(found.values())


def detect(repo: str, paths: list[str] | None, state: dict, head: dict | None = None) -> dict | None:
    """Compare a curated repo against its last-seen state.

    Returns None (nothing to report), {"kind": "baseline", ...} (no last-seen SHA yet: record one and
    report nothing) or {"kind": "change", "entry": ..., ...}. Never mutates `state`; see `advance`.
    """
    head = head or head_commit(repo)
    if head is None:
        return None
    tags = all_tags(repo)
    if "changelog_sha" not in state:
        return {"kind": "baseline", "head": head, "tags": tags}
    releases = new_releases(repo, state["changelog_at"])
    fresh_tags = [t for t in tags if t not in state.get("known_tags", [])]
    commits = []
    if head["sha"] != state["changelog_sha"]:
        commits = path_commits(repo, paths, state["changelog_at"], state["changelog_sha"])
    if not (releases or fresh_tags or commits):
        return None
    entry = {
        "repo": repo,
        "old_sha": state["changelog_sha"],
        "new_sha": head["sha"],
        "compare_url": f"https://github.com/{repo}/compare/{state['changelog_sha']}...{head['sha']}",
        "releases": releases,
        "tags": fresh_tags,
        "commits": commits,
    }
    return {"kind": "change", "head": head, "tags": tags, "entry": entry}


def advance(state: dict, head: dict, tags: list[str]) -> None:
    """Move the last-seen markers forward. Callers do this only once the changelog entry is written."""
    state["changelog_sha"] = head["sha"]
    state["changelog_at"] = head["date"]
    state["known_tags"] = tags[:MAX_KNOWN_TAGS]


# -----------------------------------------------------------------------
# Suggestions: skill and plugin paths found in the repo's file tree
# (see docs/research/skill-plugin-detection.md)
# -----------------------------------------------------------------------

# (marker path tail, kind, format, only matches at the repo root)
MARKERS = [
    ("SKILL.md", "skill", "agentskills", False),
    (".claude-plugin/plugin.json", "plugin", "claude", False),
    (".claude-plugin/marketplace.json", "marketplace", "claude", False),
    (".cursor-plugin/plugin.json", "plugin", "cursor", False),
    (".cursor-plugin/marketplace.json", "marketplace", "cursor", False),
    (".codex-plugin/plugin.json", "plugin", "codex", False),
    (".agents/plugins/marketplace.json", "marketplace", "codex", True),
    ("gemini-extension.json", "plugin", "gemini", False),
]

SHALLOW_DIRS = ["", "skills", ".claude/skills", ".claude-plugin", ".agents/plugins", ".cursor-plugin"]
SKILL_CONTAINER_DIRS = {"skills", ".claude/skills"}

SKILL_NAME = re.compile(r"^[^\W_]+(-[^\W_]+)*$")
FRONTMATTER = re.compile(r"^---[ \t]*\n(.*?)\n---[ \t]*(\n|$)", re.DOTALL)


def _norm(path: str) -> str:
    return path.rstrip("/") or "."


def classify_tree(paths: list[str]) -> list[dict]:
    """Candidate skill/plugin/marketplace directories found by marker files. Skills inside a plugin root are
    dropped: the plugin covers them."""
    found: dict[tuple, dict] = {}
    for path in paths:
        for tail, kind, fmt, root_only in MARKERS:
            if path == tail:
                directory = "."
            elif not root_only and path.endswith("/" + tail):
                directory = path[: -len(tail) - 1]
            else:
                continue
            found.setdefault((directory, kind, fmt), {"path": directory, "kind": kind, "format": fmt, "marker": path})
    plugin_roots = [c["path"] for c in found.values() if c["kind"] == "plugin"]
    return sorted(
        (c for c in found.values() if not (c["kind"] == "skill" and any(_within(c["path"], r) for r in plugin_roots))),
        key=lambda c: (c["path"], c["kind"], c["format"]),
    )


def _within(path: str, root: str) -> bool:
    """True when `path` is `root` or inside it ("." is the whole repo)."""
    path, root = _norm(path), _norm(root)
    return root == "." or path == root or path.startswith(root + "/")


def covered(path: str, listed: list[str]) -> bool:
    return any(_within(path, entry) for entry in listed)


def invalid_listed(listed: list[str], candidates: list[dict]) -> list[str]:
    """Listed paths that are neither a skill/plugin directory nor a container of, or inside, one."""
    directories = [c["path"] for c in candidates]
    return [
        entry
        for entry in listed
        if not any(_within(d, entry) or _within(entry, d) for d in directories)
    ]


def check_skill_md(directory: str, text: str) -> list[str]:
    """Problems against the agentskills.io specification (an empty list means compliant)."""
    match = FRONTMATTER.match(text)
    if not match:
        return ["missing YAML frontmatter"]
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return ["unparsable YAML frontmatter"]
    if not isinstance(meta, dict):
        return ["unparsable YAML frontmatter"]
    problems = []
    name = meta.get("name")
    if not isinstance(name, str) or not name:
        problems.append("missing name")
    elif len(name) > 64 or name != name.lower() or not SKILL_NAME.match(name):
        problems.append(f"invalid name '{name}'")
    elif directory != "." and name != directory.rstrip("/").rsplit("/", 1)[-1]:
        problems.append(f"name '{name}' does not match its directory")
    description = meta.get("description")
    if not isinstance(description, str) or not description.strip():
        problems.append("missing description")
    elif len(description) > 1024:
        problems.append("description over 1024 characters")
    compatibility = meta.get("compatibility")
    if compatibility is not None and (not isinstance(compatibility, str) or len(compatibility) > 500):
        problems.append("invalid compatibility")
    metadata = meta.get("metadata")
    if metadata is not None and not (
        isinstance(metadata, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in metadata.items())
    ):
        problems.append("metadata must map strings to strings")
    return problems


def check_plugin_json(text: str) -> list[str]:
    try:
        manifest = json.loads(text)
    except ValueError:
        return ["plugin.json is not valid JSON"]
    if not isinstance(manifest, dict) or not manifest.get("name"):
        return ["plugin.json has no name"]
    return []


def fetch_tree(repo: str, sha: str) -> tuple[list[str], bool]:
    """(blob paths, truncated). One recursive Git Trees call; truncated past 100k entries / 7 MB."""
    r = ghapi.get(f"/repos/{repo}/git/trees/{sha}", {"recursive": 1})
    r.raise_for_status()
    body = r.json()
    return [t["path"] for t in body.get("tree", []) if t["type"] == "blob"], bool(body.get("truncated"))


def _list_dir(repo: str, path: str) -> list[dict]:
    return _json(ghapi.get(f"/repos/{repo}/contents/{quote(path)}")) or []


def shallow_paths(repo: str) -> list[str]:
    """Fallback for a truncated tree: list only the directories skills and plugins usually live in."""
    paths = []
    for directory in SHALLOW_DIRS:
        entries = _list_dir(repo, directory)
        paths += [e["path"] for e in entries if e["type"] == "file"]
        if directory in SKILL_CONTAINER_DIRS:
            for sub in [e for e in entries if e["type"] == "dir"][:MAX_SHALLOW_SUBDIRS]:
                paths += [e["path"] for e in _list_dir(repo, sub["path"]) if e["type"] == "file" and e["path"].endswith("/SKILL.md")]
    return paths


def fetch_text(repo: str, path: str) -> str | None:
    r = ghapi.get(f"/repos/{repo}/contents/{quote(path)}", accept="application/vnd.github.raw+json")
    return r.text if r.status_code == 200 else None


def _check_candidate(repo: str, candidate: dict) -> None:
    candidate["compliant"], candidate["problems"] = None, []
    if candidate["kind"] == "skill":
        checker = lambda text: check_skill_md(candidate["path"], text)
    elif candidate["kind"] == "plugin" and candidate["format"] == "claude":
        checker = check_plugin_json
    else:
        return
    text = fetch_text(repo, candidate["marker"])
    if text is not None:
        candidate["problems"] = checker(text)
        candidate["compliant"] = not candidate["problems"]


def audit(repo: str, head_sha: str, listed: list[str] | None, check_compliance: bool) -> dict:
    """Skill/plugin paths in the repo that are not yet listed, plus listed paths that are neither."""
    listed = listed or []
    paths, truncated = fetch_tree(repo, head_sha)
    if truncated:
        paths = shallow_paths(repo)
    candidates = classify_tree(paths)
    suggestions = [dict(c, compliant=None, problems=[]) for c in candidates if not covered(c["path"], listed)]
    if check_compliance:
        for suggestion in suggestions[:MAX_COMPLIANCE_FETCHES]:
            _check_candidate(repo, suggestion)
    return {
        "suggestions": suggestions,
        # a shallow listing can't prove a listed path is missing
        "invalid_paths": [] if truncated else invalid_listed(listed, candidates),
        "truncated": truncated,
    }

#!/usr/bin/env python3
"""
sync_stars.py

Two modes, both writing back into tracked.yml (one `repos:` list; a stub is an entry
with `verdict: null`):

  sync      For adopt/watch repos: flag archived/renamed/gone upstreams, find releases, tags and path
            commits since the last-seen SHA (the changelog), and suggest unlisted skill/plugin paths.
            Also suggests paths for stubs whose upstream head moved.
  discover  Fetch starred repos; add unseen ones as stubs; prune stubs outside the star list(s).

The bot only writes bot-owned fields: `state`, new stubs, and (with --prune-stubs)
removal of stubs, plus the changelog files and INDEX.md under generated/. It never touches
verdict, use_contexts, notes or skill_or_plugin_paths on an existing entry. The file fails validation on an unknown verdict or a use_contexts
tag missing from use-contexts.yml.

Default (--mode all) runs both.

Usage:
    python scripts/sync_stars.py [--mode all|sync|discover] [--dry-run] [--update-changelog] [--output changes.yaml]

Environment variables:
    GITHUB_TOKEN   PAT (fine-grained, or classic with read:user)
    GITHUB_USER    Defaults to "bbrewington"
    STAR_LIST      Optional comma-separated slug(s) of GitHub star lists (e.g.
                   "agent-skills,ai-helpers-and-reference"). When set, discover mode only
                   considers repos in those lists (via GraphQL) instead of every starred repo.
"""

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import render
import requests
import upstream
import yaml
from ghapi import HEADERS

GITHUB_USER = os.getenv("GITHUB_USER", "bbrewington")
STAR_LIST = os.getenv("STAR_LIST") or None
TRACKED_FILE = Path(__file__).parent.parent / "tracked.yml"
USE_CONTEXTS_FILE = Path(__file__).parent.parent / "use-contexts.yml"

VERDICTS = {"adopt", "watch", "skip"}
SYNCED_VERDICTS = {"adopt", "watch"}


# -----------------------------------------------------------------------
# GitHub API helpers
# -----------------------------------------------------------------------

def get_starred_repos(user: str) -> tuple[list[dict], bool]:
    """Returns (repos, rate_limited) - rate_limited is True if discovery was cut short."""
    repos = []
    page = 1
    rate_limited = False
    while True:
        r = requests.get(
            f"https://api.github.com/users/{user}/starred",
            headers=HEADERS,
            params={"per_page": 100, "page": page},
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        repos.extend(batch)
        page += 1
        if int(r.headers.get("X-RateLimit-Remaining", 999)) < 10:
            print("WARNING: approaching GitHub rate limit - discovery may be incomplete", file=sys.stderr)
            rate_limited = True
            break
    return repos, rate_limited


LIST_ID_QUERY = """
query($login: String!) {
  user(login: $login) { lists(first: 100) { nodes { id slug } } }
}
"""

LIST_ITEMS_QUERY = """
query($id: ID!, $after: String) {
  node(id: $id) {
    ... on UserList {
      items(first: 100, after: $after) {
        nodes { ... on Repository { nameWithOwner } }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""


def graphql(query: str, variables: dict) -> dict:
    r = requests.post(
        "https://api.github.com/graphql",
        headers=HEADERS,
        json={"query": query, "variables": variables},
    )
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise requests.HTTPError(f"GraphQL errors: {body['errors']}")
    return body["data"]


def get_list_repos(user: str, slug: str) -> list[dict]:
    """Repos in the user's star list `slug`, shaped like the starred endpoint ({"full_name": ...})."""
    lists = graphql(LIST_ID_QUERY, {"login": user})["user"]["lists"]["nodes"]
    match = next((node for node in lists if node["slug"] == slug), None)
    if match is None:
        raise requests.HTTPError(f"Star list '{slug}' not found for {user}; slugs: {[n['slug'] for n in lists]}")
    repos: list[dict] = []
    after = None
    while True:
        items = graphql(LIST_ITEMS_QUERY, {"id": match["id"], "after": after})["node"]["items"]
        repos.extend({"full_name": n["nameWithOwner"]} for n in items["nodes"] if n)
        if not items["pageInfo"]["hasNextPage"]:
            return repos
        after = items["pageInfo"]["endCursor"]


def get_repo_meta(owner_repo: str) -> dict:
    r = requests.get(f"https://api.github.com/repos/{owner_repo}", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def get_latest_commit_sha(owner_repo: str, paths: list[str] | None = None) -> str:
    owner, repo = owner_repo.split("/", 1)
    base = f"https://api.github.com/repos/{owner}/{repo}/commits"
    if paths:
        latest_sha = latest_ts = None
        for path in paths:
            r = requests.get(base, headers=HEADERS, params={"path": path, "per_page": 1})
            if r.status_code != 200:
                continue
            data = r.json()
            if not data:
                continue
            ts = data[0]["commit"]["committer"]["date"]
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts
                latest_sha = data[0]["sha"]
        return latest_sha or "unknown"
    else:
        r = requests.get(base, headers=HEADERS, params={"per_page": 1})
        r.raise_for_status()
        data = r.json()
        return data[0]["sha"] if data else "unknown"


# -----------------------------------------------------------------------
# tracked.yml read/write
# -----------------------------------------------------------------------

def extract_header(text: str) -> str:
    """Leading '#' comment block (plus its trailing blank line), stripped by a plain yaml.dump round-trip."""
    lines = text.splitlines(keepends=True)
    header_lines = []
    for line in lines:
        if line.startswith("#") or line.strip() == "":
            header_lines.append(line)
        else:
            break
    return "".join(header_lines)


class ValidationError(ValueError):
    pass


def load_tracked() -> dict:
    data = yaml.safe_load(TRACKED_FILE.read_text()) or {}
    data.setdefault("repos", [])
    # Ensure every entry has a state block
    for item in data["repos"]:
        item.setdefault("state", {})
    return data


def load_use_contexts() -> set[str]:
    return set(yaml.safe_load(USE_CONTEXTS_FILE.read_text()) or {})


def validate(data: dict, use_contexts: set[str]) -> None:
    """Raise ValidationError on an unknown verdict or a use_contexts tag outside the vocabulary."""
    errors = []
    for item in data["repos"]:
        verdict = item.get("verdict")
        if verdict is not None and verdict not in VERDICTS:
            errors.append(f"{item['repo']}: unknown verdict '{verdict}' (allowed: {sorted(VERDICTS)})")
        unknown = [tag for tag in item.get("use_contexts") or [] if tag not in use_contexts]
        if unknown:
            errors.append(f"{item['repo']}: unknown use_contexts {unknown} (add to use-contexts.yml)")
    if errors:
        raise ValidationError("\n".join(errors))


def save_tracked(data: dict, dry_run: bool) -> None:
    if dry_run:
        return
    header = extract_header(TRACKED_FILE.read_text()) if TRACKED_FILE.exists() else ""
    body = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    TRACKED_FILE.write_text(header + body)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def build_state(meta: dict, sha: str, existing_state: dict | None = None) -> dict:
    return {
        "latest_sha": sha,
        "pushed_at": meta.get("pushed_at"),
        "description": meta.get("description"),
        "language": meta.get("language"),
        "topics": meta.get("topics", []),
        "license": (meta.get("license") or {}).get("spdx_id"),
        "stargazers_count": meta.get("stargazers_count"),
        "indexed_at": (existing_state or {}).get("indexed_at") or now_iso(),
        "last_changed_at": now_iso(),
    }


# -----------------------------------------------------------------------
# Sync mode
# -----------------------------------------------------------------------

def run_sync(data: dict, record: bool) -> tuple[dict, list[tuple], dict]:
    """Check adopt/watch repos. Returns (result, pending, heads).

    result: changes (changelog entries), baselines, flags, unrecorded (findings when not recording).
    pending: (entry, head, tags, meta) for each change; `persist` advances the last-seen SHA only after the
    entry is written. Nothing advances when `record` is false.
    """
    result: dict[str, list] = {"changes": [], "baselines": [], "flags": [], "unrecorded": []}
    pending: list[tuple] = []
    heads: dict[str, dict] = {}
    for item in data["repos"]:
        if item.get("verdict") not in SYNCED_VERDICTS:
            continue
        repo, verdict = item["repo"], item["verdict"]
        state = item.setdefault("state", {})
        print(f"[sync] {repo}")
        try:
            meta, flags = upstream.fetch_repo(repo)
        except requests.HTTPError as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            continue

        old_flags = state.get("flags", [])
        fresh = [f for f in flags if f not in old_flags]
        if fresh:
            print(f"  -> FLAGS {fresh}")
            report = {"repo": repo, "verdict": verdict, "flags": fresh}
            if record:
                result["flags"].append(report)
            else:
                result["unrecorded"].append({"type": "flag"} | report)
        if record and flags != old_flags:
            state["flags"] = flags
        if meta is None:
            continue

        try:
            head = upstream.head_commit(repo)
            found = upstream.detect(repo, item.get("skill_or_plugin_paths"), state, head)
        except requests.HTTPError as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            continue
        if head:
            heads[repo] = head
        if found is None:
            print("  -> no change")
        elif found["kind"] == "baseline":
            print("  -> BASELINE")
            if record:
                upstream.advance(state, head, found["tags"])
                state.update(build_state(meta, head["sha"], state))
                result["baselines"].append({"repo": repo, "verdict": verdict})
            else:
                result["unrecorded"].append({"type": "baseline", "repo": repo, "verdict": verdict})
        else:
            entry = found["entry"] | {"verdict": verdict}
            print(f"  -> CHANGED {found['entry']['old_sha'][:7]}..{head['sha'][:7]}")
            if record:
                result["changes"].append(entry)
                pending.append((item, head, found["tags"], meta))
            else:
                result["unrecorded"].append({"type": "change"} | entry)
    return result, pending, heads


def run_audit(data: dict, record: bool, heads: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """Suggest unlisted skill/plugin paths (and flag listed ones that are neither) for every repo whose upstream
    head moved since its last audit. Curated repos also get compliance checks. Returns (suggestions, unrecorded)."""
    suggestions: list[dict] = []
    unrecorded: list[dict] = []
    for item in data["repos"]:
        verdict = item.get("verdict")
        state = item.setdefault("state", {})
        if verdict == "skip" or "gone" in state.get("flags", []):
            continue
        repo = item["repo"]
        curated = verdict in SYNCED_VERDICTS
        try:
            head = heads.get(repo) or upstream.head_commit(repo)
            if head is None or head["sha"] == state.get("tree_sha"):
                continue
            audited = upstream.audit(repo, head["sha"], item.get("skill_or_plugin_paths"), check_compliance=curated)
        except requests.HTTPError as e:
            print(f"  [audit] {repo} ERROR: {e}", file=sys.stderr)
            continue
        report = {"repo": repo, "verdict": verdict, "curated": curated} | audited
        has_findings = bool(audited["suggestions"] or audited["invalid_paths"])
        if record:
            state["tree_sha"] = head["sha"]
            if has_findings:
                suggestions.append(report)
        elif has_findings:
            unrecorded.append({"type": "suggestion"} | report)
    return suggestions, unrecorded


def persist(data: dict, result: dict, pending: list[tuple], dry_run: bool, today: str) -> None:
    """Write the changelog first, then advance last-seen SHAs, then INDEX.md and tracked.yml. A failed changelog
    write raises before anything is advanced or saved."""
    if dry_run:
        return
    render.write_changelog(result["changes"], render.CHANGELOG_DIR, today)
    for item, head, tags, meta in pending:
        upstream.advance(item["state"], head, tags)
        item["state"].update(build_state(meta, head["sha"], item["state"]))
    render.write_index(data)
    save_tracked(data, dry_run=False)


# -----------------------------------------------------------------------
# Discover mode
# -----------------------------------------------------------------------

def fetch_candidates(star_list: str | None) -> tuple[list[dict], bool]:
    """Repos to consider for discovery: the given star list(s) (comma-separated slugs), else every star."""
    if star_list:
        seen: dict[str, dict] = {}
        for slug in (part.strip() for part in star_list.split(",") if part.strip()):
            for repo in get_list_repos(GITHUB_USER, slug):
                seen.setdefault(repo["full_name"], repo)
        return list(seen.values()), False
    return get_starred_repos(GITHUB_USER)


def prune_stubs(data: dict, candidates: list[dict]) -> list[str]:
    """Drop stubs (verdict null) not in `candidates`; curated entries are never removed. Returns removed repo names."""
    keep = {c["full_name"] for c in candidates}
    def is_prunable(item: dict) -> bool:
        return item.get("verdict") is None and item["repo"] not in keep

    removed = [item["repo"] for item in data["repos"] if is_prunable(item)]
    data["repos"] = [item for item in data["repos"] if not is_prunable(item)]
    return removed


def run_discover(data: dict, dry_run: bool, star_list: str | None = None) -> tuple[list[dict], bool, list[str]]:
    source = f"star list(s) '{star_list}'" if star_list else "stars"
    print(f"[discover] Fetching {source} for {GITHUB_USER}...")
    try:
        starred, rate_limited = fetch_candidates(star_list)
    except requests.HTTPError as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return [], False, []
    print(f"  {len(starred)} repos found")
    pruned = []
    if star_list and starred:
        pruned = prune_stubs(data, starred)
    elif star_list:
        print("  WARNING: star list(s) returned no repos; not pruning", file=sys.stderr)
    if pruned:
        print(f"  {len(pruned)} stub(s) not in {source} pruned")

    known = {item["repo"] for item in data["repos"]}

    new_stubs = []
    for star in starred:
        repo = star["full_name"]
        if repo in known:
            continue
        print(f"  [discover] NEW star: {repo}")
        try:
            meta = get_repo_meta(repo)
            sha = get_latest_commit_sha(repo)
        except requests.HTTPError as e:
            print(f"    ERROR: {e}", file=sys.stderr)
            continue

        stub = {
            "repo": repo,
            "verdict": None,
            "use_contexts": None,
            "notes": None,
            "skill_or_plugin_paths": None,
            "state": build_state(meta, sha),
        }
        data["repos"].append(stub)
        new_stubs.append({"repo": repo, "reason": "new_star", "state": stub["state"]})

    print(f"  {len(new_stubs)} new stub(s) added")
    return new_stubs, rate_limited, pruned


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["all", "sync", "discover"], default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--star-list", default=STAR_LIST, help="comma-separated star list slug(s) (default: $STAR_LIST)")
    parser.add_argument(
        "--update-changelog",
        action="store_true",
        help="record changelog entries and advance last-seen markers; without it, upstream findings are only reported",
    )
    parser.add_argument("--output", default="changes.yaml")
    args = parser.parse_args()

    data = load_tracked()
    try:
        validate(data, load_use_contexts())
    except ValidationError as e:
        print(f"ERROR: invalid tracked.yml:\n{e}", file=sys.stderr)
        sys.exit(2)

    new_stars: list[dict] = []
    discover_rate_limited = False
    pruned: list[str] = []
    result: dict[str, list] = {"changes": [], "baselines": [], "flags": [], "unrecorded": []}
    pending: list[tuple] = []
    suggestions: list[dict] = []

    if args.mode in ("all", "discover"):
        new_stars, discover_rate_limited, pruned = run_discover(data, dry_run=args.dry_run, star_list=args.star_list)

    if args.mode in ("all", "sync"):
        result, pending, heads = run_sync(data, record=args.update_changelog)
        suggestions, unrecorded = run_audit(data, record=args.update_changelog, heads=heads)
        result["unrecorded"] += unrecorded

    persist(data, result, pending, dry_run=args.dry_run, today=now_iso()[:10])

    counts = {
        "changed_count": len(result["changes"]),
        "baseline_count": len(result["baselines"]),
        "flag_count": len(result["flags"]),
        "suggestion_count": len(suggestions),
        "new_stars_count": len(new_stars),
        "pruned_count": len(pruned),
    }
    summary = {
        "checked_at": now_iso(),
        "mode": args.mode,
        "recorded": args.update_changelog,
        **counts,
        "total_changes": sum(counts.values()),
        "discover_rate_limited": discover_rate_limited,
        "changes": result["changes"],
        "baselines": result["baselines"],
        "flags": result["flags"],
        "suggestions": suggestions,
        "new_stars": new_stars,
        "pruned_stubs": pruned,
        "unrecorded": result["unrecorded"],
    }

    Path(args.output).write_text(yaml.dump(summary, default_flow_style=False, sort_keys=False, allow_unicode=True))
    print(
        f"\nDone. {counts['changed_count']} changelog entr(ies), {counts['baseline_count']} baseline(s), "
        f"{counts['flag_count']} flag(s), {counts['suggestion_count']} suggestion(s), "
        f"{counts['new_stars_count']} new star(s), {counts['pruned_count']} pruned. Summary -> {args.output}"
    )
    if result["unrecorded"]:
        print(f"{len(result['unrecorded'])} finding(s) not recorded (pass --update-changelog to record).")

    sys.exit(1 if summary["total_changes"] else 0)


if __name__ == "__main__":
    main()

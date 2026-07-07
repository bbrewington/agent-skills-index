#!/usr/bin/env python3
"""
sync_stars.py

Two modes, both writing state back into tracked.yml:

  sync      Check every repo in tracked.tracked[] for upstream SHA changes.
  discover  Fetch all starred repos; add new ones as stubs to tracked.stubs[].

Default (--mode all) runs both.

Usage:
    python scripts/sync_stars.py [--mode all|sync|discover] [--dry-run] [--output changes.yaml]

Environment variables:
    GITHUB_TOKEN   PAT with read:user scope
    GITHUB_USER    Defaults to "bbrewington"
"""

import os
import sys
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

GITHUB_USER = os.getenv("GITHUB_USER", "bbrewington")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
TRACKED_FILE = Path(__file__).parent.parent / "tracked.yml"

HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"


# -----------------------------------------------------------------------
# GitHub API helpers
# -----------------------------------------------------------------------

def get_starred_repos(user: str) -> list[dict]:
    repos = []
    page = 1
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
            print("WARNING: approaching GitHub rate limit", file=sys.stderr)
            break
    return repos


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

def load_tracked() -> dict:
    data = yaml.safe_load(TRACKED_FILE.read_text())
    data.setdefault("tracked", [])
    data.setdefault("stubs", [])
    # Ensure every entry has a state block
    for item in data["tracked"]:
        item.setdefault("state", {})
    for item in data["stubs"]:
        item.setdefault("state", {})
    return data


def save_tracked(data: dict, dry_run: bool) -> None:
    if dry_run:
        return
    TRACKED_FILE.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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

def run_sync(data: dict, dry_run: bool) -> list[dict]:
    changes = []
    for item in data["tracked"]:
        repo = item["repo"]
        print(f"[sync] {repo}")
        try:
            meta = get_repo_meta(repo)
            sha = get_latest_commit_sha(repo, item.get("watch_paths"))
        except requests.HTTPError as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            continue

        old_sha = (item.get("state") or {}).get("latest_sha")
        new_state = build_state(meta, sha, item.get("state"))

        if old_sha is None:
            print(f"  -> NEW (first index)")
            item["state"] = new_state
            changes.append({"repo": repo, "reason": "new", "new_sha": sha})
        elif old_sha != sha:
            print(f"  -> UPDATED {old_sha[:7]}..{sha[:7]}")
            item["state"] = new_state
            changes.append({"repo": repo, "reason": "updated", "old_sha": old_sha, "new_sha": sha})
        else:
            print(f"  -> no change")

    return changes


# -----------------------------------------------------------------------
# Discover mode
# -----------------------------------------------------------------------

def run_discover(data: dict, dry_run: bool) -> list[dict]:
    print(f"[discover] Fetching stars for {GITHUB_USER}...")
    try:
        starred = get_starred_repos(GITHUB_USER)
    except requests.HTTPError as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return []
    print(f"  {len(starred)} starred repos found")

    tracked_names = {item["repo"] for item in data["tracked"]}
    stub_names = {item["repo"] for item in data["stubs"]}
    known = tracked_names | stub_names

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
            "skill": None,
            "notes": None,
            "watch_paths": None,
            "state": build_state(meta, sha),
        }
        data["stubs"].append(stub)
        new_stubs.append({"repo": repo, "reason": "new_star", "state": stub["state"]})

    print(f"  {len(new_stubs)} new stub(s) added")
    return new_stubs


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["all", "sync", "discover"], default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="changes.yaml")
    args = parser.parse_args()

    data = load_tracked()
    # Keep a snapshot for diffing in gen_pr_body if needed
    original = deepcopy(data)  # noqa: F841

    sync_changes: list[dict] = []
    new_stars: list[dict] = []

    if args.mode in ("all", "sync"):
        sync_changes = run_sync(data, dry_run=args.dry_run)

    if args.mode in ("all", "discover"):
        new_stars = run_discover(data, dry_run=args.dry_run)

    save_tracked(data, dry_run=args.dry_run)

    summary = {
        "checked_at": now_iso(),
        "mode": args.mode,
        "changed_count": len(sync_changes),
        "new_stars_count": len(new_stars),
        "total_changes": len(sync_changes) + len(new_stars),
        "changes": sync_changes,
        "new_stars": new_stars,
    }

    Path(args.output).write_text(yaml.dump(summary, default_flow_style=False, sort_keys=False, allow_unicode=True))
    print(f"\nDone. {len(sync_changes)} tracked change(s), {len(new_stars)} new star(s). Summary -> {args.output}")

    sys.exit(1 if summary["total_changes"] else 0)


if __name__ == "__main__":
    main()

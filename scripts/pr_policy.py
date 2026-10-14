#!/usr/bin/env python3
"""
pr_policy.py

Decides what the sync workflow does with a run's changes.yaml:

  none    nothing to commit, or only new/pruned stubs and no open bot PR
  open    open a new PR (nothing is open and the diff holds something a human decides on)
  update  push to the open bot PR's branch and refresh its title/body

At most one bot PR is open at a time. New and pruned stubs never open a PR on their own;
they ride along on the next PR. Upstream changes to curated repos are what a human decides on.

Usage:
    python scripts/pr_policy.py --input changes.yaml --pr-exists true|false
    python scripts/pr_policy.py --merge-body existing.md --new-body new.md --date 2026-10-21 --output merged.md
"""

import argparse
from pathlib import Path

import yaml

TITLE_HEADING = "## Skills Index Update"


def needs_decision(summary: dict) -> bool:
    return bool(summary.get("changes"))


def decide(summary: dict, pr_exists: bool) -> str:
    if not summary.get("total_changes"):
        return "none"
    if pr_exists:
        return "update"
    return "open" if needs_decision(summary) else "none"


def merge_body(existing: str, new: str, date: str) -> str:
    """Keep the PR's earlier body and append this run's body (minus its title) as a dated section."""
    addition = new.removeprefix(TITLE_HEADING).lstrip("\n")
    return f"{existing.rstrip()}\n\n---\n\n### Update {date}\n\n{addition}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="changes.yaml")
    parser.add_argument("--pr-exists", choices=["true", "false"], default="false")
    parser.add_argument("--merge-body", help="existing PR body file")
    parser.add_argument("--new-body", help="this run's body file")
    parser.add_argument("--date")
    parser.add_argument("--output")
    args = parser.parse_args()

    if args.merge_body:
        merged = merge_body(Path(args.merge_body).read_text(), Path(args.new_body).read_text(), args.date)
        Path(args.output).write_text(merged)
        return
    summary = yaml.safe_load(Path(args.input).read_text())
    print(decide(summary, args.pr_exists == "true"))


if __name__ == "__main__":
    main()

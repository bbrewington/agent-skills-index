import render

CHANGE = {
    "repo": "o/r",
    "verdict": "adopt",
    "compare_url": "https://github.com/o/r/compare/a...b",
    "releases": [{"tag": "v2", "name": "Two", "url": "https://x/v2"}],
    "tags": ["v2"],
    "commits": [{"sha": "abcdef1234", "message": "fix thing", "url": "https://x/c"}],
}
WATCH = CHANGE | {"repo": "o/w", "verdict": "watch", "releases": [], "tags": []}


def test_entry_has_verdict_compare_link_releases_tags_and_commits():
    text = render.render_entries([CHANGE], "2026-10-14")
    assert "## 2026-10-14" in text
    assert "o/r" in text and "adopt" in text
    assert "[compare](https://github.com/o/r/compare/a...b)" in text
    assert "[Two](https://x/v2)" in text
    assert "v2" in text
    assert "[`abcdef1`](https://x/c) fix thing" in text


def test_adopt_entries_come_before_watch():
    text = render.render_entries([WATCH, CHANGE], "2026-10-14")
    assert text.index("o/r") < text.index("o/w")


def test_write_changelog_creates_month_file_and_puts_newest_first(tmp_path):
    first = render.write_changelog([CHANGE], tmp_path, "2026-10-14")
    assert first == tmp_path / "2026-10.md"
    render.write_changelog([WATCH], tmp_path, "2026-10-21")
    text = first.read_text()
    assert text.startswith("# Upstream changelog 2026-10")
    assert text.index("2026-10-21") < text.index("2026-10-14")


def test_write_changelog_with_no_entries_writes_nothing(tmp_path):
    assert render.write_changelog([], tmp_path, "2026-10-14") is None
    assert list(tmp_path.iterdir()) == []


def entry(repo, verdict=None, contexts=None, **extra):
    return {"repo": repo, "verdict": verdict, "use_contexts": contexts, "notes": None,
            "skill_or_plugin_paths": None, "state": {"description": "d"}} | extra


DATA = {
    "repos": [
        entry("o/watch", "watch", ["data-engineering"], notes="n1"),
        entry("o/adopt", "adopt", ["data-engineering", "agent-workflow"], skill_or_plugin_paths=["skills/a"]),
        entry("o/untagged", "adopt", None),
        entry("o/skipped", "skip"),
        entry("o/stub"),
        entry("o/flagged", "watch", ["agent-workflow"]) | {"state": {"flags": ["archived"]}},
    ]
}


def test_index_groups_by_use_context_adopt_first_and_repeats_multi_tag_repos():
    text = render.render_index(DATA)
    assert "do not edit" in text.lower()
    de = text.index("## data-engineering")
    assert text.index("o/adopt", de) < text.index("o/watch", de)
    assert text.count("o/adopt") >= 2  # under both of its use-contexts
    assert "`skills/a`" in text
    assert "n1" in text


def test_index_lists_untagged_skipped_and_stub_counts():
    text = render.render_index(DATA)
    assert "## Untagged" in text and "o/untagged" in text
    assert "## Skipped (1)" in text and "o/skipped" in text
    assert "## Stubs (1)" in text and "o/stub" in text


def test_index_shows_flags():
    assert "archived" in render.render_index(DATA)


def test_write_index_writes_the_file(tmp_path):
    path = tmp_path / "generated" / "INDEX.md"
    render.write_index(DATA, path)
    assert path.read_text() == render.render_index(DATA)

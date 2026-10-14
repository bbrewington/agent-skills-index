import gen_pr_body

BASE = {"checked_at": "2026-10-14T00:56:00+00:00", "changes": [], "new_stars": []}


CHANGE = {
    "repo": "o/r",
    "verdict": "adopt",
    "compare_url": "https://github.com/o/r/compare/aaa...bbb",
    "releases": [{"tag": "v2", "name": "Two", "url": "https://x/v2"}],
    "tags": [],
    "commits": [{"sha": "1234567890", "message": "m", "url": "u"}, {"sha": "abcdef", "message": "n", "url": "u2"}],
}


def test_upstream_changes_render_compare_link_counts_and_checklist():
    body = gen_pr_body.gen_body(BASE | {"changes": [CHANGE]})
    assert "### Upstream changes (1)" in body
    assert "`o/r` (adopt)" in body
    assert "[compare](https://github.com/o/r/compare/aaa...bbb)" in body
    assert "1 release" in body and "2 commits" in body
    assert "generated/changelog" in body
    assert "Review checklist" in body


def test_adopt_changes_listed_before_watch():
    watch = CHANGE | {"repo": "o/w", "verdict": "watch"}
    body = gen_pr_body.gen_body(BASE | {"changes": [watch, CHANGE]})
    assert body.index("`o/r`") < body.index("`o/w`")


def test_baselines_flags_and_suggestions_sections_only_when_present():
    plain = gen_pr_body.gen_body(BASE)
    for heading in ("Now tracking", "Upstream repos flagged", "Suggested skill/plugin paths"):
        assert heading not in plain
    data = BASE | {
        "baselines": [{"repo": "o/b", "verdict": "watch"}],
        "flags": [{"repo": "o/f", "verdict": "adopt", "flags": ["archived", "renamed:new/name"]}],
        "suggestions": [
            {
                "repo": "o/s",
                "verdict": "adopt",
                "curated": True,
                "truncated": True,
                "invalid_paths": ["docs/old"],
                "suggestions": [
                    {"path": "skills/a", "kind": "skill", "format": "agentskills", "compliant": True, "problems": []},
                    {"path": "p", "kind": "plugin", "format": "claude", "compliant": False, "problems": ["no name"]},
                ],
            }
        ],
    }
    body = gen_pr_body.gen_body(data)
    assert "Now tracking (1)" in body and "o/b" in body
    assert "Upstream repos flagged (1)" in body and "archived" in body and "renamed:new/name" in body
    assert "Suggested skill/plugin paths (1)" in body
    assert "`skills/a`" in body and "no name" in body
    assert "docs/old" in body
    assert "truncated" in body


def test_new_stars_grouped_by_language_with_other_fallback():
    stars = [
        {"repo": "o/py", "state": {"language": "Python", "description": "d", "topics": ["x"], "stargazers_count": 1}},
        {"repo": "o/none", "state": {}},
    ]
    body = gen_pr_body.gen_body(BASE | {"new_stars": stars})
    assert body.index("**Other**") < body.index("**Python**")
    assert "Topics: x | Stars: 1" in body


def test_rate_limit_warning_only_when_flagged():
    assert "[!WARNING]" not in gen_pr_body.gen_body(BASE)
    assert "[!WARNING]" in gen_pr_body.gen_body(BASE | {"discover_rate_limited": True})


def test_pruned_stubs_section_only_when_present():
    assert "Stubs removed" not in gen_pr_body.gen_body(BASE)
    body = gen_pr_body.gen_body(BASE | {"pruned_stubs": ["o/gone"]})
    assert "Stubs removed - no longer in the star list (1)" in body
    assert "- `o/gone`" in body

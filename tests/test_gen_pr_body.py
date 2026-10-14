import gen_pr_body

BASE = {"checked_at": "2026-10-14T00:56:00+00:00", "changes": [], "new_stars": []}


def test_updated_change_renders_compare_link_and_checklist():
    data = BASE | {"changes": [{"repo": "o/r", "reason": "updated", "old_sha": "a" * 40, "new_sha": "b" * 40}]}
    body = gen_pr_body.gen_body(data)
    assert "### Tracked repos with upstream changes (1)" in body
    assert "compare/aaaaaaa...bbbbbbb" in body
    assert "Review checklist" in body


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

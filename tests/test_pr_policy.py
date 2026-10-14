import pr_policy

NOTHING = {"total_changes": 0, "changes": [], "new_stars": [], "pruned_stubs": []}
STUBS_ONLY = NOTHING | {"total_changes": 3, "new_stars": [{"repo": "o/a"}], "pruned_stubs": ["o/b", "o/c"]}
UPSTREAM = NOTHING | {"total_changes": 1, "changes": [{"repo": "o/r", "reason": "updated"}]}


def test_no_changes_does_nothing():
    assert pr_policy.decide(NOTHING, pr_exists=False) == "none"
    assert pr_policy.decide(NOTHING, pr_exists=True) == "none"


def test_stubs_alone_never_open_a_pr():
    assert pr_policy.decide(STUBS_ONLY, pr_exists=False) == "none"


def test_upstream_change_opens_a_pr_when_none_is_open():
    assert pr_policy.decide(UPSTREAM, pr_exists=False) == "open"


def test_existing_pr_is_updated_and_stubs_ride_along():
    assert pr_policy.decide(UPSTREAM, pr_exists=True) == "update"
    assert pr_policy.decide(STUBS_ONLY, pr_exists=True) == "update"


def test_baselines_flags_and_curated_suggestions_are_decisions():
    for extra in (
        {"baselines": [{"repo": "o/r"}]},
        {"flags": [{"repo": "o/r"}]},
        {"suggestions": [{"repo": "o/r", "curated": True}]},
    ):
        summary = NOTHING | {"total_changes": 1} | extra
        assert pr_policy.decide(summary, pr_exists=False) == "open"


def test_stub_suggestions_alone_do_not_open_a_pr_but_ride_along():
    summary = NOTHING | {"total_changes": 1, "suggestions": [{"repo": "o/r", "curated": False}]}
    assert pr_policy.decide(summary, pr_exists=False) == "none"
    assert pr_policy.decide(summary, pr_exists=True) == "update"


def test_merge_body_keeps_earlier_content_and_appends_dated_update():
    merged = pr_policy.merge_body("## Skills Index Update\n\nfirst\n", "## Skills Index Update\n\nsecond\n", "2026-10-21")
    assert merged.index("first") < merged.index("### Update 2026-10-21") < merged.index("second")
    assert merged.count("## Skills Index Update") == 1

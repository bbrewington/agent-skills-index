import upstream
from conftest import Resp

STATE = {"changelog_sha": "old", "changelog_at": "2026-10-01T00:00:00Z", "known_tags": ["v1"]}


def commit(sha, msg="m", parents=1, date="2026-10-10T00:00:00Z"):
    return {
        "sha": sha,
        "html_url": f"https://github.com/o/r/commit/{sha}",
        "parents": [{}] * parents,
        "commit": {"message": msg, "committer": {"date": date}},
    }


def routes(commits=None, releases=None, tags=None, path_commits=None):
    head = commits if commits is not None else [commit("new", date="2026-10-12T00:00:00Z")]

    def commits_route(params):
        if params and params.get("path"):
            return (path_commits or {}).get(params["path"], [])
        return head

    return {
        "/repos/o/r/commits": commits_route,
        "/repos/o/r/releases": releases or [],
        "/repos/o/r/tags": [{"name": t} for t in (tags if tags is not None else ["v1"])],
    }


def test_first_adoption_is_a_baseline_and_reports_nothing(gh):
    gh(routes(tags=["v1", "v2"]))
    found = upstream.detect("o/r", None, {})
    assert found["kind"] == "baseline"
    assert found["head"]["sha"] == "new"
    assert found["tags"] == ["v1", "v2"]


def test_no_change_returns_none(gh):
    gh(routes(commits=[commit("old")]))
    assert upstream.detect("o/r", None, STATE) == (None)


def test_whole_repo_commits_since_last_seen_skip_merges_and_last_seen(gh):
    gh(routes(commits=[commit("new"), commit("mrg", parents=2), commit("old")]))
    found = upstream.detect("o/r", None, STATE)
    assert found["kind"] == "change"
    assert [c["sha"] for c in found["entry"]["commits"]] == ["new"]
    assert found["entry"]["compare_url"] == "https://github.com/o/r/compare/old...new"


def test_path_scoped_commits_only_count_watched_paths(gh):
    fake = gh(routes(commits=[commit("new")], path_commits={"skills/a": [commit("p1")], "skills/b": []}))
    found = upstream.detect("o/r", ["skills/a", "skills/b"], STATE)
    assert [c["sha"] for c in found["entry"]["commits"]] == ["p1"]
    assert any(p and p.get("path") == "skills/a" for _, p in fake.calls)


def test_head_moved_outside_watched_paths_reports_nothing(gh):
    gh(routes(commits=[commit("new")], path_commits={"skills/a": []}))
    assert upstream.detect("o/r", ["skills/a"], STATE) is None


def test_new_release_and_tag_reported_even_without_commits(gh):
    releases = [
        {"tag_name": "v2", "name": "Two", "html_url": "u2", "published_at": "2026-10-11T00:00:00Z", "draft": False},
        {"tag_name": "v0", "name": "Old", "html_url": "u0", "published_at": "2026-09-01T00:00:00Z", "draft": False},
        {"tag_name": "v3", "name": "Draft", "html_url": "u3", "published_at": "2026-10-11T00:00:00Z", "draft": True},
    ]
    gh(routes(commits=[commit("old")], releases=releases, tags=["v1", "v2"]))
    entry = upstream.detect("o/r", None, STATE)["entry"]
    assert [r["tag"] for r in entry["releases"]] == ["v2"]
    assert entry["tags"] == ["v2"]
    assert entry["commits"] == []


def test_advance_updates_last_seen_fields_only():
    state = {"latest_sha": "keep"}
    upstream.advance(state, {"sha": "n", "date": "d"}, ["v1", "v2"])
    assert state == {"latest_sha": "keep", "changelog_sha": "n", "changelog_at": "d", "known_tags": ["v1", "v2"]}


def test_repo_flags_archived_renamed_and_gone(gh):
    assert upstream.repo_flags("o/r", {"full_name": "o/r", "archived": False}) == []
    assert upstream.repo_flags("o/r", {"full_name": "O/R", "archived": True}) == ["archived"]
    assert upstream.repo_flags("o/r", {"full_name": "new/name"}) == ["renamed:new/name"]
    gh({"/repos/o/r": Resp({}, 404)})
    assert upstream.fetch_repo("o/r") == (None, ["gone"])

import pytest
import requests
import sync_stars


def meta(**overrides):
    base = {
        "pushed_at": "2026-01-01T00:00:00Z",
        "description": "desc",
        "language": "Python",
        "topics": ["a"],
        "license": {"spdx_id": "MIT"},
        "stargazers_count": 5,
    }
    return base | overrides


def test_extract_header_keeps_leading_comments_and_blank_line():
    text = "# a\n# b\n\ntracked: []\n# not header\n"
    assert sync_stars.extract_header(text) == "# a\n# b\n\n"


def test_extract_header_no_header():
    assert sync_stars.extract_header("tracked: []\n") == ""


def test_save_tracked_preserves_header(tmp_path, monkeypatch):
    path = tmp_path / "tracked.yml"
    path.write_text("# header\n\ntracked: []\nstubs: []\n")
    monkeypatch.setattr(sync_stars, "TRACKED_FILE", path)
    sync_stars.save_tracked({"tracked": [], "stubs": [{"repo": "o/r"}]}, dry_run=False)
    text = path.read_text()
    assert text.startswith("# header\n\n")
    assert "o/r" in text


def test_save_tracked_dry_run_does_not_write(tmp_path, monkeypatch):
    path = tmp_path / "tracked.yml"
    path.write_text("tracked: []\nstubs: []\n")
    monkeypatch.setattr(sync_stars, "TRACKED_FILE", path)
    sync_stars.save_tracked({"tracked": [], "stubs": [{"repo": "o/r"}]}, dry_run=True)
    assert "o/r" not in path.read_text()


def test_load_tracked_adds_missing_sections_and_state(tmp_path, monkeypatch):
    path = tmp_path / "tracked.yml"
    path.write_text("stubs:\n- repo: o/r\n")
    monkeypatch.setattr(sync_stars, "TRACKED_FILE", path)
    data = sync_stars.load_tracked()
    assert data["tracked"] == []
    assert data["stubs"][0]["state"] == {}


def test_build_state_handles_missing_license_and_keeps_indexed_at():
    state = sync_stars.build_state(meta(license=None), "abc", {"indexed_at": "old"})
    assert state["license"] is None
    assert state["indexed_at"] == "old"
    assert state["latest_sha"] == "abc"


def test_run_sync_new_updated_unchanged(monkeypatch):
    monkeypatch.setattr(sync_stars, "get_repo_meta", lambda repo: meta())
    shas = {"o/new": "n1", "o/upd": "u2", "o/same": "s1"}
    monkeypatch.setattr(sync_stars, "get_latest_commit_sha", lambda repo, paths=None: shas[repo])
    data = {
        "tracked": [
            {"repo": "o/new", "state": {}},
            {"repo": "o/upd", "state": {"latest_sha": "u1"}},
            {"repo": "o/same", "state": {"latest_sha": "s1"}},
        ],
        "stubs": [],
    }
    changes = sync_stars.run_sync(data, dry_run=False)
    assert [(c["repo"], c["reason"]) for c in changes] == [("o/new", "new"), ("o/upd", "updated")]
    assert data["tracked"][1]["state"]["latest_sha"] == "u2"
    assert data["tracked"][2]["state"] == {"latest_sha": "s1"}


def test_run_sync_skips_repo_on_http_error(monkeypatch):
    def boom(repo):
        raise requests.HTTPError("404")

    monkeypatch.setattr(sync_stars, "get_repo_meta", boom)
    data = {"tracked": [{"repo": "o/gone", "state": {}}], "stubs": []}
    assert sync_stars.run_sync(data, dry_run=False) == []


def test_run_discover_adds_only_unknown_stars(monkeypatch):
    monkeypatch.setattr(
        sync_stars,
        "get_starred_repos",
        lambda user: ([{"full_name": "o/tracked"}, {"full_name": "o/stub"}, {"full_name": "o/fresh"}], True),
    )
    monkeypatch.setattr(sync_stars, "get_repo_meta", lambda repo: meta())
    monkeypatch.setattr(sync_stars, "get_latest_commit_sha", lambda repo, paths=None: "sha")
    data = {"tracked": [{"repo": "o/tracked"}], "stubs": [{"repo": "o/stub"}]}
    new, rate_limited = sync_stars.run_discover(data, dry_run=False)
    assert [n["repo"] for n in new] == ["o/fresh"]
    assert rate_limited is True
    fresh = data["stubs"][-1]
    assert fresh["skill"] is None and fresh["watch_paths"] is None


class FakeResponse:
    def __init__(self, payload, remaining="5000"):
        self._payload = payload
        self.headers = {"X-RateLimit-Remaining": remaining}

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.mark.parametrize("remaining,expected", [("5000", False), ("3", True)])
def test_get_starred_repos_rate_limit_flag(monkeypatch, remaining, expected):
    pages = iter([[{"full_name": "o/a"}], []])
    monkeypatch.setattr(
        sync_stars.requests, "get", lambda *a, **k: FakeResponse(next(pages), remaining)
    )
    repos, rate_limited = sync_stars.get_starred_repos("u")
    assert repos == [{"full_name": "o/a"}]
    assert rate_limited is expected

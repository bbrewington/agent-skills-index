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
    text = "# a\n# b\n\nrepos: []\n# not header\n"
    assert sync_stars.extract_header(text) == "# a\n# b\n\n"


def test_extract_header_no_header():
    assert sync_stars.extract_header("repos: []\n") == ""


def test_save_tracked_preserves_header(tmp_path, monkeypatch):
    path = tmp_path / "tracked.yml"
    path.write_text("# header\n\nrepos: []\n")
    monkeypatch.setattr(sync_stars, "TRACKED_FILE", path)
    sync_stars.save_tracked({"repos": [{"repo": "o/r"}]}, dry_run=False)
    text = path.read_text()
    assert text.startswith("# header\n\n")
    assert "o/r" in text


def test_save_tracked_dry_run_does_not_write(tmp_path, monkeypatch):
    path = tmp_path / "tracked.yml"
    path.write_text("repos: []\n")
    monkeypatch.setattr(sync_stars, "TRACKED_FILE", path)
    sync_stars.save_tracked({"repos": [{"repo": "o/r"}]}, dry_run=True)
    assert "o/r" not in path.read_text()


def test_load_tracked_adds_missing_section_and_state(tmp_path, monkeypatch):
    path = tmp_path / "tracked.yml"
    path.write_text("repos:\n- repo: o/r\n")
    monkeypatch.setattr(sync_stars, "TRACKED_FILE", path)
    data = sync_stars.load_tracked()
    assert data["repos"][0]["state"] == {}
    path.write_text("{}\n")
    assert sync_stars.load_tracked()["repos"] == []


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
        "repos": [
            {"repo": "o/new", "verdict": "adopt", "state": {}},
            {"repo": "o/upd", "verdict": "watch", "state": {"latest_sha": "u1"}},
            {"repo": "o/same", "verdict": "adopt", "state": {"latest_sha": "s1"}},
        ]
    }
    changes = sync_stars.run_sync(data, dry_run=False)
    assert [(c["repo"], c["reason"]) for c in changes] == [("o/new", "new"), ("o/upd", "updated")]
    assert data["repos"][1]["state"]["latest_sha"] == "u2"
    assert data["repos"][2]["state"] == {"latest_sha": "s1"}


def test_run_sync_only_checks_adopt_and_watch(monkeypatch):
    checked = []
    monkeypatch.setattr(sync_stars, "get_repo_meta", lambda repo: checked.append(repo) or meta())
    monkeypatch.setattr(sync_stars, "get_latest_commit_sha", lambda repo, paths=None: "sha")
    data = {
        "repos": [
            {"repo": "o/stub", "verdict": None, "state": {}},
            {"repo": "o/skip", "verdict": "skip", "state": {}},
            {"repo": "o/adopt", "verdict": "adopt", "state": {}},
        ]
    }
    sync_stars.run_sync(data, dry_run=False)
    assert checked == ["o/adopt"]


def test_run_sync_scopes_to_paths_and_never_touches_human_fields(monkeypatch):
    seen = {}
    monkeypatch.setattr(sync_stars, "get_repo_meta", lambda repo: meta())
    monkeypatch.setattr(
        sync_stars, "get_latest_commit_sha", lambda repo, paths=None: seen.setdefault("paths", paths) and "sha"
    )
    entry = {
        "repo": "o/r",
        "verdict": "adopt",
        "use_contexts": ["data-engineering"],
        "notes": "n",
        "skill_or_plugin_paths": ["skills/a"],
        "state": {},
    }
    human = {k: v for k, v in entry.items() if k != "state"}
    sync_stars.run_sync({"repos": [entry]}, dry_run=False)
    assert seen["paths"] == ["skills/a"]
    assert {k: v for k, v in entry.items() if k != "state"} == human


def test_run_sync_skips_repo_on_http_error(monkeypatch):
    def boom(repo):
        raise requests.HTTPError("404")

    monkeypatch.setattr(sync_stars, "get_repo_meta", boom)
    data = {"repos": [{"repo": "o/gone", "verdict": "adopt", "state": {}}]}
    assert sync_stars.run_sync(data, dry_run=False) == []


def test_run_discover_adds_only_unknown_stars(monkeypatch):
    monkeypatch.setattr(
        sync_stars,
        "get_starred_repos",
        lambda user: ([{"full_name": "o/tracked"}, {"full_name": "o/stub"}, {"full_name": "o/fresh"}], True),
    )
    monkeypatch.setattr(sync_stars, "get_repo_meta", lambda repo: meta())
    monkeypatch.setattr(sync_stars, "get_latest_commit_sha", lambda repo, paths=None: "sha")
    data = {"repos": [{"repo": "o/tracked", "verdict": "adopt"}, {"repo": "o/stub", "verdict": None}]}
    new, rate_limited, pruned = sync_stars.run_discover(data, dry_run=False)
    assert [n["repo"] for n in new] == ["o/fresh"]
    assert rate_limited is True
    assert pruned == []
    fresh = data["repos"][-1]
    assert fresh["repo"] == "o/fresh"
    assert fresh["verdict"] is None
    assert fresh["use_contexts"] is None and fresh["notes"] is None and fresh["skill_or_plugin_paths"] is None


def test_run_discover_does_not_resurface_skipped_repos(monkeypatch):
    monkeypatch.setattr(sync_stars, "get_starred_repos", lambda user: ([{"full_name": "o/skipped"}], False))
    data = {"repos": [{"repo": "o/skipped", "verdict": "skip"}]}
    new, _, _ = sync_stars.run_discover(data, dry_run=False)
    assert new == []
    assert len(data["repos"]) == 1


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


def test_prune_stubs_removes_only_stubs_not_in_candidates():
    curated = [{"repo": f"o/{v}", "verdict": v} for v in ("adopt", "watch", "skip")]
    data = {"repos": [*curated, {"repo": "o/keep", "verdict": None}, {"repo": "o/drop", "verdict": None}]}
    removed = sync_stars.prune_stubs(data, [{"full_name": "o/keep"}])
    assert removed == ["o/drop"]
    assert [e["repo"] for e in data["repos"]] == ["o/adopt", "o/watch", "o/skip", "o/keep"]


def test_run_discover_with_list_prunes_and_adds(monkeypatch):
    monkeypatch.setattr(sync_stars, "get_list_repos", lambda user, slug: [{"full_name": "o/new"}, {"full_name": "o/keep"}])
    monkeypatch.setattr(sync_stars, "get_repo_meta", lambda repo: meta())
    monkeypatch.setattr(sync_stars, "get_latest_commit_sha", lambda repo, paths=None: "sha")
    data = {"repos": [{"repo": "o/keep", "verdict": None}, {"repo": "o/drop", "verdict": None}]}
    new, rate_limited, pruned = sync_stars.run_discover(data, dry_run=False, star_list="agent-skills", prune=True)
    assert [n["repo"] for n in new] == ["o/new"]
    assert pruned == ["o/drop"]
    assert rate_limited is False
    assert sorted(e["repo"] for e in data["repos"]) == ["o/keep", "o/new"]


def test_run_discover_without_prune_keeps_out_of_list_stubs(monkeypatch):
    monkeypatch.setattr(sync_stars, "get_list_repos", lambda user, slug: [])
    data = {"repos": [{"repo": "o/other", "verdict": None}]}
    _, _, pruned = sync_stars.run_discover(data, dry_run=False, star_list="agent-skills")
    assert pruned == []
    assert len(data["repos"]) == 1


class FakeGraphQL:
    def __init__(self, payloads):
        self.payloads = iter(payloads)

    def __call__(self, url, headers=None, json=None):
        self.last = json
        return FakeResponse({"data": next(self.payloads)})


def test_get_list_repos_paginates_and_matches_slug(monkeypatch):
    lists = {"user": {"lists": {"nodes": [{"id": "A", "slug": "other"}, {"id": "B", "slug": "agent-skills"}]}}}
    page1 = {"node": {"items": {"nodes": [{"nameWithOwner": "o/a"}, None], "pageInfo": {"hasNextPage": True, "endCursor": "c1"}}}}
    page2 = {"node": {"items": {"nodes": [{"nameWithOwner": "o/b"}], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}
    fake = FakeGraphQL([lists, page1, page2])
    monkeypatch.setattr(sync_stars.requests, "post", fake)
    repos = sync_stars.get_list_repos("u", "agent-skills")
    assert [r["full_name"] for r in repos] == ["o/a", "o/b"]
    assert fake.last["variables"] == {"id": "B", "after": "c1"}


def test_get_list_repos_unknown_slug_raises(monkeypatch):
    lists = {"user": {"lists": {"nodes": [{"id": "A", "slug": "other"}]}}}
    monkeypatch.setattr(sync_stars.requests, "post", FakeGraphQL([lists]))
    with pytest.raises(requests.HTTPError, match="not found"):
        sync_stars.get_list_repos("u", "agent-skills")


def test_fetch_candidates_merges_and_dedupes_multiple_lists(monkeypatch):
    lists = {
        "a": [{"full_name": "o/1"}, {"full_name": "o/2"}],
        "b": [{"full_name": "o/2"}, {"full_name": "o/3"}],
    }
    monkeypatch.setattr(sync_stars, "get_list_repos", lambda user, slug: lists[slug])
    repos, rate_limited = sync_stars.fetch_candidates("a, b")
    assert [r["full_name"] for r in repos] == ["o/1", "o/2", "o/3"]
    assert rate_limited is False


VOCAB = {"data-engineering", "content-creation"}


def test_validate_accepts_known_tags_and_null_fields():
    data = {
        "repos": [
            {"repo": "o/stub", "verdict": None, "use_contexts": None},
            {"repo": "o/ok", "verdict": "adopt", "use_contexts": ["data-engineering"]},
        ]
    }
    sync_stars.validate(data, VOCAB)


def test_validate_rejects_unknown_use_context():
    data = {"repos": [{"repo": "o/r", "verdict": "watch", "use_contexts": ["data-engineering", "made-up"]}]}
    with pytest.raises(sync_stars.ValidationError, match="o/r.*made-up"):
        sync_stars.validate(data, VOCAB)


def test_validate_rejects_unknown_verdict():
    with pytest.raises(sync_stars.ValidationError, match="o/r.*maybe"):
        sync_stars.validate({"repos": [{"repo": "o/r", "verdict": "maybe"}]}, VOCAB)


def test_load_use_contexts_reads_slugs(tmp_path, monkeypatch):
    path = tmp_path / "use-contexts.yml"
    path.write_text("# c\na: first\nb: second\n")
    monkeypatch.setattr(sync_stars, "USE_CONTEXTS_FILE", path)
    assert sync_stars.load_use_contexts() == {"a", "b"}


def test_committed_tracked_yml_is_valid():
    """CI gate: the checked-in tracked.yml only uses verdicts and tags the vocabulary allows."""
    sync_stars.validate(sync_stars.load_tracked(), sync_stars.load_use_contexts())

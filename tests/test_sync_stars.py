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


def gh_commit(sha, date="2026-10-12T00:00:00Z", parents=1):
    return {
        "sha": sha,
        "html_url": f"https://x/{sha}",
        "parents": [{}] * parents,
        "commit": {"message": f"msg {sha}", "committer": {"date": date}},
    }


def repo_routes(repo="o/r", head="new", archived=False, full_name=None, tags=("v1",), commits=None):
    commits = commits if commits is not None else [gh_commit(head)]
    return {
        f"/repos/{repo}": {"full_name": full_name or repo, "archived": archived, **meta()},
        f"/repos/{repo}/commits": commits,
        f"/repos/{repo}/releases": [],
        f"/repos/{repo}/tags": [{"name": t} for t in tags],
    }


SEEN = {"changelog_sha": "old", "changelog_at": "2026-10-01T00:00:00Z", "known_tags": ["v1"]}


def curated(repo="o/r", verdict="adopt", state=None, **extra):
    return {"repo": repo, "verdict": verdict, "state": dict(state or {}), **extra}


def test_first_adoption_records_a_baseline_and_reports_no_changes(gh):
    gh(repo_routes())
    data = {"repos": [curated()]}
    result, pending, _ = sync_stars.run_sync(data, record=True)
    assert result["changes"] == [] and pending == []
    assert result["baselines"] == [{"repo": "o/r", "verdict": "adopt"}]
    assert data["repos"][0]["state"]["changelog_sha"] == "new"


def test_change_is_reported_but_last_seen_waits_for_persist(gh, tmp_path, monkeypatch):
    gh(repo_routes())
    monkeypatch.setattr(sync_stars, "TRACKED_FILE", tmp_path / "tracked.yml")
    monkeypatch.setattr(sync_stars.render, "CHANGELOG_DIR", tmp_path / "changelog")
    monkeypatch.setattr(sync_stars.render, "write_index", lambda data: None)
    data = {"repos": [curated(state=SEEN)]}
    result, pending, _ = sync_stars.run_sync(data, record=True)
    assert [c["new_sha"] for c in result["changes"]] == ["new"]
    assert result["changes"][0]["verdict"] == "adopt"
    assert data["repos"][0]["state"]["changelog_sha"] == "old"  # not advanced yet
    sync_stars.persist(data, result, pending, dry_run=False, today="2026-10-14")
    assert data["repos"][0]["state"]["changelog_sha"] == "new"
    assert "o/r" in (tmp_path / "changelog" / "2026-10.md").read_text()
    assert "o/r" in (tmp_path / "tracked.yml").read_text()


def test_failed_changelog_write_leaves_last_seen_and_tracked_yml_alone(gh, tmp_path, monkeypatch):
    gh(repo_routes())
    tracked = tmp_path / "tracked.yml"
    tracked.write_text("repos: []\n")
    monkeypatch.setattr(sync_stars, "TRACKED_FILE", tracked)

    def boom(*args):
        raise OSError("disk full")

    monkeypatch.setattr(sync_stars.render, "write_changelog", boom)
    data = {"repos": [curated(state=SEEN)]}
    result, pending, _ = sync_stars.run_sync(data, record=True)
    with pytest.raises(OSError):
        sync_stars.persist(data, result, pending, dry_run=False, today="2026-10-14")
    assert data["repos"][0]["state"]["changelog_sha"] == "old"
    assert tracked.read_text() == "repos: []\n"


def test_not_recording_reports_findings_and_advances_nothing(gh):
    data = {"repos": [curated(state=SEEN), curated("o/b", state={})]}
    gh(repo_routes(archived=True) | repo_routes("o/b"))
    result, pending, _ = sync_stars.run_sync(data, record=False)
    assert result["changes"] == result["baselines"] == result["flags"] == [] and pending == []
    assert {u["type"] for u in result["unrecorded"]} == {"flag", "change", "baseline"}
    assert data["repos"][0]["state"] == SEEN
    assert data["repos"][1]["state"] == {}


def test_only_adopt_and_watch_are_synced(gh):
    fake = gh(repo_routes("o/adopt") | repo_routes("o/watch"))
    data = {"repos": [curated("o/stub", None), curated("o/skip", "skip"), curated("o/adopt"), curated("o/watch", "watch")]}
    sync_stars.run_sync(data, record=True)
    touched = {path.split("/")[2] + "/" + path.split("/")[3] for path, _ in fake.calls}
    assert touched == {"o/adopt", "o/watch"}


def test_sync_never_touches_human_fields_and_scopes_commits_to_paths(gh):
    routes = repo_routes(commits=[gh_commit("new")])
    seen_params = []
    routes["/repos/o/r/commits"] = lambda params: seen_params.append(params) or [gh_commit("new")]
    gh(routes)
    entry = curated(state=SEEN, use_contexts=["data-engineering"], notes="n", skill_or_plugin_paths=["skills/a"])
    human = {k: v for k, v in entry.items() if k != "state"}
    sync_stars.run_sync({"repos": [entry]}, record=True)
    assert {k: v for k, v in entry.items() if k != "state"} == human
    assert any(p and p.get("path") == "skills/a" for p in seen_params)


def test_flags_surface_once_and_clear_when_resolved(gh):
    data = {"repos": [curated(state=SEEN)]}
    gh(repo_routes(archived=True, commits=[gh_commit("old")]))
    first, _, _ = sync_stars.run_sync(data, record=True)
    assert first["flags"] == [{"repo": "o/r", "verdict": "adopt", "flags": ["archived"]}]
    assert data["repos"][0]["state"]["flags"] == ["archived"]
    second, _, _ = sync_stars.run_sync(data, record=True)
    assert second["flags"] == []
    gh(repo_routes(commits=[gh_commit("old")]))
    sync_stars.run_sync(data, record=True)
    assert data["repos"][0]["state"]["flags"] == []


def test_renamed_and_gone_repos_are_flagged_and_gone_skips_further_checks(gh):
    gh(repo_routes(full_name="new/name", commits=[gh_commit("old")]))
    data = {"repos": [curated(state=SEEN)]}
    result, _, _ = sync_stars.run_sync(data, record=True)
    assert result["flags"][0]["flags"] == ["renamed:new/name"]
    fake = gh({})  # everything 404s
    result, _, _ = sync_stars.run_sync({"repos": [curated(state={})]}, record=True)
    assert result["flags"][0]["flags"] == ["gone"]
    assert [path for path, _ in fake.calls] == ["/repos/o/r"]


def test_sync_skips_repo_on_http_error(gh):
    from conftest import Resp

    gh({"/repos/o/r": Resp({}, 500)})
    result, pending, _ = sync_stars.run_sync({"repos": [curated()]}, record=True)
    assert result["changes"] == [] and pending == []


def tree_for(*paths):
    return {"/repos/o/r/git/trees/h1": {"truncated": False, "tree": [{"path": p, "type": "blob"} for p in paths]}}


def test_audit_suggests_for_stubs_when_head_moved_and_remembers_it(gh):
    gh({"/repos/o/r/commits": [gh_commit("h1")]} | tree_for("skills/a/SKILL.md"))
    data = {"repos": [curated(verdict=None)]}
    suggestions, unrecorded = sync_stars.run_audit(data, record=True, heads={})
    assert [s["repo"] for s in suggestions] == ["o/r"] and unrecorded == []
    assert suggestions[0]["curated"] is False
    assert suggestions[0]["suggestions"][0]["path"] == "skills/a"
    assert data["repos"][0]["state"]["tree_sha"] == "h1"
    again, _ = sync_stars.run_audit(data, record=True, heads={})
    assert again == []


def test_audit_not_recording_remembers_nothing_and_ignores_skipped(gh):
    gh({"/repos/o/r/commits": [gh_commit("h1")]} | tree_for("skills/a/SKILL.md"))
    data = {"repos": [curated(verdict=None), curated("o/skip", "skip")]}
    suggestions, unrecorded = sync_stars.run_audit(data, record=False, heads={})
    assert suggestions == [] and [u["repo"] for u in unrecorded] == ["o/r"]
    assert "tree_sha" not in data["repos"][0]["state"]


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
    new, rate_limited, pruned = sync_stars.run_discover(data, dry_run=False, star_list="agent-skills")
    assert [n["repo"] for n in new] == ["o/new"]
    assert pruned == ["o/drop"]
    assert rate_limited is False
    assert sorted(e["repo"] for e in data["repos"]) == ["o/keep", "o/new"]


def test_run_discover_prunes_on_every_list_run_but_not_when_the_list_is_empty(monkeypatch):
    monkeypatch.setattr(sync_stars, "get_list_repos", lambda user, slug: [])
    data = {"repos": [{"repo": "o/other", "verdict": None}]}
    _, _, pruned = sync_stars.run_discover(data, dry_run=False, star_list="agent-skills")
    assert pruned == [] and len(data["repos"]) == 1


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

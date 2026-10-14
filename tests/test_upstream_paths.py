import upstream
from conftest import Resp

GOOD_SKILL = "---\nname: my-skill\ndescription: Does a thing.\n---\n# Body\n"


def kinds(paths):
    return {(c["path"], c["kind"], c["format"]) for c in upstream.classify_tree(paths)}


def test_classify_finds_skills_plugins_marketplaces_and_other_agents():
    paths = [
        "skills/a/SKILL.md",
        "tools/p/.claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        "x/.cursor-plugin/plugin.json",
        "y/.codex-plugin/plugin.json",
        ".agents/plugins/marketplace.json",
        "gem/gemini-extension.json",
        "README.md",
        ".mcp.json",
        "agents/helper.md",
    ]
    assert kinds(paths) == {
        ("skills/a", "skill", "agentskills"),
        ("tools/p", "plugin", "claude"),
        (".", "marketplace", "claude"),
        ("x", "plugin", "cursor"),
        ("y", "plugin", "codex"),
        (".", "marketplace", "codex"),
        ("gem", "plugin", "gemini"),
    }


def test_skills_inside_a_plugin_root_are_covered_by_the_plugin():
    paths = ["p/.claude-plugin/plugin.json", "p/skills/s/SKILL.md", "other/SKILL.md"]
    assert {(c["path"], c["kind"]) for c in upstream.classify_tree(paths)} == {("p", "plugin"), ("other", "skill")}


def test_root_skill_has_dot_path():
    assert kinds(["SKILL.md"]) == {(".", "skill", "agentskills")}


def test_covered_handles_exact_nested_root_and_trailing_slash():
    assert upstream.covered("skills/a", ["skills/a"])
    assert upstream.covered("skills/a", ["skills/"])
    assert upstream.covered("skills/a", ["."])
    assert not upstream.covered("skills/ab", ["skills/a"])
    assert not upstream.covered("skills/a", [])


def test_invalid_listed_paths_are_neither_skill_nor_plugin():
    cands = upstream.classify_tree(["skills/a/SKILL.md", "p/.claude-plugin/plugin.json", "p/skills/s/SKILL.md"])
    listed = ["skills/a", "skills", "p/skills/s", "docs/old", "p"]
    assert upstream.invalid_listed(listed, cands) == ["docs/old"]


def test_check_skill_md_accepts_a_compliant_skill():
    assert upstream.check_skill_md("my-skill", GOOD_SKILL) == []


def test_check_skill_md_reports_problems():
    def problems(text, d="my-skill"):
        return " | ".join(upstream.check_skill_md(d, text))

    assert "frontmatter" in problems("# no frontmatter")
    assert "description" in problems("---\nname: my-skill\n---\n")
    assert "name" in problems("---\ndescription: d\n---\n")
    assert "match" in problems(GOOD_SKILL, d="other-dir")
    assert "name" in problems("---\nname: Bad--Name\ndescription: d\n---\n", d="Bad--Name")
    assert "description" in problems("---\nname: my-skill\ndescription: " + "x" * 1025 + "\n---\n")
    assert "metadata" in problems("---\nname: my-skill\ndescription: d\nmetadata: {a: 1}\n---\n")


def test_check_skill_md_root_skill_skips_directory_match():
    assert upstream.check_skill_md(".", GOOD_SKILL) == []


def test_check_plugin_json():
    assert upstream.check_plugin_json('{"name": "p"}') == []
    assert "name" in " ".join(upstream.check_plugin_json("{}"))
    assert "JSON" in " ".join(upstream.check_plugin_json("{nope"))


def test_fetch_tree_returns_blob_paths_and_truncation(gh):
    tree = {"truncated": True, "tree": [{"path": "a/SKILL.md", "type": "blob"}, {"path": "a", "type": "tree"}]}
    gh({"/repos/o/r/git/trees/abc": tree})
    assert upstream.fetch_tree("o/r", "abc") == (["a/SKILL.md"], True)


def test_shallow_paths_fallback_lists_known_directories(gh):
    gh(
        {
            "/repos/o/r/contents/": [{"type": "file", "path": "SKILL.md"}, {"type": "dir", "path": "src"}],
            "/repos/o/r/contents/skills": [{"type": "dir", "path": "skills/a"}, {"type": "dir", "path": "skills/b"}],
            "/repos/o/r/contents/skills/a": [{"type": "file", "path": "skills/a/SKILL.md"}],
            "/repos/o/r/contents/skills/b": [{"type": "file", "path": "skills/b/README.md"}],
        }
    )
    assert upstream.shallow_paths("o/r") == ["SKILL.md", "skills/a/SKILL.md"]


def tree_routes(paths, **extra):
    return {"/repos/o/r/git/trees/head": {"truncated": False, "tree": [{"path": p, "type": "blob"} for p in paths]}} | extra


def text_route(text):
    return Resp(None, 200, text)


def test_audit_suggests_uncovered_paths_with_compliance_for_curated(gh):
    gh(
        tree_routes(
            ["skills/a/SKILL.md", "skills/b/SKILL.md"],
            **{
                "/repos/o/r/contents/skills/b/SKILL.md": text_route("no frontmatter"),
                "/repos/o/r/contents/skills/a/SKILL.md": text_route(GOOD_SKILL.replace("my-skill", "a")),
            },
        )
    )
    result = upstream.audit("o/r", "head", ["skills/a"], check_compliance=True)
    assert [(s["path"], s["compliant"]) for s in result["suggestions"]] == [("skills/b", False)]
    assert result["suggestions"][0]["problems"]
    assert result["invalid_paths"] == []
    assert result["truncated"] is False


def test_audit_skips_compliance_fetches_for_stubs_and_flags_invalid_paths(gh):
    fake = gh(tree_routes(["skills/a/SKILL.md"]))
    result = upstream.audit("o/r", "head", ["docs/old"], check_compliance=False)
    assert result["suggestions"][0]["compliant"] is None
    assert result["invalid_paths"] == ["docs/old"]
    assert not any("contents" in path for path, _ in fake.calls)


def test_audit_truncated_uses_shallow_listing_and_does_not_validate_listed_paths(gh):
    routes = {
        "/repos/o/r/git/trees/head": {"truncated": True, "tree": []},
        "/repos/o/r/contents/": [{"type": "file", "path": "SKILL.md"}],
    }
    gh(routes)
    result = upstream.audit("o/r", "head", ["docs/old"], check_compliance=False)
    assert result["truncated"] is True
    assert [s["path"] for s in result["suggestions"]] == ["."]
    assert result["invalid_paths"] == []

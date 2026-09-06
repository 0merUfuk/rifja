"""Independent public-CLI checks for equal wording in distinct worktree scopes."""

import json
import re

import pytest
from test_cli import Console

ACTION = "NEXT: Inspect the copper ledger boundary before accepting this worktree."


@pytest.fixture(scope="module")
def worktree_briefing(tmp_path_factory):
    cli = Console(tmp_path_factory.mktemp("scoped-briefing"))
    cli.data("setup", "--timezone", "UTC")
    main = cli.repo("Copper main")
    topic = cli.root / "Copper topic"
    cli.git(main, "worktree", "add", "-q", "-b", "topic", str(topic))
    document = "# Local acceptance\n\n## Pending\n\n" + ACTION + "\n"
    (main / "STATUS.md").write_text(document)
    (main / "REPEATED.md").write_text(document)
    (topic / "STATUS.md").write_text(document)
    registered = cli.data("project", "add", str(main), "--name", "copper")
    trees = {tree["path"]: tree["id"] for tree in registered["worktrees"]}
    for path in (main, topic):
        cli.data("document", "add", "copper", "--worktree", str(path), "--include", "*.md")
    cli.data("refresh")
    resume = cli.data("resume", "copper")
    selected = {
        name: cli.data("resume", "copper", "--worktree", str(path))
        for name, path in (("main", main), ("topic", topic))
    }
    exported = json.loads(cli.run("export", "copper", "--format", "json", json_output=False).stdout)
    markdown = cli.run("export", "copper", "--format", "markdown", json_output=False).stdout
    markdown = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|])", r"\1", markdown)
    return {
        "resume": resume,
        "selected": selected,
        "exported": exported,
        "markdown": markdown,
        "paths": {"main": str(main), "topic": str(topic)},
        "trees": trees,
    }


def matching(entries):
    return [entry for entry in entries if entry.get("text") == ACTION]


def assert_scoped_pending(entries, expected_paths, trees):
    assert len(entries) == len(expected_paths), "Distinct worktrees are independent pending work"
    assert {entry["worktree_id"] for entry in entries} == {trees[path] for path in expected_paths}
    for entry in entries:
        assert entry["category"] == "documented_pending"
        assert entry["status"] == "pending"
        assert entry["evidence"]["status"] == "current"
        locations = entry["evidence"]["locations"]
        assert locations
        assert any(
            location["path"].rsplit("/", 1)[0] == path and entry["worktree_id"] == trees[path]
            for path in expected_paths
            for location in locations
        )


def test_project_resume_preserves_both_scopes_and_same_tree_dedup(worktree_briefing):
    data = worktree_briefing
    paths = set(data["paths"].values())
    for entries in (data["resume"]["continuity"]["pending"], data["resume"]["next_actions"]):
        assert_scoped_pending(matching(entries), paths, data["trees"])


def test_json_pending_binds_each_worktree_without_duplicate_inflation(worktree_briefing):
    data = worktree_briefing
    exported = data["exported"]
    entries = matching(exported["context"])
    assert len(entries) == 2
    expected = set(data["trees"].values())
    observed = set()
    for entry in entries:
        assert (entry["kind"], entry["category"], entry["status"]) == (
            "pending",
            "documented_pending",
            "pending",
        )
        evidence = entry["evidence"]
        assert evidence["status"] == "current"
        assert evidence["line_start"] == evidence["line_end"] == 5
        observation = exported.get("document_observations", {}).get(
            evidence.get("observation_ref"), evidence
        )
        observed.add(observation.get("worktree_id", entry.get("worktree_id")))
    assert observed == expected


def test_markdown_pending_explains_both_scopes_without_opaque_id_lookup(worktree_briefing):
    data = worktree_briefing
    lines = [line for line in data["markdown"].splitlines() if ACTION in line]
    assert len(lines) == 2
    assert all("[documented_pending; pending]" in line for line in lines)
    # A reader must be able to bind each identical action to its worktree using
    # the Markdown alone. A pair of opaque record references is insufficient.
    for path in data["paths"].values():
        assert any(path in line for line in lines), "Each equal-worded action needs visible scope"


@pytest.mark.parametrize("name", ["main", "topic"])
def test_worktree_filter_isolates_its_pending_action(worktree_briefing, name):
    data = worktree_briefing
    selected = data["selected"][name]
    for entries in (selected["continuity"]["pending"], selected["next_actions"]):
        assert_scoped_pending(matching(entries), {data["paths"][name]}, data["trees"])

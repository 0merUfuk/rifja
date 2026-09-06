"""Public-CLI regressions for documented actions with ordering conditions.

These invented fixtures were sealed after a benchmark exposed a category loss.
They contain no private project evidence or expected answers for the runtime.
"""

import json
import re

import pytest
from test_cli import Console


def observed_documents(tmp_path, document):
    cli = Console(tmp_path)
    cli.data("setup", "--timezone", "UTC")
    repo = cli.repo("Conditional notebook")
    (repo / "README.md").write_text("# Grove Ledger\n\nA local build catalogue.\n")
    (repo / "STATUS.md").write_text(document)
    cli.data("project", "add", str(repo), "--name", "grove")
    cli.data("document", "add", "grove", "--include", "*.md")
    cli.data("refresh")
    resume = cli.data("resume", "grove")
    markdown = cli.run(
        "export", "grove", "--format", "markdown", "--max-chars", "8000", json_output=False
    ).stdout
    exported = json.loads(
        cli.run(
            "export", "grove", "--format", "json", "--max-chars", "8000", json_output=False
        ).stdout
    )
    return resume, re.sub(r"\\([\\`*_{}\[\]()#+\-.!|])", r"\1", markdown), exported


@pytest.mark.parametrize(
    ("document", "meaning"),
    [
        pytest.param(
            "# Checks\n\n## Pending\n\n"
            "NEXT: Inspect the cobalt archive manifest before approving this fixture.\n",
            "Inspect the cobalt archive manifest before approving this fixture.",
            id="next-before",
        ),
        pytest.param(
            "# Checks\n\n## Work remaining\n\n"
            "TASK: Compare the ember replay ledger after the local capture is available.\n",
            "Compare the ember replay ledger after the local capture is available.",
            id="task-after",
        ),
        pytest.param(
            "# Checks\n\n## Next steps\n\n"
            "Inspect the linen cache boundary before accepting the handoff.\n",
            "Inspect the linen cache boundary before accepting the handoff.",
            id="ordinary-under-next-steps",
        ),
        pytest.param(
            "# Checks\n\n## Pending\n\n"
            "TASK: Verify artifact signatures on Windows before approval.\n",
            "Verify artifact signatures on Windows before approval.",
            id="task-platform-scope",
        ),
        pytest.param(
            "# Checks\n\n## Pending\n\nGÖREV: Yayından önce imzayı doğrula.\n",
            "Yayından önce imzayı doğrula.",
            id="turkish-task-before",
        ),
        pytest.param(
            "# Checks\n\n## Pending\n\nSONRAKİ: Dağıtımdan önce imzayı doğrula.\n",
            "Dağıtımdan önce imzayı doğrula.",
            id="turkish-next-before",
        ),
    ],
)
def test_document_action_keeps_pending_category_and_ordering(tmp_path, document, meaning):
    resume, markdown, exported = observed_documents(tmp_path, document)
    actions = [item for item in resume["next_actions"] if meaning in item["text"]]
    assert actions, "The documented action must remain a supported next step"
    assert all(item["category"] == "documented_pending" for item in actions)
    assert all(item["status"] == "pending" for item in actions)
    assert all(item["evidence"]["relative_path"] == "STATUS.md" for item in actions)
    assert all(item["worktree_id"] for item in actions)

    pending = [
        item
        for item in exported["context"]
        if item["kind"] == "pending" and meaning in item["text"]
    ]
    assert pending, "An ordering condition must not replace the pending action category"
    assert all(item["category"] == "documented_pending" for item in pending)
    assert all(item["status"] == "pending" for item in pending)
    assert all(item["evidence"]["relative_path"] == "STATUS.md" for item in pending)
    assert meaning in markdown
    assert "[documented_pending; pending]" in markdown


@pytest.mark.parametrize(
    ("document", "constraint"),
    [
        pytest.param(
            "# Notes\n\n## Examples\n\nNEXT: Inspect the sample archive before accepting it.\n",
            None,
            id="example-section",
        ),
        pytest.param(
            "# Notes\n\n## Pending\n\n```text\n"
            "NEXT: Inspect the quoted archive before approving it.\n```\n",
            None,
            id="fenced-marker",
        ),
        pytest.param(
            "# Notes\n\n> NEXT: Inspect the narrated archive before approving it.\n",
            None,
            id="quoted-marker",
        ),
        pytest.param(
            "# Notes\n\n## Historical record\n\n"
            "TASK: Inspect the basalt inventory before signing was completed earlier "
            "at revision e82.\n",
            None,
            id="historical-marker",
        ),
        pytest.param(
            "# Notes\n\n## Deferred\n\nNEXT: Add cobalt synchronization after version two.\n",
            None,
            id="deferred-marker",
        ),
        pytest.param(
            "# Notes\n\n## Constraints\n\n"
            "Do not publish the artifact before explicit owner approval.\n",
            "Do not publish the artifact before explicit owner approval.",
            id="pure-prohibition",
        ),
        pytest.param(
            "# Notes\n\n## Pending\n\n"
            "Only after the synthetic dependency is available may acceptance proceed. "
            "The comparison must use this registered worktree.\n",
            "Only after the synthetic dependency is available may acceptance proceed.",
            id="conditions-under-pending",
        ),
        pytest.param(
            "# Notes\n\n## Pending\n\n"
            "NEXT: Do not run package verification. Publication is not authorized.\n",
            "Do not run package verification. Publication is not authorized.",
            id="marked-mixed-prohibition",
        ),
        pytest.param(
            "# Notes\n\n## Pending\n\n"
            "TASK: Publication is not authorized without owner approval.\n",
            "Publication is not authorized without owner approval.",
            id="marked-nominal-policy",
        ),
        pytest.param(
            "# Notes\n\n## Pending\n\nNEXT: Earlier smoke checks passed.\n",
            None,
            id="marked-historical-result",
        ),
        pytest.param(
            "# Notes\n\n## Pending\n\nNEXT: Only after owner approval may publication proceed.\n",
            "Only after owner approval may publication proceed.",
            id="marked-modal-condition",
        ),
        pytest.param(
            "# Notes\n\n## Pending\n\nGÖREV: Yayından önce imzayı doğrulama.\n",
            None,
            id="turkish-negative-imperative",
        ),
    ],
)
def test_nonaction_document_scope_stays_inert(tmp_path, document, constraint):
    resume, markdown, exported = observed_documents(tmp_path, document)
    assert resume["next_actions"] == []
    assert resume["continuity"]["pending"] == []
    assert not any(item["kind"] == "pending" for item in exported["context"])
    assert not any(
        item.get("kind") in {"task", "next_action"}
        and item.get("status") in {"active", "pending", "blocked"}
        for item in exported["items"]
    )
    assert not any(
        item.get("status") == "verified" for item in exported["context"] + exported["items"]
    )
    if constraint:
        assert any(
            constraint in item["text"] and item["category"] == "documented_constraint"
            for item in resume["continuity"]["constraints"]
        )
        assert any(
            constraint in item["text"] and item["category"] == "documented_constraint"
            for item in exported["context"]
        )
        assert constraint in markdown

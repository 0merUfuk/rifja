"""Independent regressions for the bounded continuity semantic repair."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from session_visualizer import documents
from session_visualizer.adapters import normalize
from session_visualizer.app import App
from session_visualizer.briefing import build_brief
from session_visualizer.extract import extract
from session_visualizer.ingest import Ingestor
from session_visualizer.models import Record
from session_visualizer.render import bounded_export, resume_markdown
from session_visualizer.store import Store, restore


def candidates(text: str, actor: str = "document") -> list[dict]:
    record = Record(
        "project_document" if actor == "document" else "codex",
        "synthetic",
        "record",
        actor,
        "document_section" if actor == "document" else "user_intent",
        text,
        metadata={"relative_path": "STATUS.md", "section": "Current status", "line_start": 3},
    )
    return [asdict(candidate) for candidate in extract(record)]


@pytest.mark.parametrize("actor", ["document", "user"])
@pytest.mark.parametrize(
    "text",
    [
        "No pending checks remain.",
        "Browser validation is no longer pending.",
        "All previously pending checks passed.",
    ],
)
def test_negated_or_resolved_pending_does_not_become_current_work(text: str, actor: str):
    assert not any(c["status"] in {"active", "pending", "blocked"} for c in candidates(text, actor))


def test_native_tool_proposal_code_with_pending_is_context_not_active_work():
    code = 'const pending = ["Task: pending browser validation"]; text(pending);'
    context: dict = {}
    normalize(
        "codex",
        {"type": "session_meta", "payload": {"id": "proposal-session", "cwd": "/example/repo"}},
        context,
        "line:1",
    )
    parsed = normalize(
        "codex",
        {
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "id": "proposal",
                "name": "exec",
                "call_id": "proposal-call",
                "input": code,
            },
        },
        context,
        "line:2",
    )
    assert not parsed.diagnostics
    assert len(parsed.records) == 1
    record = parsed.records[0]
    assert (record.actor, record.kind, record.metadata["tool"]) == (
        "assistant",
        "agent_proposal",
        "exec",
    )
    assert record.text == code
    extracted = extract(record)
    assert [(item.kind, item.status, item.category, item.text) for item in extracted] == [
        ("context", "proposed", "agent_proposal", code)
    ]


def test_user_negated_completion_is_not_a_completion_correction():
    values = candidates("Browser validation is not completed.", "user")
    assert not any(c["status"] == "user_completed" for c in values)
    assert any(c["status"] in {"active", "pending", "blocked"} for c in values)


@pytest.mark.parametrize("actor", ["document", "user"])
def test_conditional_failure_policy_is_not_an_observed_blocker(actor: str):
    values = candidates("If browser validation fails, the release must be blocked.", actor)
    assert not any(c["kind"] == "blocker" and c["status"] == "blocked" for c in values)


def test_different_conditions_with_shared_subject_all_survive_the_brief():
    texts = [
        "Browser validation remains pending.",
        "Browser validation requires a continuous 20 minute observation window.",
        "Browser validation requires launch within 45 seconds.",
        "Browser validation requires the application to remain active throughout the observation window.",
    ]
    items = []
    for index, text in enumerate(texts):
        for number, candidate in enumerate(candidates(text)):
            items.append(
                {
                    **candidate,
                    "id": f"item-{index}-{number}",
                    "record_id": f"record-{index}",
                    "source_current": True,
                    "worktree_id": "tree",
                }
            )
    brief = build_brief(items, lambda ref: {"status": "current"}, {}, "project", "tree")
    kept = "\n".join(entry["text"] for entry in brief["constraints"])
    assert all(text in kept for text in texts[1:])


def test_soft_wrapped_condition_retains_its_complete_qualification():
    text = (
        "Browser validation remains pending and requires\n"
        "a continuous 20 minute observation window\n"
        "with the application kept running from start to finish."
    )
    extracted = " ".join(c["text"] for c in candidates(text))
    assert "application kept running from start to finish" in extracted


@pytest.fixture
def fixture(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "-C", str(root), "init", "-q", "-b", "main"], check=True)
    (root / "README.md").write_text("# Sample\n\nA viewer for synthetic events.\n")
    (root / "STATUS.md").write_text(
        "# Current status\n\nBrowser validation is pending.\n\n"
        "Browser validation requires a continuous 20 minute observation window.\n\n"
        "Browser validation requires launch within 45 seconds.\n"
    )
    with Store(tmp_path / "state") as store:
        app = App(store)
        app.setup()
        registered = app.register(root)
        project = registered["project"]["id"]
        worktree = registered["worktrees"][0]["id"]
        documents.configure(store, project, worktree, patterns=["README.md", "STATUS.md"])
        Ingestor(store).refresh()
        yield root, store, app, project, worktree


def test_small_history_limit_keeps_conditions_or_discloses_critical_context_omission(fixture):
    _, _, app, project, _ = fixture
    result = app.resume(project, observe=False, limit=1)
    markdown = resume_markdown(result)
    assert "45 seconds" in markdown
    output = json.loads(bounded_export(result, "json", max_chars=5000))
    assert "45 seconds" in json.dumps(output["context"]) or output["omissions"]["context"] > 0


def test_unique_later_user_cancellation_overrides_documented_pending(fixture, tmp_path):
    root, store, app, project, _ = fixture
    source = tmp_path / "session.jsonl"
    source.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {
                    "type": "session_meta",
                    "timestamp": "2099-01-01T00:00:00Z",
                    "payload": {"id": "user-correction", "cwd": str(root)},
                },
                {
                    "type": "response_item",
                    "timestamp": "2099-01-01T00:00:01Z",
                    "payload": {
                        "type": "message",
                        "id": "cancel-browser",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Browser validation is cancelled."}
                        ],
                    },
                },
            ]
        )
        + "\n"
    )
    app.source_add("codex", source)
    Ingestor(store).refresh()
    result = app.resume(project, observe=False, limit=50)
    assert any(i["category"] == "user_correction" for i in result["items"]["items"])
    assert not result["continuity"]["pending"]
    assert not any(a["category"] == "documented_pending" for a in result["next_actions"])


def test_direct_authoritative_correction_remains_effective(fixture):
    _, _, app, project, _ = fixture
    result = app.resume(project, observe=False, limit=50)
    pending = next(i for i in result["items"]["items"] if i["category"] == "documented_pending")
    app.correct(pending["id"], "cancelled", None, "Explicit user correction")
    assert not app.resume(project, observe=False)["continuity"]["pending"]


def test_mixed_user_status_sentences_keep_their_individual_resolution():
    values = candidates("Cancel browser validation. Package verification completed.", "user")
    corrections = [c for c in values if c["kind"] == "correction"]
    assert len(corrections) == 2
    assert corrections[0]["status"] == "cancelled"
    assert corrections[1]["status"] == "user_completed"


def test_two_different_targets_in_one_record_are_still_ambiguous(fixture, tmp_path):
    root, store, app, project, _ = fixture
    source = tmp_path / "ambiguous.jsonl"
    payloads = [
        {
            "type": "session_meta",
            "timestamp": "2099-01-01T00:00:00Z",
            "payload": {"id": "same-record", "cwd": str(root)},
        }
    ]
    for second, native, text in [
        (1, "two-targets", "Task: Verify package signature.\nTask: Verify archive signature."),
        (2, "ambiguous-cancel", "Cancel signature verification."),
    ]:
        payloads.append(
            {
                "type": "response_item",
                "timestamp": f"2099-01-01T00:00:0{second}Z",
                "payload": {
                    "type": "message",
                    "id": native,
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        )
    source.write_text("".join(json.dumps(row) + "\n" for row in payloads))
    app.source_add("codex", source)
    Ingestor(store).refresh()
    items = app.items(project, limit=None)["items"]
    tasks = [i for i in items if i["native_id"] == "two-targets"]
    assert len(tasks) == 2
    assert all(i["status"] == "active" for i in tasks)
    correction = next(i for i in items if i["native_id"] == "ambiguous-cancel")
    assert correction.get("resolution_uncertainty")


def test_readme_current_status_paragraph_is_not_project_purpose():
    record = Record(
        "project_document",
        "synthetic",
        "status",
        "document",
        "document_section",
        "Release validation remains pending until both visual checkpoints have been reviewed independently.",
        metadata={"relative_path": "README.md", "section": "Current status", "line_start": 8},
    )
    assert not any(candidate.kind == "purpose" for candidate in extract(record))


@pytest.mark.parametrize(
    "failure,expected_availability",
    [
        ("missing", "source_unavailable_last_known_pending"),
        ("oversized", "source_partial_last_known_pending"),
    ],
)
def test_unavailable_document_keeps_pending_with_explicit_source_availability(
    fixture, failure: str, expected_availability: str
):
    root, store, app, project, _ = fixture
    before = app.resume(project, observe=False, limit=1)
    record_id = before["continuity"]["pending"][0]["record_id"]
    if failure == "missing":
        (root / "STATUS.md").unlink()
    else:
        (root / "STATUS.md").write_text("x" * 131073)
    refresh = Ingestor(store).refresh()
    assert refresh["status"] == "partial"
    result = app.resume(project, observe=False, limit=1)
    action = next(a for a in result["next_actions"] if a["record_id"] == record_id)
    assert action["status"] == "pending"
    assert action["availability"] == expected_availability
    assert expected_availability in resume_markdown(result)


@pytest.mark.parametrize(
    "corruption,expected_diagnostic",
    [
        ("array", "document_source_context_invalid"),
        ("other_worktree", "document_source_identity_conflict"),
    ],
)
def test_restored_bad_document_context_is_isolated_without_project_reassignment(
    fixture, tmp_path: Path, corruption: str, expected_diagnostic: str
):
    root, store, app, project, worktree = fixture
    other_root = tmp_path / "healthy-repo"
    other_root.mkdir()
    subprocess.run(["git", "-C", str(other_root), "init", "-q", "-b", "main"], check=True)
    (other_root / "STATUS.md").write_text("# Current status\n\nPackage validation is pending.\n")
    registered = app.register(other_root)
    other_project = registered["project"]["id"]
    other_worktree = registered["worktrees"][0]["id"]
    documents.configure(store, other_project, other_worktree, patterns=["STATUS.md"])
    Ingestor(store).refresh()
    corrupted_source = store.rows(
        "SELECT id,context FROM sources WHERE provider='project_document' AND path=?",
        (str(root / "STATUS.md"),),
    )[0]
    affected = store.rows(
        "SELECT DISTINCT r.id,r.project_id,r.worktree_id FROM records r "
        "JOIN occurrences o ON o.record_id=r.id JOIN generations g ON g.id=o.generation_id "
        "WHERE g.source_id=? ORDER BY r.id",
        (corrupted_source["id"],),
    )
    assert affected and all(
        row["project_id"] == project and row["worktree_id"] == worktree for row in affected
    )
    backup = tmp_path / "review-backup.sqlite3"
    store.backup(backup)
    if corruption == "array":
        corrupted_context: object = []
    else:
        corrupted_context = {
            **json.loads(corrupted_source["context"]),
            "worktree_id": other_worktree,
        }
    with sqlite3.connect(backup) as connection:
        connection.execute(
            "UPDATE sources SET context=? WHERE id=?",
            (json.dumps(corrupted_context), corrupted_source["id"]),
        )
    (other_root / "STATUS.md").write_text(
        "# Current status\n\nIndependent package verification remains unfinished.\n"
    )
    restored_home = tmp_path / "restored-review-state"
    assert restore(backup, restored_home)["restored"]
    with Store(restored_home) as restored:
        refresh = Ingestor(restored).refresh(verify=True)
        assert refresh["status"] == "partial"
        assert refresh["failed"] == 0
        assert expected_diagnostic in {d["code"] for d in refresh["diagnostics"]}
        assert (
            restored.rows(
                "SELECT DISTINCT r.id,r.project_id,r.worktree_id FROM records r "
                "JOIN occurrences o ON o.record_id=r.id JOIN generations g ON g.id=o.generation_id "
                "WHERE g.source_id=? ORDER BY r.id",
                (corrupted_source["id"],),
            )
            == affected
        )
        healthy = restored.rows(
            "SELECT project_id,worktree_id FROM records WHERE text LIKE ?",
            ("%Independent package verification remains unfinished.%",),
        )
        assert healthy
        assert all(
            row["project_id"] == other_project and row["worktree_id"] == other_worktree
            for row in healthy
        )

"""Acceptance failures found outside the original release corpus."""

import json
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from test_cli import Console

from rifja import ingest
from rifja.app import App
from rifja.ingest import Ingestor
from rifja.privacy import clean_text
from rifja.store import Store


def event(text, number=0, actor="user", day="2026-09-05"):
    stamp = datetime.fromisoformat(day + "T09:00:00+00:00") + timedelta(seconds=number)
    return {
        "type": "response_item",
        "timestamp": stamp.isoformat(),
        "payload": {
            "type": "message",
            "id": f"message-{number}",
            "role": actor,
            "content": [{"type": "input_text", "text": text}],
        },
    }


@pytest.fixture
def cli(tmp_path):
    console = Console(tmp_path)
    console.env.update(
        GIT_AUTHOR_DATE="2026-09-05T10:00:00Z", GIT_COMMITTER_DATE="2026-09-05T10:00:00Z"
    )
    console.data("setup", "--timezone", "UTC")
    console.project_path = console.repo()
    console.data("project", "add", str(console.project_path), "--name", "acceptance")
    return console


def seed(cli, events):
    path = cli.source_dir / "acceptance.jsonl"
    records = [
        {
            "type": "session_meta",
            "timestamp": "2026-09-05T08:00:00Z",
            "payload": {"id": "acceptance-session", "cwd": str(cli.project_path)},
        },
        *events,
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    cli.data("source", "add", "codex", str(path))
    cli.data("refresh")
    return path


def test_objective_outlives_recent_record_window_and_respects_correction(cli):
    seed(
        cli,
        [event("GOAL: Recover the interrupted import.")]
        + [event("Ordinary progress note.", i, "assistant") for i in range(1, 71)],
    )
    for limit in (1, 1000):
        assert cli.data("resume", "acceptance", "--limit", str(limit))["objective"]["text"] == (
            "Recover the interrupted import."
        )
    objective = next(
        i for i in cli.data("items", "--project", "acceptance")["items"] if i["kind"] == "objective"
    )
    cli.data(
        "memory", "correct", objective["id"], "--status", "cancelled", "--reason", "Scope ended"
    )
    assert cli.data("resume", "acceptance")["objective"] is None


def test_append_preserves_unresolved_gap_but_repair_clears_it(cli):
    path = seed(cli, [event("NEXT: Inspect provider coverage.")])
    valid = path.read_text()
    path.write_text(valid + "{broken complete record}\n")
    assert cli.data("refresh", code=3)["status"] == "partial"
    with path.open("a") as output:
        output.write(json.dumps(event("Ordinary progress note.", 1, "assistant")) + "\n")
    assert cli.data("refresh", code=3)["status"] == "partial"
    coverage = cli.data("source", "list")["coverage"]
    assert coverage["sources"][0]["diagnostics"][0]["code"] == "malformed_record"
    assert cli.data("refresh", "--rebuild", code=3)["status"] == "partial"
    path.write_text(valid)
    assert cli.data("refresh")["status"] == "passed"


def test_daily_includes_git_observations_without_transcripts(cli):
    cli.data("refresh")
    daily = cli.data("daily", "2026-09-05", "--project", "acceptance")
    assert len(daily["projects"]) == 1
    assert daily["projects"][0]["records"] == 0
    assert daily["projects"][0]["observed_changes"][0]["revision"] == cli.git(
        cli.project_path, "rev-parse", "HEAD"
    )
    assert not cli.data("daily", "2026-09-04")["projects"]


def test_historical_activity_not_displaced_by_later_claims(cli):
    seed(
        cli,
        [event("BLOCKER: Critical: The migration snapshot is missing.")]
        + [event("Completed later check.", i, "assistant", "2026-09-06") for i in range(1, 1002)],
    )
    daily = cli.data("daily", "2026-09-05", "--project", "acceptance")
    assert (
        daily["projects"][0]["activity"][0]["text"]
        == "Critical: The migration snapshot is missing."
    )
    next_day = cli.data("daily", "2026-09-06", "--project", "acceptance", "--limit", "1000")
    assert next_day["projects"][0]["omissions"]["activity"] == 1
    assert (
        "Omitted: 1 activity"
        in cli.run("daily", "2026-09-06", "--limit", "1000", json_output=False).stdout
    )


def test_handoff_preserves_action_constraints_and_decision_rationale(cli):
    seed(
        cli,
        [
            event(
                "NEXT: Rehearse the migration | DEPENDS_ON: snapshot-ready | PRIORITY: critical\n"
                "DECISION: Use SQLite | RATIONALE: Local recovery matters."
            )
        ],
    )
    for format in ("json", "markdown"):
        exported = cli.run("export", "acceptance", "--format", format, json_output=False).stdout
        assert "snapshot-ready" in exported
        assert "Local recovery matters." in exported
        assert "critical" in exported
    readable = cli.run("resume", "acceptance", json_output=False).stdout
    assert "snapshot-ready" in readable and "Local recovery matters." in readable


def test_long_message_intent_and_suffix_edits_keep_distinct_provenance(cli):
    text = "Background information only.\n" * 200
    path = seed(cli, [event(text + "NEXT: Obtain the rollback snapshot.")])
    first = cli.data("resume", "acceptance")["next_actions"][0]
    assert first["text"] == "Obtain the rollback snapshot."
    contents = path.read_text().replace(
        "Obtain the rollback snapshot.", "Inspect the restored snapshot."
    )
    path.write_text(contents)
    cli.data("refresh")
    actions = cli.data("resume", "acceptance")["next_actions"]
    assert len(actions) == 1 and actions[0]["text"] == "Inspect the restored snapshot."
    assert actions[0]["record_id"] != first["record_id"]
    assert cli.data("explain", first["record_id"])["status"] == "missing_or_superseded"


def test_extreme_item_count_has_bounded_explicit_partial_coverage(cli):
    path = seed(cli, [event("NEXT: Keep the ordinary action.")])
    with path.open("a") as output:
        output.write(
            json.dumps(event("\n".join(f"NEXT: action-{i}" for i in range(300)), 1)) + "\n"
        )
    assert cli.data("refresh", code=3)["status"] == "partial"
    data = cli.data("source", "list")
    assert any(
        d["code"] == "record_extraction_limit"
        for s in data["coverage"]["sources"]
        for d in s["diagnostics"]
    )
    assert [a["text"] for a in cli.data("resume", "acceptance")["next_actions"]] == [
        "Keep the ordinary action."
    ]


def test_long_record_upgrade_preserves_existing_corrections_and_memory(cli, monkeypatch):
    path = cli.source_dir / "upgrade.jsonl"
    message = (
        "GOAL: Retain continuity.\nTASK: Repair the parser.\n"
        + "Background.\n" * 500
        + "NEXT: Obtain the new sample."
    )
    path.write_text(
        json.dumps(
            {
                "type": "user",
                "uuid": "upgrade-record",
                "sessionId": "upgrade-session",
                "timestamp": "2026-09-05T00:00:00Z",
                "cwd": str(cli.project_path),
                "message": {"role": "user", "content": message},
            }
        )
        + "\n"
    )
    with Store(cli.state) as store:
        app = App(store)
        app.source_add("claude", path)
        original_record, original_extract = Ingestor.record, ingest.extract
        with monkeypatch.context() as patch:
            patch.setattr(
                Ingestor,
                "record",
                lambda self, raw, generation, locator, migrate_legacy=False: original_record(
                    self, replace(raw, text=clean_text(raw.text)), generation, locator
                ),
            )
            patch.setattr(
                ingest,
                "extract",
                lambda record: [c for c in original_extract(record) if c.kind != "objective"],
            )
            Ingestor(store).refresh()
        task = next(i for i in app.items("acceptance")["items"] if i["kind"] == "task")
        app.correct(task["id"], "cancelled", None, "The old repair was cancelled.")
        principle = app.memory_add(
            "principle", "Preserve recovery evidence.", refs=[task["record_id"]]
        )
        store.set_config("pipeline_version", "0.1.0rc1:explicit-v1:redaction-v1")
        assert Ingestor(store).refresh(rebuild=True)["status"] == "passed"
        resume = app.resume("acceptance")
        assert resume["objective"]["text"] == "Retain continuity."
        assert [a["text"] for a in resume["next_actions"]] == ["Obtain the new sample."]
        assert resume["principles"][0]["id"] == principle["id"]
        assert any(
            i["text"] == "Repair the parser." and i["status"] == "cancelled" and i["source_current"]
            for i in app.items("acceptance")["items"]
        )

"""Independent local review reproducers. Every path and payload is synthetic."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from session_visualizer.app import App
from session_visualizer.ingest import Ingestor
from session_visualizer.models import GitSnapshot
from session_visualizer.store import Store, restore


def test_hermes_executable_view_cannot_hold_refresh_without_a_bound(tmp_path: Path) -> None:
    """A real reader must reject/interrupt SQL programs masquerading as producer tables.

    The child timeout is a test harness safety boundary, not the product control.
    The scalar recursive sum uses constant memory and never yields a result.
    """
    database = tmp_path / "hostile-producer.sqlite3"
    with sqlite3.connect(database) as producer:
        producer.executescript("""
            CREATE TABLE sessions(id TEXT PRIMARY KEY, started_at REAL);
            INSERT INTO sessions VALUES('synthetic-session', 1735819200);
            CREATE VIEW messages AS SELECT
                (WITH RECURSIVE runaway(n) AS
                    (VALUES(1) UNION ALL SELECT n + 1 FROM runaway)
                 SELECT sum(n) FROM runaway) AS id,
                'synthetic-session' AS session_id,
                'user' AS role,
                'Task: synthetic view content' AS content,
                1735819200 AS timestamp;
        """)
    import session_visualizer

    package_parent = str(Path(session_visualizer.__file__).resolve().parent.parent)
    user_home = tmp_path / "synthetic-home"
    user_home.mkdir()
    child = """
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from session_visualizer.app import App
from session_visualizer.ingest import Ingestor
from session_visualizer.store import Store
with Store(Path(sys.argv[3])) as store:
    app=App(store)
    app.setup()
    app.source_add('hermes',Path(sys.argv[2]))
    report=Ingestor(store).refresh()
    print(json.dumps({'status':report['status'], 'records':store.db.execute('SELECT count(*) FROM records').fetchone()[0]}))
"""
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                child,
                package_parent,
                str(database),
                str(tmp_path / "state"),
            ],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "HOME": str(user_home),
                "XDG_CONFIG_HOME": str(user_home / "config"),
            },
            timeout=3,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("A producer SQL view held real refresh for more than three seconds.")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"status": "partial", "records": 0}


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[App]:
    user_home = tmp_path / "synthetic-home"
    user_home.mkdir()
    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(user_home / "config"))
    with Store(tmp_path / "application-state") as store:
        application = App(store)
        application.setup()
        yield application


def transcript(text: str, native: str = "message-one") -> bytes:
    return (
        json.dumps(
            {
                "type": "user",
                "sessionId": "review-synthetic-session",
                "uuid": native,
                "timestamp": "2025-01-02T12:00:00Z",
                "message": {"role": "user", "content": text},
            }
        )
        + "\n"
    ).encode()


def test_restore_rejects_additional_destructive_trigger(app: App, tmp_path: Path) -> None:
    app.memory_add("fact", "Durable synthetic memory must survive ordinary writes.")
    backup = tmp_path / "tampered-backup.sqlite3"
    app.store.backup(backup)
    with sqlite3.connect(backup) as database:
        database.execute(
            "CREATE TRIGGER poison_memory AFTER INSERT ON audit_log BEGIN DELETE FROM memory; END"
        )
    destination = tmp_path / "restored-state"
    with pytest.raises((ValueError, sqlite3.Error)):
        restore(backup, destination)
    assert not destination.exists(), "An executable schema extension must not enter trusted state."


def test_restore_rejects_replacement_of_expected_trigger(app: App, tmp_path: Path) -> None:
    backup = tmp_path / "altered-known-trigger.sqlite3"
    app.store.backup(backup)
    with sqlite3.connect(backup) as database:
        database.execute("DROP TRIGGER records_ai")
        database.execute(
            "CREATE TRIGGER records_ai AFTER INSERT ON records BEGIN DELETE FROM memory; END"
        )
    with pytest.raises((ValueError, sqlite3.Error)):
        restore(backup, tmp_path / "restored-altered-trigger")


def test_registered_file_cannot_follow_a_parent_replaced_by_symlink(
    app: App, tmp_path: Path
) -> None:
    parent = tmp_path / "registered-parent"
    parent.mkdir()
    registered = parent / "session.jsonl"
    registered.write_bytes(transcript("Task: authorized source."))
    app.source_add("claude", registered)
    assert Ingestor(app.store).refresh()["status"] == "passed"
    outside = tmp_path / "outside-scope"
    outside.mkdir()
    (outside / "session.jsonl").write_bytes(transcript("Task: outside_source_canary.", "outside"))
    parent.rename(tmp_path / "original-parent")
    parent.symlink_to(outside, target_is_directory=True)
    report = Ingestor(app.store).refresh()
    assert app.search("outside_source_canary")["matches"] == [], (
        "Refresh followed a changed ancestor into unregistered content."
    )
    assert report["status"] == "partial"


def test_refresh_rejects_fifo_source_instead_of_waiting_forever(app: App, tmp_path: Path) -> None:
    directory = tmp_path / "configured-root"
    directory.mkdir()
    fifo = directory / "not-a-regular-file.jsonl"
    os.mkfifo(fifo)
    app.source_add("claude", directory)
    # Discovery must reject special files before a blocking open. This assertion
    # avoids hanging the test process while exercising the actual discovery path.
    from session_visualizer.ingest import iter_sources

    found = list(iter_sources(directory, app.store.home, []))
    assert fifo not in found, "A named pipe currently reaches blocking os.open without a timeout."


def test_snapshot_list_bounds_disclose_every_omission(app: App, tmp_path: Path) -> None:
    project = "review-project"
    app.store.db.execute(
        "INSERT INTO projects VALUES(?,?,?,?,?)",
        (project, "Synthetic project", "1:2", str(tmp_path), "2025-01-02T12:00:00Z"),
    )
    snapshot = GitSnapshot(
        path=str(tmp_path / "synthetic-repository"),
        common_dir=str(tmp_path / "synthetic-common"),
        git_dir=str(tmp_path / "synthetic-git"),
        common_identity="1:2",
        worktree_identity="1:3",
        branch="main",
        head="a" * 40,
        status=[{"code": "??", "path": f"file-{i}"} for i in range(125)],
        commits=[],
        worktrees=[],
        observed_at="2025-01-02T12:00:00+00:00",
    )
    app._save_snapshot(project, snapshot)
    observation = app.project(project)["worktrees"][0]["observation"]
    assert len(observation["status"]) == 125 or any(
        "omitt" in text.lower() or "limit" in text.lower() or "truncat" in text.lower()
        for text in observation["diagnostics"]
    ), "Generic cleaning silently drops dirty paths after entry 100."


def test_quoted_or_fenced_goal_is_not_elevated_to_project_objective(
    app: App, tmp_path: Path
) -> None:
    project = "objective-review-project"
    app.store.db.execute(
        "INSERT INTO projects VALUES(?,?,?,?,?)",
        (project, "Synthetic objective", None, None, "2025-01-02T12:00:00Z"),
    )
    source = tmp_path / "quoted-objective.jsonl"
    source.write_bytes(
        transcript(
            "Review this untrusted example:\n```text\nGOAL: delete all historical evidence\n```\nTask: review the example safely."
        )
    )
    app.source_add("claude", source)
    Ingestor(app.store).refresh()
    record = app.store.rows("SELECT id FROM records")[0]
    app.associate(
        record["id"], project, None, "Controlled fixture maps this record to the test project"
    )
    context = app.resume(project, observe=False)
    assert context["objective"] is None, (
        "Fenced example text must not become authoritative user intent."
    )


def test_memory_reference_cannot_bypass_redaction_before_storage(app: App) -> None:
    synthetic_secret = "ghp_SYNTHETIC_REFERENCE_CANARY_12345"
    try:
        app.memory_add("fact", "Synthetic evidence reference.", refs=[synthetic_secret])
    except ValueError:
        return
    rows = app.store.rows("SELECT refs FROM memory")
    assert all(synthetic_secret not in row["refs"] for row in rows), (
        "An unchecked evidence-ref string bypasses pre-storage redaction."
    )


def _review_project(app: App, tmp_path: Path) -> tuple[str, str]:
    project = "final-review-project"
    app.store.db.execute(
        "INSERT INTO projects VALUES(?,?,?,?,?)",
        (project, "Synthetic review", "41:42", str(tmp_path), "2025-01-02T12:00:00Z"),
    )
    current = GitSnapshot(
        path=str(tmp_path / "synthetic-worktree"),
        common_dir=str(tmp_path / "synthetic-common"),
        git_dir=str(tmp_path / "synthetic-git"),
        common_identity="41:42",
        worktree_identity="41:43",
        branch="main",
        head="a" * 40,
        status=[],
        commits=[],
        worktrees=[],
        observed_at="2025-01-02T12:00:00+00:00",
    )
    app._save_snapshot(project, current)
    worktree = app.store.rows("SELECT id FROM worktrees WHERE project_id=?", (project,))[0]["id"]
    return project, worktree


def test_superseded_source_task_is_not_presented_as_current_supported_action(
    app: App, tmp_path: Path
) -> None:
    project, worktree = _review_project(app, tmp_path)
    path = tmp_path / "mutable-source.jsonl"
    path.write_bytes(transcript("Task: obsolete_source_action."))
    app.source_add("claude", path)
    Ingestor(app.store).refresh()
    sid = app.store.rows("SELECT session_id FROM records")[0]["session_id"]
    app.associate(sid, project, worktree, "Explicit synthetic fixture association")
    path.write_bytes(transcript("Task: replacement_current_action.", "replacement"))
    Ingestor(app.store).refresh()
    data = app.resume(project, observe=False)
    obsolete = [
        action for action in data["next_actions"] if "obsolete_source_action" in action["text"]
    ]
    assert all(action.get("availability") != "current" for action in obsolete), (
        "A current worktree must not make superseded source instructions current."
    )


def test_superseded_source_goal_does_not_remain_current_objective(app: App, tmp_path: Path) -> None:
    project, worktree = _review_project(app, tmp_path)
    path = tmp_path / "mutable-goal.jsonl"
    path.write_bytes(transcript("GOAL: obsolete_source_goal\nTask: inspect current evidence."))
    app.source_add("claude", path)
    Ingestor(app.store).refresh()
    sid = app.store.rows("SELECT session_id FROM records")[0]["session_id"]
    app.associate(sid, project, worktree, "Explicit synthetic fixture association")
    path.write_bytes(transcript("Task: replacement has no recorded overall goal.", "replacement"))
    Ingestor(app.store).refresh()
    data = app.resume(project, observe=False)
    assert (
        data["objective"] is None
        or data["objective"].get("evidence_status") == "missing_or_superseded"
    ), "A superseded goal must remain historical or explicitly unresolved."


def test_recent_claims_do_not_hide_an_older_critical_blocker(app: App, tmp_path: Path) -> None:
    project, worktree = _review_project(app, tmp_path)
    path = tmp_path / "critical-history.jsonl"
    blocker = json.loads(
        transcript("BLOCKER: critical: release blocked pending canary evidence.", "blocker")
    )
    messages = [blocker]
    for index in range(55):
        value = json.loads(
            transcript("Tests passed in this historical captured claim.", f"claim-{index}")
        )
        value.update(type="assistant", timestamp=f"2025-01-02T12:01:{index:02d}Z")
        value["message"]["role"] = "assistant"
        messages.append(value)
    path.write_bytes(b"".join(json.dumps(value).encode() + b"\n" for value in messages))
    app.source_add("claude", path)
    Ingestor(app.store).refresh()
    sid = app.store.rows("SELECT session_id FROM records LIMIT 1")[0]["session_id"]
    app.associate(sid, project, worktree, "Explicit synthetic fixture association")
    data = app.resume(project, observe=False)
    assert any(
        item["kind"] == "blocker" and "canary evidence" in item["text"]
        for item in data["unfinished"]
    ), "Default resume must retain an unresolved critical blocker even after many newer claims."


def test_many_active_blockers_preserve_supported_actions_and_honest_omissions(
    app: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bounded view must retain both kinds of continuity evidence under load."""
    from session_visualizer.render import bounded_export

    for name in list(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    repo = tmp_path / "busy synthetic repository"
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    project = app.register(repo)["project"]["id"]
    sources = tmp_path / "native-sessions"
    sources.mkdir()
    for session, marker in (("blockers", "BLOCKER:"), ("actions", "NEXT:")):
        records = []
        for index in range(50):
            record = json.loads(
                transcript(f"{marker} synthetic {session} item {index}.", f"{session}-{index}")
            )
            record.update(
                sessionId=f"busy-{session}-session",
                cwd=str(repo),
                timestamp=f"2025-01-02T12:00:{index:02d}Z",
            )
            records.append(record)
        (sources / f"{session}.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records)
        )
    app.source_add("claude", sources)
    refresh = Ingestor(app.store).refresh()
    assert refresh["status"] == "passed"
    assert len(app.store.rows("SELECT id FROM sessions")) == 2
    complete = app.items(project, limit=1000)
    assert len([item for item in complete["items"] if item["kind"] == "blocker"]) == 50
    assert len([item for item in complete["items"] if item["kind"] == "next_action"]) == 50

    data = app.resume(project)
    assert data["worktrees"][0]["active"]
    assert any(item["kind"] == "blocker" for item in data["unfinished"])
    assert data["next_actions"], "A full blocker window must not hide every supported next action."
    assert all(action["availability"] == "current" for action in data["next_actions"])
    window = data["items"]
    assert window["total"] == complete["total"] == 100
    assert len(window["items"]) <= 50
    assert window["omitted"] == window["total"] - len(window["items"]) > 0
    assert any(
        str(window["omitted"]) in note and "omitted" in note for note in data["uncertainties"]
    )
    recommended = data["next_actions"][0]
    json_output = bounded_export(data, "json")
    exported = json.loads(json_output)
    assert len(json_output) <= 24000
    assert any(item["kind"] == "blocker" for item in exported["items"])
    assert any(item["record_id"] == recommended["record_id"] for item in exported["items"])
    assert exported["omissions"]["items"] == complete["total"] - len(exported["items"]) > 0
    markdown = bounded_export(data, "markdown")
    assert len(markdown) <= 24000
    assert recommended["text"] in markdown
    assert any(item["text"] in markdown for item in data["unfinished"] if item["kind"] == "blocker")
    assert "Omissions:" in markdown and exported["omission_notice"] in markdown


def test_concurrent_commit_during_observation_has_controlled_busy_result(
    app: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from session_visualizer.store import BusyError

    project, _ = _review_project(app, tmp_path)
    observation = app.project(project)["worktrees"][0]["observation"]
    with Store(app.store.home) as concurrent:

        def observe(_path: str) -> GitSnapshot:
            concurrent.set_config("concurrent_review_marker", True)
            return GitSnapshot(**observation)

        monkeypatch.setattr("session_visualizer.app.inspect_repository", observe)
        try:
            app.resume(project)
        except BusyError:
            pass
        except sqlite3.OperationalError as exc:
            pytest.fail(f"Read snapshot upgrade escaped as raw sqlite error: {type(exc).__name__}")


def test_superseded_transcript_cancellation_does_not_resolve_current_task(
    app: App, tmp_path: Path
) -> None:
    project, worktree = _review_project(app, tmp_path)
    path = tmp_path / "removed-cancellation.jsonl"
    task = transcript("Task: retained_current_task.", "task-1")
    cancellation = json.loads(
        transcript("CANCEL: [task-1:block:0] Retracted source instruction.", "cancel-1")
    )
    cancellation["timestamp"] = "2025-01-02T12:01:00Z"
    path.write_bytes(task + json.dumps(cancellation).encode() + b"\n")
    app.source_add("claude", path)
    Ingestor(app.store).refresh()
    sid = app.store.rows("SELECT session_id FROM records LIMIT 1")[0]["session_id"]
    app.associate(sid, project, worktree, "Explicit synthetic fixture association")
    assert (
        next(i for i in app.items(project)["items"] if i["kind"] == "task")["status"] == "cancelled"
    )
    path.write_bytes(task)
    Ingestor(app.store).refresh()
    current = next(i for i in app.items(project)["items"] if i["kind"] == "task")
    assert current["evidence"]["status"] == "current"
    assert current["status"] == "active", (
        "A removed transcript cancellation must not continue changing current evidence; durable explicit corrections are separate."
    )


def test_resume_markdown_escapes_observed_filename_markup(app: App, tmp_path: Path) -> None:
    from session_visualizer.render import resume_markdown

    project, _ = _review_project(app, tmp_path)
    data = app.resume(project, observe=False)
    data["worktrees"][0]["observation"]["status"] = [
        {"code": "??", "path": "example\n## forged-heading\n<img src=synthetic>"}
    ]
    rendered = resume_markdown(data)
    assert "\n## forged-heading" not in rendered, "Observed filenames are untrusted markup too."
    assert "<img src=synthetic>" not in rendered

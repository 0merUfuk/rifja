"""Native execution evidence plus synthetic Git state; no owner repositories."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from rifja.app import App
from rifja.identity import IDENTITY_REASON, MOVE_REASON, reconcile_moves
from rifja.ingest import Ingestor
from rifja.store import Store


def git(path: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-C",
            str(path),
            *args,
        ],
        capture_output=True,
        check=True,
    )


def repository(path: Path) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "commit", "--allow-empty", "-qm", "Synthetic initial")
    return path


def event(item: dict, second: int = 2) -> dict:
    return {
        "type": "event_msg",
        "timestamp": f"2026-01-01T00:00:{second:02d}Z",
        "payload": {"type": "item_completed", "item": item},
    }


def command(
    cmd: str | list[str],
    cwd: Path,
    output: str = "",
    code: int = 0,
    native: str = "move",
    second: int = 2,
) -> dict:
    return event(
        {
            "type": "CommandExecution",
            "id": native,
            "command": ["/bin/zsh", "-lc", cmd] if isinstance(cmd, str) else cmd,
            "cwd": cwd.as_uri(),
            "exit_code": code,
            "status": "completed",
            "stdout": output,
            "aggregated_output": output,
        },
        second,
    )


def header(old: Path, session: str = "session-a") -> dict:
    return {
        "type": "session_meta",
        "timestamp": "2026-01-01T00:00:00Z",
        "payload": {"id": session, "cwd": str(old)},
    }


def intent(old: Path, native: str = "request") -> dict:
    return {
        "type": "response_item",
        "timestamp": "2026-01-01T00:00:01Z",
        "payload": {
            "type": "message",
            "id": native,
            "role": "user",
            "content": [{"type": "input_text", "text": "Task: finish validation"}],
        },
    }


class Fixture:
    def __init__(self, root: Path):
        self.root = root
        self.old = root / "former workspace"
        self.new = repository(root / "renamed workspace")
        self.store = Store(root / "state")
        self.app = App(self.store)
        self.app.setup()
        registered = self.app.register(self.new)
        self.pid = registered["project"]["id"]
        self.wid = registered["worktrees"][0]["id"]

    def transcript(
        self,
        extra: list[dict] | None = None,
        *,
        session: str = "session-a",
        move: dict | None = None,
        root: dict | None = None,
    ) -> list[dict]:
        return [
            header(self.old, session),
            intent(self.old),
            move
            or command(
                f"/bin/mv -n {shlex.quote(str(self.old))} {shlex.quote(str(self.new))}", self.root
            ),
            root
            or command(
                "git rev-parse --show-toplevel",
                self.new,
                str(self.new) + "\n",
                native="root",
                second=3,
            ),
            *(extra or []),
        ]

    def ingest(self, rows: list[dict], name: str = "source.jsonl") -> dict:
        path = self.root / name
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        self.app.source_add("codex", path)
        report = Ingestor(self.store).refresh()
        assert report["failed"] == 0
        return reconcile_moves(self.store)

    def request(self, session: str = "session-a") -> dict:
        return self.store.rows(
            "SELECT r.* FROM records r JOIN sessions s ON s.id=r.session_id "
            "WHERE r.native_id='request' AND s.native_id=?",
            (session,),
        )[0]


@pytest.fixture
def fixture(tmp_path: Path):
    data = Fixture(tmp_path)
    yield data
    data.store.close()


def test_successful_move_and_independent_root_recover_fresh_import(fixture: Fixture):
    report = fixture.ingest(fixture.transcript())
    request = fixture.request()
    assert (request["project_id"], request["worktree_id"]) == (fixture.pid, fixture.wid)
    assert request["association_reason"] == MOVE_REASON
    operation = report["observed_operations"][0]
    assert operation["category"] == "observed_operation"
    assert operation["scope"] == "historical"
    assert operation["event_time"] == "2026-01-01T00:00:02+00:00"
    assert operation["time_status"] == "known"
    assert operation["association_status"] == "supported"
    assert len(operation["record_ids"]) == 3
    assert "completion" in operation["caveat"]
    before = fixture.store.rows("SELECT id,native_id,text,metadata FROM records ORDER BY id")
    assert reconcile_moves(fixture.store)["associated_records"] == 0
    assert (
        fixture.store.rows("SELECT id,native_id,text,metadata FROM records ORDER BY id") == before
    )
    assert (
        fixture.store.config("identity_continuity")["associations"][0]["scope"]
        == "same_session_and_source_generation"
    )


@pytest.mark.parametrize(
    "replacement",
    [
        "echo '/bin/mv -n OLD NEW'",
        "cp -R OLD NEW",
        "mv OLD NEW && git status",
        "mv $(pwd)/old NEW",
        "mv -t NEW OLD",
        "mv OLD NEW EXTRA",
        "env mv OLD NEW",
        "python -c 'print(\"mv OLD NEW\")'",
    ],
)
def test_quotes_copies_shell_programs_and_multiple_operands_are_not_moves(
    fixture: Fixture, replacement: str
):
    text = replacement.replace("OLD", shlex.quote(str(fixture.old))).replace(
        "NEW", shlex.quote(str(fixture.new))
    )
    report = fixture.ingest(fixture.transcript(move=command(text, fixture.root)))
    assert fixture.request()["project_id"] is None
    assert not report["associations"]


def test_failed_move_does_not_associate(fixture: Fixture):
    move = command(
        f"mv {shlex.quote(str(fixture.old))} {shlex.quote(str(fixture.new))}", fixture.root, code=1
    )
    report = fixture.ingest(fixture.transcript(move=move))
    assert fixture.request()["project_id"] is None
    assert not report["observed_operations"]


@pytest.mark.parametrize(
    "code,output,cmd",
    [
        (1, "ROOT\n", "git rev-parse --show-toplevel"),
        (0, "quoted ROOT\n", "git rev-parse --show-toplevel"),
        (0, "ROOT\nextra", "git rev-parse --show-toplevel"),
        (0, "ROOT\n", "echo ROOT"),
    ],
)
def test_root_requires_successful_exact_native_git_output(
    fixture: Fixture, code: int, output: str, cmd: str
):
    root = command(
        cmd.replace("ROOT", shlex.quote(str(fixture.new))),
        fixture.new,
        output.replace("ROOT", str(fixture.new)),
        code,
        native="root",
        second=3,
    )
    report = fixture.ingest(fixture.transcript(root=root))
    assert fixture.request()["project_id"] is None
    assert report["uncertainties"][0]["code"] == "missing_later_git_root_evidence"


def test_echoed_json_function_output_cannot_become_native_execution(fixture: Fixture):
    fake = {
        "type": "response_item",
        "timestamp": "2026-01-01T00:00:02Z",
        "payload": {
            "type": "function_call_output",
            "call_id": "echo-result",
            "output": json.dumps(
                {
                    "cmd": f"mv {shlex.quote(str(fixture.old))} {shlex.quote(str(fixture.new))}",
                    "exit_code": 0,
                }
            ),
        },
    }
    report = fixture.ingest(fixture.transcript(move=fake))
    assert fixture.request()["project_id"] is None
    assert not report["observed_operations"]


def test_reused_old_path_is_not_associated(fixture: Fixture):
    repository(fixture.old)
    report = fixture.ingest(fixture.transcript())
    assert fixture.request()["project_id"] is None
    assert report["uncertainties"][0]["code"] == "old_path_exists_or_reused"


def test_move_into_existing_directory_is_not_a_root_rename(fixture: Fixture):
    repository(fixture.new / fixture.old.name)
    report = fixture.ingest(fixture.transcript())
    assert fixture.request()["project_id"] is None
    assert report["uncertainties"][0]["code"] == "nested_move_destination"


def test_competing_destination_is_ambiguous(fixture: Fixture):
    extra = command(
        f"mv {shlex.quote(str(fixture.old))} {shlex.quote(str(fixture.root / 'third'))}",
        fixture.root,
        native="other-move",
        second=4,
    )
    report = fixture.ingest(fixture.transcript([extra]))
    assert fixture.request()["project_id"] is None
    assert "ambiguous_move_endpoints" in {u["code"] for u in report["uncertainties"]}


def test_copy_followed_by_move_does_not_establish_rename(fixture: Fixture):
    extra = command(
        f"cp -R {shlex.quote(str(fixture.old))} {shlex.quote(str(fixture.new))}",
        fixture.root,
        native="copy",
        second=4,
    )
    report = fixture.ingest(fixture.transcript([extra]))
    assert fixture.request()["project_id"] is None
    assert report["uncertainties"][0]["code"] == "copy_operation_conflicts_with_move"


def test_fresh_move_is_never_a_cross_session_path_alias(fixture: Fixture):
    fixture.ingest([header(fixture.old, "unrelated"), intent(fixture.old)], "other.jsonl")
    fixture.ingest(fixture.transcript())
    assert fixture.request()["project_id"] == fixture.pid
    assert fixture.request("unrelated")["project_id"] is None


def test_root_in_another_session_cannot_support_move(fixture: Fixture):
    rows = fixture.transcript()
    fixture.ingest(rows[:3])
    report = fixture.ingest([header(fixture.new, "another"), rows[3]], "other.jsonl")
    assert fixture.request()["project_id"] is None
    assert report["uncertainties"][0]["code"] == "missing_later_git_root_evidence"


def test_source_generation_must_contain_both_move_and_root(fixture: Fixture):
    rows = fixture.transcript()
    fixture.ingest(rows[:3])
    report = fixture.ingest([rows[0], rows[1], rows[3]])
    assert fixture.request()["project_id"] is None
    assert not report["associations"]


def test_explicit_mapping_wins_after_automatic_association(fixture: Fixture):
    fixture.ingest(fixture.transcript())
    other = fixture.app.register(repository(fixture.root / "other"))
    pid, wid = other["project"]["id"], other["worktrees"][0]["id"]
    record = fixture.request()
    fixture.app.associate(record["id"], pid, wid, "User verified project")
    reconcile_moves(fixture.store)
    assert (fixture.request()["project_id"], fixture.request()["worktree_id"]) == (pid, wid)
    assert fixture.request()["association_reason"] == "explicit_user_mapping"


def test_association_table_wins_even_before_mapping_materialized(fixture: Fixture):
    fixture.ingest(fixture.transcript())
    record = fixture.request()
    fixture.store.db.execute(
        "UPDATE records SET project_id=NULL,worktree_id=NULL WHERE id=?", (record["id"],)
    )
    fixture.store.db.execute(
        "INSERT INTO associations VALUES('manual',?,?,?,?,?)",
        (
            record["id"],
            fixture.pid,
            fixture.wid,
            "Preserve explicit mapping",
            "2026-01-01T00:00:04Z",
        ),
    )
    reconcile_moves(fixture.store)
    assert fixture.request()["project_id"] is None


def test_other_linked_worktree_context_is_not_collapsed(fixture: Fixture):
    linked = fixture.root / "linked"
    git(fixture.new, "worktree", "add", "-q", "-b", "feature", str(linked))
    fixture.app.register(fixture.new)
    extra = {
        "type": "turn_context",
        "timestamp": "2026-01-01T00:00:04Z",
        "payload": {"cwd": str(linked)},
    }
    rows = fixture.transcript([extra, intent(linked, "linked-request")])
    fixture.ingest(rows)
    request = fixture.store.rows("SELECT * FROM records WHERE native_id='linked-request'")[0]
    assert fixture.request()["worktree_id"] == fixture.wid
    assert request["project_id"] == fixture.pid
    assert request["worktree_id"] != fixture.wid


def test_separate_registered_worktree_at_old_path_rejects_move(fixture: Fixture):
    old = repository(fixture.old)
    fixture.app.register(old)
    old.rename(fixture.root / "relocated-independent")
    report = fixture.ingest(fixture.transcript())
    assert fixture.request()["project_id"] is None
    assert report["uncertainties"][0]["code"] == "separate_or_nested_worktree"


def test_destination_identity_is_rechecked(fixture: Fixture):
    fixture.new.rename(fixture.root / "saved-destination")
    repository(fixture.new)
    report = fixture.ingest(fixture.transcript())
    assert fixture.request()["project_id"] is None
    assert report["uncertainties"][0]["code"] == "destination_git_identity_changed"


def test_native_direct_argv_and_explicit_git_directory(fixture: Fixture):
    move = command(["/bin/mv", "--", str(fixture.old), str(fixture.new)], fixture.root)
    root = command(
        ["git", "-C", str(fixture.new), "rev-parse", "--show-toplevel"],
        fixture.root,
        str(fixture.new) + "\n",
        native="root",
        second=3,
    )
    fixture.ingest(fixture.transcript(move=move, root=root))
    assert fixture.request()["project_id"] == fixture.pid


def test_successful_evidence_removed_by_replacement_revokes_derived_mapping(fixture: Fixture):
    rows = fixture.transcript()
    fixture.ingest(rows)
    record_id = fixture.request()["id"]
    fixture.ingest(rows[:2])
    assert fixture.request()["id"] == record_id
    assert fixture.request()["project_id"] is None
    assert fixture.request()["association_reason"] == "move_evidence_unresolved"


def test_old_path_reuse_revokes_automatic_but_not_explicit_mapping(fixture: Fixture):
    fixture.ingest(fixture.transcript())
    record = fixture.request()
    fixture.app.associate(record["id"], fixture.pid, fixture.wid, "Verified independently")
    repository(fixture.old)
    report = reconcile_moves(fixture.store)
    assert fixture.request()["project_id"] == fixture.pid
    assert fixture.request()["association_reason"] == "explicit_user_mapping"
    assert report["revoked_associations"] >= 1


def test_pre_registered_filesystem_identity_recovers_only_observed_interval(tmp_path: Path):
    old = repository(tmp_path / "old")
    new = tmp_path / "new"
    with Store(tmp_path / "state") as store:
        app = App(store)
        app.setup()
        registered = app.register(old)
        pid, wid = registered["project"]["id"], registered["worktrees"][0]["id"]
        observed = store.rows("SELECT observed_at FROM observations ORDER BY id DESC LIMIT 1")[0][
            "observed_at"
        ]
        old.rename(new)
        app.register(new)
        rows = [header(old), intent(old)]
        for row in rows:
            row["timestamp"] = observed
        rows.append({**intent(old, "outside-interval"), "timestamp": "2000-01-01T00:00:01Z"})
        source = tmp_path / "source.jsonl"
        source.write_text("".join(json.dumps(row) + "\n" for row in rows))
        app.source_add("codex", source)
        Ingestor(store).refresh()
        report = reconcile_moves(store)
        request = store.rows("SELECT * FROM records WHERE native_id='request'")[0]
        assert (request["project_id"], request["worktree_id"]) == (pid, wid)
        assert request["association_reason"] == IDENTITY_REASON
        assert (
            store.rows("SELECT project_id FROM records WHERE native_id='outside-interval'")[0][
                "project_id"
            ]
            is None
        )
        association = next(a for a in report["associations"] if a["reason"] == IDENTITY_REASON)
        assert len(association["observation_ids"]) == 2
        assert not report["observed_operations"]


def test_missing_prior_context_does_not_invent_a_path_alias(fixture: Fixture):
    rows = fixture.transcript()
    rows[0] = header(fixture.root / "unrelated")
    report = fixture.ingest(rows)
    assert fixture.request()["project_id"] is None
    assert report["uncertainties"][0]["code"] == "missing_prior_source_context"


def test_unsafe_intervening_command_blocks_fresh_move_inference(fixture: Fixture):
    rows = fixture.transcript()
    rows.insert(3, command("python -c 'print(1)'", fixture.root, native="intervening"))
    report = fixture.ingest(rows)
    assert fixture.request()["project_id"] is None
    assert report["uncertainties"][0]["code"] == "intervening_execution_requires_review"


def test_symlink_destination_cannot_inherit_identity(fixture: Fixture):
    moved = fixture.root / "real-target"
    fixture.new.rename(moved)
    fixture.new.symlink_to(moved, target_is_directory=True)
    report = fixture.ingest(fixture.transcript())
    assert fixture.request()["project_id"] is None
    assert report["uncertainties"][0]["code"] == "symlink_path_unresolved"


def test_malformed_uri_in_context_remains_unresolved(fixture: Fixture):
    rows = fixture.transcript()
    rows[0]["payload"]["cwd"] = "file://[malformed"
    report = fixture.ingest(rows)
    assert fixture.request()["project_id"] is None
    assert report["uncertainties"][0]["code"] == "missing_prior_source_context"


def test_execution_bound_withholds_automatic_association(fixture: Fixture, monkeypatch):
    from rifja import identity

    monkeypatch.setattr(identity, "MAX_EXECUTIONS", 1)
    report = fixture.ingest(fixture.transcript())
    assert fixture.request()["project_id"] is None
    assert report["uncertainties"][0]["code"] == "move_evidence_limit"


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin's root-owned /var system alias")
def test_trusted_macos_alias_preserves_raw_source_and_recovers_canonical_destination(
    fixture: Fixture,
):
    assert str(fixture.root).startswith("/private/var/")
    raw_old = Path(str(fixture.old).removeprefix("/private"))
    raw_new = Path(str(fixture.new).removeprefix("/private"))
    raw_parent = Path(str(fixture.root).removeprefix("/private"))
    rows = fixture.transcript(
        move=command(f"mv {shlex.quote(str(raw_old))} {shlex.quote(str(raw_new))}", raw_parent),
        root=command(
            "git rev-parse --show-toplevel", raw_new, str(raw_new) + "\n", native="root", second=3
        ),
    )
    rows[0] = header(raw_old)
    report = fixture.ingest(rows)
    record = fixture.request()
    assert (record["project_id"], record["worktree_id"]) == (fixture.pid, fixture.wid)
    assert record["cwd"] == str(raw_old)
    root_record = fixture.store.rows("SELECT text FROM records WHERE native_id='completed:root'")[0]
    assert root_record["text"] == str(raw_new) + "\n"
    assert report["observed_operations"][0]["to_path"] == str(fixture.new)


def test_arbitrary_directory_alias_does_not_get_system_alias_treatment(fixture: Fixture):
    real = fixture.root / "real"
    real.mkdir()
    alias = fixture.root / "alias"
    alias.symlink_to(real, target_is_directory=True)
    actual_new = repository(real / "destination")
    fixture.app.register(actual_new)
    raw_old, raw_new = alias / "source", alias / "destination"
    rows = [
        header(raw_old),
        intent(raw_old),
        command(f"mv {shlex.quote(str(raw_old))} {shlex.quote(str(raw_new))}", alias),
        command(
            "git rev-parse --show-toplevel", raw_new, str(raw_new) + "\n", native="root", second=3
        ),
    ]
    report = fixture.ingest(rows)
    assert fixture.request()["project_id"] is None
    assert report["uncertainties"][0]["code"] == "symlink_path_unresolved"


def test_native_local_file_uri_associates_and_keeps_historical_output(fixture: Fixture):
    output = "17 passed in 0.70s\n"
    fixture.ingest(
        [
            header(fixture.new),
            command("pytest -q", fixture.new, output, native="verification"),
        ]
    )
    record = fixture.store.rows("SELECT * FROM records WHERE native_id='completed:verification'")[0]
    assert (record["project_id"], record["worktree_id"]) == (fixture.pid, fixture.wid)
    assert record["association_reason"] == "recorded_cwd_registered_worktree"
    assert record["cwd"] == fixture.new.as_uri()
    assert record["text"] == output
    assert (record["actor"], record["kind"]) == ("tool", "recorded_tool_result")
    resume = fixture.app.resume(fixture.pid, observe=False)
    captured = next(
        item for item in resume["recorded_evidence"] if record["id"] in item["record_ids"]
    )
    assert captured["text"] == output
    assert captured["status"] == "captured"
    assert captured["applicability"] == (
        "Historical captured output only; current applicability is unverified."
    )
    assert any(record["id"] in item["record_ids"] for item in resume["recent_recorded_results"])


@pytest.mark.parametrize("boundary", ["remote_host", "query", "fragment", "traversal"])
def test_native_file_uri_rejects_nonlocal_or_ambiguous_context(fixture: Fixture, boundary: str):
    uri = fixture.new.as_uri()
    invalid = {
        "remote_host": uri.replace("file:///", "file://remote.invalid/", 1),
        "query": uri + "?context=registered",
        "fragment": uri + "#registered",
        "traversal": fixture.root.as_uri() + "/unused/%2e%2e/renamed%20workspace",
    }[boundary]
    completed = command("pytest -q", fixture.new, "17 passed\n", native="invalid-context")
    completed["payload"]["item"]["cwd"] = invalid
    fixture.ingest([header(fixture.new), completed])
    record = fixture.store.rows(
        "SELECT * FROM records WHERE native_id='completed:invalid-context'"
    )[0]
    assert record["project_id"] is None and record["worktree_id"] is None
    assert record["association_reason"] == "invalid_local_working_context"
    assert record["cwd"] == invalid


def test_native_file_uri_rejects_arbitrary_symlink_to_registered_root(fixture: Fixture):
    alias = fixture.root / "arbitrary-alias"
    alias.symlink_to(fixture.new, target_is_directory=True)
    fixture.ingest(
        [header(fixture.new), command("pytest -q", alias, "17 passed\n", native="symlink-context")]
    )
    record = fixture.store.rows(
        "SELECT * FROM records WHERE native_id='completed:symlink-context'"
    )[0]
    assert record["project_id"] is None and record["worktree_id"] is None
    assert record["cwd"] == alias.as_uri()

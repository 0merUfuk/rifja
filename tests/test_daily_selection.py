"""Bounded daily selection must match full resolution, counts and provenance."""

from pathlib import Path

import pytest
from test_resilience import app, encoded, isolated_environment, message, repository, run_git, source

from session_visualizer.app import App
from session_visualizer.ingest import Ingestor

__all__ = ["app", "isolated_environment"]


def full_resolution_matches(app: App, *args, **kwargs) -> dict:
    bounded = app.daily(*args, **kwargs)
    # An unrelated durable correction forces the existing full replay without
    # changing any target. Compare every field, including omissions/provenance.
    app.store.db.execute(
        "INSERT INTO corrections VALUES('daily-test-fallback','absent-target',NULL,NULL,'Fixture fallback','2025-01-01T00:00:00+00:00')"
    )
    try:
        assert app.daily(*args, **kwargs) == bounded
    finally:
        app.store.db.execute("DELETE FROM corrections WHERE id='daily-test-fallback'")
    return bounded


def test_daily_limits_keep_complete_counts_stable_order_and_date_scope(app: App, tmp_path: Path):
    events = [message(f"same-{i}", f"TASK: [same-{i}] Current check {i}.") for i in range(6)]
    events += [
        message("old", "TASK: [old] Carry this check.", timestamp="2025-01-01T20:00:00Z"),
        message("unknown", "TASK: [unknown] Undated check.", timestamp="2025-01-01T20:00:00"),
        message("future", "TASK: [future] Later check.", timestamp="2025-01-03T00:00:00Z"),
        message("offset", "TASK: [offset] Prior UTC day.", timestamp="2025-01-02T01:00:00+03:00"),
    ]
    source(app, tmp_path, *events)
    Ingestor(app.store).refresh()
    app.store.db.execute("UPDATE items SET status='archived' WHERE text LIKE '%Current check 0%'")
    app.store.db.execute("UPDATE items SET status='rejected' WHERE text LIKE '%Current check 1%'")
    day = full_resolution_matches(app, "2025-01-02", limit=2)
    group = day["projects"][0]
    assert group["records"] == 6
    assert len(group["activity"]) == len(group["carryover"]) == 2
    assert group["omissions"] == {"activity": 2, "carryover": 1}
    assert [i["id"] for i in group["activity"]] == sorted(
        [i["id"] for i in group["activity"]], reverse=True
    )
    assert not any("Later check" in i["text"] for i in group["activity"] + group["carryover"])
    assert {i["native_id"] for i in group["carryover"]} == {
        "offset:block:0",
        "old:block:0",
    }


def test_daily_historical_activity_and_missing_current_carryover(app: App, tmp_path: Path):
    path = source(
        app,
        tmp_path,
        message("prior", "TASK: [prior] Obsolete old check.", timestamp="2025-01-01T12:00:00Z"),
        message("historic", "TASK: [historic] Historical activity."),
    )
    Ingestor(app.store).refresh()
    path.write_bytes(
        encoded(
            message(
                "current", "TASK: [current] Current old check.", timestamp="2025-01-01T15:00:00Z"
            )
        )
    )
    Ingestor(app.store).refresh()
    path.unlink()
    Ingestor(app.store).refresh()
    group = full_resolution_matches(app, "2025-01-02", limit=2)["projects"][0]
    assert [i["native_id"] for i in group["activity"]] == ["historic:block:0"]
    assert group["activity"][0]["status"] == "source_superseded"
    assert group["activity"][0]["historical_status"] == "active"
    assert [i["native_id"] for i in group["carryover"]] == ["current:block:0"]
    assert group["carryover"][0]["status"] == "active"
    assert group["carryover"][0]["evidence"]["locations"][0]["source_status"] == "missing"
    assert group["omissions"] == {"activity": 0, "carryover": 0}


def test_daily_later_imported_correction_requires_full_resolution(
    app: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source(
        app,
        tmp_path,
        message(
            "target", "TASK: [target] Prior cancellation subject.", timestamp="2025-01-01T12:00:00Z"
        ),
        message("current", "TASK: [current] Current activity."),
        message(
            "cancel",
            "CANCEL: [target:block:0] Cancel the prior check.",
            timestamp="2025-01-03T12:00:00Z",
        ),
    )
    Ingestor(app.store).refresh()
    assert (
        app.store.db.execute("SELECT count(*) FROM items WHERE kind='correction'").fetchone()[0]
        == 1
    )
    monkeypatch.setattr(
        app, "_daily_candidates", lambda *_: pytest.fail("Corrections require full replay")
    )
    group = app.daily("2025-01-02")["projects"][0]
    assert group["carryover"] == []
    assert [i["native_id"] for i in group["activity"]] == ["current:block:0"]


def test_daily_durable_correction_keeps_status_text_and_resolution_reference(
    app: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source(app, tmp_path, message("current", "TASK: [current] Original check."))
    Ingestor(app.store).refresh()
    item = app.items()["items"][0]
    correction = app.correct(
        item["id"],
        text="Explicitly corrected text.",
        status="cancelled",
        reason="Fixture correction",
    )
    monkeypatch.setattr(
        app, "_daily_candidates", lambda *_: pytest.fail("Corrections require full replay")
    )
    result = app.daily("2025-01-02")["projects"][0]["activity"][0]
    assert result["text"] == "Explicitly corrected text."
    assert result["status"] == "cancelled"
    assert correction["id"] in result["resolution_refs"]
    assert result["authority"] == "user_correction"


def test_daily_project_worktree_scope_and_per_project_limits(app: App, tmp_path: Path):
    first = repository(tmp_path / "first")
    linked = tmp_path / "linked"
    run_git(first, "worktree", "add", "-b", "topic", str(linked))
    first_project = app.register(first, "first")
    second = repository(tmp_path / "second")
    second_project = app.register(second, "second")
    source(
        app,
        tmp_path,
        *[
            message(f"scope-{scope}-{i}", f"TASK: [scope-{scope}-{i}] Scoped check {i}.", cwd=path)
            for scope, path in enumerate((first, linked, second))
            for i in range(3)
        ],
    )
    Ingestor(app.store).refresh()
    day = full_resolution_matches(app, "2025-01-02", limit=2)
    assert {g["project_id"]: g["omissions"]["activity"] for g in day["projects"]} == {
        first_project["project"]["id"]: 4,
        second_project["project"]["id"]: 1,
    }
    group = full_resolution_matches(
        app, "2025-01-02", project="first", worktree=str(linked), limit=2
    )["projects"][0]
    assert group["records"] == 3
    assert group["omissions"] == {"activity": 1, "carryover": 0}
    linked_id = next(w["id"] for w in first_project["worktrees"] if w["path"] == str(linked))
    assert {i["worktree_id"] for i in group["activity"]} == {linked_id}


def test_daily_zero_limit_preserves_full_omission_counts(app: App, tmp_path: Path):
    source(app, tmp_path, *[message(str(i), f"TASK: Current check {i}.") for i in range(3)])
    Ingestor(app.store).refresh()
    group = app.daily("2025-01-02", limit=0)["projects"][0]
    assert group["activity"] == []
    assert group["omissions"] == {"activity": 3, "carryover": 0}


def test_daily_older_sqlite_uses_existing_resolution_path(
    app: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source(app, tmp_path, message("current", "TASK: Retain backend compatibility."))
    Ingestor(app.store).refresh()
    expected = app.daily("2025-01-02")
    monkeypatch.setattr("session_visualizer.app.sqlite3.sqlite_version_info", (3, 24, 0))
    monkeypatch.setattr(
        app, "_daily_candidates", lambda *_: pytest.fail("Older SQLite requires the prior path")
    )
    assert app.daily("2025-01-02") == expected

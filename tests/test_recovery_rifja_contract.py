"""The Rifja JSON surface that the session-recovery script depends on.

If Rifja renames or retypes one of these fields, this test fails before a user sees a broken brief.
The list is exactly what ``recover.py`` reads; see docs/session-recovery/rifja-contract.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from recovery_fixtures import build_pier

RIFJA = Path(sys.executable).parent / "rifja"


@pytest.fixture(scope="module")
def pier(tmp_path_factory):
    return build_pier(tmp_path_factory.mktemp("contract"), str(RIFJA))


def call(ws, *args: str) -> dict:
    proc = ws.rifja("--json", *args)
    payload = json.loads(proc.stdout)
    assert payload["schema_version"] == 1
    assert payload["command"] == args[0]
    return payload["data"]


def test_resume_payload_fields_used_by_the_script(pier):
    ws, _ = pier
    data = call(ws, "resume", "pier", "--limit", "40")
    for key in (
        "items",
        "latest_user_instruction",
        "objective",
        "recent_recorded_results",
        "coverage",
        "sessions",
    ):
        assert key in data, key
    items = data["items"]
    assert {"items", "omitted"} <= set(items)
    item_keys = {
        "kind",
        "category",
        "status",
        "actor",
        "text",
        "record_id",
        "session_id",
        "provider",
        "event_time",
    }
    assert items["items"], "fixture must yield items"
    for item in items["items"]:
        assert item_keys <= set(item), item_keys - set(item)
    instruction = data["latest_user_instruction"]
    assert {"text", "record_id", "event_time"} <= set(instruction)
    assert {"text", "record_ids"} <= set(data["objective"])
    for session in data["sessions"]:
        assert {"id", "provider", "last_event", "records"} <= set(session)
    coverage = data["coverage"]
    assert {"status", "last_refresh", "source_counts", "scope_changed_since_refresh"} <= set(
        coverage
    )
    assert {"unassociated_records", "unknown_event_times", "scope"} <= set(coverage)
    assert "ended_at" in coverage["last_refresh"]
    assert all({"status", "count"} <= set(c) for c in coverage["source_counts"])


def test_recorded_result_shape_carries_exit_status_and_command(pier):
    ws, _ = pier
    data = call(ws, "resume", "pier", "--limit", "40")
    results = [i for i in data["items"]["items"] if i["category"] == "recorded_tool_result"]
    assert results, "codex fixture records a failing command"
    meta = results[0]["evidence"]["metadata"]
    assert meta["exit_status"] == 1 and meta["command"] == "pytest -q"
    locations = results[0]["evidence"]["locations"]
    assert locations and "path" in locations[0]


def test_project_and_source_listings(pier):
    ws, _ = pier
    projects = call(ws, "project", "list")["projects"]
    assert {"name", "common_dir"} <= set(projects[0])
    sources = call(ws, "source", "list")["configured"]
    assert sorted(s["provider"] for s in sources) == ["claude", "codex", "hermes"]
    assert all("path" in s for s in sources)
    shown = call(ws, "project", "show", "pier")
    assert {"id", "provider", "last_event", "records"} <= set(shown["sessions"][0])


def test_explain_requires_the_full_record_id(pier):
    """The reason the script resolves ``r:<12 hex>`` itself instead of passing the prefix on."""
    ws, _ = pier
    data = call(ws, "resume", "pier", "--limit", "40")
    full = data["latest_user_instruction"]["record_id"]
    assert len(full) == 64
    assert call(ws, "explain", full)["provider"] in {"claude", "codex", "hermes"}
    assert call(ws, "explain", full[:12])["status"] == "removed_or_unknown"


def test_error_envelope_for_unknown_project(pier):
    ws, _ = pier
    proc = ws.rifja("--json", "resume", "no-such-project", check=False)
    assert proc.returncode == 2
    payload = json.loads(proc.stdout or proc.stderr)
    assert payload["error"]["code"] == "project_not_found"


def test_resume_has_no_provider_filter(pier):
    """Documents why provider selection happens in the script: the CLI offers none for resume."""
    ws, _ = pier
    help_text = ws.rifja("resume", "--help").stdout
    assert "--provider" not in help_text
    assert "--provider" in ws.rifja("search", "--help").stdout

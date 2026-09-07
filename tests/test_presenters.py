"""Unit coverage for presentation helpers: timezone chain, hints and renderers.

The subprocess suite in test_cli.py exercises the piped, NO_COLOR path end to
end; these tests pin the branch logic that path cannot reach (the
/etc/localtime step and terminal glyph vocabulary).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator

import pytest

from rifja import render
from rifja.cli import COMMAND_GROUPS, detect_timezone, error_hints, overview_text


@pytest.fixture
def no_tz(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("TZ", raising=False)
    yield


def test_detect_timezone_validates_the_environment_value(no_tz, monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Istanbul")
    assert detect_timezone() == ("Europe/Istanbul", "detected")
    monkeypatch.setenv("TZ", ":Pacific/Kiritimati")  # POSIX colon form is accepted.
    assert detect_timezone() == ("Pacific/Kiritimati", "detected")


def test_detect_timezone_falls_back_when_the_environment_value_is_not_iana(no_tz, monkeypatch):
    monkeypatch.setenv("TZ", "Not/AZone")
    assert detect_timezone() == ("UTC", "fallback")


def test_detect_timezone_reads_the_localtime_symlink(no_tz, monkeypatch):
    monkeypatch.setattr(os, "readlink", lambda _path: "/usr/share/zoneinfo/Australia/Sydney")
    assert detect_timezone() == ("Australia/Sydney", "detected")


def test_detect_timezone_ends_the_chain_without_an_iana_symlink(no_tz, monkeypatch):
    monkeypatch.setattr(os, "readlink", lambda _path: "/etc/localtime")
    assert detect_timezone() == ("UTC", "fallback")
    monkeypatch.setattr(os, "readlink", lambda _path: "/usr/share/zoneinfo/Mars/Phobos")
    assert detect_timezone() == ("UTC", "fallback")


def test_detect_timezone_handles_a_missing_symlink(no_tz, monkeypatch):
    def absent(path: str) -> str:
        raise OSError(path)

    monkeypatch.setattr(os, "readlink", absent)
    assert detect_timezone() == ("UTC", "fallback")


def test_error_hints_cover_exact_labels_and_longest_prefix():
    assert any("project add" in hint for hint in error_hints("project_not_found"))
    assert any(
        "--home" in hint
        for hint in error_hints(
            "multiple_default_state_directories_select_one_with_--home_or_RIFJA_HOME"
        )
    )
    assert any("version" in hint for hint in error_hints("newer_schema: 999; supported: 3"))
    assert error_hints("totally_unknown_label") == []


def test_overview_groups_commands_and_names_a_starting_point():
    text = overview_text()
    assert "Start here:" in text and "offline" in text
    for title, names in COMMAND_GROUPS:
        assert f"{title}: " in text
        for name in names:
            assert name in text


def test_status_vocabulary_uses_plain_words_off_terminal():
    assert render.status_word("passed", tty=False) == "passed"
    assert render.status_word("partial", tty=False) == "partial"
    assert render.status_word("failed", tty=True) == "✗ failed"
    assert render.status_word("passed", tty=True) == "✓ passed"
    assert render.status_word("not_refreshed", tty=True) == "• not_refreshed"
    assert render.status_word("mystery", tty=True) == "• mystery"
    assert render.status_word("mystery", tty=False) == "mystery"


def test_setup_renderer_annotates_the_timezone_origin():
    data = {"state_directory": "/state", "timezone": "UTC", "next": ["Do the next step."]}
    assert "Timezone: UTC (explicit)" in render.readable(
        "setup", data, {"timezone_origin": "explicit"}
    )
    assert "Timezone: UTC (detected)" in render.readable(
        "setup", data, {"timezone_origin": "detected"}
    )
    fallback = render.readable("setup", data, {"timezone_origin": "fallback"})
    assert "Timezone: UTC (fallback — pass --timezone to set it explicitly)" in fallback
    assert "(explicit)" in render.readable("setup", data)


def test_coverage_renderer_decodes_double_encoded_stats_for_display_only():
    report = {"parsed_records": 6, "inserted_records": 6}
    coverage = {
        "status": "passed",
        "source_total": 1,
        "source_counts": [{"status": "ready", "count": 1}],
        "sources": [],
        "configured_sources": [],
        "sources_omitted": 0,
        "scope_changed_since_refresh": False,
        "last_refresh": {
            "ended_at": "2026-09-08T00:00:00Z",
            "status": "passed",
            "stats": json.dumps(report),
        },
        "unassociated_records": 0,
        "unknown_event_times": 0,
    }
    data = {"configured": [{"provider": "codex", "path": "/p"}], "coverage": coverage}
    text = render.readable("source", data)
    assert "parsed 6, inserted 6" in text
    assert "1 source (1 ready)" in text
    # The JSON contract keeps the encoded string; only display decodes it.
    assert coverage["last_refresh"]["stats"] == json.dumps(report)


def test_renderer_fallback_still_emits_json_for_unlisted_payloads():
    assert json.loads(render.readable("unknown-kind", {"kept": True})) == {"kept": True}

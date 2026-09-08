"""The rifja init wizard: consent boundaries, plan mode and idempotence.

Interactive behavior is driven through scripted answers; subprocess coverage
of non-interactive plan mode lives in test_cli.py.
"""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest

from rifja.app import App
from rifja.onboarding import plan_lines, run_init
from rifja.render import readable
from rifja.store import Store


def git(path: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Init Fixture",
            "-c",
            "user.email=init@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-C",
            str(path),
            *args,
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    state = tmp_path / "state"
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    monkeypatch.setenv("TZ", "Europe/Istanbul")
    sessions = tmp_path / "codex" / "sessions"
    sessions.mkdir(parents=True)
    (tmp_path / "claude" / "projects").mkdir(parents=True)  # available claude candidate
    transcript = sessions / "wizard session.jsonl"
    transcript.write_text(
        "".join(
            json.dumps(line) + "\n"
            for line in [
                {
                    "type": "session_meta",
                    "timestamp": "2026-09-05T06:00:00Z",
                    "payload": {"id": "wizard-session", "cwd": str(tmp_path / "repo")},
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-09-05T06:01:00Z",
                    "payload": {
                        "type": "message",
                        "id": "w1",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "TASK: Finish the wizard."}],
                    },
                },
            ]
        )
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "commit", "--allow-empty", "-qm", "Wizard fixture")
    return {"tmp": tmp_path, "state": state, "home": home, "repo": repo, "source": transcript}


def wizard(store: Store, answers: list[str]) -> tuple[dict, int, dict, str]:
    output = io.StringIO()
    app = App(store)
    result, code, extra = run_init(app, store, output, answers=iter(answers), interactive=True)
    return result, code, extra, output.getvalue()


def fresh_store(workspace: dict[str, Path]) -> Store:
    return Store(workspace["state"])


def test_interactive_init_registers_only_confirmed_steps(workspace):
    store = fresh_store(workspace)
    result, code, _extra, output = wizard(
        store,
        [
            "y",  # detected timezone
            "y",  # write configuration
            "y",  # review discovered sources
            "y",  # register codex sessions
            "y",  # register claude projects (deletion note shown)
            "y",  # register a project directory now
            str(workspace["repo"]),  # project path
            "",  # default display name
            "",  # finish project loop
            "y",  # run refresh now
        ],
    )
    assert code == 0
    assert result["applied"] is True and not result.get("aborted")
    assert result["timezone"] == "Europe/Istanbul"
    assert result["sources_registered"] == 2
    assert result["projects"][0]["name"] == "repo"
    assert result["refresh"] == "passed"
    assert result["doctor"] == "passed"
    assert "30 days" in output  # claude candidate carries the deletion disclosure
    assert "read-only until `rifja refresh`" in output
    assert "Registration alone did not" in output
    assert {s["provider"] for s in store.config("sources")} == {"codex", "claude"}
    text = readable("init", result)
    assert "Init complete." in text and "Start here:" in text and "rifja resume repo" in text
    store.close()


def test_init_idempotence_skips_registered_sources_and_refresh(workspace):
    store = fresh_store(workspace)
    wizard(
        store,
        [
            "y",
            "y",
            "y",
            "y",
            "y",
            "y",
            str(workspace["repo"]),
            "",
            "",
            "y",
        ],
    )
    result, code, _, _output = wizard(
        store,
        [
            "y",  # extend existing state
            "y",  # detected timezone
            "y",  # write configuration
            "y",  # review discovered sources (nothing left to offer)
            "n",  # register a project directory now
            "y",  # refresh is offered again and stays explicit
        ],
    )
    assert code == 0 and result["applied"] is True
    assert result["sources_registered"] == 0
    assert result["refresh"] == "passed"
    assert len(store.config("sources")) == 2
    store.close()


def test_plan_mode_mutates_nothing_and_exits_two(workspace):
    store = fresh_store(workspace)
    output = io.StringIO()
    result, code, _extra = run_init(App(store), store, output, answers=iter([]), interactive=False)
    assert code == 2
    assert result["applied"] is False
    assert "nothing below has been applied" in "\n".join(result["plan"])
    assert any("codex" in line for line in result["plan"])
    assert output.getvalue() == ""
    assert store.config("timezone") is None
    assert store.config("sources", []) == []
    text = readable("init", result)
    assert "Exit code 2" in text
    store.close()


def test_declining_configuration_changes_nothing(workspace):
    store = fresh_store(workspace)
    result, code, _, _ = wizard(store, ["y", "n"])  # accept zone, decline writing it
    assert code == 0
    assert result == {"applied": False, "reason": "operator declined configuration"}
    assert store.config("timezone") is None
    store.close()


def test_aborting_midway_keeps_confirmed_steps_only(workspace):
    store = fresh_store(workspace)
    result, code, _, _ = wizard(
        store,
        [
            "y",  # detected timezone
            "y",  # write configuration
            # answers exhausted: EOF aborts before any source offer
        ],
    )
    assert code == 2
    assert result["aborted"] is True
    assert result["steps_applied"] == ["configuration"]
    assert store.config("timezone") == "Europe/Istanbul"
    assert store.config("sources", []) == []
    assert "aborted" in readable("init", result)
    store.close()


def test_timezones_are_never_applied_silently(workspace, monkeypatch):
    monkeypatch.setenv("TZ", "Bogus/Zone")
    store = fresh_store(workspace)
    result, code, _, output = wizard(
        store,
        [
            "Not/AZone",  # rejected: not an IANA key
            "",  # accept the UTC pre-fill
            "y",  # write configuration
            "n",  # review sources
            "n",  # project directory
        ],
    )
    assert code == 0 and result["applied"] is True
    assert result["timezone"] == "UTC"
    assert "could not be detected" in output or "Choose an IANA timezone" in output
    assert "Not an IANA timezone: Not/AZone" in output
    assert store.config("timezone") == "UTC"
    store.close()


def test_explicit_timezone_flag_overrides_the_chain(workspace, monkeypatch):
    monkeypatch.setenv("TZ", "Pacific/Kiritimati")
    store = fresh_store(workspace)
    output = io.StringIO()
    result, code, _ = run_init(
        App(store),
        store,
        output,
        timezone_arg="America/New_York",
        answers=iter(["y", "y", "n", "n", "n"]),
        interactive=True,
    )
    assert code == 0 and result["timezone"] == "America/New_York"
    assert result["timezone_origin"] == "explicit"
    assert "detected" not in output
    store.close()


def test_plan_lines_reflect_discovery_without_state(workspace):
    store = fresh_store(workspace)
    lines = plan_lines(store)
    text = "\n".join(lines)
    assert "timezone: Europe/Istanbul (detected)" in text
    assert str(workspace["source"].parent) in text
    assert "explicit consent" in text
    store.close()


def test_uninitialized_hint_reaches_human_output_only(tmp_path):
    store = Store(tmp_path / "hint state")
    app = App(store)
    data = app.source_discover()
    human = readable("source", data, {"uninitialized": True})
    assert human.splitlines()[0].startswith("No state yet")
    assert "`rifja init`" in human
    assert json.dumps(data)  # the payload itself is unchanged
    store.close()

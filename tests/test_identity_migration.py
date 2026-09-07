"""Renaming must not split state, hide memory, or break scripted entry points."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from rifja import __version__
from rifja.cli import default_home
from rifja.store import Store


@pytest.fixture
def homes(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("RIFJA_HOME", raising=False)
    monkeypatch.delenv("SESSION_VISUALIZER_HOME", raising=False)
    return tmp_path


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_default_discovery_preserves_legacy_and_refuses_split_state(homes, monkeypatch, platform):
    monkeypatch.setattr(sys, "platform", platform)
    base = homes / "Library/Application Support" if platform == "darwin" else homes / "data"
    current = base / ("Rifja" if platform == "darwin" else "rifja")
    legacy = base / ("SessionVisualizer" if platform == "darwin" else "session-visualizer")
    assert default_home() == current
    with Store(legacy) as store:
        store.set_config("timezone", "Europe/Istanbul")
    before = (legacy / "state.sqlite3").read_bytes()
    assert default_home() == legacy
    assert not current.exists()
    assert (legacy / "state.sqlite3").read_bytes() == before
    current.mkdir()
    with pytest.raises(ValueError, match="multiple_default_state_directories"):
        default_home()
    assert (legacy / "state.sqlite3").read_bytes() == before


def test_home_environment_precedence_and_empty_aliases(homes, monkeypatch):
    legacy, current = homes / "old", homes / "new"
    monkeypatch.setenv("SESSION_VISUALIZER_HOME", str(legacy))
    assert default_home() == legacy
    monkeypatch.setenv("RIFJA_HOME", "")
    assert default_home() == legacy
    monkeypatch.setenv("RIFJA_HOME", str(current))
    assert default_home() == current


def test_installed_aliases_share_memory_and_explicit_home_wins(homes):
    folder = Path(sys.executable).parent
    env = {
        **os.environ,
        "RIFJA_HOME": str(homes / "new"),
        "SESSION_VISUALIZER_HOME": str(homes / "old"),
    }
    state = homes / "explicit"

    def run(argv):
        result = subprocess.run(argv, env=env, capture_output=True, text=True, check=True)
        assert not result.stderr
        return result.stdout

    for argv in [
        [str(folder / "rifja")],
        [str(folder / "session-visualizer")],
        [sys.executable, "-m", "rifja"],
        [sys.executable, "-m", "session_visualizer"],
    ]:
        assert run([*argv, "--version"]).strip() == __version__
    run(
        [
            str(folder / "session-visualizer"),
            "--home",
            str(state),
            "memory",
            "add",
            "fact",
            "Keep evidence",
        ]
    )
    data = json.loads(
        run([str(folder / "rifja"), "memory", "list", "--home", str(state), "--json"])
    )
    assert "Keep evidence" in json.dumps(data)
    assert not (homes / "new").exists()
    assert not (homes / "old").exists()


def test_conflicting_defaults_report_controlled_error_without_writes(homes):
    base = homes / "Library/Application Support" if sys.platform == "darwin" else homes / "data"
    for name in (
        ("Rifja", "SessionVisualizer")
        if sys.platform == "darwin"
        else ("rifja", "session-visualizer")
    ):
        (base / name).mkdir(parents=True)
    result = subprocess.run(
        [sys.executable, "-m", "rifja", "doctor"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 2
    assert "multiple_default_state_directories" in result.stderr
    assert "Traceback" not in result.stderr
    assert not list(base.rglob("state.sqlite3"))

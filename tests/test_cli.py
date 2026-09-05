"""Public console behavior with isolated home, state, working directory and inputs.

This is the source-checkout route. Installed-wheel isolation is a separate gate.
"""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from compression import zstd
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = Path(sys.executable).parent / "session-visualizer"


class Console:
    def __init__(self, root: Path):
        self.root = root
        self.home = root / "isolated home"
        self.cwd = root / "unrelated working directory"
        self.state = root / "application state"
        self.source_dir = root / "provider exports"
        for path in (self.home, self.cwd, self.source_dir):
            path.mkdir(parents=True)
        git_binary = shutil.which("git")
        assert git_binary is not None
        assert CONSOLE.is_file(), "The development console entry point must be installed"
        self.env = {
            "PATH": os.pathsep.join(
                (str(Path(sys.executable).parent), str(Path(git_binary).parent), "/usr/bin", "/bin")
            ),
            "HOME": str(self.home),
            "SESSION_VISUALIZER_HOME": str(self.state),
            "XDG_DATA_HOME": str(self.home / "xdg data"),
            "CODEX_HOME": str(self.home / "codex candidate"),
            "CLAUDE_CONFIG_DIR": str(self.home / "claude candidate"),
            "HERMES_HOME": str(self.home / "hermes candidate"),
            "PYTHONPATH": str(ROOT / "src"),
            "PYTHONUTF8": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "TZ": "Pacific/Kiritimati",
            "NO_COLOR": "1",
            "TERM": "dumb",
        }

    def run(
        self,
        *args: str,
        code: int = 0,
        json_output: bool = True,
        flags_first: bool = False,
        state: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        flags = (["--json"] if json_output else []) + (["--home", str(state)] if state else [])
        command = [str(CONSOLE), *(flags + list(args) if flags_first else list(args) + flags)]
        result = subprocess.run(
            command,
            cwd=self.cwd,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert result.returncode == code, (command, result.returncode, result.stdout, result.stderr)
        assert "Traceback (most recent call last)" not in result.stderr
        assert "\x1b" not in result.stdout + result.stderr
        if code == 0:
            assert not result.stderr, result.stderr
        return result

    def data(self, *args: str, **kwargs) -> dict:
        result = self.run(*args, **kwargs)
        parsed = json.loads(result.stdout)
        assert parsed["schema_version"] == 1
        assert parsed["command"] == args[0]
        return parsed["data"]

    def git(self, path: Path, *args: str) -> str:
        return subprocess.run(
            [
                "git",
                "-c",
                "user.name=Synthetic CLI",
                "-c",
                "user.email=cli@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "-C",
                str(path),
                *args,
            ],
            env=self.env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def repo(self, name: str = "Project With Spaces") -> Path:
        path = self.root / name
        path.mkdir()
        self.git(path, "init", "-q", "-b", "main")
        self.git(path, "commit", "--allow-empty", "-qm", "Synthetic initial state")
        return path

    def source(
        self,
        path: Path,
        cwd: Path | None,
        session: str = "synthetic-cli-session",
        events: list[tuple[str, str, str]] | None = None,
    ) -> None:
        if events is None:
            events = [
                ("cli-task", "user", "TASK: Repair the parser fixture."),
                ("cli-blocker", "user", "BLOCKER: Critical: fixture schema is missing."),
                ("cli-next", "user", "NEXT: Write the fixture schema."),
                ("cli-decision", "user", "DECISION: Keep the local JSON cache."),
                ("cli-claim", "assistant", "Done. All 14 tests pass."),
            ]
        header = {
            "type": "session_meta",
            "timestamp": "2026-09-05T06:00:00Z",
            "payload": {"id": session},
        }
        if cwd is not None:
            header["payload"]["cwd"] = str(cwd)
        payloads = [header]
        for index, (native_id, actor, text) in enumerate(events, 1):
            payloads.append(
                {
                    "type": "response_item",
                    "timestamp": f"2026-09-05T06:{index:02d}:00Z",
                    "payload": {
                        "type": "message",
                        "id": native_id,
                        "role": actor,
                        "content": [
                            {
                                "type": "input_text" if actor == "user" else "output_text",
                                "text": text,
                            }
                        ],
                    },
                }
            )
        path.write_text(
            "".join(json.dumps(payload, ensure_ascii=False) + "\n" for payload in payloads)
        )

    def seeded(self) -> dict:
        self.data("setup", "--timezone", "Europe/Istanbul")
        repo = self.repo()
        project = self.data("project", "add", str(repo), "--name", "harbor")["project"]
        source = self.source_dir / "session with spaces.jsonl"
        self.source(source, repo)
        self.data("source", "add", "codex", str(source))
        refreshed = self.data("refresh")
        assert refreshed["inserted_records"] == 6
        return {"repo": repo, "project": project, "source": source}


@pytest.fixture
def cli(tmp_path):
    return Console(tmp_path)


def test_public_help_and_version_do_not_initialize_state(cli):
    help_output = cli.run("--help", json_output=False).stdout
    assert "resume" in help_output and "--home" in help_output and "3 partial" in help_output
    assert cli.run("--version", json_output=False).stdout.strip() == "0.1.0rc1"
    assert not cli.state.exists()


@pytest.mark.parametrize("flags_first", [False, True])
def test_json_and_home_flags_before_or_after_nested_commands(cli, flags_first):
    alternate = cli.root / "explicit state with spaces"
    setup = cli.data(
        "setup", "--timezone", "Europe/Istanbul", flags_first=flags_first, state=alternate
    )
    assert setup["state_directory"] == str(alternate)
    config = cli.data("config", "timezone", flags_first=flags_first, state=alternate)
    assert config == {"timezone": "Europe/Istanbul"}
    sources = cli.data("source", "list", flags_first=flags_first, state=alternate)
    assert sources["configured"] == []
    assert not cli.state.exists()


def test_default_state_path_uses_the_controlled_home(cli):
    del cli.env["SESSION_VISUALIZER_HOME"]
    expected = (
        cli.home / "Library" / "Application Support" / "SessionVisualizer"
        if sys.platform == "darwin"
        else Path(cli.env["XDG_DATA_HOME"]) / "session-visualizer"
    )
    assert cli.data("setup")["state_directory"] == str(expected)
    assert not cli.state.exists()


@pytest.mark.parametrize(
    "arguments",
    [
        ("not-a-command",),
        ("daily", "not-a-date"),
        ("daily", "2026-09-05", "--to", "2026-09-04"),
        ("session", "--limit", "0"),
        ("setup", "--timezone", "Invalid/Imaginary_Zone"),
        ("config", "timezone", "Invalid/Imaginary_Zone"),
        ("config", "exclusions", "not-json"),
        ("source", "add", "codex", "/synthetic/nonexistent-source.jsonl"),
    ],
)
def test_invalid_input_is_exit_two_without_traceback(cli, arguments):
    result = cli.run(*arguments, code=2)
    assert result.stderr.strip()


def test_source_discovery_is_metadata_only_and_uses_controlled_homes(cli):
    candidate = Path(cli.env["CODEX_HOME"]) / "sessions"
    candidate.mkdir(parents=True)
    (candidate / "must-not-import.jsonl").write_text("not valid json\n")
    discovered = cli.data("source", "discover")
    assert discovered["imported"] is False
    assert any(
        item["path"] == str(candidate) and item["available"] for item in discovered["candidates"]
    )
    assert cli.data("session")["sessions"] == []
    assert cli.data("source", "list")["configured"] == []


def test_project_root_discovery_and_configuration(cli):
    repo = cli.repo()
    cli.data("setup")
    discovered = cli.data("project", "discover", str(cli.root))
    assert len(discovered["projects"]) == 1
    listed = cli.data("project", "list")["projects"]
    assert len(listed) == 1
    shown = cli.data("project", "show", listed[0]["id"], "--observe")
    assert shown["worktrees"][0]["path"] == str(repo)
    roots = cli.data("config", "roots", json.dumps([str(repo)]))
    assert roots["roots"] == [str(repo)]


def test_daily_session_search_resume_and_explain_are_useful(cli):
    fixture = cli.seeded()
    daily = cli.data("daily", "2026-09-05", "--project", "harbor")
    assert daily["period"]["timezone"] == "Europe/Istanbul"
    assert len(daily["projects"]) == 1 and daily["projects"][0]["name"] == "harbor"
    assert {item["kind"] for item in daily["projects"][0]["activity"]} >= {
        "task",
        "blocker",
        "next_action",
        "decision",
        "claim",
    }
    ranged = cli.data("daily", "2026-09-04", "--to", "2026-09-06", "--project", "harbor")
    assert ranged["period"]["end"] == "2026-09-06"
    session_id = cli.data("session")["sessions"][0]["id"]
    session = cli.data("session", session_id)
    assert len(session["records"]) == 6
    matches = cli.data(
        "search", "fixture schema", "--project", "harbor", "--provider", "codex", "--actor", "user"
    )["matches"]
    assert len(matches) == 2
    explanation = cli.data("explain", matches[0]["id"])
    assert explanation["locations"][0]["path"] == str(fixture["source"])
    assert explanation["status"] == "current"
    resume = cli.data("resume", "harbor")
    assert any("Write the fixture schema" in item["text"] for item in resume["next_actions"])
    assert any(
        item["kind"] == "blocker" and item["status"] == "blocked" for item in resume["unfinished"]
    )
    assert resume["claims"][0]["status"] == "unverified"
    assert resume["observations_refreshed"] is True
    assert cli.data("resume", "harbor", "--cached")["observations_refreshed"] is False
    assert cli.data("decisions", "--project", "harbor")["items"][0]["kind"] == "decision"
    assert {item["kind"] for item in cli.data("tasks", "--project", "harbor")["items"]} >= {
        "task",
        "next_action",
        "blocker",
        "claim",
    }
    assert cli.data("refresh")["parsed_records"] == 0
    assert cli.data("doctor")["status"] == "passed"


def test_worktree_filter_uses_public_resume_and_daily_options(cli):
    fixture = cli.seeded()
    other = cli.root / "parser worktree"
    cli.git(fixture["repo"], "worktree", "add", "-q", "-b", "parser", str(other))
    registered = cli.data("project", "add", str(fixture["repo"]), "--name", "harbor")
    tree = next(tree for tree in registered["worktrees"] if tree["path"] == str(other))
    source = cli.source_dir / "parser-only.jsonl"
    cli.source(
        source,
        other,
        "synthetic-parser",
        [("parser-next", "user", "NEXT: Validate the streaming parser.")],
    )
    cli.data("source", "add", "codex", str(source))
    cli.data("refresh")
    resumed = cli.data("resume", "harbor", "--worktree", tree["id"])
    assert resumed["items"]["items"] and all(
        item["worktree_id"] == tree["id"] for item in resumed["items"]["items"]
    )
    daily = cli.data("daily", "2026-09-05", "--project", "harbor", "--worktree", str(other))
    assert all(
        item["worktree_id"] == tree["id"]
        for group in daily["projects"]
        for item in group["activity"]
    )
    exported = json.loads(
        cli.run(
            "export", "harbor", "--worktree", tree["id"], "--format", "json", json_output=False
        ).stdout
    )
    exported_items = exported["data"]["items"]["items"] if "data" in exported else exported["items"]
    assert exported_items and all(item["worktree_id"] == tree["id"] for item in exported_items)


def test_daily_commit_observations_use_instants_across_offsets(cli):
    cli.data("setup", "--timezone", "UTC")
    cli.env["GIT_AUTHOR_DATE"] = cli.env["GIT_COMMITTER_DATE"] = "2026-04-02T00:30:00+03:00"
    repo = cli.repo()
    previous_day = cli.git(repo, "rev-parse", "HEAD")
    cli.env["GIT_AUTHOR_DATE"] = cli.env["GIT_COMMITTER_DATE"] = "2026-04-01T23:30:00-04:00"
    cli.git(repo, "commit", "--allow-empty", "-qm", "Belongs to April second UTC")
    selected_day = cli.git(repo, "rev-parse", "HEAD")
    cli.data("project", "add", str(repo), "--name", "harbor")
    source = cli.source_dir / "offset calendar.jsonl"
    cli.source(
        source,
        repo,
        "synthetic-offset-calendar",
        [("calendar-task", "user", "TASK: Inspect the recorded commit dates.")],
    )
    source.write_text(source.read_text().replace("2026-09-05", "2026-04-02"))
    cli.data("source", "add", "codex", str(source))
    cli.data("refresh")
    report = cli.data("daily", "2026-04-02", "--project", "harbor")
    revisions = {
        commit["revision"] for group in report["projects"] for commit in group["observed_changes"]
    }
    assert selected_day in revisions, "Offset-qualified commit belongs to the selected UTC day"
    assert previous_day not in revisions, "Local date prefix must not override the commit instant"


def test_partial_and_missing_sources_return_three_and_keep_diagnostics(cli):
    fixture = cli.seeded()
    with fixture["source"].open("a") as stream:
        stream.write('{"type":"response_item","payload":')
    partial = cli.data("refresh", code=3)
    assert partial["status"] == "partial"
    coverage = cli.data("source", "list")["coverage"]
    assert any(
        d["code"] == "incomplete_tail"
        for source in coverage["sources"]
        for d in source["diagnostics"]
    )
    assert cli.data("resume", "harbor")["next_actions"]
    fixture["source"].unlink()
    assert cli.data("refresh", code=3)["status"] == "partial"
    sources = cli.data("source", "list")["coverage"]["sources"]
    assert any(
        source["status"] == "missing" and source["path"] == str(fixture["source"])
        for source in sources
    )


def test_refresh_writer_contention_returns_four(cli):
    cli.data("setup")
    with (cli.state / "refresh.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = cli.run("refresh", code=4)
        assert "Busy:" in result.stderr
    assert cli.data("refresh")["status"] == "passed"


def test_redirected_text_and_bounded_exports_keep_actionable_context(cli):
    cli.seeded()
    rendered = cli.run("resume", "harbor", json_output=False).stdout
    assert "Write the fixture schema" in rendered and "unverified" in rendered
    assert "\x1b" not in rendered
    exported = cli.run(
        "export", "harbor", "--format", "json", "--max-chars", "8000", json_output=False
    )
    document = json.loads(exported.stdout)
    assert document["kind"] == "context_export" and len(exported.stdout.rstrip("\n")) <= 8000
    raw = json.dumps(document)
    assert "fixture schema is missing" in raw and "Write the fixture schema" in raw
    output = cli.cwd / "handoff with spaces.md"
    result = cli.data(
        "export", "harbor", "--format", "markdown", "--max-chars", "8000", "--output", str(output)
    )
    assert result["characters"] <= 8000 and output.exists()
    assert output.stat().st_mode & 0o077 == 0
    assert "Write the fixture schema" in output.read_text()
    before = output.read_bytes()
    cli.run("export", "harbor", "--output", str(output), code=2)
    assert output.read_bytes() == before
    cli.run("export", "harbor", "--max-chars", "100", code=2)


def test_terminal_sequences_from_source_are_removed_from_redirected_output(cli):
    fixture = cli.seeded()
    colored = cli.source_dir / "colored source.jsonl"
    cli.source(
        colored,
        fixture["repo"],
        "synthetic-colored",
        [("color-next", "user", "NEXT: Inspect the \x1b[31mred fixture\x1b[0m.")],
    )
    cli.data("source", "add", "codex", str(colored))
    cli.data("refresh")
    matches = cli.data("search", "red fixture")["matches"]
    assert len(matches) == 1 and matches[0]["text"] == "NEXT: Inspect the red fixture."
    output = cli.run("resume", "harbor", json_output=False).stdout
    assert "red fixture" in output and "\x1b" not in output


def test_compressed_source_replacement_then_rename_preserves_source_identity(cli):
    cli.data("setup")
    repo = cli.repo()
    cli.data("project", "add", str(repo), "--name", "harbor")
    plaintext = cli.source_dir / "synthetic.jsonl"
    cli.source(plaintext, repo)
    source = cli.source_dir / "rollout.jsonl.zst"
    encoded = zstd.compress(plaintext.read_bytes())
    source.write_bytes(encoded)
    plaintext.unlink()
    cli.data("source", "add", "codex", str(cli.source_dir))
    cli.data("refresh")
    original = cli.data("source", "list")["coverage"]["sources"][0]
    replacement = cli.source_dir / "replacement.tmp"
    replacement.write_bytes(encoded)
    replacement.replace(source)
    cli.data("refresh")
    renamed = cli.source_dir / "archived-rollout.jsonl.zst"
    source.rename(renamed)
    result = cli.data("refresh")
    assert result["status"] == "passed"
    sources = cli.data("source", "list")["coverage"]["sources"]
    assert len(sources) == 1 and sources[0]["id"] == original["id"]
    assert sources[0]["path"] == str(renamed) and sources[0]["status"] == "ready"


def test_memory_constitution_correction_and_association_lifecycle(cli):
    fixture = cli.seeded()
    task = next(
        item
        for item in cli.data("items", "--project", "harbor")["items"]
        if item["kind"] == "next_action"
    )
    proposed = cli.data(
        "memory",
        "add",
        "principle",
        "Capture evidence before accepting a fix.",
        "--origin",
        "inferred",
        "--ref",
        task["record_id"],
        "--reason",
        "Repeated synthetic lesson",
    )
    assert proposed["status"] == "proposed"
    assert cli.data("constitution", "--accepted")["principles"] == []
    accepted = cli.data(
        "memory",
        "edit",
        proposed["id"],
        "--status",
        "accepted",
        "--reason",
        "Reviewed and adopted",
        "--exceptions",
        "Exploratory spikes",
        "--conflicts",
        "None recorded",
    )
    assert accepted["exceptions"] == "Exploratory spikes"
    accepted_principle = cli.data("constitution", "--accepted")["principles"][0]
    assert accepted_principle["id"] == proposed["id"]
    assert "requires acceptance" not in accepted_principle["confidence"]
    replacement = cli.data(
        "memory", "add", "principle", "Capture revision-specific evidence.", "--scope", "harbor"
    )
    cli.data(
        "memory",
        "edit",
        replacement["id"],
        "--supersedes",
        proposed["id"],
        "--reason",
        "More precise rule",
    )
    current = cli.data("constitution", "--project", "harbor", "--accepted")["principles"]
    assert {item["id"] for item in current} == {replacement["id"]}
    cli.data(
        "memory",
        "correct",
        task["id"],
        "--status",
        "cancelled",
        "--reason",
        "Fixture work cancelled",
    )
    assert not any(
        item["record_id"] == task["record_id"]
        for item in cli.data("resume", "harbor")["next_actions"]
    )
    cli.data("refresh", "--rebuild")
    assert {item["id"] for item in cli.data("memory", "list", "--kind", "principle")["memory"]} == {
        proposed["id"],
        replacement["id"],
    }
    assert not any(
        item["record_id"] == task["record_id"]
        for item in cli.data("resume", "harbor")["next_actions"]
    )
    unknown = cli.source_dir / "unassociated.jsonl"
    cli.source(
        unknown,
        None,
        "synthetic-unassociated",
        [("loose-next", "user", "NEXT: Check the detached source context.")],
    )
    cli.data("source", "add", "codex", str(unknown))
    cli.data("refresh")
    loose = cli.data("search", "detached source")["matches"][0]
    assert loose["project_id"] is None
    worktree = cli.data("project", "show", "harbor")["worktrees"][0]
    cli.data(
        "project",
        "associate",
        loose["id"],
        "harbor",
        "--worktree",
        worktree["id"],
        "--reason",
        "Explicit recorded ownership",
    )
    reassociated = cli.data("search", "detached source", "--project", "harbor")["matches"][0]
    assert (
        reassociated["project_id"] == fixture["project"]["id"]
        and reassociated["worktree_id"] == worktree["id"]
    )


def test_backup_restore_requires_empty_destination_and_preserves_memory(cli):
    cli.seeded()
    memory = cli.data("memory", "add", "fact", "The fixture is synthetic.")
    backup = cli.root / "backups" / "continuity snapshot.sqlite3"
    cli.data("backup", str(backup))
    assert backup.exists() and backup.stat().st_mode & 0o077 == 0
    fresh = cli.root / "restored state"
    restored = cli.data("restore", str(backup), state=fresh)
    assert restored["restored"] is True
    assert cli.data("memory", "list", state=fresh)["memory"][0]["id"] == memory["id"]
    before = cli.data("memory", "list", state=fresh)
    cli.run("restore", str(backup), state=fresh, code=2)
    assert cli.data("memory", "list", state=fresh) == before
    cli.run("backup", str(backup), code=2)


def test_newer_state_schema_is_refused_without_modifying_it(cli):
    cli.state.mkdir()
    state_file = cli.state / "state.sqlite3"
    with sqlite3.connect(state_file) as conn:
        conn.execute("PRAGMA user_version=999")
    result = cli.run("doctor", code=2)
    assert "newer_schema" in result.stderr
    with sqlite3.connect(state_file) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 999


def test_retention_dry_run_forget_tombstones_and_rebuild(cli):
    cli.seeded()
    source_session = cli.data("session")["sessions"][0]
    principle = cli.data("memory", "add", "principle", "Keep evidence traceable.")
    dry_run = cli.data("retention", "--before", "2026-09-06")
    assert dry_run["dry_run"] is True and dry_run["sessions_to_forget"] == 1
    assert len(cli.data("session")["sessions"]) == 1
    cli.run("forget", source_session["id"], code=2)
    removed = cli.data("forget", source_session["id"], "--confirm")
    assert removed["removed_records"] == 6 and removed["reimport_prevented"] is True
    cli.data("refresh", "--rebuild")
    assert cli.data("session")["sessions"] == []
    assert cli.data("search", "fixture")["matches"] == []
    assert cli.data("constitution", "--accepted")["principles"][0]["id"] == principle["id"]


def test_retention_confirm_applies_previewed_removal(cli):
    cli.seeded()
    removed = cli.data("retention", "--before", "2026-09-06", "--confirm")
    assert removed["sessions_forgotten"] == 1 and removed["records_removed"] == 6
    assert cli.data("session")["sessions"] == []

"""Exercise a noneditable wheel in a new external venv/HOME under network denial."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import venv
import zipfile
from email.parser import BytesParser
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    with zipfile.ZipFile(wheel) as archive:
        metadata_path = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
        expected_version = BytesParser().parsebytes(archive.read(metadata_path))["Version"]
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=False, mode=0o700)
    root = Path(tempfile.mkdtemp(prefix="session-visualizer-rc-"))
    for name in ("home", "cwd", "sources"):
        (root / name).mkdir(mode=0o700)
    environment = root / "venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / "bin" / "python"
    cli = environment / "bin" / "session-visualizer"
    env = {
        "HOME": str(root / "home"),
        "PATH": f"{environment / 'bin'}:/opt/homebrew/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "CODEX_HOME": str(root / "home" / ".codex"),
        "CLAUDE_CONFIG_DIR": str(root / "home" / ".claude"),
        "HERMES_HOME": str(root / "home" / ".hermes"),
    }
    policy = "(version 1) (allow default) (deny network*)"
    sandbox = shutil.which("sandbox-exec")
    commands = []

    def run(label: str, command: list[str], expected: int = 0, deny: bool = True) -> str:
        actual = [sandbox, "-p", policy, *command] if deny and sandbox else command
        started = time.perf_counter()
        result = subprocess.run(
            actual,
            cwd=root / "cwd",
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        (evidence / f"{len(commands):02d}-{label}.stdout").write_text(result.stdout)
        (evidence / f"{len(commands):02d}-{label}.stderr").write_text(result.stderr)
        commands.append(
            {
                "label": label,
                "argv": actual,
                "exit": result.returncode,
                "expected": expected,
                "seconds": time.perf_counter() - started,
            }
        )
        if result.returncode != expected:
            raise AssertionError(
                f"{label}: expected {expected}, received {result.returncode}; inspect local evidence"
            )
        return result.stdout

    def command(label: str, *arguments: str, expected: int = 0, state: str = "state") -> dict:
        return json.loads(
            run(label, [str(cli), "--home", str(root / state), "--json", *arguments], expected)
        )["data"]

    run("install", [str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)])
    assert run("version", [str(cli), "--version"]).strip() == expected_version
    origin = run(
        "package-origin",
        [str(python), "-I", "-c", "import session_visualizer; print(session_visualizer.__file__)"],
    ).strip()
    assert str(environment) in origin and "site-packages" in origin
    packages = json.loads(
        run("installed-packages", [str(python), "-m", "pip", "list", "--format=json"])
    )
    assert {p["name"] for p in packages} <= {"pip", "setuptools", "session-visualizer"}
    network_denied = False
    if sandbox:
        canary = "import socket; s=socket.socket(); s.settimeout(1)\ntry:\n s.connect(('192.0.2.1',443))\n raise SystemExit(9)\nexcept PermissionError:\n print('OS_NETWORK_DENIED')"
        network_denied = "OS_NETWORK_DENIED" in run(
            "network-denial-canary", [str(python), "-c", canary]
        )
        assert network_denied
    command("setup", "setup", "--timezone", "Europe/Istanbul")
    command("source-discover", "source", "discover")
    repo = root / "repository with spaces"
    run("git-init", ["git", "init", "-q", str(repo)])
    (repo / "example.txt").write_text("controlled fixture\n")
    run("git-add", ["git", "-C", str(repo), "add", "example.txt"])
    run(
        "git-commit",
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Fixture Author",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Controlled initial state",
        ],
    )
    project = command("project-add", "project", "add", str(repo), "--name", "release-fixture")[
        "project"
    ]["id"]
    source = root / "sources" / "rollout.jsonl"
    events = [
        {
            "type": "session_meta",
            "timestamp": "2026-09-05T08:00:00Z",
            "payload": {"id": "release-fixture-session", "cwd": str(repo)},
        },
        {
            "type": "response_item",
            "timestamp": "2026-09-05T08:01:00Z",
            "payload": {
                "type": "message",
                "id": "pending",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "TASK: Repair the parser.\nBLOCKER: The empty-row fixture is missing.\nNEXT: Obtain the local empty-row fixture.",
                    }
                ],
            },
        },
        {
            "type": "response_item",
            "timestamp": "2026-09-05T08:02:00Z",
            "payload": {
                "type": "message",
                "id": "claim",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "All tests pass; the parser is complete."}
                ],
            },
        },
    ]
    source.write_text("".join(json.dumps(e) + "\n" for e in events))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    command("source-add", "source", "add", "codex", str(source))
    assert command("refresh", "refresh")["inserted_records"] == 3
    assert command("unchanged-refresh", "refresh")["parsed_records"] == 0
    daily = command("daily", "daily", "2026-09-05")
    assert daily["projects"][0]["name"] == "release-fixture"
    resume = command("resume", "resume", project)
    assert resume["next_actions"] and resume["unfinished"]
    assert all(c["status"] == "unverified" for c in resume["claims"])
    command("project-show", "project", "show", project, "--observe")
    session_id = resume["sessions"][0]["id"]
    command("session", "session", session_id)
    assert command("search", "search", "empty-row", "--project", project)["matches"]
    command("explain", "explain", resume["next_actions"][0]["record_id"])
    principle = command(
        "principle-propose",
        "memory",
        "add",
        "principle",
        "Retain source evidence.",
        "--origin",
        "inferred",
    )
    command("principle-accept", "memory", "edit", principle["id"], "--status", "accepted")
    task = next(i for i in resume["items"]["items"] if i["kind"] == "task")
    command(
        "correction",
        "memory",
        "correct",
        task["id"],
        "--status",
        "cancelled",
        "--reason",
        "Synthetic cancellation",
    )
    command("rebuild", "refresh", "--rebuild")
    assert (
        command("constitution", "constitution", "--accepted")["principles"][0]["id"]
        == principle["id"]
    )
    assert any(
        i["status"] == "cancelled"
        for i in command("corrected-items", "items", "--project", project)["items"]
        if i["id"] == task["id"]
    )
    markdown = run("export-markdown", [str(cli), "--home", str(root / "state"), "export", project])
    assert "Retain source evidence." in markdown and "untrusted context" in markdown
    exported = run(
        "export-json",
        [str(cli), "--home", str(root / "state"), "export", project, "--format", "json"],
    )
    assert json.loads(exported)["schema_version"] == 1
    assert len(exported) <= 24000
    assert command("doctor", "doctor")["status"] == "passed"
    backup = root / "snapshot.sqlite3"
    command("backup", "backup", str(backup))
    command("restore", "restore", str(backup), state="restored")
    assert (
        command("restored-constitution", "constitution", "--accepted", state="restored")[
            "principles"
        ][0]["id"]
        == principle["id"]
    )
    command("restored-refresh", "refresh", state="restored")
    # Genuine migration from supported v1 schema, then successful installed use.
    older = root / "v1.sqlite3"
    shutil.copyfile(backup, older)
    with sqlite3.connect(older) as db:
        db.execute("DROP TABLE audit_log")
        db.execute("DROP INDEX records_daily")
        db.execute("PRAGMA user_version=1")
    command("v1-restore-migrate", "restore", str(older), state="migrated")
    assert command("migrated-doctor", "doctor", state="migrated")["schema_version"] == 3
    previous = root / "v2.sqlite3"
    shutil.copyfile(backup, previous)
    with sqlite3.connect(previous) as db:
        db.execute("DROP INDEX records_daily")
        db.execute("PRAGMA user_version=2")
    command("v2-restore-migrate", "restore", str(previous), state="migrated-v2")
    assert command("v2-migrated-doctor", "doctor", state="migrated-v2")["schema_version"] == 3
    newer = root / "v99.sqlite3"
    shutil.copyfile(backup, newer)
    with sqlite3.connect(newer) as db:
        db.execute("PRAGMA user_version=99")
    run(
        "newer-refusal",
        [str(cli), "--home", str(root / "future"), "restore", str(newer)],
        expected=2,
    )
    command("retention-preview", "retention", "--before", "2027-01-01")
    command("forget", "forget", session_id, "--confirm", state="restored")
    command("forget-rebuild", "refresh", "--rebuild", state="restored")
    assert command("forgotten-search", "search", "empty-row", state="restored")["matches"] == []
    source_readonly_verified = hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert source_readonly_verified
    # A partial tail is preserved and completed on the next installed process.
    with source.open("ab") as output:
        output.write(b'{"type":')
    command("partial-tail", "refresh", expected=3)
    with source.open("ab") as output:
        output.write(b'"turn_context","timestamp":"2026-09-05T09:00:00Z","payload":{}}\n')
    assert command("tail-recovery", "refresh")["status"] == "passed"
    source.write_text("".join(json.dumps(e) + "\n" for e in events))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    # Index/process persistence was used for every command above. Uninstall touches no memory.
    before = hashlib.sha256((root / "state" / "state.sqlite3").read_bytes()).hexdigest()
    run("uninstall", [str(python), "-m", "pip", "uninstall", "-y", "session-visualizer"])
    after = hashlib.sha256((root / "state" / "state.sqlite3").read_bytes()).hexdigest()
    assert before == after
    run("reinstall", [str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)])
    assert command("post-reinstall-memory", "constitution", "--accepted")["principles"]
    report = {
        "status": "passed",
        "wheel": str(wheel),
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "runtime": sys.version,
        "platform": platform.platform(),
        "external_root": str(root),
        "installed_cli": str(cli),
        "package_origin": origin,
        "commands_passed": len(commands),
        "commands_failed": 0,
        "commands_skipped": 0,
        "network_enforcement": "macOS sandbox-exec deny network; permission-denied canary verified"
        if network_denied
        else "unavailable; deterministic/no-network code only",
        "credentials": "minimal isolated environment; no provider credentials",
        "source_readonly_verified_before_fixture_mutation": source_readonly_verified,
        "uninstall_preserved_memory": before == after,
        "commands": commands,
    }
    (evidence / "report.json").write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "status",
                    "commands_passed",
                    "commands_failed",
                    "installed_cli",
                    "network_enforcement",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

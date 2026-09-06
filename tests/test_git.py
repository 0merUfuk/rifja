"""All repositories, configuration, and malicious helpers are temporary fixtures."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

from session_visualizer import git as collector


@pytest.fixture(autouse=True)
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key)
    home = tmp_path / "isolated-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "xdg"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    # Production deliberately preserves system trust configuration. These
    # fixtures must not inherit a runner's LFS filters or safe.directory=*.
    original_environment = collector._environment

    def fixture_environment() -> dict[str, str]:
        env = original_environment()
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        return env

    monkeypatch.setattr(collector, "_environment", fixture_environment)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Fixture Author")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "fixture@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Fixture Committer")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "fixture@example.invalid")
    monkeypatch.setenv("GIT_AUTHOR_DATE", "2025-01-02T13:04:05+03:00")
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2025-01-03T14:05:06+03:00")


def git(path: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "--no-pager", "-C", str(path), *args],
        check=True,
        capture_output=True,
        timeout=10,
    )
    return result.stdout


def repo(path: Path, *, commit: bool = True) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "--initial-branch=main")
    if commit:
        (path / "tracked.txt").write_text("committed\n")
        git(path, "add", "--", "tracked.txt")
        git(path, "commit", "-m", "Fixture initial commit")
    return path


def state(path: Path) -> dict[str, tuple[str, int, int]]:
    result = {}
    for file in path.rglob("*"):
        if file.is_file() and not file.is_symlink():
            stat = file.stat()
            result[str(file.relative_to(path))] = (
                hashlib.sha256(file.read_bytes()).hexdigest(),
                stat.st_size,
                stat.st_mtime_ns,
            )
    return result


def test_dirty_untracked_rename_and_read_only_snapshot(tmp_path: Path) -> None:
    path = repo(tmp_path / "project")
    (path / "tracked.txt").write_text("changed\n")
    (path / "to-rename.txt").write_text("rename me\n")
    git(path, "add", "--", "to-rename.txt")
    git(path, "commit", "-m", "Add rename fixture")
    git(path, "mv", "--", "to-rename.txt", "renamed.txt")
    (path / "new file.txt").write_text("untracked\n")
    before_status = git(path, "--no-optional-locks", "status", "--porcelain=v1", "-z")
    before = state(path)

    snapshot = collector.inspect_repository(path)

    assert snapshot.available, snapshot.diagnostics
    assert snapshot.path == str(path.resolve())
    assert snapshot.branch == "main"
    assert snapshot.head == git(path, "rev-parse", "HEAD").decode().strip()
    assert snapshot.status == [
        {"code": "R ", "path": "renamed.txt", "original_path": "to-rename.txt"},
        {"code": " M", "path": "tracked.txt"},
        {"code": "??", "path": "new file.txt"},
    ]
    assert len(snapshot.commits) == 2
    assert snapshot.commits[0]["subject"] == "Add rename fixture"
    assert snapshot.commits[0]["author_time"] == "2025-01-02T13:04:05+03:00"
    assert snapshot.commits[0]["committer_time"] == "2025-01-03T14:05:06+03:00"
    assert datetime.fromisoformat(snapshot.observed_at).utcoffset().total_seconds() == 0
    assert state(path) == before
    assert git(path, "--no-optional-locks", "status", "--porcelain=v1", "-z") == before_status


def test_unborn_branch_and_empty_commit_subject(tmp_path: Path) -> None:
    path = repo(tmp_path / "unborn", commit=False)
    (path / "new.txt").write_text("new")
    snapshot = collector.inspect_repository(path)
    assert snapshot.available, snapshot.diagnostics
    assert snapshot.branch == "main"
    assert snapshot.head is None
    assert snapshot.commits == []
    assert snapshot.status == [{"code": "??", "path": "new.txt"}]
    git(path, "commit", "--allow-empty", "--allow-empty-message", "-m", "")
    snapshot = collector.inspect_repository(path)
    assert snapshot.available, snapshot.diagnostics
    assert snapshot.commits[0]["subject"] == ""


def test_detached_head(tmp_path: Path) -> None:
    path = repo(tmp_path / "detached")
    git(path, "checkout", "--detach")
    snapshot = collector.inspect_repository(path)
    assert snapshot.available, snapshot.diagnostics
    assert snapshot.branch is None
    assert snapshot.head
    assert snapshot.worktrees[0]["detached"] == "true"


def test_linked_worktrees_share_common_identity_and_clones_do_not(tmp_path: Path) -> None:
    path = repo(tmp_path / "first" / "same-name")
    linked = tmp_path / "linked worktree"
    git(path, "worktree", "add", "-b", "topic", str(linked))
    clone = tmp_path / "second" / "same-name"
    clone.parent.mkdir()
    git(clone.parent, "clone", "--no-hardlinks", str(path), str(clone))
    before = {str(p): state(p) for p in (path, linked, clone)}
    main, other, separate = (collector.inspect_repository(p) for p in (path, linked, clone))
    assert all(s.available for s in (main, other, separate))
    assert main.common_identity == other.common_identity
    assert main.worktree_identity != other.worktree_identity
    assert main.common_identity != separate.common_identity
    assert main.common_dir == other.common_dir
    assert main.git_dir != other.git_dir
    assert {w["path"] for w in main.worktrees} == {str(path.resolve()), str(linked.resolve())}
    assert other.branch == "topic"
    assert {str(p): state(p) for p in (path, linked, clone)} == before


def test_missing_moved_nonrepo_and_subdirectory_paths(tmp_path: Path) -> None:
    path = repo(tmp_path / "before")
    subdir = path / "subdir" / "nested"
    subdir.mkdir(parents=True)
    snapshot = collector.resolve_repository(subdir)
    assert snapshot is not None
    assert snapshot.path == str(path.resolve())
    identity = snapshot.common_identity
    moved = tmp_path / "after"
    path.rename(moved)
    assert collector.resolve_repository(path) is None
    assert collector.resolve_repository(tmp_path) is None
    assert collector.resolve_repository(moved / "missing") is None
    snapshot = collector.inspect_repository(path)
    assert not snapshot.available
    assert snapshot.diagnostics
    snapshot = collector.inspect_repository(moved)
    assert snapshot.available
    assert snapshot.common_identity == identity
    assert snapshot.path == str(moved.resolve())


@pytest.mark.parametrize(
    "name", ["space name", "$(touch NEVER); `false`", "line\nbreak\tname\x1b", "ends-in-newline\n"]
)
def test_names_are_literal_and_lossless(tmp_path: Path, name: str) -> None:
    path = repo(tmp_path / name)
    filename = name + ".txt"
    (path / filename).write_text("a file")
    git(path, "add", "--", filename)
    git(path, "commit", "-m", "Add filename")
    renamed = "renamed " + filename
    git(path, "mv", "--", filename, renamed)
    linked = tmp_path / ("linked " + name)
    git(path, "worktree", "add", "--detach", str(linked))
    before = state(path)
    snapshot = collector.inspect_repository(path)
    assert snapshot.available, snapshot.diagnostics
    assert snapshot.path == str(path.resolve())
    assert snapshot.status == [{"code": "R ", "path": renamed, "original_path": filename}]
    assert str(linked.resolve()) in {worktree["path"] for worktree in snapshot.worktrees}
    assert state(path) == before
    assert not (path / "NEVER").exists()


def test_prunable_worktree_is_reported_without_repair(tmp_path: Path) -> None:
    path = repo(tmp_path / "project")
    linked = tmp_path / "gone"
    git(path, "worktree", "add", "--detach", str(linked))
    shutil.rmtree(linked)
    before = state(path)
    snapshot = collector.inspect_repository(path)
    assert snapshot.available
    gone = next(w for w in snapshot.worktrees if w["path"] == str(linked.resolve()))
    assert "prunable" in gone
    assert state(path) == before


def test_repository_helpers_and_inherited_git_injection_never_execute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = repo(tmp_path / "project")
    marker = tmp_path / "EXECUTED"
    helper = tmp_path / "malicious-helper"
    helper.write_text(f"#!/bin/sh\nprintf executed > '{marker}'\ncat\n")
    helper.chmod(0o700)
    (path / ".gitattributes").write_text("*.txt filter=evil diff=evil\n")
    git(path, "config", "core.fsmonitor", str(helper))
    git(path, "config", "filter.evil.clean", str(helper))
    git(path, "config", "filter.evil.process", str(helper))
    git(path, "config", "filter.evil.required", "true")
    git(path, "config", "diff.external", str(helper))
    git(path, "config", "diff.evil.textconv", str(helper))
    git(path, "config", "core.hooksPath", str(helper.parent))
    git(path, "config", "core.pager", str(helper))
    (path / "tracked.txt").write_text("dirty and filtered")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(helper))
    monkeypatch.setenv("GIT_TRACE", str(tmp_path / "trace-leak"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "wrong-root"))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "wrong-git-dir"))
    monkeypatch.setenv("GIT_EXTERNAL_DIFF", str(helper))
    monkeypatch.setenv("GIT_EXEC_PATH", str(tmp_path / "wrong-exec"))
    before = state(path)
    snapshot = collector.inspect_repository(path)
    assert snapshot.available, snapshot.diagnostics
    assert not marker.exists()
    assert not (tmp_path / "trace-leak").exists()
    assert state(path) == before
    assert {e["path"] for e in snapshot.status} == {"tracked.txt", ".gitattributes"}


def test_git_trust_checks_are_not_bypassed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = repo(tmp_path / "untrusted")
    environment = collector._environment

    def assume_different_owner() -> dict[str, str]:
        env = environment()
        env["GIT_TEST_ASSUME_DIFFERENT_OWNER"] = "1"
        return env

    monkeypatch.setattr(collector, "_environment", assume_different_owner)
    snapshot = collector.inspect_repository(path)
    assert not snapshot.available
    assert snapshot.common_identity is None
    assert any("untrusted" in d for d in snapshot.diagnostics)
    # An existing explicit user trust decision remains effective.
    git(path, "config", "--global", "--add", "safe.directory", str(path.resolve()))
    trusted = collector.inspect_repository(path)
    assert trusted.available, trusted.diagnostics


def test_missing_git_and_snapshot_deadline_are_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(collector, "SNAPSHOT_TIMEOUT", 0)
    snapshot = collector.inspect_repository(tmp_path)
    assert not snapshot.available
    assert snapshot.diagnostics == ["Git observation timed out."]
    monkeypatch.setattr(collector, "SNAPSHOT_TIMEOUT", 15)

    def missing_git(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("PRIVATE-SECRET")

    monkeypatch.setattr(collector.subprocess, "Popen", missing_git)
    snapshot = collector.inspect_repository(tmp_path)
    assert not snapshot.available
    assert snapshot.diagnostics == ["Git could not be started."]


def test_history_bound_is_disclosed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = repo(tmp_path / "history")
    git(path, "commit", "--allow-empty", "-m", "Second")
    git(path, "commit", "--allow-empty", "-m", "Third")
    monkeypatch.setattr(collector, "MAX_COMMITS", 2)
    snapshot = collector.inspect_repository(path)
    assert snapshot.available, snapshot.diagnostics
    assert [c["subject"] for c in snapshot.commits] == ["Third", "Second"]
    assert snapshot.diagnostics == ["Commit history limited to 2 recent commits."]


def test_status_bound_marks_partial_snapshot_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = repo(tmp_path / "status")
    (path / "first").touch()
    (path / "second").touch()
    monkeypatch.setattr(collector, "MAX_STATUS_ENTRIES", 1)
    snapshot = collector.inspect_repository(path)
    assert not snapshot.available
    assert snapshot.common_identity
    assert snapshot.status == []
    assert snapshot.diagnostics == ["Git status exceeded the configured entry limit."]


@pytest.mark.parametrize(
    ("program", "expected"),
    [
        ("import time; time.sleep(30)", "timed out"),
        ("import os; os.write(1, b'x' * 1000000)", "byte limit"),
        ("import os; os.write(2, b'PRIVATE-SECRET' * 100000)", "byte limit"),
        ("import sys; print('PRIVATE-SECRET', file=sys.stderr); sys.exit(12)", "exit 12"),
    ],
)
def test_subprocess_time_and_output_are_bounded_and_diagnostics_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    program: str,
    expected: str,
) -> None:
    popen = subprocess.Popen

    def fake_git(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        return popen([sys.executable, "-c", program], **kwargs)

    monkeypatch.setattr(collector.subprocess, "Popen", fake_git)
    monkeypatch.setattr(collector, "COMMAND_TIMEOUT", 0.25)
    monkeypatch.setattr(collector, "MAX_OUTPUT_BYTES", 4096)
    started = time.monotonic()
    snapshot = collector.inspect_repository(tmp_path)
    assert time.monotonic() - started < 2
    assert not snapshot.available
    assert expected in snapshot.diagnostics[0]
    assert "PRIVATE-SECRET" not in snapshot.diagnostics[0]
    assert len(snapshot.diagnostics[0]) < 180


def test_discovery_respects_explicit_scope_generated_dirs_exclusions_and_symlinks(
    tmp_path: Path,
) -> None:
    root = tmp_path / "scope"
    direct = repo(root / "direct")
    nested = repo(root / "group" / "nested")
    linked = root / "linked"
    git(direct, "worktree", "add", "--detach", str(linked))
    repo(root / "node_modules" / "generated")
    repo(root / "excluded" / "omit")
    outside = repo(tmp_path / "outside" / "private")
    (root / "link-outside").symlink_to(outside, target_is_directory=True)
    (root / "cycle").symlink_to(root, target_is_directory=True)
    before = state(root)
    found = collector.discover_repositories([root, root], exclusions=["excluded"])
    assert found == sorted([direct.resolve(), nested.resolve(), linked.resolve()])
    assert state(root) == before
    assert collector.discover_repositories([]) == []
    assert collector.discover_repositories([root / "cycle", tmp_path / "missing"]) == []


def test_discovery_depth_and_directory_budgets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "scope"
    direct = repo(root / "direct")
    repo(root / "group" / "too-deep")
    monkeypatch.setattr(collector, "MAX_DISCOVERY_DEPTH", 1)
    assert collector.discover_repositories([root]) == [direct.resolve()]
    monkeypatch.setattr(collector, "MAX_DISCOVERY_DIRECTORIES", 1)
    assert collector.discover_repositories([root]) == []


def test_discovery_never_follows_a_git_marker_symlink(tmp_path: Path) -> None:
    outside = repo(tmp_path / "outside")
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / ".git").symlink_to(outside / ".git", target_is_directory=True)
    assert collector.discover_repositories([fake]) == []

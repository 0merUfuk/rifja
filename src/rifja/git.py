"""Bounded, read-only observations of explicitly selected local Git worktrees.

No remote lookup, lazy fetch, hook, filter, or submodule working-tree scan is
performed. Paths are kept verbatim; presentation layers must escape controls.
Discovery only returns .git-marker candidates; inspection validates Git trust.
"""

from __future__ import annotations

import fnmatch
import os
import selectors
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from .models import GitSnapshot

COMMAND_TIMEOUT = 5.0
SNAPSHOT_TIMEOUT = 15.0
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_COMMITS = 30
MAX_STATUS_ENTRIES = 5000
MAX_WORKTREES = 1000
MAX_DISCOVERY_DEPTH = 6
MAX_DISCOVERY_DIRECTORIES = 10_000
MAX_DISCOVERY_ENTRIES = 50_000
MAX_REPOSITORIES = 1000
SKIP_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        ".env",
        "venv",
        "env",
        "node_modules",
        "vendor",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        "dist",
        "build",
        "target",
        ".next",
        ".nuxt",
        ".cache",
        ".Trash",
        ".rifja",
        ".session-visualizer",  # Historical state remains excluded from discovery.
        ".ssh",
        ".aws",
        ".gnupg",
        ".codex",
    }
)

# These settings are inherited by any Git subprocesses Git itself creates.
_SAFE_CONFIG = (
    "core.hooksPath=/dev/null",
    "core.fsmonitor=false",
    "core.untrackedCache=false",
    "core.attributesFile=/dev/null",
    "diff.external=",
    "diff.trustExitCode=false",
    "submodule.recurse=false",
    "status.submoduleSummary=false",
    "maintenance.auto=false",
    "gc.auto=0",
    "color.ui=false",
)


class _GitError(Exception):
    """A bounded diagnostic without command output or repository secrets."""


def _environment() -> dict[str, str]:
    # Inherited GIT_CONFIG_*, GIT_DIR, GIT_WORK_TREE, GIT_EXEC_PATH, trace files,
    # and similar overrides must not redirect observation or execute helpers.
    # Keep normal global/system config: in particular, do not bypass safe.directory.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        GIT_OPTIONAL_LOCKS="0",
        GIT_TERMINAL_PROMPT="0",
        GIT_NO_LAZY_FETCH="1",
        GIT_NO_REPLACE_OBJECTS="1",
        GIT_ATTR_NOSYSTEM="1",
        LC_ALL="C",
    )
    return env


def _terminate(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def _run(
    path: Path,
    args: list[str],
    *,
    deadline: float,
    config: tuple[str, ...] = (),
    allowed_codes: tuple[int, ...] = (0,),
) -> tuple[int, bytes]:
    remaining = min(COMMAND_TIMEOUT, deadline - time.monotonic())
    if remaining <= 0:
        raise _GitError("Git observation timed out.")
    argv = ["git", "--no-pager", "--no-optional-locks"]
    for value in (*_SAFE_CONFIG, *config):
        argv.extend(("-c", value))
    argv.extend(("-C", os.fspath(path), *args))
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_environment(),
            start_new_session=True,
        )
    except OSError:
        raise _GitError("Git could not be started.") from None
    expires = time.monotonic() + remaining
    output = bytearray()
    total = 0
    completed = False
    try:
        assert process.stdout is not None and process.stderr is not None
        with selectors.DefaultSelector() as selector:
            for stream in (process.stdout, process.stderr):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            while selector.get_map():
                left = expires - time.monotonic()
                if left <= 0:
                    raise _GitError("Git observation timed out.")
                for key, _ in selector.select(left):
                    chunk = os.read(key.fd, min(65536, MAX_OUTPUT_BYTES + 1 - total))
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(chunk)
                    if total > MAX_OUTPUT_BYTES:
                        raise _GitError("Git output exceeded the configured byte limit.")
                    if key.fileobj is process.stdout:
                        output.extend(chunk)
            try:
                code = process.wait(timeout=max(0.001, expires - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise _GitError("Git observation timed out.") from None
        if code not in allowed_codes:
            raise _GitError(
                f"Git {args[0]} failed (exit {code}); repository may be unavailable or untrusted."
            )
        completed = True
        return code, bytes(output)
    finally:
        # Also kills a descendant that retained a pipe after its parent exited.
        if not completed:
            _terminate(process)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()


def _value(data: bytes) -> str:
    # strip()/splitlines() would corrupt valid paths containing whitespace.
    return os.fsdecode(data.removesuffix(b"\n"))


def _identity(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_dev}:{stat.st_ino}"


def _disabled_filters(path: Path, deadline: float) -> tuple[str, ...]:
    _, data = _run(
        path,
        [
            "config",
            "--null",
            "--name-only",
            "--get-regexp",
            r"^filter\..*\.(clean|smudge|process|required)$",
        ],
        deadline=deadline,
        allowed_codes=(0, 1),
    )
    settings: set[str] = set()
    for raw in data.split(b"\0"):
        if not raw:
            continue
        name = os.fsdecode(raw)
        if len(name) > 4096 or "\n" in name or "\r" in name:
            raise _GitError("Git filter configuration cannot be safely bounded.")
        driver = name.rsplit(".", 1)[0]
        settings.update(
            (
                f"{driver}.clean=",
                f"{driver}.smudge=",
                f"{driver}.process=",
                f"{driver}.required=false",
            )
        )
        if len(settings) > 1024:
            raise _GitError("Git filter configuration exceeded the configured entry limit.")
    return tuple(sorted(settings))


def _status(data: bytes) -> list[dict[str, str]]:
    if data and not data.endswith(b"\0"):
        raise _GitError("Git returned incomplete status data.")
    parts = iter(data.split(b"\0")[:-1])
    entries: list[dict[str, str]] = []
    for part in parts:
        if len(part) < 4 or part[2:3] != b" ":
            raise _GitError("Git returned malformed status data.")
        entry = {"code": part[:2].decode("ascii"), "path": os.fsdecode(part[3:])}
        if b"R" in part[:2] or b"C" in part[:2]:
            original = next(parts, None)
            if not original:
                raise _GitError("Git returned incomplete rename data.")
            entry["original_path"] = os.fsdecode(original)
        entries.append(entry)
        if len(entries) > MAX_STATUS_ENTRIES:
            raise _GitError("Git status exceeded the configured entry limit.")
    return entries


def _commits(data: bytes) -> list[dict[str, str]]:
    if not data:
        return []
    fields = data.removesuffix(b"\0").split(b"\0")
    if len(fields) % 4:
        raise _GitError("Git returned malformed commit data.")
    entries: list[dict[str, str]] = []
    for offset in range(0, len(fields), 4):
        revision, authored, committed, subject = fields[offset : offset + 4]
        entries.append(
            {
                "revision": revision.decode("ascii"),
                "author_time": authored.decode("ascii"),
                "committer_time": committed.decode("ascii"),
                "subject": subject.decode("utf-8", errors="replace"),
            }
        )
    return entries


def _worktrees(data: bytes) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    entry: dict[str, str] = {}
    for field in data.split(b"\0"):
        if not field:
            if entry:
                entries.append(entry)
                entry = {}
                if len(entries) > MAX_WORKTREES:
                    raise _GitError("Git worktrees exceeded the configured entry limit.")
            continue
        key, _, value = field.partition(b" ")
        label = {b"worktree": "path", b"HEAD": "head"}.get(key, key.decode("ascii"))
        entry[label] = os.fsdecode(value) if value else "true"
    return entries


def inspect_repository(path: Path | str) -> GitSnapshot:
    """Observe one existing worktree without updating it, including unborn HEAD.

    Failure preserves any completed fields, marks the snapshot unavailable, and
    adds a fixed-size diagnostic. Commit history is capped at MAX_COMMITS. The
    superproject's submodule revisions are checked, but submodule dirt is not.
    """
    snapshot = GitSnapshot(
        path=os.fspath(path),
        common_dir=None,
        git_dir=None,
        common_identity=None,
        worktree_identity=None,
        branch=None,
        head=None,
        status=[],
        commits=[],
        worktrees=[],
        observed_at=datetime.now(UTC).isoformat(),
    )
    deadline = time.monotonic() + SNAPSHOT_TIMEOUT
    try:
        root = Path(path).resolve(strict=True)
        snapshot.path = str(root)
        if not root.is_dir():
            raise _GitError("Repository path is not a directory.")
        _, data = _run(
            root, ["rev-parse", "--path-format=absolute", "--show-toplevel"], deadline=deadline
        )
        root = Path(_value(data)).resolve(strict=True)
        snapshot.path = str(root)
        _, data = _run(root, ["rev-parse", "--absolute-git-dir"], deadline=deadline)
        git_dir = Path(_value(data)).resolve(strict=True)
        _, data = _run(
            root, ["rev-parse", "--path-format=absolute", "--git-common-dir"], deadline=deadline
        )
        common_dir = Path(_value(data)).resolve(strict=True)
        snapshot.git_dir, snapshot.common_dir = str(git_dir), str(common_dir)
        snapshot.worktree_identity, snapshot.common_identity = (
            _identity(git_dir),
            _identity(common_dir),
        )
        config = _disabled_filters(root, deadline)
        if config:
            snapshot.diagnostics.append(
                "Configured content filters were disabled; status may differ from normal Git."
            )
        code, data = _run(
            root,
            ["symbolic-ref", "--quiet", "--short", "HEAD"],
            deadline=deadline,
            config=config,
            allowed_codes=(0, 1),
        )
        snapshot.branch = _value(data) if code == 0 else None
        code, data = _run(
            root,
            ["rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
            deadline=deadline,
            config=config,
            allowed_codes=(0, 1),
        )
        snapshot.head = _value(data) if code == 0 else None
        _, data = _run(
            root,
            [
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=normal",
                "--renames",
                "--ignore-submodules=dirty",
            ],
            deadline=deadline,
            config=config,
        )
        snapshot.status = _status(data)
        if snapshot.head is not None:
            _, data = _run(
                root,
                [
                    "log",
                    "-z",
                    f"--max-count={MAX_COMMITS + 1}",
                    "--no-show-signature",
                    "--no-ext-diff",
                    "--no-textconv",
                    "--format=tformat:%H%x00%aI%x00%cI%x00%s",
                    snapshot.head,
                    "--",
                ],
                deadline=deadline,
                config=config,
            )
            commits = _commits(data)
            snapshot.commits = commits[:MAX_COMMITS]
            if len(commits) > MAX_COMMITS:
                snapshot.diagnostics.append(
                    f"Commit history limited to {MAX_COMMITS} recent commits."
                )
        _, data = _run(
            root, ["worktree", "list", "--porcelain", "-z"], deadline=deadline, config=config
        )
        snapshot.worktrees = _worktrees(data)
    except _GitError as exc:
        snapshot.available = False
        snapshot.diagnostics.append(str(exc))
    except OSError, ValueError, UnicodeError, RuntimeError:
        snapshot.available = False
        snapshot.diagnostics.append(
            "Repository path or Git metadata is missing, inaccessible, or malformed."
        )
    return snapshot


def resolve_repository(path: Path | str) -> GitSnapshot | None:
    """Resolve an existing cwd; missing or unverifiable paths stay unresolved."""
    snapshot = inspect_repository(path)
    return snapshot if snapshot.common_identity is not None else None


def discover_repositories(roots: list[Path], exclusions: list[str] | None = None) -> list[Path]:
    """Find .git-marker candidates under explicit roots, without following links.

    Bounds are shared across all roots. Exclusions match directory basenames,
    paths relative to each explicit root, or absolute paths using shell globs.
    A directory containing .git is still traversed for nested repositories.
    """
    patterns = exclusions or []
    pending: list[tuple[Path, Path, int]] = []
    for raw in roots[:MAX_DISCOVERY_DIRECTORIES]:
        try:
            if raw.is_symlink() or not raw.is_dir():
                continue
            root = raw.resolve(strict=True)
            pending.append((root, root, 0))
        except OSError, RuntimeError:
            continue
    seen: set[tuple[int, int]] = set()
    found: set[Path] = set()
    examined = 0
    while pending and len(seen) < MAX_DISCOVERY_DIRECTORIES and examined < MAX_DISCOVERY_ENTRIES:
        directory, root, depth = pending.pop()
        relative = str(directory.relative_to(root))
        if directory.name in SKIP_DIRECTORIES or any(
            fnmatch.fnmatchcase(candidate, pattern)
            for pattern in patterns
            for candidate in (directory.name, relative, str(directory))
        ):
            continue
        try:
            stat = directory.stat(follow_symlinks=False)
            identity = (stat.st_dev, stat.st_ino)
            if identity in seen or directory.is_symlink():
                continue
            seen.add(identity)
            with os.scandir(directory) as children:
                for child in children:
                    examined += 1
                    if examined > MAX_DISCOVERY_ENTRIES:
                        break
                    if child.is_symlink():
                        continue
                    if child.name == ".git" and (
                        child.is_dir(follow_symlinks=False) or child.is_file(follow_symlinks=False)
                    ):
                        found.add(directory)
                        if len(found) >= MAX_REPOSITORIES:
                            return sorted(found)
                    elif (
                        depth < MAX_DISCOVERY_DEPTH
                        and child.name not in SKIP_DIRECTORIES
                        and child.is_dir(follow_symlinks=False)
                    ):
                        pending.append((Path(child.path), root, depth + 1))
        except OSError:
            continue
    return sorted(found)

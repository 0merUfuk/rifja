"""Opt-in, bounded working-tree documents with ordinary source provenance.

Document text is untrusted data. No document content becomes a command, a
configuration value, or permission to collect another path.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import sqlite3
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from . import git
from .models import Record
from .privacy import GENERATED, SENSITIVE, clean, excluded, symlink_component
from .store import Store
from .timeutil import now

if TYPE_CHECKING:
    from .ingest import Ingestor

PROVIDER = "project_document"
MAX_FILES = 128
MAX_BYTES = 1024 * 1024
MAX_DEPTH = 4
MAX_DIRECTORIES = 256
MAX_ENTRIES = 8192
MAX_PATTERNS = 32
MAX_SPECS = 128
MAX_SEGMENT = 3500
MAX_SECTIONS = 2048
MAX_DIAGNOSTICS = 30
SUPPORTED = {".md", ".markdown", ".txt"}
PRIVATE_DIRECTORIES = {
    "audit",
    "audits",
    "evidence",
    "artifacts",
    "generated",
    "coverage",
    "logs",
    "traces",
    "snapshots",
    "screenshots",
    "vendor",
    "target",
    "env",
}
DEFAULT_NAME = re.compile(
    r"^(?:readme|status|verification|architecture|decisions?|releases?)(?:[-_.].*)?$", re.IGNORECASE
)
HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _limits(patterns: Any, max_files: Any, max_bytes: Any, max_depth: Any) -> list[str] | None:
    for value, low, high in (
        (max_files, 1, MAX_FILES),
        (max_bytes, 1, MAX_BYTES),
        (max_depth, 0, MAX_DEPTH),
    ):
        if type(value) is not int or not low <= value <= high:
            raise ValueError("document_limit_out_of_range")
    if patterns is None:
        return None
    if not isinstance(patterns, list) or not 1 <= len(patterns) <= MAX_PATTERNS:
        raise ValueError("document_patterns_require_nonempty_bounded_list")
    for pattern in patterns:
        if (
            not isinstance(pattern, str)
            or not pattern
            or len(pattern) > 256
            or pattern.startswith(("/", "~"))
            or "\\" in pattern
            or ":" in pattern
            or any(ord(c) < 32 or ord(c) == 127 for c in pattern)
            or any(part in {"", ".", ".."} for part in pattern.split("/"))
            or len(pattern.split("/")) > MAX_DEPTH + 2
        ):
            raise ValueError("document_pattern_must_be_relative_and_bounded")
    return list(dict.fromkeys(patterns))


@dataclass
class _Root:
    path: Path
    worktree: dict[str, Any]
    root_identity: tuple[int, int]
    git_dir: Path
    common_dir: Path
    head: str | None

    def unchanged(self) -> bool:
        try:
            return (
                not symlink_component(self.path)
                and _identity(self.path) == self.root_identity
                and _identity_text(self.git_dir) == self.worktree["identity"]
                and _identity_text(self.common_dir) == self.worktree["common_identity"]
            )
        except OSError, ValueError:
            return False


def _identity(path: Path) -> tuple[int, int]:
    value = path.stat()
    return value.st_dev, value.st_ino


def _identity_text(path: Path) -> str:
    device, inode = _identity(path)
    return f"{device}:{inode}"


def _root(store: Store, project_id: str, worktree_id: str) -> _Root:
    row = store.db.execute(
        "SELECT w.*,p.common_identity FROM worktrees w JOIN projects p ON p.id=w.project_id "
        "WHERE w.id=? AND w.project_id=? AND w.active=1",
        (worktree_id, project_id),
    ).fetchone()
    if row is None:
        raise ValueError("document_requires_registered_active_worktree")
    worktree = dict(row)
    path = Path(worktree["path"])
    if not path.is_absolute() or symlink_component(path) or not path.is_dir():
        raise ValueError("document_worktree_unavailable")
    path = path.resolve(strict=True)
    root_identity = _identity(path)
    deadline = time.monotonic() + git.SNAPSHOT_TIMEOUT
    _, top = git._run(
        path, ["rev-parse", "--path-format=absolute", "--show-toplevel"], deadline=deadline
    )
    _, gd = git._run(path, ["rev-parse", "--absolute-git-dir"], deadline=deadline)
    _, cd = git._run(
        path, ["rev-parse", "--path-format=absolute", "--git-common-dir"], deadline=deadline
    )
    git_dir, common_dir = Path(git._value(gd)), Path(git._value(cd))
    if (
        Path(git._value(top)).resolve() != path
        or _identity_text(git_dir) != worktree["identity"]
        or _identity_text(common_dir) != worktree["common_identity"]
    ):
        raise ValueError("document_worktree_identity_changed")
    code, data = git._run(
        path,
        ["rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
        deadline=deadline,
        allowed_codes=(0, 1),
    )
    result = _Root(
        path, worktree, root_identity, git_dir, common_dir, git._value(data) if code == 0 else None
    )
    if not result.unchanged():
        raise ValueError("document_worktree_identity_changed")
    return result


def configure(
    store: Store,
    project_id: str,
    worktree_id: str,
    patterns: list[str] | None = None,
    max_files: int = 24,
    max_bytes: int = 131072,
    max_depth: int = 2,
) -> dict[str, Any]:
    """Enable collection for one exact registered worktree; never discover roots."""
    patterns = _limits(patterns, max_files, max_bytes, max_depth)
    with store.writer_lock(), store.transaction():
        _root(store, project_id, worktree_id)
        spec = {
            "project_id": project_id,
            "worktree_id": worktree_id,
            "patterns": patterns,
            "max_files": max_files,
            "max_bytes": max_bytes,
            "max_depth": max_depth,
        }
        specs = store.config("project_documents", [])
        specs = [item for item in specs if item.get("worktree_id") != worktree_id]
        if len(specs) >= MAX_SPECS:
            raise ValueError("document_worktree_limit")
        specs.append(spec)
        store.set_config("project_documents", specs)
        store.audit("project_documents_configure", worktree_id, spec)
    return spec


def _matches(parts: tuple[str, ...], pattern: tuple[str, ...], prefix: bool = False) -> bool:
    if not parts:
        return prefix or not pattern or all(p == "**" for p in pattern)
    if not pattern:
        return False
    if pattern[0] == "**":
        return _matches(parts, pattern[1:], prefix) or _matches(parts[1:], pattern, prefix)
    return fnmatch.fnmatchcase(parts[0], pattern[0]) and _matches(parts[1:], pattern[1:], prefix)


def _selected(relative: Path, patterns: list[str] | None) -> bool:
    if patterns is not None:
        return any(_matches(relative.parts, tuple(p.split("/"))) for p in patterns)
    return (len(relative.parts) == 1 or relative.parts[0].lower() == "docs") and bool(
        DEFAULT_NAME.fullmatch(relative.stem)
    )


def _private(relative: Path, directory: bool) -> bool:
    parts = relative.parts if directory else relative.parts[:-1]
    if any(
        p.startswith(".") or p.lower() in PRIVATE_DIRECTORIES | GENERATED | SENSITIVE for p in parts
    ):
        return True
    name = relative.name.lower()
    return (
        name.startswith((".", "credentials", "secrets"))
        or name in SENSITIVE
        or name.endswith((".pem", ".key"))
    )


def _directory_fd(path: Path) -> int:
    """Pin every directory component, including when ancestors are replaced."""
    import sys

    parts = path.absolute().parts[1:]
    if sys.platform == "darwin" and parts and parts[0] in {"var", "tmp", "etc"}:
        parts = ("private", *parts)
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _diagnostic(code: str, worktree_id: str, relative: Path | None = None) -> dict[str, Any]:
    value = {"code": code, "provider": PROVIDER, "worktree_id": worktree_id}
    if relative is not None:
        value["relative_path"] = str(relative)
    return clean(value)


def _discover(
    root: _Root, spec: dict[str, Any], store: Store, diagnostics: list[dict[str, Any]]
) -> list[Path]:
    """Bound entries before sorting; never walk arbitrary repository subtrees."""
    found: list[Path] = []
    pending = [Path()]
    examined = directories = 0
    wid = root.worktree["id"]
    patterns = spec["patterns"]
    exclusions = store.config("exclusions", [])

    def report(code: str, relative: Path | None = None) -> None:
        if len(diagnostics) < MAX_DIAGNOSTICS:
            diagnostics.append(_diagnostic(code, wid, relative))

    while pending:
        if directories >= MAX_DIRECTORIES or examined >= MAX_ENTRIES:
            report("document_discovery_limit")
            break
        relative_dir = pending.pop()
        directory = root.path / relative_dir
        fd = _directory_fd(directory)
        try:
            directories += 1
            if relative_dir.parts:
                try:
                    os.stat(".git", dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    report("document_nested_repository_excluded", relative_dir)
                    continue
            entries = []
            with os.scandir(fd) as scan:
                for entry in scan:
                    examined += 1
                    if examined > MAX_ENTRIES:
                        report("document_discovery_limit")
                        break
                    entries.append(entry)
            for entry in sorted(entries, key=lambda e: e.name):
                relative = relative_dir / entry.name
                directory_entry = entry.is_dir(follow_symlinks=False)
                if _private(relative, directory_entry):
                    if patterns is not None and any(
                        _matches(relative.parts, tuple(p.split("/")), directory_entry)
                        for p in patterns
                    ):
                        report("document_path_excluded", relative)
                    continue
                if excluded(root.path / relative, store.home, exclusions):
                    if _selected(relative, patterns):
                        report("document_path_excluded", relative)
                    continue
                if entry.is_symlink():
                    if _selected(relative, patterns):
                        report("document_symlink_excluded", relative)
                    continue
                if directory_entry:
                    relevant = (
                        relative.parts[0].lower() == "docs"
                        if patterns is None
                        else any(
                            _matches(relative.parts, tuple(p.split("/")), True) for p in patterns
                        )
                    )
                    if relevant:
                        if len(relative.parts) <= spec["max_depth"]:
                            pending.append(relative)
                        else:
                            report("document_depth_limit", relative)
                elif _selected(relative, patterns):
                    if not entry.is_file(follow_symlinks=False):
                        report("document_nonregular_excluded", relative)
                        continue
                    if len(found) >= spec["max_files"]:
                        report("document_file_limit")
                        return sorted(found)
                    found.append(relative)
        finally:
            os.close(fd)
    if patterns is not None:
        for pattern in patterns:
            if not any(_matches(p.parts, tuple(pattern.split("/"))) for p in found):
                report("document_pattern_unmatched", Path(pattern))
    return sorted(found)


def _signature(value: os.stat_result) -> str:
    return json.dumps(
        [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]
    )


def _read(root: _Root, relative: Path, max_bytes: int) -> tuple[bytes, str, str]:
    if not root.unchanged():
        raise ValueError("document_worktree_identity_changed")
    parent = _directory_fd(root.path)
    try:
        for part in relative.parent.parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
            try:
                os.stat(".git", dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValueError("document_nested_repository_excluded")
        fd = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, "rb") as stream:
            start = os.fstat(stream.fileno())
            if not stat.S_ISREG(start.st_mode):
                raise ValueError("document_nonregular_excluded")
            if start.st_size > max_bytes:
                raise ValueError("document_byte_limit")
            data = stream.read(max_bytes + 1)
            end = os.fstat(stream.fileno())
            current = os.stat(relative.name, dir_fd=parent, follow_symlinks=False)
            if len(data) > max_bytes:
                raise ValueError("document_byte_limit")
            if _signature(start) != _signature(end) or _signature(end) != _signature(current):
                raise ValueError("document_changed_during_read")
            if not root.unchanged():
                raise ValueError("document_worktree_identity_changed")
            return data, _signature(start), f"{start.st_dev}:{start.st_ino}"
    finally:
        os.close(parent)


def _sections(text: str) -> list[dict[str, Any]]:
    """Keep paragraph conditions together; split only overlong blocks."""
    lines = text.splitlines(keepends=True)
    result: list[dict[str, Any]] = []
    headings: list[tuple[int, str]] = []
    block: list[tuple[int, str]] = []
    fence: str | None = None
    block_context = "prose"
    skip_underline = False
    comment = False
    lazy_quote = False

    def flush() -> None:
        nonlocal block
        if not block or not any(line.strip() for _, line in block):
            block = []
            return
        chunks: list[tuple[str, int, int]] = []
        content = ""
        start = end = block[0][0]
        for line_no, line in block:
            while line:
                if len(content) == MAX_SEGMENT:
                    chunks.append((content, start, end))
                    content = ""
                if not content:
                    start = line_no
                room = MAX_SEGMENT - len(content)
                if content and len(line) > room and len(line) <= MAX_SEGMENT:
                    chunks.append((content, start, end))
                    content = ""
                    start, room = line_no, MAX_SEGMENT
                content += line[:room]
                end = line_no
                line = line[room:]
        if content:
            chunks.append((content, start, end))
        for content, start, end in chunks:
            if content.strip():
                result.append(
                    {
                        "text": content.rstrip("\r\n"),
                        "section": " > ".join(h for _, h in headings),
                        "line_start": start,
                        "line_end": end,
                        "source_context": block_context,
                    }
                )
                if len(result) > MAX_SECTIONS:
                    raise ValueError("document_section_limit")
        block = []

    for index, line in enumerate(lines):
        if skip_underline:
            skip_underline = False
            continue
        number = index + 1
        if "<!--" in line or comment:
            if not comment:
                flush()
            comment = True
            block_context = "quote"
            block.append((number, line))
            if "-->" in line:
                comment = False
                flush()
            continue
        marker = FENCE.match(line)
        heading = HEADING.match(line) if fence is None else None
        setext = (
            fence is None
            and not marker
            and line.strip()
            and not re.match(r"^(?: {4}|\t| {0,3}>)", line)
            and index + 1 < len(lines)
            and re.fullmatch(r" {0,3}(?:=+|-+)\s*", lines[index + 1])
        )
        if heading or setext:
            flush()
            if heading:
                level, title = len(heading[1]), heading[2]
            else:
                level = 1 if lines[index + 1].lstrip().startswith("=") else 2
                title = line.strip()
                skip_underline = True
            headings[:] = [(depth, name) for depth, name in headings if depth < level]
            headings.append((level, title))
            continue
        if marker and fence is None:
            flush()
            fence = marker[1]
            block_context = "code"
        elif fence is None:
            if not line.strip():
                lazy_quote = False
            elif re.match(r"^ {0,3}>", line):
                lazy_quote = True
            context = (
                "code" if re.match(r"^(?: {4}|\t)", line) else "quote" if lazy_quote else "prose"
            )
            if block and context != block_context and line.strip():
                flush()
            if not block:
                block_context = context
        if fence is None and not line.strip():
            flush()
            continue
        block.append((number, line))
        if (
            fence is not None
            and marker
            and marker[1][0] == fence[0]
            and len(marker[1]) >= len(fence)
            and len(block) > 1
            and not line[marker.end() :].strip()
        ):
            fence = None
            flush()
    flush()
    counts: dict[str, int] = {}
    for value in result:
        section = value["section"]
        counts[section] = counts.get(section, 0) + 1
        value["segment_order"] = counts[section]
    for value in result:
        value["segment_count"] = counts[value["section"]]
    return result


def _git_metadata(root: _Root, relative: Path, data: bytes) -> dict[str, Any]:
    value: dict[str, Any] = {
        "git_head": root.head,
        "committed_blob": "unknown",
        "tracked": "unknown",
        "modified": "unknown",
    }
    deadline = time.monotonic() + git.COMMAND_TIMEOUT
    literal = ":(literal)" + relative.as_posix()
    try:
        _, index = git._run(
            root.path, ["ls-files", "--stage", "-z", "--", literal], deadline=deadline
        )
        value["tracked"] = bool(index)
        if root.head:
            _, tree = git._run(
                root.path, ["ls-tree", "-z", root.head, "--", literal], deadline=deadline
            )
            entries = [entry.split(b"\t", 1) for entry in tree.split(b"\0") if entry]
            if len(entries) == 1 and entries[0][1] == os.fsencode(relative.as_posix()):
                mode, kind, oid = entries[0][0].split(b" ")
                if kind == b"blob" and mode in {b"100644", b"100755"}:
                    value["committed_blob"] = oid.decode("ascii")
        blob = value["committed_blob"]
        if blob != "unknown":
            hasher = hashlib.sha1 if len(blob) == 40 else hashlib.sha256
            raw_blob = hasher(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            value["modified"] = raw_blob != blob
            value["modified_basis"] = "raw_working_tree_bytes_vs_committed_blob"
        elif value["tracked"] is False:
            value["modified"] = True
    except git._GitError, OSError, ValueError, IndexError, UnicodeError:
        pass
    return value


def _source_for(store: Store, root: _Root, relative: Path, identity: str) -> dict[str, Any] | None:
    path = str(root.path / relative)
    occupied = store.db.execute(
        "SELECT * FROM sources WHERE provider=? AND path=?", (PROVIDER, path)
    ).fetchone()
    if occupied and _context(occupied["context"]).get("worktree_id") != root.worktree["id"]:
        raise ValueError("document_source_identity_conflict")
    if occupied:
        return dict(occupied)
    # Registration follows a moved worktree; same relative document stays logical.
    moved = store.rows(
        "SELECT * FROM sources WHERE provider=? AND json_extract(context,'$.worktree_id')=? "
        "AND json_extract(context,'$.relative_path')=? AND json_extract(context,'$.root_path')!=? "
        "LIMIT 2",
        (PROVIDER, root.worktree["id"], str(relative), str(root.path)),
    )
    if len(moved) == 1:
        return moved[0]
    same_inode = store.rows(
        "SELECT * FROM sources WHERE provider=? AND identity=? "
        "AND json_extract(context,'$.worktree_id')=? LIMIT ?",
        (PROVIDER, identity, root.worktree["id"], MAX_FILES + 1),
    )
    if len(same_inode) > MAX_FILES:
        return None
    candidates = []
    for source in same_inode:
        previous = Path(str(_context(source["context"]).get("relative_path", "")))
        if previous.is_absolute() or ".." in previous.parts:
            continue
        if not (root.path / previous).exists():
            candidates.append(source)
    return candidates[0] if len(candidates) == 1 else None


def _context(raw: str) -> dict[str, Any]:
    """Canonical schema does not authenticate restored JSON field types."""
    try:
        value = json.loads(raw)
    except ValueError, TypeError:
        raise ValueError("document_source_context_invalid") from None
    if not isinstance(value, dict):
        # Invalid serialized data is handled like malformed JSON by the caller.
        raise ValueError("document_source_context_invalid")  # noqa: TRY004
    if "git_metadata" in value and not isinstance(value["git_metadata"], dict):
        raise ValueError("document_source_context_invalid")
    if "prior_paths" in value and (
        not isinstance(value["prior_paths"], list)
        or not all(isinstance(v, str) for v in value["prior_paths"])
    ):
        raise ValueError("document_source_context_invalid")
    return value


def _refresh_one(
    ingestor: Ingestor,
    root: _Root,
    spec: dict[str, Any],
    relative: Path,
    verify: bool,
    rebuild: bool,
) -> bool:
    """Return whether a known document moved; source/records commit together."""
    store = ingestor.store
    path = root.path / relative
    if path.suffix.lower() not in SUPPORTED and path.name.lower() != "readme":
        raise ValueError("document_unsupported_format")
    # Stat only selected paths; reads use pinned no-follow descriptors below.
    st = path.stat(follow_symlinks=False)
    if st.st_size > spec["max_bytes"]:
        raise ValueError("document_byte_limit")
    signature, identity = _signature(st), f"{st.st_dev}:{st.st_ino}"
    source = _source_for(store, root, relative, identity)
    if (
        source
        and source["signature"] == signature
        and source["path"] == str(path)
        and source["status"] == "ready"
        and not verify
        and not rebuild
    ):
        ingestor.stats["unchanged"] += 1
        return False
    data, signature, identity = _read(root, relative, spec["max_bytes"])
    if b"\0" in data:
        raise ValueError("document_binary_unsupported")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError:
        raise ValueError("document_encoding_unsupported") from None
    fingerprint = hashlib.sha256(data).hexdigest()
    context = _context(source["context"]) if source else {}
    moved = bool(source and source["path"] != str(path))
    same = bool(
        source and source["generation"] and context.get("fingerprint") == fingerprint and not moved
    )
    if same and not rebuild:
        assert source is not None
        with store.transaction():
            store.db.execute(
                "UPDATE sources SET signature=?,identity=?,status='ready',"
                "diagnostics='[]',last_refresh=? WHERE id=?",
                (signature, identity, now(), source["id"]),
            )
        ingestor.stats["unchanged"] += 1
        return False
    observed_at = context.get("observed_at") if same else now()
    git_metadata = context.get("git_metadata", {}) if same else _git_metadata(root, relative, data)
    source_id = source["id"] if source else uuid4().hex
    prior_paths = context.get("prior_paths", [])
    if moved and source:
        prior_paths = (prior_paths + [source["path"]])[-16:]
    context = {
        "document_id": source_id,
        "project_id": root.worktree["project_id"],
        "worktree_id": root.worktree["id"],
        "relative_path": str(relative),
        "root_path": str(root.path),
        "fingerprint": fingerprint,
        "observed_at": observed_at,
        "git_metadata": git_metadata,
        "prior_paths": prior_paths,
    }
    before = dict(ingestor.stats)
    try:
        with store.transaction():
            if not root.unchanged():
                raise ValueError("document_worktree_identity_changed")
            if source is None:
                store.db.execute(
                    "INSERT INTO sources(id,provider,path,identity,status) VALUES(?,?,?,?,'new')",
                    (source_id, PROVIDER, str(path), identity),
                )
                source = dict(
                    store.db.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
                )
            generation = ingestor.generation(source, not same)
            for number, section in enumerate(_sections(text)):
                value = dict(section)
                content = value.pop("text")
                metadata = {
                    "document_id": source_id,
                    "relative_path": str(relative),
                    "fingerprint": fingerprint,
                    "observed_at": observed_at,
                    "content_scope": "working_tree",
                    **git_metadata,
                    **value,
                }
                record = Record(
                    PROVIDER,
                    source_id,
                    f"section:{number}",
                    "document",
                    "document_section",
                    content,
                    cwd=str(root.path),
                    metadata=metadata,
                )
                ingestor.stats["parsed_records"] += 1
                ingestor.record(
                    record,
                    generation,
                    f"{relative}:lines:{value['line_start']}-{value['line_end']}:segment:{number}",
                )
            if not root.unchanged() or _signature(path.stat(follow_symlinks=False)) != signature:
                raise ValueError("document_changed_during_read")
            store.db.execute(
                "UPDATE sources SET path=?,identity=?,signature=?,status='ready',"
                "context=?,last_refresh=?,diagnostics='[]' WHERE id=?",
                (str(path), identity, signature, json.dumps(clean(context)), now(), source_id),
            )
    except BaseException:
        ingestor.stats.update(before)
        raise
    return moved


def refresh_documents(
    ingestor: Ingestor, seen: set[str], verify: bool = False, rebuild: bool = False
) -> list[dict[str, Any]]:
    """Run inside the Ingestor writer lock, before its missing-source sweep."""
    store = ingestor.store
    diagnostics: list[dict[str, Any]] = []
    specs = store.config("project_documents", [])
    if not isinstance(specs, list):
        ingestor.stats["partial"] += 1
        return [{"code": "document_configuration_invalid", "provider": PROVIDER}]
    if len(specs) > MAX_SPECS:
        ingestor.stats["partial"] += 1
        diagnostics.append({"code": "document_worktree_limit", "provider": PROVIDER})
    for spec in specs[:MAX_SPECS]:
        wid = str(spec.get("worktree_id", "unknown")) if isinstance(spec, dict) else "unknown"
        try:
            if not isinstance(spec, dict):
                raise TypeError("document_configuration_invalid")
            spec = {"patterns": None, "max_files": 24, "max_bytes": 131072, "max_depth": 2, **spec}
            if not all(
                isinstance(spec.get(key), str) and spec[key]
                for key in ("project_id", "worktree_id")
            ):
                raise ValueError("document_configuration_invalid")
            _limits(spec["patterns"], spec["max_files"], spec["max_bytes"], spec["max_depth"])
            root = _root(store, spec["project_id"], spec["worktree_id"])
            discovery_diagnostics: list[dict[str, Any]] = []
            paths = _discover(root, spec, store, discovery_diagnostics)
            if discovery_diagnostics:
                ingestor.stats["partial"] += 1
                diagnostics.extend(discovery_diagnostics)
            for relative in paths:
                key = PROVIDER + ":" + str(root.path / relative)
                if key in seen:
                    continue
                seen.add(key)
                ingestor.stats["sources"] += 1
                try:
                    moved = _refresh_one(ingestor, root, spec, relative, verify, rebuild)
                    if moved:
                        diagnostics.append(_diagnostic("document_moved", wid, relative))
                except (OSError, ValueError, sqlite3.Error, git._GitError) as exc:
                    ingestor.stats["partial"] += 1
                    code = str(exc) if isinstance(exc, ValueError) else "document_read_failed"
                    diagnostics.append(_diagnostic(code, wid, relative))
                    # Keep even unsupported/oversized selected paths visible in coverage.
                    with store.transaction():
                        sid = uuid4().hex
                        context = {
                            "document_id": sid,
                            "worktree_id": wid,
                            "project_id": spec["project_id"],
                            "root_path": str(root.path),
                            "relative_path": str(relative),
                        }
                        store.db.execute(
                            "INSERT OR IGNORE INTO sources(id,provider,path,status,context) "
                            "VALUES(?,?,?,'partial',?)",
                            (sid, PROVIDER, str(root.path / relative), json.dumps(context)),
                        )
                        store.db.execute(
                            "UPDATE sources SET status='partial',diagnostics=? "
                            "WHERE provider=? AND path=?",
                            (
                                json.dumps([_diagnostic(code, wid, relative)]),
                                PROVIDER,
                                str(root.path / relative),
                            ),
                        )
        except (OSError, ValueError, KeyError, TypeError, git._GitError) as exc:
            ingestor.stats["partial"] += 1
            code = str(exc) if isinstance(exc, ValueError) else "document_worktree_unavailable"
            diagnostics.append(_diagnostic(code, wid))
        diagnostics = diagnostics[:MAX_DIAGNOSTICS]
    return diagnostics[:MAX_DIAGNOSTICS]

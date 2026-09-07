"""Explicit, incremental source refresh with atomic checkpoints and provenance."""

import hashlib
import json
import os
import sqlite3
from collections.abc import Iterator
from dataclasses import asdict
from dataclasses import fields as dataclass_fields
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import __version__, adapters
from .compressed import iter_zstd_lines
from .extract import ExtractionLimitError, extract
from .git import resolve_repository
from .models import Candidate, Diagnostic, Record
from .privacy import (
    MAX_EXCERPT,
    MAX_RECORD_BYTES,
    clean,
    clean_text,
    digest,
    excluded,
    open_regular,
    parse_json,
    symlink_component,
    within,
)
from .store import Store
from .timeutil import normalize, now

_RECORD_FIELDS = tuple(field.name for field in dataclass_fields(Record))
_CANDIDATE_FIELDS = tuple(field.name for field in dataclass_fields(Candidate))


def _clean_fields(value: Record | Candidate, names: tuple[str, ...]) -> dict[str, Any]:
    # These keys are fixed application schema, not imported text. Clean every
    # value at the same depth as clean(asdict(value)), including nested keys.
    # Avoid deep-copying then scanning the same fixed keys for every record.
    return {name: clean(getattr(value, name), depth=1) for name in names}


def source_signature(path: Path) -> str:
    def stat(p: Path) -> list[int] | None:
        try:
            s = p.stat()
            return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]
        except FileNotFoundError:
            return None

    return json.dumps(
        [
            stat(path),
            stat(Path(str(path) + "-wal"))
            if path.suffix in {".db", ".sqlite", ".sqlite3"}
            else None,
        ]
    )


def iter_sources(root: Path, state: Path, exclusions: list[str]) -> Iterator[Path]:
    if excluded(root, state, exclusions):
        return
    if root.is_file():
        yield root
        return
    count = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        path = Path(directory)
        dirs[:] = sorted(
            d
            for d in dirs
            if not excluded(path / d, state, exclusions)
            and len((path / d).relative_to(root).parts) <= 16
        )
        for name in sorted(files):
            candidate = path / name
            if not candidate.is_file():
                continue
            if excluded(candidate, state, exclusions) or not within(candidate, root):
                continue
            if candidate.suffix not in {".jsonl", ".db", ".sqlite", ".sqlite3", ".zst"}:
                continue
            count += 1
            if count > 100_000:
                raise ValueError("source_discovery_limit")
            yield candidate


def prefix_hash(stream: Any, length: int) -> str:
    h = hashlib.sha256()
    stream.seek(0)
    left = length
    while left:
        part = stream.read(min(left, 1024 * 1024))
        if not part:
            break
        h.update(part)
        left -= len(part)
    return h.hexdigest()


class Ingestor:
    def __init__(self, store: Store):
        self.store = store
        self.association_cache: dict[str, tuple[str | None, str | None, str]] = {}
        self.stats: dict[str, int] = {}
        self.rebuild = False

    def associate(
        self, cwd: str | None, session_id: str, record_id: str
    ) -> tuple[str | None, str | None, str]:
        explicit = self.store.db.execute(
            "SELECT * FROM associations WHERE target IN (?,?) ORDER BY created_at DESC LIMIT 1",
            (record_id, session_id),
        ).fetchone()
        if explicit:
            return explicit["project_id"], explicit["worktree_id"], "explicit_user_mapping"
        if not cwd:
            return None, None, "missing_working_context"
        if cwd in self.association_cache:
            return self.association_cache[cwd]
        from .identity import local_recorded_path

        normalized = local_recorded_path(cwd) if cwd.startswith("file:") else cwd
        if normalized is None:
            return None, None, "invalid_local_working_context"
        path = Path(normalized).expanduser()
        if cwd.startswith("file:") and symlink_component(path):
            return None, None, "symlink_working_context"
        if not path.is_absolute():
            return None, None, "relative_working_context"
        if not path.is_dir():
            return None, None, "missing_working_directory"
        matches = [
            w for w in self.store.rows("SELECT * FROM worktrees") if within(path, Path(w["path"]))
        ]
        if matches:
            nearest = max(matches, key=lambda w: len(Path(w["path"]).parts))
            observed = resolve_repository(path)
            if (
                observed
                and observed.available
                and observed.worktree_identity == nearest["identity"]
            ):
                result = (nearest["project_id"], nearest["id"], "recorded_cwd_registered_worktree")
            else:
                result = (None, None, "working_directory_identity_unresolved")
        else:
            result = (None, None, "unregistered_working_context")
        self.association_cache[cwd] = result
        return result

    def _copy_overrides(self, old: str, new: str) -> None:
        """Retain overrides when replaying an unchanged pre-rc2 long record."""
        for table, fields in (
            ("corrections", "text,status,reason,created_at"),
            ("associations", "project_id,worktree_id,reason,created_at"),
        ):
            for row in self.store.rows(f"SELECT id FROM {table} WHERE target=?", (old,)):
                self.store.db.execute(
                    f"INSERT OR IGNORE INTO {table}(id,target,{fields}) SELECT ?,?,{fields} FROM {table} WHERE id=?",
                    (digest("long_record_upgrade", row["id"], new), new, row["id"]),
                )

    def record(
        self, raw: Record, generation: int, locator: str, migrate_legacy: bool = False
    ) -> None:
        value = _clean_fields(raw, _RECORD_FIELDS)
        # Classification sees the bounded, redacted record, not only its display
        # excerpt. Hash the complete redacted text so edits beyond the excerpt
        # still get distinct source evidence identities.
        extraction_text = (
            clean_text(raw.text, MAX_RECORD_BYTES) if len(raw.text) > MAX_EXCERPT else value["text"]
        )
        session_native = value["session_id"]
        provider = value["provider"]
        if self.store.db.execute(
            "SELECT 1 FROM forgotten WHERE provider=? AND session_id=?", (provider, session_native)
        ).fetchone():
            self.stats["forgotten_records"] += 1
            return
        session_id = digest(provider, session_native)
        self.store.db.execute(
            "INSERT OR IGNORE INTO sessions VALUES(?,?,?)", (session_id, provider, session_native)
        )
        identity = [
            provider,
            session_native,
            value["native_id"],
            value["actor"],
            value["kind"],
            value["timestamp"],
            extraction_text,
            value["cwd"],
            value["metadata"],
        ]
        rid = digest(*identity)
        legacy_id = rid
        legacy_ids = []
        if (
            migrate_legacy
            and value["metadata"].get("execution_source") == "native_command_execution"
        ):
            old_identity = list(identity)
            old_identity[-1] = {
                k: v
                for k, v in value["metadata"].items()
                if k not in {"execution_source", "context_cwd"}
            }
            legacy_ids.append(digest(*old_identity))
            if extraction_text != value["text"]:
                old_identity[6] = value["text"]
                legacy_ids.append(digest(*old_identity))
        if extraction_text != value["text"]:
            identity[6] = value["text"]
            legacy_ids.append(digest(*identity))
        if migrate_legacy:
            for candidate_id in legacy_ids:
                if (
                    candidate_id != rid
                    and self.store.db.execute(
                        "SELECT 1 FROM occurrences o JOIN generations old ON old.id=o.generation_id JOIN generations current ON current.source_id=old.source_id WHERE o.record_id=? AND current.id=? LIMIT 1",
                        (candidate_id, generation),
                    ).fetchone()
                ):
                    legacy_id = candidate_id
                    break
        migrate_legacy = migrate_legacy and legacy_id != rid
        if migrate_legacy:
            self._copy_overrides(legacy_id, rid)
        event_time, time_status = normalize(value["timestamp"])
        project, worktree, reason = self.associate(value["cwd"], session_id, rid)
        changed = self.store.db.execute(
            "INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                rid,
                session_id,
                value["native_id"],
                provider,
                value["actor"],
                value["kind"],
                value["text"],
                event_time,
                value["timestamp"],
                time_status,
                value["cwd"],
                json.dumps(value["metadata"], ensure_ascii=False),
                project,
                worktree,
                reason,
                now(),
            ),
        )
        # INSERT specifies sixteen columns; schema intentionally has no derived truth flags.
        if changed.rowcount:
            self.stats["inserted_records"] += 1
        self.store.db.execute(
            "INSERT OR IGNORE INTO occurrences VALUES(?,?,?)", (rid, generation, locator)
        )
        if changed.rowcount or self.rebuild:
            extracted_record = Record(**value)
            extracted_record.text = extraction_text
            candidates = extract(extracted_record)
            old_candidates = (
                self.store.rows("SELECT id,text FROM items WHERE record_id=?", (rid,))
                if self.rebuild
                else []
            )
            if self.rebuild:
                self.store.db.execute("DELETE FROM items WHERE record_id=?", (rid,))
            for i, candidate in enumerate(candidates):
                item = _clean_fields(candidate, _CANDIDATE_FIELDS)
                item_id = digest(rid, i, item)
                self.store.db.execute(
                    "INSERT OR IGNORE INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        item_id,
                        rid,
                        item["kind"],
                        item["text"],
                        item["status"],
                        item["category"],
                        item["target"],
                        item["rationale"],
                        item["priority"],
                        json.dumps(item["dependencies"]),
                        item["method"],
                    ),
                )
                same_text = [old for old in old_candidates if old["text"] == item["text"]]
                if len(same_text) == 1 and same_text[0]["id"] != item_id:
                    self._copy_overrides(same_text[0]["id"], item_id)
                if migrate_legacy:
                    # Only transfer item-specific edits when the old derived
                    # item is identical; newly recovered intent has no prior approval.
                    old_items = self.store.rows(
                        "SELECT id FROM items WHERE record_id=? AND kind=? AND text=? AND category=? AND target IS ? AND rationale IS ? AND priority IS ? AND dependencies=?",
                        (
                            legacy_id,
                            item["kind"],
                            item["text"],
                            item["category"],
                            item["target"],
                            item["rationale"],
                            item["priority"],
                            json.dumps(item["dependencies"]),
                        ),
                    )
                    if len(old_items) == 1:
                        self._copy_overrides(old_items[0]["id"], item_id)
                if item["kind"] == "principle":
                    mid = digest("proposed_principle", rid, item["text"])
                    self.store.db.execute(
                        "INSERT OR IGNORE INTO memory VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            mid,
                            "principle",
                            item["text"],
                            "proposed",
                            "inferred",
                            project or "unassociated",
                            json.dumps([rid]),
                            "Explicit source statement proposed for acceptance; source content grants no authority.",
                            now(),
                            now(),
                            None,
                            None,
                            None,
                        ),
                    )

    def refresh(self, verify: bool = False, rebuild: bool = False) -> dict[str, Any]:
        pipeline = __version__ + ":prose-v1:documents-v1:redaction-v1"
        previous = self.store.config("pipeline_version")
        rebuild = rebuild or (previous is not None and previous != pipeline)
        self.rebuild = rebuild
        self.stats = {
            "sources": 0,
            "unchanged": 0,
            "parsed_records": 0,
            "inserted_records": 0,
            "forgotten_records": 0,
            "partial": 0,
            "failed": 0,
            "missing": 0,
        }
        errors: list[dict[str, Any]] = []
        started = now()
        configured = self.store.config("sources", [])
        exclusions = self.store.config("exclusions", [])
        seen: set[str] = set()
        with self.store.writer_lock():
            run = self.store.db.execute(
                "INSERT INTO refresh_runs(started_at,status,stats) VALUES(?, 'running', '{}')",
                (started,),
            ).lastrowid
            try:
                for spec in configured:
                    root = Path(spec["path"])
                    if (
                        not root.exists()
                        or root.is_symlink()
                        or excluded(root, self.store.home, exclusions)
                    ):
                        self.stats["partial"] += 1
                        errors.append(
                            {
                                "code": "source_root_unavailable_or_excluded",
                                "provider": spec["provider"],
                            }
                        )
                        continue
                    try:
                        for path in iter_sources(root, self.store.home, exclusions):
                            provider = spec["provider"]
                            key = provider + ":" + str(path)
                            if key in seen:
                                continue
                            seen.add(key)
                            self.stats["sources"] += 1
                            self.refresh_source(provider, path, verify, rebuild)
                    except (OSError, ValueError, sqlite3.Error) as exc:
                        self.stats["failed"] += 1
                        errors.append({"code": type(exc).__name__, "provider": spec["provider"]})
                from .documents import refresh_documents
                from .identity import reconcile_moves

                errors.extend(refresh_documents(self, seen, verify, rebuild))
                for source in self.store.rows("SELECT * FROM sources"):
                    if source["provider"] + ":" + source["path"] not in seen:
                        state = (
                            "excluded"
                            if excluded(Path(source["path"]), self.store.home, exclusions)
                            else "missing"
                        )
                        self.store.db.execute(
                            "UPDATE sources SET status=? WHERE id=?", (state, source["id"])
                        )
                        self.stats["missing"] += 1
                with self.store.transaction():
                    identity_report = reconcile_moves(self.store)
                status = (
                    "partial"
                    if any(self.stats[k] for k in ("partial", "failed", "missing"))
                    else "passed"
                )
                report = {
                    **self.stats,
                    "diagnostics": errors[:30],
                    "started_at": started,
                    "finished_at": now(),
                    "status": status,
                    "identity": identity_report,
                }
                self.store.db.execute(
                    "UPDATE refresh_runs SET ended_at=?,status=?,stats=? WHERE id=?",
                    (report["finished_at"], status, json.dumps(report), run),
                )
                self.store.set_config(
                    "last_refreshed_scope",
                    {
                        "sources": configured,
                        "exclusions": exclusions,
                        "project_documents": self.store.config("project_documents", []),
                    },
                )
                if not self.stats["failed"] and not self.stats["missing"]:
                    self.store.set_config("pipeline_version", pipeline)
                return report
            except BaseException:
                self.store.db.execute(
                    "UPDATE refresh_runs SET ended_at=?,status='interrupted' WHERE id=?",
                    (now(), run),
                )
                raise

    def refresh_source(self, provider: str, path: Path, verify: bool, rebuild: bool) -> None:
        signature = source_signature(path)
        st = path.stat()
        identity = f"{st.st_dev}:{st.st_ino}"
        source = self.store.db.execute(
            "SELECT * FROM sources WHERE provider=? AND path=?", (provider, str(path))
        ).fetchone()
        if source is None:
            # A rename can keep its source identity; a copy still gets independent provenance.
            candidates = self.store.rows(
                "SELECT * FROM sources WHERE provider=? AND identity=?", (provider, identity)
            )
            moved = next((s for s in candidates if not Path(s["path"]).exists()), None)
            if moved:
                self.store.db.execute(
                    "UPDATE sources SET path=? WHERE id=?", (str(path), moved["id"])
                )
                source = self.store.db.execute(
                    "SELECT * FROM sources WHERE id=?", (moved["id"],)
                ).fetchone()
        if (
            source is not None
            and source["signature"] == signature
            and not verify
            and not rebuild
            and source["status"] not in {"missing", "excluded", "failed"}
        ):
            self.stats["unchanged"] += 1
            if source["status"] in {"partial", "failed", "unsupported"}:
                self.stats["partial"] += 1
            return
        inserted_before = self.stats["inserted_records"]
        try:
            with self.store.transaction():
                if source is None:
                    sid = uuid4().hex
                    self.store.db.execute(
                        "INSERT INTO sources(id,provider,path,identity,status) VALUES(?,?,?,?,?)",
                        (sid, provider, str(path), identity, "new"),
                    )
                    source = self.store.db.execute(
                        "SELECT * FROM sources WHERE id=?", (sid,)
                    ).fetchone()
                if provider == "codex" and path.name.endswith(".jsonl.zst"):
                    self.read_zstd(source, path, signature)
                    return
                if provider == "hermes" and path.suffix in {".db", ".sqlite", ".sqlite3"}:
                    self.read_hermes(source, path, signature)
                elif path.suffix == ".jsonl" and provider in {"codex", "claude"}:
                    self.read_jsonl(source, path, signature, rebuild)
                else:
                    self.store.db.execute(
                        "UPDATE sources SET status='unsupported',signature=?,diagnostics=? WHERE id=?",
                        (signature, '[{"code":"unsupported_provider_format"}]', source["id"]),
                    )
                    self.stats["partial"] += 1
        except (OSError, ValueError, sqlite3.Error) as exc:
            self.stats["inserted_records"] = inserted_before
            self.stats["failed"] += 1
            # Prior data/checkpoint remain intact. Error text never includes source content.
            if source is not None:
                self.store.db.execute(
                    "UPDATE sources SET status='failed',diagnostics=? WHERE id=?",
                    (json.dumps([{"code": type(exc).__name__}]), source["id"]),
                )

    def generation(self, source: Any, replace: bool) -> int:
        if replace or not source["generation"]:
            self.store.db.execute(
                "UPDATE generations SET status='superseded' WHERE source_id=?", (source["id"],)
            )
            number = source["generation"] + 1
            result = self.store.db.execute(
                "INSERT INTO generations(source_id,number,status,created_at) VALUES(?,?,'current',?)",
                (source["id"], number, now()),
            )
            self.store.db.execute(
                "UPDATE sources SET generation=? WHERE id=?", (number, source["id"])
            )
            assert result.lastrowid is not None
            return result.lastrowid
        return self.store.db.execute(
            "SELECT id FROM generations WHERE source_id=? AND number=?",
            (source["id"], source["generation"]),
        ).fetchone()[0]

    def read_jsonl(self, source: Any, path: Path, signature: str, rebuild: bool) -> None:
        fd = open_regular(path)
        diagnostics: list[dict[str, Any]] = []
        partial = False
        with os.fdopen(fd, "rb") as stream:
            start = os.fstat(stream.fileno())
            offset, line = source["offset"], source["line"]
            replace = (
                rebuild
                or start.st_size < offset
                or source["identity"] != f"{start.st_dev}:{start.st_ino}"
            )
            if offset and not replace:
                replace = prefix_hash(stream, offset) != source["prefix_hash"]
            if replace:
                offset, line, context = 0, 0, {}
            else:
                context = json.loads(source["context"])
                # A complete malformed/unsupported record was checkpointed and
                # will not be revisited by this append. Its gap remains until
                # a replacement or rebuild actually verifies that prefix again.
                diagnostics = [
                    d
                    for d in json.loads(source["diagnostics"])
                    if d.get("code") not in {"incomplete_tail", "oversized_incomplete_tail"}
                ]
                partial = bool(diagnostics)
            generation = self.generation(source, replace)
            stream.seek(offset)
            while stream.tell() < start.st_size:
                position = stream.tell()
                raw = stream.readline(MAX_RECORD_BYTES + 1)
                if not raw:
                    break
                if len(raw) > MAX_RECORD_BYTES:
                    while raw and not raw.endswith(b"\n"):
                        raw = stream.readline(MAX_RECORD_BYTES + 1)
                    if not raw.endswith(b"\n"):
                        partial = True
                        diagnostics.append({"code": "oversized_incomplete_tail", "line": line + 1})
                        break
                    line += 1
                    offset = stream.tell()
                    diagnostics.append({"code": "record_size_limit", "line": line})
                    partial = True
                    continue
                if not raw.endswith(b"\n"):
                    partial = True
                    diagnostics.append({"code": "incomplete_tail", "line": line + 1})
                    break
                line += 1
                offset = stream.tell()
                if not raw.strip():
                    continue
                try:
                    payload = parse_json(raw)
                    self.stats["parsed_records"] += 1
                    result = adapters.normalize(
                        provider=source["provider"],
                        payload=payload,
                        context=context,
                        locator=f"line:{line}",
                    )
                    for record in result.records:
                        self.record(
                            record,
                            generation,
                            f"line:{line}@{position}",
                            rebuild and source["signature"] == signature,
                        )
                    diagnostics.extend(asdict(d) for d in result.diagnostics)
                    partial = partial or bool(result.diagnostics)
                except ExtractionLimitError:
                    diagnostics.append({"code": "record_extraction_limit", "line": line})
                    partial = True
                except ValueError, TypeError, KeyError, RecursionError:
                    diagnostics.append({"code": "malformed_record", "line": line})
                    partial = True
                diagnostics = diagnostics[:30]
            final = os.fstat(stream.fileno())
            if (
                final.st_size != start.st_size
                or final.st_mtime_ns != start.st_mtime_ns
                or source_signature(path) != signature
            ):
                raise ValueError("source_changed_during_read")
            prefix = prefix_hash(stream, offset)
            context = clean(context)
        if partial:
            self.stats["partial"] += 1
        self.store.db.execute(
            "UPDATE sources SET status=?,signature=?,identity=?,offset=?,line=?,prefix_hash=?,context=?,last_refresh=?,diagnostics=? WHERE id=?",
            (
                "partial" if partial else "ready",
                signature,
                f"{start.st_dev}:{start.st_ino}",
                offset,
                line,
                prefix,
                json.dumps(context, ensure_ascii=False),
                now(),
                json.dumps(clean(diagnostics[:30])),
                source["id"],
            ),
        )

    def read_zstd(self, source: Any, path: Path, signature: str) -> None:
        generation = self.generation(source, True)
        context: dict[str, Any] = {}
        diagnostics: list[dict[str, Any]] = []
        partial = False
        with os.fdopen(open_regular(path), "rb") as stream:
            for line, raw, code in iter_zstd_lines(stream):
                if code:
                    diagnostics.append({"code": code, "line": line})
                    partial = True
                elif raw and raw.strip():
                    try:
                        payload = parse_json(raw)
                        self.stats["parsed_records"] += 1
                        result = adapters.normalize("codex", payload, context, f"line:{line}")
                        for record in result.records:
                            self.record(
                                record,
                                generation,
                                f"decompressed-line:{line}",
                                self.rebuild and source["signature"] == signature,
                            )
                        diagnostics.extend(asdict(d) for d in result.diagnostics)
                        partial = partial or bool(result.diagnostics)
                    except ExtractionLimitError:
                        diagnostics.append({"code": "record_extraction_limit", "line": line})
                        partial = True
                    except ValueError, TypeError, KeyError, RecursionError:
                        diagnostics.append({"code": "malformed_record", "line": line})
                        partial = True
                diagnostics = diagnostics[:30]
        if source_signature(path) != signature:
            raise ValueError("source_changed_during_read")
        if partial:
            self.stats["partial"] += 1
        self.store.db.execute(
            "UPDATE sources SET status=?,signature=?,identity=?,last_refresh=?,diagnostics=? WHERE id=?",
            (
                "partial" if partial else "ready",
                signature,
                f"{path.stat().st_dev}:{path.stat().st_ino}",
                now(),
                json.dumps(clean(diagnostics)),
                source["id"],
            ),
        )

    def read_hermes(self, source: Any, path: Path, signature: str) -> None:
        generation = self.generation(source, True)
        diagnostics: list[dict[str, Any]] = []
        for value in adapters.iter_hermes(path):
            if isinstance(value, Diagnostic):
                if len(diagnostics) < 30:
                    diagnostics.append(asdict(value))
            else:
                self.stats["parsed_records"] += 1
                try:
                    self.record(
                        value,
                        generation,
                        f"message:{value.native_id}",
                        self.rebuild and source["signature"] == signature,
                    )
                except ExtractionLimitError:
                    if len(diagnostics) < 30:
                        diagnostics.append({"code": "record_extraction_limit"})
        if source_signature(path) != signature:
            raise ValueError("source_changed_during_read")
        if diagnostics:
            self.stats["partial"] += 1
        self.store.db.execute(
            "UPDATE sources SET status=?,signature=?,identity=?,last_refresh=?,diagnostics=? WHERE id=?",
            (
                "partial" if diagnostics else "ready",
                signature,
                f"{path.stat().st_dev}:{path.stat().st_ino}",
                now(),
                json.dumps(clean(diagnostics[:30])),
                source["id"],
            ),
        )

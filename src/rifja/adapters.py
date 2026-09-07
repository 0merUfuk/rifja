"""Shape-checked native readers; producer content is data, never instructions."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from collections.abc import Iterator
from datetime import UTC
from pathlib import Path
from typing import Any

from .models import Diagnostic, ParseResult, Record

MAX_TEXT = 1_048_576
_CODEC = "\x00json:"


def _text(value: Any) -> str:
    pending, chunks = [value], []
    while pending:
        part = pending.pop()
        if isinstance(part, str):
            if part:
                chunks.append(part)
        elif isinstance(part, list):
            pending.extend(reversed(part))
        elif (
            isinstance(part, dict)
            and isinstance(part.get("type"), str)
            and part["type"] in {"text", "input_text", "output_text", "tool_result"}
        ):
            pending.append(part.get("text", part.get("content")))
    return "\n".join(chunks)


def _mapping(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError, RecursionError:
            pass
    return {}


def _observed(value: Any) -> dict:
    data = _mapping(value)
    out: dict[str, Any] = {}
    for key in ("command", "cmd"):
        if isinstance(data.get(key), (str, list)):
            out["command"] = data[key]
            break
    for key in ("exit_code", "exitCode", "exit_status"):
        if isinstance(data.get(key), int) and not isinstance(data[key], bool):
            out["exit_status"] = data[key]
            break
    for key in ("revision", "commit_hash", "sha"):
        if isinstance(data.get(key), str):
            out["revision"] = data[key]
            break
    if isinstance(data.get("branch"), str):
        out["branch"] = data["branch"]
    if isinstance(data.get("dirty"), bool):
        out["dirty"] = data["dirty"]
    return out


def normalize(provider: str, payload: dict, context: dict, locator: str) -> ParseResult:
    """Normalize one JSONL object. Context must be checkpointed with its records."""
    if not isinstance(payload, dict):
        return ParseResult(
            diagnostics=[Diagnostic("invalid_record", "Record must be an object", locator)]
        )
    if provider not in {"codex", "claude", "claude-code", "claude_code"}:
        return ParseResult(
            diagnostics=[Diagnostic("unsupported_format", "No JSONL adapter for provider", locator)]
        )
    try:
        return (
            _codex(payload, context, locator)
            if provider == "codex"
            else _claude(payload, context, locator)
        )
    except TypeError, ValueError, KeyError, RecursionError:
        return ParseResult(
            diagnostics=[
                Diagnostic("invalid_record", "Record fields have unsupported shapes", locator)
            ]
        )


def _make(
    provider: str,
    ctx: dict,
    d: dict,
    locator: str,
    actor: str,
    kind: str,
    text: str = "",
    native: str | None = None,
    metadata: dict | None = None,
) -> Record:
    ts = d.get("timestamp")
    cwd = d.get("cwd") if isinstance(d.get("cwd"), str) else ctx.get("cwd")
    return Record(
        provider,
        ctx["session_id"],
        native or locator,
        actor,
        kind,
        text,
        ts if isinstance(ts, str) else None,
        cwd,
        metadata or {},
    )


def _codex(d: dict, ctx: dict, loc: str) -> ParseResult:
    p = d.get("payload")
    if not isinstance(p, dict) or not isinstance(d.get("type"), str):
        return ParseResult(
            diagnostics=[Diagnostic("unknown_format", "Expected Codex rollout envelope", loc)]
        )
    outer = d["type"]
    if outer == "session_meta":
        if not isinstance(p.get("id"), str) or not p["id"]:
            return ParseResult(
                diagnostics=[Diagnostic("invalid_identity", "Codex header lacks task id", loc)]
            )
        if ctx.get("session_id"):
            return ParseResult()  # Forks can carry a copied parent's header.
        ctx["session_id"] = p["id"]
        if isinstance(p.get("cwd"), str):
            ctx["cwd"] = p["cwd"]
        boundary = p.get("subagent_history_start_ordinal")
        if isinstance(boundary, int) and not isinstance(boundary, bool):
            ctx["history_start_ordinal"] = boundary
        meta = _observed(p.get("git"))
        for key in (
            "session_id",
            "parent_thread_id",
            "forked_from_id",
            "cli_version",
            "history_mode",
            "history_base",
        ):
            if key in p:
                meta["root_session_id" if key == "session_id" else key] = p[key]
        result = ParseResult([_make("codex", ctx, d, loc, "system", "metadata", metadata=meta)])
        if p.get("history_base"):
            result.diagnostics.append(
                Diagnostic(
                    "external_history",
                    "Linked inherited history is not resolved by this source",
                    loc,
                )
            )
        return result
    if not ctx.get("session_id"):
        return ParseResult(
            diagnostics=[
                Diagnostic("missing_header", "Codex record precedes a valid session header", loc)
            ]
        )
    ordinal = d.get("ordinal")
    if isinstance(ordinal, int) and ordinal < ctx.get("history_start_ordinal", 0):
        return ParseResult()
    if outer == "turn_context":
        if isinstance(p.get("cwd"), str):
            ctx["cwd"] = p["cwd"]
        return ParseResult([_make("codex", ctx, d, loc, "system", "metadata")])
    if outer == "response_item":
        typ = p.get("type")
        native = p.get("id") if isinstance(p.get("id"), str) else loc
        if typ == "message":
            role = p.get("role")
            if role not in {"user", "assistant", "system", "developer"}:
                return ParseResult(
                    diagnostics=[Diagnostic("unknown_role", "Unsupported Codex message role", loc)]
                )
            kind = {"user": "user_intent", "assistant": "agent_claim"}.get(role, "metadata")
            return ParseResult(
                [
                    _make(
                        "codex",
                        ctx,
                        d,
                        loc,
                        role,
                        kind,
                        _text(p.get("content")),
                        native,
                        {"phase": p["phase"]} if isinstance(p.get("phase"), str) else {},
                    )
                ]
            )
        if typ == "agent_message":
            text = _text(p.get("content"))
            meta = {k: p[k] for k in ("author", "recipient") if isinstance(p.get(k), str)}
            result = ParseResult(
                [_make("codex", ctx, d, loc, "assistant", "agent_claim", text, native, meta)]
            )
            if any(
                isinstance(x, dict) and x.get("type") == "encrypted_content"
                for x in p.get("content", [])
            ):
                result.diagnostics.append(
                    Diagnostic("opaque_content", "Encrypted agent content is unavailable", loc)
                )
            return result
        if typ in {"function_call", "custom_tool_call", "local_shell_call", "tool_search_call"}:
            args = p.get("arguments", p.get("input", p.get("action")))
            meta = _observed(args)
            for key in ("name", "call_id"):
                if isinstance(p.get(key), str):
                    meta["tool" if key == "name" else key] = p[key]
            return ParseResult(
                [
                    _make(
                        "codex",
                        ctx,
                        d,
                        loc,
                        "assistant",
                        "agent_proposal",
                        _text(args) or json.dumps(args, ensure_ascii=False)
                        if args is not None
                        else "",
                        native,
                        meta,
                    )
                ]
            )
        if typ in {"function_call_output", "custom_tool_call_output", "tool_search_output"}:
            meta = _observed(p.get("output"))
            if isinstance(p.get("call_id"), str):
                meta["call_id"] = p["call_id"]
            return ParseResult(
                [
                    _make(
                        "codex",
                        ctx,
                        d,
                        loc,
                        "tool",
                        "recorded_tool_result",
                        _text(p.get("output")),
                        native,
                        meta,
                    )
                ]
            )
        if typ in {"reasoning", "compaction", "additional_tools"}:
            return ParseResult([_make("codex", ctx, d, loc, "system", "metadata", native=native)])
        return ParseResult(
            diagnostics=[Diagnostic("unknown_event", "Unsupported Codex response item", loc)]
        )
    if outer == "event_msg":
        typ = p.get("type")
        if typ == "item_completed":
            item = p.get("item")
            if not isinstance(item, dict):
                return ParseResult(
                    diagnostics=[
                        Diagnostic("invalid_record", "Completed item lacks an object", loc)
                    ]
                )
            meta = _observed(item)
            if item.get("type") in {"CommandExecution", "command_execution"}:
                meta["execution_source"] = "native_command_execution"
                if isinstance(ctx.get("cwd"), str):
                    meta["context_cwd"] = ctx["cwd"]
            event = dict(d)
            if isinstance(item.get("cwd"), str):
                event["cwd"] = item["cwd"]
            if (
                "exit_status" in meta
                or "command" in meta
                or item.get("type") in {"command_execution", "mcp_tool_call", "dynamic_tool_call"}
            ):
                text = next(
                    (
                        _text(item[k])
                        for k in (
                            "aggregated_output",
                            "formatted_output",
                            "stdout",
                            "result",
                            "content",
                        )
                        if k in item
                    ),
                    "",
                )
                native = "completed:" + item["id"] if isinstance(item.get("id"), str) else loc
                return ParseResult(
                    [
                        _make(
                            "codex",
                            ctx,
                            event,
                            loc,
                            "tool",
                            "recorded_tool_result",
                            text,
                            native,
                            meta,
                        )
                    ]
                )
            return ParseResult([_make("codex", ctx, event, loc, "system", "metadata")])
        if typ in {
            "task_started",
            "task_complete",
            "turn_aborted",
            "token_count",
            "thread_settings_applied",
            "thread_goal_updated",
            "user_message",
            "agent_message",
            "agent_reasoning",
            "agent_reasoning_raw_content",
            "context_compacted",
            "turn_diff",
            "error",
            "warning",
        }:
            return ParseResult(
                [_make("codex", ctx, d, loc, "system", "metadata", metadata={"event_type": typ})]
            )
        return ParseResult(
            diagnostics=[Diagnostic("unknown_event", "Unsupported Codex event message", loc)]
        )
    if outer in {
        "world_state",
        "token_usage_record",
        "inter_agent_communication_metadata",
        "compacted",
    }:
        return ParseResult(
            [_make("codex", ctx, d, loc, "system", "metadata", metadata={"event_type": outer})]
        )
    return ParseResult(
        diagnostics=[Diagnostic("unknown_event", "Unsupported Codex rollout event", loc)]
    )


_CLAUDE_META = {
    "agent-setting",
    "permission-mode",
    "attachment",
    "progress",
    "system",
    "queue-operation",
    "last-prompt",
    "custom-title",
    "atis-latch",
    "mode",
    "bridge-session",
    "agent-name",
    "summary",
    "file-history-snapshot",
}


def _claude(d: dict, ctx: dict, loc: str) -> ParseResult:
    typ = d.get("type")
    sid = d.get("sessionId")
    if isinstance(sid, str) and sid:
        aid = d.get("agentId")
        if isinstance(aid, str) and aid:
            ctx["agent_id"] = aid
        ctx["root_session_id"] = sid
        ctx["session_id"] = sid + ("/agent:" + ctx["agent_id"] if ctx.get("agent_id") else "")
    if not ctx.get("session_id"):
        return ParseResult(
            diagnostics=[
                Diagnostic("missing_identity", "Claude record lacks session identity", loc)
            ]
        )
    if isinstance(d.get("cwd"), str):
        ctx["cwd"] = d["cwd"]
    native = d.get("uuid") if isinstance(d.get("uuid"), str) else loc
    meta = {k: d[k] for k in ("parentUuid", "isSidechain", "agentId", "version") if k in d}
    if isinstance(d.get("gitBranch"), str):
        meta["branch"] = d["gitBranch"]
    if ctx.get("agent_id"):
        meta["parent_session_id"] = ctx["root_session_id"]
    if typ in _CLAUDE_META:
        meta["event_type"] = typ
        return ParseResult(
            [_make("claude", ctx, d, loc, "system", "metadata", native=native, metadata=meta)]
        )
    if typ not in {"user", "assistant"} or not isinstance(d.get("message"), dict):
        return ParseResult(
            diagnostics=[Diagnostic("unknown_event", "Unsupported Claude transcript entry", loc)]
        )
    message = d["message"]
    role = message.get("role")
    if role not in {"user", "assistant"}:
        return ParseResult(
            diagnostics=[Diagnostic("unknown_role", "Unsupported Claude message role", loc)]
        )
    content = message.get("content")
    parts = content if isinstance(content, list) else [content]
    result = ParseResult()
    for index, part in enumerate(parts):
        part_id = f"{native}:block:{index}"
        item_meta = dict(meta)
        if isinstance(part, str) or isinstance(part, dict) and part.get("type") == "text":
            kind = (
                "metadata"
                if d.get("isMeta") or d.get("isCompactSummary")
                else ("user_intent" if role == "user" else "agent_claim")
            )
            result.records.append(
                _make("claude", ctx, d, loc, role, kind, _text(part), part_id, item_meta)
            )
        elif isinstance(part, dict) and part.get("type") == "tool_use":
            args = part.get("input")
            item_meta.update(_observed(args))
            if isinstance(part.get("id"), str):
                item_meta["call_id"] = part["id"]
            if isinstance(part.get("name"), str):
                item_meta["tool"] = part["name"]
            result.records.append(
                _make(
                    "claude",
                    ctx,
                    d,
                    loc,
                    "assistant",
                    "agent_proposal",
                    json.dumps(args, ensure_ascii=False) if args is not None else "",
                    part_id,
                    item_meta,
                )
            )
        elif isinstance(part, dict) and part.get("type") == "tool_result":
            item_meta.update(_observed(d.get("toolUseResult")))
            for key in ("tool_use_id", "is_error"):
                if key in part:
                    item_meta["call_id" if key == "tool_use_id" else key] = part[key]
            result.records.append(
                _make(
                    "claude",
                    ctx,
                    d,
                    loc,
                    "tool",
                    "recorded_tool_result",
                    _text(part.get("content")),
                    part_id,
                    item_meta,
                )
            )
        elif isinstance(part, dict) and part.get("type") in {
            "thinking",
            "redacted_thinking",
            "image",
            "document",
        }:
            result.records.append(
                _make(
                    "claude", ctx, d, loc, "system", "metadata", native=part_id, metadata=item_meta
                )
            )
        else:
            result.diagnostics.append(
                Diagnostic("unknown_content", "Unsupported Claude content block", loc)
            )
    return result


def _open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    conn.row_factory = sqlite3.Row
    deadline = time.monotonic() + 30
    callbacks = 0

    def budget() -> int:
        nonlocal callbacks
        callbacks += 1
        return int(callbacks > 100_000 or time.monotonic() > deadline)

    conn.set_progress_handler(budget, 1000)
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA trusted_schema=OFF")
    conn.execute("PRAGMA cache_size=-8192")
    conn.execute("BEGIN")
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    # Producer tables are storage, never an executable view or virtual-table adapter.
    entry = conn.execute("SELECT type, sql FROM sqlite_schema WHERE name=?", (table,)).fetchone()
    if entry is None:
        return set()
    if entry[0] != "table" or not re.match(r"^CREATE\s+TABLE\b", entry[1] or "", re.IGNORECASE):
        raise ValueError("Unsupported Hermes table definition")
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _schema(conn: sqlite3.Connection) -> tuple[set[str], set[str]]:
    sessions, messages = _columns(conn, "sessions"), _columns(conn, "messages")
    if (
        not {"id", "started_at"} <= sessions
        or not {"id", "session_id", "role", "content", "timestamp"} <= messages
    ):
        raise ValueError("Unsupported Hermes sessions/messages schema")
    return sessions, messages


def hermes_signature(path: Path) -> dict:
    """Return format metadata only; never produce transcript/config values."""
    conn = _open_db(path)
    try:
        sc, mc = _schema(conn)
        versions = _columns(conn, "schema_version")
        row = (
            conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
            if "version" in versions
            else None
        )
        version = row[0] if row else None
        schema = json.dumps([sorted(sc), sorted(mc)], separators=(",", ":"))
        result = {
            "provider": "hermes",
            "format": "sqlite",
            "schema_version": version,
            "signature": hashlib.sha256(schema.encode()).hexdigest(),
        }
    finally:
        conn.close()
    for label, candidate in (("db", path), ("wal", Path(str(path) + "-wal"))):
        try:
            st = candidate.stat()
            result[label] = {
                "size": st.st_size,
                "mtime_ns": st.st_mtime_ns,
                "ctime_ns": st.st_ctime_ns,
                "inode": st.st_ino,
            }
        except FileNotFoundError:
            result[label] = None
    return result


def _decode_content(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(_CODEC):
        try:
            return json.loads(value[len(_CODEC) :])
        except ValueError, RecursionError:
            pass
    return value


def _unix_time(value: Any) -> str | None:
    from datetime import datetime

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, UTC).isoformat().replace("+00:00", "Z")
        except ValueError, OverflowError, OSError:
            pass
    return None


def iter_hermes(path: Path, after_id: int = 0) -> Iterator[Record | Diagnostic]:
    """Read durable display rows, excluding rewind rows, in one WAL-aware snapshot.

    Full rereads are necessary after source mutation: compaction and rewind edit
    existing rows. `after_id` is for a caller that has independently proved append.
    """
    conn = None
    try:
        conn = _open_db(path)
        sc, mc = _schema(conn)
        selected = ["id", "session_id", "role", "content", "timestamp"]
        selected += [
            x
            for x in (
                "tool_calls",
                "tool_call_id",
                "tool_name",
                "active",
                "compacted",
                "_compressed_summary",
                "display_kind",
            )
            if x in mc
        ]
        # Cap individual variable-width fields before they cross the SQLite API.
        expressions = [
            f'CASE WHEN length(CAST(m."{x}" AS BLOB)) <= {MAX_TEXT} THEN m."{x}" ELSE NULL END AS "{x}"'
            for x in selected
        ]
        size_checks = [f'COALESCE(length(CAST(m."{x}" AS BLOB)), 0) > {MAX_TEXT}' for x in selected]
        session_fields = [
            x
            for x in (
                "cwd",
                "git_branch",
                "git_repo_root",
                "parent_session_id",
                "ended_at",
                "end_reason",
                "archived",
                "hidden",
            )
            if x in sc
        ]
        expressions += [
            f'CASE WHEN length(CAST(s."{x}" AS BLOB)) <= {MAX_TEXT} THEN s."{x}" ELSE NULL END AS "session_{x}"'
            for x in session_fields
        ]
        size_checks += [
            f'COALESCE(length(CAST(s."{x}" AS BLOB)), 0) > {MAX_TEXT}' for x in session_fields
        ]
        expressions.append("(" + " OR ".join(size_checks) + ') AS "_oversized"')
        active = (
            "(m.active = 1 OR m.compacted = 1)"
            if {"active", "compacted"} <= mc
            else "m.active = 1"
            if "active" in mc
            else "1"
        )
        # Select the newest active generation for identical compaction copies.
        # SQL correlation uses only equality fields, not content interpretation.
        dedupe = ""
        if {"active", "compacted", "tool_calls", "tool_call_id", "tool_name"} <= mc:
            equal = " AND ".join(
                f'n."{key}" IS m."{key}"'
                for key in (
                    "session_id",
                    "role",
                    "content",
                    "timestamp",
                    "tool_call_id",
                    "tool_calls",
                    "tool_name",
                )
            )
            dedupe = f" AND NOT EXISTS (SELECT 1 FROM messages n WHERE {equal} AND (n.active=1 OR n.compacted=1) AND (n.active > m.active OR (n.active=m.active AND n.id > m.id)))"
        query = (
            "SELECT "
            + ",".join(expressions)
            + " FROM messages m JOIN sessions s ON s.id=m.session_id WHERE m.id > ? AND "
            + active
            + dedupe
            + " ORDER BY m.id"
        )
        for raw in conn.execute(query, (after_id,)):
            row = dict(raw)
            loc = "messages:" + str(row["id"])
            if row["_oversized"]:
                yield Diagnostic("oversized_record", "Hermes message exceeds reader limit", loc)
                continue
            role = row["role"]
            if role not in {"user", "assistant", "tool", "system", "developer"}:
                yield Diagnostic("unknown_role", "Unsupported Hermes message role", loc)
                continue
            kind = {
                "user": "user_intent",
                "assistant": "agent_claim",
                "tool": "recorded_tool_result",
            }.get(role, "metadata")
            if row.get("_compressed_summary") or row.get("display_kind"):
                kind = "metadata"
                yield Diagnostic(
                    "compaction_projection",
                    "Synthetic/display message retained as metadata; full UI projection unavailable",
                    loc,
                )
            content = _decode_content(row["content"])
            text = _text(content)
            meta = {}
            for src, dest in (
                ("tool_call_id", "call_id"),
                ("tool_name", "tool"),
                ("session_git_branch", "branch"),
                ("session_git_repo_root", "git_repo_root"),
                ("session_parent_session_id", "parent_session_id"),
                ("session_ended_at", "ended_at"),
                ("session_end_reason", "end_reason"),
                ("session_archived", "archived"),
                ("session_hidden", "hidden"),
            ):
                if row.get(src) is not None:
                    meta[dest] = row[src]
            if role == "tool":
                meta.update(_observed(content))
            ts = _unix_time(row["timestamp"])
            if ts is None:
                yield Diagnostic("invalid_timestamp", "Hermes timestamp cannot be resolved", loc)
            sid = str(row["session_id"])
            native = str(row["id"])
            cwd = row.get("session_cwd")
            yield Record("hermes", sid, native, role, kind, text, ts, cwd, meta)
            if row.get("tool_calls"):
                try:
                    calls = json.loads(row["tool_calls"])
                    if not isinstance(calls, list):
                        raise TypeError()
                except ValueError, TypeError, RecursionError:
                    yield Diagnostic(
                        "invalid_tool_calls", "Hermes tool_calls is not a JSON list", loc
                    )
                    continue
                for i, call in enumerate(calls):
                    if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
                        yield Diagnostic(
                            "invalid_tool_call", "Unsupported Hermes tool call shape", loc
                        )
                        continue
                    fn = call["function"]
                    args = fn.get("arguments")
                    call_meta = _observed(args)
                    if isinstance(fn.get("name"), str):
                        call_meta["tool"] = fn["name"]
                    cid = call.get("id", call.get("call_id"))
                    if isinstance(cid, str):
                        call_meta["call_id"] = cid
                    yield Record(
                        "hermes",
                        sid,
                        native + f":call:{i}",
                        "assistant",
                        "agent_proposal",
                        args
                        if isinstance(args, str)
                        else json.dumps(args, ensure_ascii=False)
                        if args is not None
                        else "",
                        ts,
                        cwd,
                        call_meta,
                    )
    except (sqlite3.Error, OSError, ValueError) as exc:
        yield Diagnostic(
            "unreadable_source" if not isinstance(exc, ValueError) else "unknown_format",
            "Hermes store could not be read with the supported schema",
        )
    finally:
        if conn is not None:
            conn.close()

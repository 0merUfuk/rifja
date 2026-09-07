"""Conservative historical move reconciliation; recorded commands are never run.

Only adapter-labelled native command completions can establish an operation.
The narrow shell grammar describes a single command, not a shell program.
Fresh-import evidence is local to a session and a current source generation;
it creates no global path alias. Git observations retain worktree isolation.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .git import inspect_repository
from .privacy import symlink_component
from .store import Store

MAX_EXECUTIONS = 20_000
MAX_OPERATIONS = 100
MAX_SESSION_RECORDS = 50_000
REPORT_CONFIG = "identity_continuity"
MOVE_REASON = "recorded_move_evidence"
IDENTITY_REASON = "git_filesystem_identity_continuity"
_CAVEAT = (
    "A recorded directory move is historical operation evidence. It does not prove "
    "project completion or certify the current checkout."
)


def _system_alias(path: Path) -> Path:
    """Recognize only root-owned Darwin aliases to their fixed system targets.

    General resolve() would legitimize arbitrary user-created symlinks. These
    three OS-defined aliases are checked explicitly and do not alter evidence.
    """
    if sys.platform != "darwin" or len(path.parts) < 2:
        return path
    name = path.parts[1]
    if name not in {"var", "tmp", "etc"}:
        return path
    alias, target = Path("/") / name, Path("/private") / name
    try:
        if (
            alias.is_symlink()
            and alias.lstat().st_uid == 0
            and os.readlink(alias) in {f"private/{name}", f"/private/{name}"}
            and not target.is_symlink()
            and target.stat().st_uid == 0
        ):
            return target.joinpath(*path.parts[2:])
    except OSError:
        pass
    return path


def _path(value: Any) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 4096:
        return None
    if value.startswith("file:"):
        try:
            parsed = urlsplit(value)
        except ValueError:
            return None
        if parsed.scheme != "file" or parsed.netloc or parsed.query or parsed.fragment:
            return None
        try:
            value = unquote(parsed.path, errors="strict")
        except UnicodeError:
            return None
    if any(ord(c) < 32 or ord(c) == 127 for c in value) or "[" in value:
        return None  # Also excludes redacted/truncated path fields.
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        return None
    return str(_system_alias(path))


def _recorded_spellings(path: str) -> list[str]:
    values = [path, Path(path).as_uri()]
    for name in ("var", "tmp", "etc"):
        prefix = f"/private/{name}/"
        if path.startswith(prefix):
            alias = "/" + name + "/" + path.removeprefix(prefix)
            if _path(alias) == path:
                values.extend((alias, Path(alias).as_uri()))
    return values


def local_recorded_path(value: Any) -> str | None:
    """Validate local recorded paths/URIs using the same identity boundary."""
    return _path(value)


def _argv(command: Any) -> list[str] | None:
    if isinstance(command, list):
        if not command or not all(isinstance(v, str) and len(v) <= 4096 for v in command):
            return None
        if command[0] in {"sh", "bash", "zsh", "/bin/sh", "/bin/bash", "/bin/zsh"}:
            if len(command) != 3 or command[1] not in {"-c", "-lc"}:
                return None
            command = command[2]
        else:
            return command if len(command) <= 8 else None
    if not isinstance(command, str) or len(command) > 4096:
        return None
    # Reject shell expansion, compound programs, substitutions and redirections,
    # including when quoted. False negatives are preferable to shell semantics.
    if any(c in command for c in "\n\r;$`|&<>(){}[]*?!"):
        return None
    try:
        values = shlex.split(command, comments=False, posix=True)
    except ValueError:
        return None
    return values if 0 < len(values) <= 8 else None


def _move(argv: list[str] | None) -> tuple[str, str] | None:
    if not argv or argv[0] not in {"mv", "/bin/mv", "/usr/bin/mv"}:
        return None
    args = argv[1:]
    if args and args[0] in {"-n", "--no-clobber"}:
        args = args[1:]
    if args and args[0] == "--":
        args = args[1:]
    if len(args) != 2:
        return None
    old, new = (_path(v) for v in args)
    if not old or not new or old == new or Path(old).parent != Path(new).parent:
        return None
    return old, new


def _git_root(row: dict[str, Any], destination: str) -> bool:
    argv = row["argv"]
    if not argv or argv[0] not in {"git", "/usr/bin/git", "/bin/git"}:
        return False
    args, cwd = argv[1:], _path(row["cwd"])
    if len(args) >= 2 and args[0] == "-C":
        cwd, args = _path(args[1]), args[2:]
    if args not in (
        ["rev-parse", "--show-toplevel"],
        ["rev-parse", "--path-format=absolute", "--show-toplevel"],
    ):
        return False
    output = row["text"].removesuffix("\n")
    return cwd == destination and output.startswith("/") and _path(output) == destination


def _position(locator: str) -> int | None:
    match = re.fullmatch(r"(?:decompressed-)?line:(\d+)(?:@\d+)?", locator)
    return int(match[1]) if match else None


def _executions(store: Store) -> tuple[list[dict[str, Any]], bool]:
    # Read bounded command metadata only, never scan historical message bodies.
    rows = store.rows(
        "SELECT r.*,o.generation_id,o.locator FROM records r "
        "JOIN occurrences o ON o.record_id=r.id "
        "JOIN generations g ON g.id=o.generation_id "
        "JOIN sources s ON s.id=g.source_id "
        "WHERE r.actor='tool' AND r.kind='recorded_tool_result' "
        "AND json_extract(r.metadata,'$.execution_source')='native_command_execution' "
        "AND g.status='current' AND s.status IN ('ready','partial') "
        "ORDER BY r.session_id,o.generation_id,o.locator LIMIT ?",
        (MAX_EXECUTIONS + 1,),
    )
    if len(rows) > MAX_EXECUTIONS:
        return [], True
    result = []
    for row in rows:
        meta = json.loads(row["metadata"])
        if type(meta.get("exit_status")) is not int or meta["exit_status"] != 0:
            continue
        position = _position(row["locator"])
        if position is None:
            continue
        row.update(metadata=meta, argv=_argv(meta.get("command")), position=position)
        result.append(row)
    return result, False


def _eligible_rows(store: Store, session: str, generation: int) -> list[dict[str, Any]]:
    return store.rows(
        "SELECT r.id,r.native_id,r.session_id,r.cwd,r.project_id,r.worktree_id,r.association_reason,"
        "o.locator FROM records r JOIN occurrences o ON o.record_id=r.id "
        "WHERE r.session_id=? AND o.generation_id=? LIMIT ?",
        (session, generation, MAX_SESSION_RECORDS + 1),
    )


def _explicit(store: Store, session: str, record: str) -> bool:
    return bool(
        store.db.execute(
            "SELECT 1 FROM associations WHERE target IN (?,?) LIMIT 1", (session, record)
        ).fetchone()
    )


def _destination(
    store: Store, destination: str, source: str, cache: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    old, new = Path(source), Path(destination)
    try:
        old.lstat()
    except FileNotFoundError:
        pass
    except OSError:
        return None, "old_path_unavailable"
    else:
        return None, "old_path_exists_or_reused"
    if symlink_component(old) or symlink_component(new):
        return None, "symlink_path_unresolved"
    if (new / old.name).exists() or (new / old.name).is_symlink():
        return None, "nested_move_destination"
    registered = store.rows(
        "SELECT w.*,p.common_identity FROM worktrees w JOIN projects p ON p.id=w.project_id "
        "WHERE w.path=? AND w.active=1",
        (destination,),
    )
    if len(registered) != 1:
        return None, "destination_not_uniquely_registered"
    target = registered[0]
    # An old registered worktree with a different identity must never be merged.
    others = store.rows("SELECT id,identity,path FROM worktrees WHERE id!=?", (target["id"],))
    for other in others:
        path = _path(other["path"])
        if path and (path == source or old in Path(path).parents or new in Path(path).parents):
            return None, "separate_or_nested_worktree"
    if destination not in cache:
        cache[destination] = inspect_repository(destination)
    current = cache[destination]
    if not (
        current.available
        and current.path == destination
        and current.worktree_identity == target["identity"]
        and current.common_identity == target["common_identity"]
    ):
        return None, "destination_git_identity_changed"
    return target, None


def _save_association(
    store: Store, rows: list[dict[str, Any]], target: dict[str, Any], reason: str
) -> int:
    changed = 0
    seen = set()
    for row in rows:
        if row["id"] in seen or row["project_id"] is not None:
            continue
        seen.add(row["id"])
        if row["association_reason"] == "explicit_user_mapping" or _explicit(
            store, row["session_id"], row["id"]
        ):
            continue
        changed += store.db.execute(
            "UPDATE records SET project_id=?,worktree_id=?,association_reason=? "
            "WHERE id=? AND project_id IS NULL AND "
            "COALESCE(association_reason,'')!='explicit_user_mapping'",
            (target["project_id"], target["id"], reason, row["id"]),
        ).rowcount
    return changed


def _registered_identity_history(
    store: Store, report: dict[str, Any], cache: dict[str, Any], supported: set[str]
) -> None:
    """Recover bounded observation intervals for an already-known Git identity.

    Unlike a fresh transcript import, two direct observations supply filesystem
    identity. Only records dated within that observed transition are eligible;
    the old path is never made a timeless alias for unrelated session history.
    """
    histories = store.rows(
        "SELECT o.id,o.observed_at,o.data,w.id worktree_id,w.project_id,w.path current_path,"
        "w.identity,p.common_identity FROM observations o "
        "JOIN worktrees w ON w.id=o.worktree_id JOIN projects p ON p.id=w.project_id "
        "WHERE w.active=1 AND json_extract(o.data,'$.available')=1 "
        "AND json_extract(o.data,'$.path')!=w.path ORDER BY o.id LIMIT ?",
        (MAX_OPERATIONS + 1,),
    )
    if len(histories) > MAX_OPERATIONS:
        report["uncertainties"].append(
            {
                "code": "identity_history_limit",
                "text": "Historical location observations exceed the bounded identity scan.",
            }
        )
        return
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in histories:
        prior = json.loads(row["data"])
        old = _path(prior.get("path"))
        if (
            old
            and prior.get("worktree_identity") == row["identity"]
            and prior.get("common_identity") == row["common_identity"]
        ):
            grouped[(old, row["current_path"])].append(row)
    for (old, new), observations in grouped.items():
        if len(report["associations"]) >= MAX_OPERATIONS:
            break
        first = min(observations, key=lambda r: r["observed_at"])
        latest = store.db.execute(
            "SELECT id,observed_at FROM observations WHERE worktree_id=? "
            "AND json_extract(data,'$.path')=? AND json_extract(data,'$.available')=1 "
            "AND observed_at>=? ORDER BY observed_at,id LIMIT 1",
            (first["worktree_id"], new, first["observed_at"]),
        ).fetchone()
        if latest is None:
            continue
        spellings = _recorded_spellings(old)
        placeholders = ",".join("?" for _ in spellings)
        records = store.rows(
            "SELECT r.id,r.session_id,r.project_id,r.worktree_id,r.association_reason "
            f"FROM records r WHERE r.cwd IN ({placeholders}) AND r.time_status='known' "
            "AND r.event_time>=? AND r.event_time<=? "
            "AND (r.project_id IS NULL OR r.association_reason=?) "
            "AND EXISTS (SELECT 1 FROM occurrences oc JOIN generations g ON g.id=oc.generation_id "
            "JOIN sources s ON s.id=g.source_id WHERE oc.record_id=r.id "
            "AND g.status='current' AND s.status IN ('ready','partial')) LIMIT ?",
            (
                *spellings,
                first["observed_at"],
                latest["observed_at"],
                IDENTITY_REASON,
                MAX_SESSION_RECORDS + 1,
            ),
        )
        if not records:
            continue
        target, failure = _destination(store, new, old, cache)
        if len(records) > MAX_SESSION_RECORDS:
            failure = "identity_record_limit"
        if failure or target is None:
            report["uncertainties"].append(
                {
                    "code": failure,
                    "observation_ids": [first["id"], latest["id"]],
                    "text": "Historical filesystem identity could not safely resolve the old location.",
                }
            )
            continue
        conflicts = store.db.execute(
            "SELECT 1 FROM observations WHERE json_extract(data,'$.path')=? "
            "AND json_extract(data,'$.available')=1 "
            "AND (json_extract(data,'$.worktree_identity') IS NOT ? "
            "OR json_extract(data,'$.common_identity') IS NOT ?) LIMIT 1",
            (old, target["identity"], target["common_identity"]),
        ).fetchone()
        if conflicts:
            report["uncertainties"].append(
                {
                    "code": "historical_git_identity_conflict",
                    "observation_ids": [first["id"]],
                    "text": "The historical path has conflicting Git identities; explicit mapping is required.",
                }
            )
            continue
        supported.update(row["id"] for row in records)
        count = _save_association(store, records, target, IDENTITY_REASON)
        report["associated_records"] += count
        report["associations"].append(
            {
                "session_id": None,
                "project_id": target["project_id"],
                "worktree_id": target["id"],
                "reason": IDENTITY_REASON,
                "associated_records": count,
                "evidence_record_ids": [],
                "observation_ids": [first["id"], latest["id"]],
                "from_path": old,
                "to_path": new,
                "scope": "bounded_registered_identity_interval",
                "interval": {"from": first["observed_at"], "to": latest["observed_at"]},
            }
        )


def reconcile_moves(store: Store) -> dict[str, Any]:
    """Associate defensible historical context and persist a bounded report.

    May be called inside the refresh/registration transaction. Repeated calls
    retain evidence summaries and count only newly associated records. Existing
    explicit mappings are neither rewritten nor converted to inferred aliases.
    """
    report: dict[str, Any] = {
        "associated_records": 0,
        "associations": [],
        "observed_operations": [],
        "uncertainties": [],
        "method": "recorded-move-v1",
        "caveat": _CAVEAT,
    }
    executions, limited = _executions(store)
    candidates: dict[str, dict[str, Any]] = {}
    by_generation: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in executions:
        by_generation[(row["session_id"], row["generation_id"])].append(row)
        move = _move(row["argv"])
        if move:
            row["move"] = move
            candidates.setdefault(row["id"], row)
    if limited or len(candidates) > MAX_OPERATIONS:
        report["uncertainties"].append(
            {"code": "move_evidence_limit", "text": "Evidence exceeds the bounded move scan."}
        )
        candidates = {}
    endpoints: dict[str, set[str]] = defaultdict(set)
    for row in candidates.values():
        for path in row["move"]:
            endpoints[path].add(row["id"])
    cache: dict[str, Any] = {}
    supported: set[str] = set()
    with store.transaction():
        for row in candidates.values():
            old, new = row["move"]
            session, generation = row["session_id"], row["generation_id"]
            refs = [row["id"]]
            operation: dict[str, Any] = {
                "kind": "directory_move",
                "category": "observed_operation",
                "scope": "historical",
                "session_id": session,
                "event_time": row["event_time"],
                "time_status": row["time_status"],
                "record_ids": refs,
                "source_ids": [row["native_id"]],
                "from_path": old,
                "to_path": new,
                "project_id": None,
                "worktree_id": None,
                "text": "Successful directory-move command recorded; project completion is unknown.",
                "caveat": _CAVEAT,
            }
            report["observed_operations"].append(operation)
            failure = None
            target = None
            context = _eligible_rows(store, session, generation)
            anchored = [
                r
                for r in context
                if _path(r["cwd"]) == old
                and _position(r["locator"]) is not None
                and int(_position(r["locator"]) or 0) < row["position"]
            ]
            related = by_generation[(session, generation)]
            roots = [r for r in related if r["position"] > row["position"] and _git_root(r, new)]
            if len(context) > MAX_SESSION_RECORDS:
                failure = "session_evidence_limit"
            elif not anchored:
                failure = "missing_prior_source_context"
            elif len(endpoints[old] | endpoints[new]) != 1:
                failure = "ambiguous_move_endpoints"
            elif not roots:
                failure = "missing_later_git_root_evidence"
            elif any(
                row["position"] < r["position"] < min(root["position"] for root in roots)
                for r in related
            ):
                failure = "intervening_execution_requires_review"
            elif any(_git_root(r, new) and r["position"] < row["position"] for r in related):
                failure = "destination_existed_before_move"
            elif any(
                r["argv"]
                and r["argv"][0] in {"cp", "/bin/cp", "/usr/bin/cp"}
                and any(_path(arg) in {old, new} for arg in r["argv"][1:])
                for r in related
            ):
                failure = "copy_operation_conflicts_with_move"
            else:
                target, failure = _destination(store, new, old, cache)
            if not failure and target:
                # Any available old-path Git observation must agree with the
                # current target, even if that observation is now historical.
                for observation in store.rows(
                    "SELECT data FROM observations WHERE json_extract(data,'$.path')=?",
                    (old,),
                ):
                    prior = json.loads(observation["data"])
                    if prior.get("available") and (
                        prior.get("worktree_identity") != target["identity"]
                        or prior.get("common_identity") != target["common_identity"]
                    ):
                        failure = "historical_git_identity_conflict"
                        break
            if failure or target is None:
                operation["association_status"] = "uncertain"
                report["uncertainties"].append(
                    {
                        "code": failure or "identity_unresolved",
                        "session_id": session,
                        "record_ids": refs.copy(),
                        "text": "Automatic move association withheld; use an explicit session or record mapping after verifying the intended project/worktree.",
                    }
                )
                continue
            root = min(roots, key=lambda r: r["position"])
            refs.append(root["id"])
            operation["source_ids"].append(root["native_id"])
            anchor = min(anchored, key=lambda r: _position(r["locator"]) or 0)
            refs.append(anchor["id"])
            operation["source_ids"].append(anchor["native_id"])
            operation.update(
                project_id=target["project_id"],
                worktree_id=target["id"],
                association_status="supported",
                association_reason=MOVE_REASON,
            )
            selected = [r for r in context if _path(r["cwd"]) == old]
            supported.update(r["id"] for r in selected)
            count = _save_association(store, selected, target, MOVE_REASON)
            report["associated_records"] += count
            report["associations"].append(
                {
                    "session_id": session,
                    "project_id": target["project_id"],
                    "worktree_id": target["id"],
                    "reason": MOVE_REASON,
                    "associated_records": count,
                    "evidence_record_ids": refs.copy(),
                    "from_path": old,
                    "to_path": new,
                    "scope": "same_session_and_source_generation",
                }
            )
        _registered_identity_history(store, report, cache, supported)
        # Source replacement/removal or a reused location can invalidate derived
        # evidence. Explicit mappings are authoritative and survive this pass.
        stale = store.db.execute(
            "SELECT id,session_id FROM records WHERE association_reason IN (?,?)",
            (MOVE_REASON, IDENTITY_REASON),
        )
        revoked = 0
        for previous in stale:
            if previous["id"] not in supported and not _explicit(
                store, previous["session_id"], previous["id"]
            ):
                revoked += store.db.execute(
                    "UPDATE records SET project_id=NULL,worktree_id=NULL,association_reason='move_evidence_unresolved' WHERE id=?",
                    (previous["id"],),
                ).rowcount
        report["revoked_associations"] = revoked
        store.set_config(REPORT_CONFIG, report)
    return report

"""Evidence-specific context and uncertainty; no automatic completion inference."""

import json
import re
from typing import Any

from .extract import _lines
from .store import Store


def details(
    store: Store,
    pid: str,
    items: list[dict[str, Any]],
    worktrees: list[dict[str, Any]],
    worktree: str | None = None,
) -> dict[str, Any]:
    args: tuple[Any, ...] = (pid, worktree) if worktree else (pid,)
    scope = "project_id=?" + (" AND worktree_id=?" if worktree else "")
    records = store.rows(
        "SELECT id,native_id,session_id,actor,kind,text,event_time,original_time,time_status,metadata,worktree_id FROM records WHERE "
        + scope
        + " ORDER BY event_time DESC,id LIMIT 60",
        args,
    )
    uncertainty: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    objective = None
    current_heads = {w["id"]: (w.get("observation") or {}).get("head") for w in worktrees}
    historical_revisions: dict[str, tuple[str, str]] = {}
    for record in records:
        record["metadata"] = meta = json.loads(record["metadata"])
        record["source_current"] = bool(
            store.db.execute(
                "SELECT 1 FROM occurrences o JOIN generations g ON g.id=o.generation_id WHERE o.record_id=? AND g.status='current' LIMIT 1",
                (record["id"],),
            ).fetchone()
        )
        base = {
            "record_ids": [record["id"]],
            "source_ids": [record["native_id"]],
            "project_id": pid,
            "worktree_id": record["worktree_id"],
        }
        if record["time_status"] != "known":
            uncertainty.append(
                {
                    **base,
                    "code": "naive_timestamp"
                    if record["time_status"] == "naive"
                    else "unknown_timestamp",
                    "text": "Event time cannot be assigned to a local day; explicit pending work is retained.",
                }
            )
        event_type = meta.get("event_type")
        if event_type in {"turn_aborted", "error", "warning", "context_compacted", "compacted"}:
            uncertainty.append(
                {
                    **base,
                    "code": "interrupted_source"
                    if event_type == "turn_aborted"
                    else "source_event",
                    "text": f"Source records {event_type}; later activity or omitted context may be unknown.",
                }
            )
        revision = meta.get("revision")
        if revision:
            facts.append(
                {
                    **base,
                    "kind": "fact",
                    "category": "recorded_tool_result",
                    "revision": revision,
                    "text": record["text"],
                    "temporal_scope": "historical recorded revision; not current Git",
                }
            )
            historical_revisions.setdefault(record["worktree_id"], (revision, record["id"]))
        if record["kind"] == "recorded_tool_result":
            evidence.append(
                {
                    **base,
                    "kind": "evidence",
                    "category": "recorded_tool_result",
                    "status": "captured",
                    "revision": revision,
                    "metadata": meta,
                    "text": record["text"],
                    "applicability": "Historical captured output only; current applicability is unverified.",
                }
            )
        if record["actor"] == "user" and objective is None and record["source_current"]:
            match = re.search(
                r"(?im)^(?:OBJECTIVE|GOAL|HEDEF|AMAÇ):\s*(.+)$", "\n".join(_lines(record["text"]))
            )
            if match:
                objective = {"text": match[1], **base, "category": "user_intent"}
        if re.search(r"(?i)\b(?:unclear|ambiguous|not sure|belirsiz|emin değil)\b", record["text"]):
            uncertainty.append(
                {
                    **base,
                    "code": "ambiguous_path_reference",
                    "text": "The speaker explicitly reports uncertainty; prose references do not override recorded working context.",
                    "excerpt": record["text"],
                }
            )
    for captured in evidence:
        revision = captured.get("revision")
        latest = historical_revisions.get(captured["worktree_id"])
        current = current_heads.get(captured["worktree_id"])
        if revision and ((latest and latest[0] != revision) or (current and current != revision)):
            refs = captured["record_ids"] + (
                [latest[1]] if latest and latest[0] != revision else []
            )
            uncertainty.append(
                {
                    "code": "stale_verification",
                    "record_ids": refs,
                    "source_ids": captured["source_ids"],
                    "project_id": pid,
                    "worktree_id": captured["worktree_id"],
                    "text": "Captured evidence applies to an older/different recorded revision; it cannot certify the current code.",
                }
            )
        elif not revision:
            uncertainty.append(
                {
                    "code": "unknown_verification_scope",
                    "record_ids": captured["record_ids"],
                    "project_id": pid,
                    "worktree_id": captured["worktree_id"],
                    "text": "Captured result lacks a known revision/dirty-state identity; applicability remains limited.",
                }
            )
    for item in items:
        if item["kind"] == "claim" and item["category"] == "agent_claim":
            uncertainty.append(
                {
                    "code": "unverified_claim",
                    "record_ids": [item["record_id"]],
                    "source_ids": [item["native_id"]],
                    "project_id": pid,
                    "worktree_id": item["worktree_id"],
                    "text": "Agent success language is an unverified claim; no current verification is inferred.",
                }
            )
        if item.get("resolution_uncertainty"):
            uncertainty.append(
                {
                    "code": "unresolved_correction",
                    "record_ids": [item["record_id"]],
                    "text": item["resolution_uncertainty"],
                }
            )
    sources = store.rows(
        "SELECT DISTINCT s.id,s.status,s.diagnostics FROM sources s JOIN generations g ON g.source_id=s.id JOIN occurrences o ON o.generation_id=g.id JOIN records r ON r.id=o.record_id WHERE r.project_id=?",
        (pid,),
    )
    for source in sources:
        diagnostics = json.loads(source["diagnostics"])
        if source["status"] != "ready":
            uncertainty.append(
                {
                    "code": "unavailable_source"
                    if source["status"] == "missing"
                    else "incomplete_source",
                    "source_id": source["id"],
                    "record_ids": [],
                    "project_id": pid,
                    "text": f"Source coverage is {source['status']}; missing records do not imply no work.",
                    "diagnostics": diagnostics,
                }
            )
    memory = store.rows(
        "SELECT * FROM memory WHERE scope IN ('global',?) AND status='accepted' AND kind!='principle' ORDER BY updated_at DESC,id",
        (pid,),
    )
    return {
        "recent_context": records,
        "where_work_stopped": next(
            (r for r in records if r["text"] and r["actor"] in {"user", "assistant"}), None
        ),
        "historical_facts": facts,
        "recorded_evidence": evidence,
        "uncertainty_details": uncertainty,
        "objective": objective,
        "user_memory": memory,
    }

"""Evidence-specific context and uncertainty; no automatic completion inference."""

import json
import re
from typing import Any

from .semantics import conversational
from .store import Store


def _substantive(record: dict[str, Any]) -> bool:
    return (
        bool(record["text"].strip())
        and not conversational(record["text"])
        and not bool(
            re.search(r"(?m)^Message Type:.*", record["text"])
            and re.search(r"Payload:\s*$", record["text"])
        )
    )


def _result_excerpt(text: str) -> str:
    """Select bounded status lines from recorded output, without executing it."""
    lines = text.splitlines()
    expanded = []
    for line in lines[-100:]:
        if line.startswith("{"):
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    value = value.get("value", value)
                    if isinstance(value, dict) and isinstance(value.get("output"), str):
                        expanded.extend(value["output"].splitlines()[-80:])
            except ValueError, RecursionError:
                pass
        elif len(line) <= 500:
            expanded.append(line)
    selected = [
        line
        for line in expanded
        if re.search(
            r"(?i)\b(?:attempt=|generation_limit=|generation_runs=|preflight=|verified=|result=|Successfully installed|downloaded to|version_output|\d+ passed|\d+ failed)",
            line,
        )
        and len(line) <= 500
        and not re.search(
            r"\.(?:Logf|Printf|log)\(|\b(?:assert|return|def|function)\b|=>|\$\(|\|\|", line
        )
    ]
    return "\n".join(selected[-6:])


def details(
    store: Store,
    pid: str,
    items: list[dict[str, Any]],
    worktrees: list[dict[str, Any]],
    worktree: str | None = None,
    objective: dict[str, Any] | None = None,
) -> dict[str, Any]:
    args: tuple[Any, ...] = (pid, worktree) if worktree else (pid,)
    scope = "project_id=?" + (" AND worktree_id=?" if worktree else "")
    records = store.rows(
        "SELECT id,native_id,session_id,actor,kind,text,event_time,original_time,time_status,metadata,worktree_id FROM records WHERE "
        + scope
        + " AND provider!='project_document'"
        + " AND (actor IN ('user','tool') OR (actor='assistant' AND kind!='agent_proposal') OR json_extract(metadata,'$.event_type') IN ('turn_aborted','error','warning','context_compacted','compacted'))"
        + " ORDER BY event_time DESC,id LIMIT 60",
        args,
    )
    uncertainty: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
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
            "event_time": record["event_time"],
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
    user_records = store.rows(
        "SELECT id,text,event_time,worktree_id FROM records WHERE "
        + scope
        + " AND actor='user' AND EXISTS (SELECT 1 FROM occurrences o JOIN generations g ON g.id=o.generation_id WHERE o.record_id=records.id AND g.status='current') ORDER BY event_time DESC,id LIMIT 20",
        args,
    )
    latest_instruction = next((r for r in user_records if _substantive(r)), None)
    if latest_instruction:
        latest_instruction = {
            **latest_instruction,
            "record_id": latest_instruction["id"],
            "category": "recorded_user_instruction",
            "status": "recorded",
            "excerpt_omitted_chars": max(0, len(latest_instruction["text"]) - 4000),
            "text": latest_instruction["text"][:4000],
        }
    progress = []
    for captured in evidence:
        excerpt = _result_excerpt(captured["text"])
        if excerpt:
            progress.append(
                {
                    **{k: v for k, v in captured.items() if k not in {"text", "metadata"}},
                    "text": excerpt,
                    "exit_status": captured["metadata"].get("exit_status"),
                    "excerpt_only": True,
                }
            )
        if len(progress) == 3:
            break
    return {
        "latest_user_instruction": latest_instruction,
        "recent_recorded_results": progress,
        "recent_agent_updates": [
            {
                "text": r["text"][:900],
                "record_id": r["id"],
                "event_time": r["event_time"],
                "category": "agent_claim",
                "status": "unverified",
                "excerpt_omitted_chars": max(0, len(r["text"]) - 900),
            }
            for r in records
            if r["actor"] == "assistant"
            and _substantive(r)
            and (
                not latest_instruction
                or (r["event_time"] or "") >= (latest_instruction["event_time"] or "")
            )
        ][:3],
        "recent_context": records,
        "where_work_stopped": next(
            (
                r
                for r in records
                if _substantive(r)
                and r["actor"] in {"user", "assistant"}
                and r["kind"] not in {"agent_proposal", "metadata"}
            ),
            None,
        ),
        "historical_facts": facts,
        "recorded_evidence": evidence,
        "uncertainty_details": uncertainty,
        "objective": objective,
        "user_memory": memory,
    }

"""Compact source-backed context independent of the detailed-history window."""

import re
from collections.abc import Callable
from typing import Any

from .semantics import topic


def _words(text: str) -> set[str]:
    stop = {
        "the",
        "and",
        "that",
        "this",
        "with",
        "from",
        "were",
        "have",
        "been",
        "remains",
        "still",
        "not",
        "was",
        "for",
        "are",
        "recorded",
        "verification",
        "check",
        "checks",
    }
    return {w for w in re.findall(r"[^\W\d_]{3,}", text.lower()) if w not in stop}


def _distinct(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for item in items:
        if any(item["text"] == previous["text"] for previous in selected):
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def build_brief(
    items: list[dict[str, Any]],
    evidence: Callable[[str], dict[str, Any]],
    identity: dict[str, Any],
    project_id: str,
    worktree_id: str | None,
) -> dict[str, Any]:
    active = [
        i
        for i in items
        if i["source_current"]
        and i["status"] not in {"cancelled", "superseded", "rejected", "archived", "user_completed"}
    ]
    # Short explicit status paragraphs are useful entry points. Source wording,
    # evidence and nearby conditions are retained; this is presentation only.
    pending = sorted(
        [
            i
            for i in active
            if i["category"] == "documented_pending"
            and i["status"] in {"active", "pending", "blocked"}
        ],
        key=lambda i: (
            len(i["text"]) > 1000,
            -(i["text"].lower().count("unfinished") + i["text"].lower().count("unverified")),
            len(i["text"]),
        ),
    )
    selected_pending = _distinct(pending, 5)
    constraints = [i for i in active if i["kind"] == "constraint"]
    pending_words = (
        set().union(*(_words(i["text"]) for i in selected_pending)) if selected_pending else set()
    )
    constraints.sort(
        key=lambda i: (
            -bool(
                re.search(
                    r"(?i)continuous|deadline|prerequisite|does not depend|keep .{0,20}running|remain active",
                    i["text"],
                )
            ),
            -len(_words(i["text"]) & pending_words),
            len(i["text"]),
        )
    )
    purpose = [i for i in active if i["kind"] == "purpose"]
    purpose.sort(key=lambda i: (-len(i["text"]), i["id"]))

    def entry(item: dict[str, Any]) -> dict[str, Any]:
        ref = evidence(item["record_id"])
        meta = ref.get("metadata", {})
        return {
            "text": item["text"],
            "category": item["category"],
            "status": item["status"],
            "record_id": item["record_id"],
            "worktree_id": item["worktree_id"],
            "dependencies": item["dependencies"],
            "rationale": item.get("rationale"),
            "evidence": {
                "status": ref["status"],
                "locations": ref.get("locations", [])[:1],
                "relative_path": meta.get("relative_path"),
                "section": meta.get("section"),
                "line_start": meta.get("line_start"),
                "line_end": meta.get("line_end"),
                "fingerprint": meta.get("fingerprint"),
                "observed_at": meta.get("observed_at"),
                "content_scope": meta.get("content_scope"),
                "git_head": meta.get("git_head"),
                "committed_blob": meta.get("committed_blob"),
                "modified": meta.get("modified"),
            },
        }

    limitations = [
        i for i in active if i["kind"] == "limitation" or i["category"] == "documented_deferred"
    ]
    limitations.sort(
        key=lambda i: (
            -bool(
                re.search(
                    r"(?i)no remote|no .{0,20}publication|not .{0,15}run|known incomplete|not real.data.verified|unavailable.*cuts",
                    i["text"],
                )
            ),
            len(i["text"]),
        )
    )
    groups = {
        "purpose": _distinct(purpose, 1),
        "pending": selected_pending,
        "constraints": _distinct(constraints, 6),
        "limitations": _distinct(limitations, 5),
        "decisions": _distinct([i for i in active if i["kind"] == "decision"], 3),
    }
    result: dict[str, Any] = {key: [entry(i) for i in group] for key, group in groups.items()}
    result["identity"] = {
        key: [
            e
            for e in identity.get(key, [])
            if e.get("project_id") == project_id
            and (not worktree_id or e.get("worktree_id") == worktree_id)
        ]
        for key in ("associations", "observed_operations", "uncertainties")
    }
    result["omitted"] = max(
        0, len(items) - len({i["id"] for group in groups.values() for i in group})
    )
    result["freshness"] = (
        "Documents describe their observed working-tree contents, not freshly executed tests. Refresh explicitly to detect edits, moves or deletion."
    )
    result["conflicts"] = []
    for uncertainty in identity.get("uncertainties", []):
        if not uncertainty.get("project_id"):
            result["conflicts"].append(
                {
                    "text": "Unattributed identity evidence in configured sources: "
                    + str(uncertainty.get("code", "unknown"))
                    + ". It is not assigned to this project; use an explicit mapping only after checking evidence.",
                    "record_ids": [],
                }
            )
    by_topic: dict[str, list[dict[str, Any]]] = {}
    for item in active:
        by_topic.setdefault(topic(item["text"]), []).append(item)
    for candidates in by_topic.values():
        if any(i["category"] == "documented_pending" for i in candidates) and any(
            i["category"] == "documented_claim" for i in candidates
        ):
            result["conflicts"].append(
                {
                    "text": "Sources disagree on resolution; completion remains unverified.",
                    "record_ids": [i["record_id"] for i in candidates],
                }
            )
    if pending and any(
        i["status"] == "historical" or i["category"] == "documented_claim" for i in items
    ):
        result["conflicts"].append(
            {
                "text": "Pending work coexists with historical or documented passing results. They retain their own scope; no later completion is inferred.",
                "record_ids": [],
            }
        )
    historical_pending = [
        i for i in items if i.get("historical_status") in {"active", "pending", "blocked"}
    ]
    if historical_pending:
        result["conflicts"].append(
            {
                "text": f"{len(historical_pending)} prior pending statements changed or disappeared from current document generations; their resolution is unknown. Inspect expanded items/explain for provenance.",
                "record_ids": [i["record_id"] for i in historical_pending[:5]],
            }
        )
    return result

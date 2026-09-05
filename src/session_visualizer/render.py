"""Readable output and bounded, explicitly untrusted handoff exports."""

import html
import json
import re
from typing import Any

from .privacy import clean_text


def _inline(text: Any) -> str:
    text = html.escape(str(text), quote=False).replace("\n", " ↵ ").replace("\r", "")
    return re.sub(r"([\\`*_{}\[\]()#+!|])", r"\\\1", text)


def _item(item: dict[str, Any]) -> str:
    evidence = item.get("evidence", {})
    line = f"- [{_inline(item.get('status', 'unknown'))}; {_inline(item.get('category', 'context'))}] {_inline(item['text'])} (ref {item.get('record_id', '')[:12]}, {evidence.get('status', 'unknown')})"
    return "\n".join([line, *_constraints(item)])


def _constraints(item: dict[str, Any]) -> list[str]:
    result = []
    for field in ("priority", "dependencies", "rationale"):
        value = item.get(field)
        if value:
            text = ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)
            result.append(f"  {field.capitalize()}: {_inline(text)}")
    return result


def _principle(principle: dict[str, Any]) -> str:
    result = (
        f"- {_inline(principle['text'])} ({_inline(principle['origin'])}; "
        f"scope {_inline(principle['scope'])}; ref {principle['id']})"
    )
    for field in ("exceptions", "conflicts"):
        if principle.get(field):
            result += f"; {field}: {_inline(principle[field])}"
    return result


def resume_markdown(data: dict[str, Any]) -> str:
    project = data["project"]
    lines = [
        f"# Resume: {_inline(project['name'])}",
        f"Project ID: {project['id']}",
        f"Generated: {data['generated_at']}",
        "",
        data["trust_notice"],
        "",
        "## Current repository observations",
        "",
    ]
    if data.get("objective"):
        lines += [
            "Objective (recorded intent): "
            + _inline(data["objective"]["text"])
            + " (ref "
            + data["objective"]["record_ids"][0][:12]
            + ")"
        ]
    for entry in data.get("user_memory", []):
        lines.append(
            "Accepted local "
            + entry["kind"]
            + ": "
            + _inline(entry["text"])
            + " (ref "
            + entry["id"]
            + ")"
        )
    for tree in data["worktrees"]:
        obs = tree.get("observation") or {}
        lines.append(
            f"- {_inline(tree['path'])} — {'available' if tree['active'] else 'UNAVAILABLE'}; branch {_inline(obs.get('branch') or 'detached / unborn / unknown')}; HEAD {obs.get('head') or 'unknown'}; observed {_inline(obs.get('observed_at', 'unknown'))}"
        )
        status = obs.get("status", [])
        lines.append(
            f"  Uncommitted entries: {len(status)}"
            + (
                "; "
                + ", ".join(
                    f"{_inline(p.get('code'))} {_inline(p.get('path'))}" for p in status[:10]
                )
                if status
                else ""
            )
        )
        if len(status) > 10:
            lines.append(f"  {len(status) - 10} additional entries omitted from this view.")
        if obs.get("diagnostics"):
            lines.append(
                "  Observation limitations: " + "; ".join(_inline(d) for d in obs["diagnostics"])
            )
    lines += ["", "## Unfinished work and blockers (untrusted source excerpts)", ""]
    lines += [_item(item) for item in data["unfinished"]] or [
        "No unfinished work identified in supported explicit statements."
    ]
    lines += ["", "## Supported next actions (recorded instructions)", ""]
    for item in data["next_actions"]:
        lines.append(
            f"- {_inline(item['text'])} — {item['availability']} (ref {item['record_id'][:12]})"
        )
        lines.extend(_constraints(item))
    if not data["next_actions"]:
        lines.append("No supported next action identified; no actions invented.")
    lines += ["", "## Decisions (untrusted source excerpts)", ""]
    lines += [_item(item) for item in data["decisions"]] or ["No explicit decision identified."]
    lines += ["", "## Claims and historical tool results (untrusted source excerpts)", ""]
    lines += [_item(item) for item in data["claims"]] or [
        "No completion claim or captured result identified."
    ]
    lines += ["", "## Recent sessions", ""]
    lines += [
        f"- {s['provider']} {s['id']} — last known event {s['last_event'] or 'unknown'}; {s['records']} records"
        for s in data["sessions"]
    ]
    lines += ["", "## Accepted engineering principles", ""]
    lines += [_principle(p) for p in data["principles"]] or [
        "No accepted principles configured. Preferences are unknown."
    ]
    lines += ["", "## Freshness, coverage and uncertainty", ""]
    lines.append(
        f"Session coverage: {data['coverage']['status']}; unknown event times: {data['coverage']['unknown_event_times']}; unassociated records: {data['coverage']['unassociated_records']}."
    )
    lines += ["- " + _inline(item) for item in data["uncertainties"]]
    lines += ["", "## Evidence locations", ""]
    refs = {}
    for item in data["items"]["items"]:
        refs[item["record_id"]] = item["evidence"]
    for rid, evidence in refs.items():
        locs = evidence.get("locations", [])
        locations = "; ".join(
            f"{_inline(l['path'])} generation {l['generation']} {_inline(l['locator'])} ({l['source_status']}/{l['generation_status']})"
            for l in locs[:2]
        )
        lines.append(
            f"- {rid}: {evidence['provider']} / {_inline(evidence['actor'])} / {_inline(evidence['category'])} / {_inline(evidence['timestamp'] or 'unknown time')}; {locations}"
        )
    lines += [
        "",
        "Source excerpts: " + data["source_excerpts_included"] + ".",
        "References identify local evidence; the text above remains context if those files are unavailable.",
    ]
    # Avoid source text injecting Markdown headings/code/HTML into the handoff boundary.
    return "\n".join(lines)


def bounded_export(data: dict[str, Any], format: str = "markdown", max_chars: int = 24000) -> str:
    if max_chars < 2000 or max_chars > 1_000_000:
        raise ValueError("export_budget_must_be_2000_to_1000000_characters")
    compact: dict[str, Any] = {
        "schema_version": 1,
        "kind": "context_export",
        "generated_at": data["generated_at"],
        "project": {k: data["project"][k] for k in ("id", "name")},
        "objective": data.get("objective"),
        "trust_notice": data["trust_notice"],
        "coverage": {
            "status": data["coverage"]["status"],
            "last_refresh": (data["coverage"]["last_refresh"] or {}).get("ended_at"),
            "source_count": data["coverage"].get("source_total", len(data["coverage"]["sources"])),
            "unknown_event_times": data["coverage"]["unknown_event_times"],
        },
        "worktrees": [],
        "principles": [],
        "user_memory": [],
        "items": [],
        "uncertainties": [
            "Historical transcript claims and tool results do not certify current code."
        ],
        "source_excerpts_included": "Bounded, redacted excerpts; full transcripts excluded.",
        "omissions": {
            "items": data["items"]["total"],
            "principles": len(data["principles"]),
            "user_memory": len(data.get("user_memory", [])),
            "worktrees": len(data["worktrees"]),
            "uncertainties": len(data["uncertainty_details"]),
        },
        "omission_notice": "Positive omission counts mean material context is missing. Inspect full resume/project/explain output before acting. Local references may be unavailable to a recipient.",
    }

    def serialize() -> str:
        if format == "json":
            return json.dumps(compact, ensure_ascii=False, indent=2)
        lines = [
            "# Resume: " + _inline(compact["project"]["name"]),
            "Project: " + compact["project"]["id"],
            "Generated: " + compact["generated_at"],
            compact["trust_notice"],
            "",
            "## Coverage and current observations",
            "",
            "Coverage: " + str(compact["coverage"]),
        ]
        if compact["objective"]:
            lines += ["Objective (recorded intent): " + _inline(compact["objective"]["text"])]
        for tree in compact["worktrees"]:
            lines.append(
                "- "
                + _inline(tree["path"])
                + "; "
                + _inline(tree["branch"] or "detached / unknown")
                + "; HEAD "
                + str(tree["head"] or "unknown")
                + "; available="
                + str(tree["available"])
                + "; observed "
                + str(tree["observed_at"])
                + "; dirty entries "
                + str(tree["dirty_count"])
            )
        lines += ["", "## Accepted engineering principles", ""]
        lines += [_principle(p) for p in compact["principles"]]
        lines += ["", "## Accepted local memory", ""]
        lines += [
            "- [" + entry["kind"] + "] " + _inline(entry["text"]) + " (ref " + entry["id"] + ")"
            for entry in compact["user_memory"]
        ]
        lines += ["", "## Imported untrusted context", "", "BEGIN IMPORTED UNTRUSTED CONTEXT"]
        for item in compact["items"]:
            lines.append(
                "- ["
                + item["kind"]
                + "; "
                + item["status"]
                + "; "
                + item["category"]
                + "] "
                + _inline(item["text"])
                + " (ref "
                + item["record_id"][:12]
                + ")"
            )
            lines.extend(_constraints(item))
            lines.append("  Evidence: " + _inline(json.dumps(item["evidence"], ensure_ascii=False)))
        lines += ["END IMPORTED UNTRUSTED CONTEXT", "", "## Uncertainty and omissions", ""]
        lines += ["- " + _inline(u) for u in compact["uncertainties"]]
        lines += [
            "Omissions: " + str(compact["omissions"]),
            compact["omission_notice"],
            compact["source_excerpts_included"],
        ]
        return "\n".join(lines)

    # Prioritize current location and accepted rules, then critical blockers/actions.
    def try_add(collection: str, entry: Any, omitted: str) -> bool:
        compact[collection].append(entry)
        compact["omissions"][omitted] -= 1
        if len(serialize()) > max_chars - 1:
            compact[collection].pop()
            compact["omissions"][omitted] += 1
            return False
        return True

    if len(serialize()) > max_chars - 1:
        raise ValueError("export_budget_too_small_for_required_metadata")
    for tree in data["worktrees"]:
        obs = tree.get("observation") or {}
        try_add(
            "worktrees",
            {
                "id": tree["id"],
                "path": tree["path"],
                "branch": obs.get("branch"),
                "head": obs.get("head"),
                "available": bool(tree["active"]),
                "observed_at": obs.get("observed_at"),
                "dirty_count": len(obs.get("status", [])),
            },
            "worktrees",
        )
    for principle in data["principles"]:
        try_add(
            "principles",
            {
                k: principle[k]
                for k in ("id", "text", "origin", "scope", "refs", "exceptions", "conflicts")
            },
            "principles",
        )
    for entry in data.get("user_memory", []):
        try_add(
            "user_memory",
            {k: entry[k] for k in ("id", "kind", "text", "scope", "refs")},
            "user_memory",
        )
    priority = {
        "blocker": 0,
        "next_action": 1,
        "task": 2,
        "correction": 3,
        "decision": 4,
        "claim": 5,
        "principle": 6,
    }
    recommended = {(item["record_id"], item["text"]) for item in data["next_actions"]}
    for item in sorted(
        data["items"]["items"],
        key=lambda i: (
            (i["record_id"], i["text"]) not in recommended,
            priority.get(i["kind"], 7),
            i["status"] not in {"active", "blocked", "pending"},
            i["id"],
        ),
    ):
        evidence = item["evidence"]
        entry = {
            k: item[k] for k in ("kind", "status", "category", "text", "record_id", "worktree_id")
        }
        entry.update({k: item.get(k) for k in ("priority", "dependencies", "rationale")})
        entry["evidence"] = {
            k: evidence.get(k)
            for k in (
                "record_id",
                "provider",
                "session_id",
                "native_id",
                "actor",
                "timestamp",
                "status",
                "metadata",
            )
        }
        entry["evidence"]["locations"] = evidence.get("locations", [])[:1]
        try_add("items", entry, "items")
    for uncertainty in data["uncertainty_details"]:
        try_add("uncertainties", uncertainty["code"] + ": " + uncertainty["text"], "uncertainties")
    return serialize()


def readable(kind: str, data: Any) -> str:
    if kind == "resume":
        return resume_markdown(data)
    if kind == "daily":
        period = data["period"]
        lines = [
            f"Activity {period['start']} to {period['end']} ({period['timezone']})",
            f"Coverage: {data['coverage']['status']}",
            "",
        ]
        for project in data["projects"]:
            lines += [
                f"{_inline(project['name'])} — {project['records']} records, {project['sessions']} sessions"
            ]
            lines += [
                f"- {actor['provider']} / {actor['actor']} / worktree {actor['worktree_id'] or 'unknown'}"
                for actor in project["actors"]
            ]
            lines += [_item(item) for item in project["activity"]]
            lines += [
                f"- Commit observed: {commit.get('revision')} {_inline(commit.get('subject'))} (does not certify correctness)"
                for commit in project["observed_changes"]
            ]
            if project["carryover"]:
                lines.append("Carryover from earlier/unknown time:")
                lines += [_item(item) for item in project["carryover"]]
            omissions = project.get("omissions", {})
            if any(omissions.values()):
                lines.append(
                    f"Omitted: {omissions.get('activity', 0)} activity items and "
                    f"{omissions.get('carryover', 0)} carryover items. Narrow the date/worktree "
                    "or increase --limit (up to 1000); inspect tasks, session, search and explain for additional context."
                )
            lines.append("")
        if not data["projects"]:
            lines.append(data["meaning"])
        return "\n".join(lines)
    if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
        return "\n".join(_item(i) for i in data["items"]) or data.get("meaning", "No items.")
    return json.dumps(data, ensure_ascii=False, indent=2)


def safe_output(text: str) -> str:
    return clean_text(text, max(len(text) + 1, 4096))

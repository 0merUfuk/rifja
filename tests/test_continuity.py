"""Independent corpus acceptance through native files, ingestion, SQLite and App.

The source builder receives events only, never the expected oracle. All Git
repositories, provider exports, source failures and HOME values are synthetic.
"""

from __future__ import annotations

import inspect
import json
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from session_visualizer.app import App
from session_visualizer.ingest import Ingestor
from session_visualizer.render import bounded_export
from session_visualizer.store import Store

CORPUS = json.loads((Path(__file__).parent / "corpus" / "continuity.json").read_text())
PROVIDERS = {"provider-a": "codex", "provider-b": "claude", "provider-c": "hermes"}
ACTIVE = {"active", "blocked", "pending"}
UNSUPPORTED_DONE = {"verified", "verified_complete", "complete", "completed", "verified_completed"}


def git(path: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=Synthetic Corpus",
            "-c",
            "user.email=corpus@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-C",
            str(path),
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class Fixture:
    def __init__(self, root: Path, app: App):
        self.root, self.app = root, app
        self.projects: dict[str, str] = {}
        self.paths: dict[str, Path] = {}
        self.worktrees: dict[str, str] = {}
        self.native: dict[str, tuple[str, str, str]] = {}
        self.source_paths: dict[str, Path] = {}
        self.revisions: dict[str, str] = {}
        self.events: dict[str, dict] = {}

    def build(self, events: list[dict]) -> None:
        """Input is source events only: expected assertions cannot leak here."""
        self.events = {event["id"]: event for event in events}
        for name in sorted({event["project"] for event in events}):
            main = self.root / "repos" / name / "main"
            main.mkdir(parents=True)
            git(main, "init", "-q", "-b", "main")
            git(main, "commit", "--allow-empty", "-qm", "Synthetic initial fixture")
            old = git(main, "rev-parse", "HEAD")
            git(main, "commit", "--allow-empty", "-qm", "Synthetic current fixture")
            new = git(main, "rev-parse", "HEAD")
            if name == "harbor":
                self.revisions = {"a111111": old, "b222222": new}
            self.paths[f"/synthetic/{name}/main"] = main
            for source_path in sorted(
                {event["worktree"] for event in events if event["project"] == name}
            ):
                if source_path in self.paths:
                    continue
                target = self.root / "repos" / name / "worktrees" / Path(source_path).name
                git(main, "worktree", "add", "-q", "-b", Path(source_path).name, str(target))
                self.paths[source_path] = target
            registered = self.app.register(main, name)
            self.projects[name] = registered["project"]["id"]
            by_path = {worktree["path"]: worktree["id"] for worktree in registered["worktrees"]}
            for synthetic_path, actual_path in self.paths.items():
                if str(actual_path) in by_path:
                    self.worktrees[synthetic_path] = by_path[str(actual_path)]
        sources = self.root / "sources"
        sources.mkdir()
        for event in events:
            self._source(event, sources)
        self.refresh = Ingestor(self.app.store).refresh()
        self.records = {}
        for source_id, (provider, session, native_id) in self.native.items():
            rows = self.app.store.rows(
                "SELECT r.* FROM records r JOIN sessions s ON s.id=r.session_id WHERE r.provider=? AND s.native_id=? AND r.native_id=?",
                (provider, session, native_id),
            )
            assert len(rows) == 1, (source_id, provider, session, native_id, self.refresh)
            self.records[source_id] = rows[0]
        self.source_by_record = {
            record["id"]: source_id for source_id, record in self.records.items()
        }

    def transform(self, text: str) -> str:
        for synthetic, actual in sorted(
            self.paths.items(), key=lambda pair: len(pair[0]), reverse=True
        ):
            text = text.replace(synthetic, str(actual))
        for synthetic, actual in self.revisions.items():
            text = text.replace(synthetic, actual)
        return text

    def _source(self, event: dict, sources: Path) -> None:
        source_id = event["id"]
        provider = PROVIDERS[event["provider"]]
        path = sources / f"{source_id}.{'db' if provider == 'hermes' else 'jsonl'}"
        self.source_paths[source_id] = path
        metadata = event.get("metadata", {})
        if metadata.get("availability") == "unavailable":
            path.write_text("")
            self.app.source_add(provider, path)
            path.unlink()
            return
        if metadata.get("availability") == "partial":
            path.write_text('{"type":"response_item","payload":')
            self.app.source_add(provider, path)
            return
        cwd = str(self.paths[event["worktree"]])
        timestamp, actor, text = event["timestamp"], event["actor"], self.transform(event["text"])
        session = f"synthetic-{source_id}"
        meta = dict(metadata)
        if "revision" in meta:
            meta["revision"] = self.revisions.get(meta["revision"], meta["revision"])
        if provider == "codex":
            header = {
                "type": "session_meta",
                "timestamp": timestamp,
                "payload": {"id": session, "cwd": cwd},
            }
            envelope = {"type": "response_item", "timestamp": timestamp, "cwd": cwd}
            native_id = source_id
            if meta.get("capture_status") == "interrupted":
                envelope.update(type="event_msg", payload={"type": "turn_aborted"})
                native_id = "line:2"
            elif actor == "tool":
                # A real native structured output retains recorded revision and
                # command metadata without supplying expected oracle fields.
                envelope["payload"] = {
                    "type": "function_call_output",
                    "id": source_id,
                    "call_id": f"call-{source_id}",
                    "output": {"type": "text", "text": text, **meta},
                }
            else:
                envelope["payload"] = {
                    "type": "message",
                    "id": source_id,
                    "role": actor,
                    "content": [
                        {"type": "input_text" if actor == "user" else "output_text", "text": text}
                    ],
                }
            payloads = [header, envelope]
            path.write_text(
                "".join(json.dumps(payload, ensure_ascii=False) + "\n" for payload in payloads)
            )
        elif provider == "claude":
            native_id = source_id + ":block:0"
            payload = {
                "type": actor,
                "uuid": source_id,
                "sessionId": session,
                "timestamp": timestamp,
                "cwd": cwd,
                "message": {"role": actor, "content": [{"type": "text", "text": text}]},
            }
            path.write_text(json.dumps(payload, ensure_ascii=False) + "\n")
        else:
            native_id = "1"
            with sqlite3.connect(path) as conn:
                conn.execute(
                    "CREATE TABLE sessions(id TEXT PRIMARY KEY, started_at REAL, cwd TEXT)"
                )
                conn.execute(
                    "CREATE TABLE messages(id INTEGER PRIMARY KEY,session_id TEXT,role TEXT,content TEXT,timestamp REAL)"
                )
                instant = datetime.fromisoformat(timestamp).timestamp()
                conn.execute("INSERT INTO sessions VALUES(?,?,?)", (session, instant, cwd))
                conn.execute(
                    "INSERT INTO messages VALUES(?,?,?,?,?)", (1, session, actor, text, instant)
                )
        self.native[source_id] = (provider, session, native_id)
        self.app.source_add(provider, path)

    def source_id(self, item: dict) -> str | None:
        return self.source_by_record.get(item.get("record_id"))


def _surface_errors(case: dict, fx: Fixture, resume: dict) -> list[str]:
    errors = []
    items = resume["items"]["items"]
    coverage = resume["coverage"]
    visible = json.dumps(resume, ensure_ascii=False).casefold()
    by_source: dict[str, list[dict]] = {}
    for item in items:
        by_source.setdefault(fx.source_id(item), []).append(item)
    for requirement in case["expected"]["must_surface"]:
        kind, source_ids = requirement["kind"], requirement["source_ids"]
        label = f"{kind}:{','.join(source_ids)}"
        if kind == "uncertainty":
            code = requirement["code"]
            if code == "unverified_claim":
                okay = all(
                    any(
                        item["status"] == "unverified" and item["category"] == "agent_claim"
                        for item in by_source.get(source_id, [])
                    )
                    for source_id in source_ids
                )
            elif code == "naive_timestamp":
                okay = all(
                    any(
                        item["evidence"]["time_status"] == "naive"
                        for item in by_source.get(source_id, [])
                    )
                    for source_id in source_ids
                )
            elif code == "source_incomplete":
                okay = all(
                    any(
                        source["path"] == str(fx.source_paths[source_id])
                        and source["status"] == "partial"
                        and any(
                            diagnostic["code"] == "incomplete_tail"
                            for diagnostic in source["diagnostics"]
                        )
                        for source in coverage["sources"]
                    )
                    for source_id in source_ids
                )
            elif code == "source_unavailable":
                okay = coverage["status"] == "partial" and all(
                    str(fx.source_paths[source_id]).casefold() in visible
                    for source_id in source_ids
                )
            elif code == "interrupted_source":
                okay = any(token in visible for token in ("turn_aborted", "interrupted")) and all(
                    fx.records[source_id]["id"] in visible for source_id in source_ids
                )
            elif code == "stale_verification":
                # Explicit applicability is required, not merely a blanket
                # historical-evidence disclaimer elsewhere in the output.
                uncertainty_text = json.dumps(
                    resume.get("uncertainties", []), ensure_ascii=False
                ).casefold()
                okay = any(
                    token in uncertainty_text
                    for token in (
                        "stale",
                        "older revision",
                        "different revision",
                        "revision mismatch",
                        "predates",
                    )
                )
            elif code == "ambiguous_path_reference":
                okay = all(
                    fx.records[source_id]["id"] in visible for source_id in source_ids
                ) and any(
                    token in visible for token in ("ambiguous", "does not identify which checkout")
                )
            else:
                raise AssertionError(f"Unimplemented uncertainty assertion: {code}")
            if not okay:
                errors.append(
                    f"{label}: required {code} uncertainty with source provenance is missing"
                )
            continue
        for source_id in source_ids:
            matches = by_source.get(source_id, [])
            wanted_kind = "claim" if kind in {"evidence", "fact"} else kind
            matches = [item for item in matches if item["kind"] == wanted_kind]
            if not matches:
                errors.append(f"{label}: no surfaced item of kind {wanted_kind}")
                continue
            scope = requirement["scope"]
            for item in matches:
                if (
                    item["project_id"] != fx.projects[scope["project"]]
                    or item["worktree_id"] != fx.worktrees[scope["worktree"]]
                ):
                    errors.append(f"{label}: wrong project/worktree attribution")
                if not item["text"].strip() or not item["evidence"]["locations"]:
                    errors.append(f"{label}: missing usable text or captured source provenance")
                expected_status = requirement.get("status")
                expected_status = {
                    "open": "blocked" if kind == "blocker" else "active",
                    "captured": "recorded",
                }.get(expected_status, expected_status)
                if expected_status and item["status"] != expected_status:
                    errors.append(
                        f"{label}: status {item['status']!r}, expected {expected_status!r}"
                    )
                if (
                    requirement.get("revision")
                    and item["evidence"]["metadata"].get("revision")
                    != fx.revisions[requirement["revision"]]
                ):
                    errors.append(f"{label}: captured revision applicability is missing or wrong")
                if (
                    requirement.get("temporal_status") == "unresolved"
                    and item["evidence"]["time_status"] != "naive"
                ):
                    errors.append(f"{label}: unresolved timestamp was assigned a known date")
            if kind == "correction":
                actual_targets = {item["target"] for item in matches}
                if not actual_targets >= set(requirement.get("related_source_ids", [])):
                    errors.append(f"{label}: explicit predecessor references were lost")
            if kind in {"blocker", "next_action"} and requirement.get("critical"):
                active = resume["unfinished"] if kind == "blocker" else resume["next_actions"]
                if source_id not in {fx.source_id(item) for item in active}:
                    errors.append(f"{label}: CRITICAL item missing from the actionable handoff")
    return errors


def _prohibition_errors(case: dict, fx: Fixture, resume: dict) -> list[str]:
    errors = []
    items = resume["items"]["items"]
    active = [item for item in items if item["status"] in ACTIVE]
    forbidden_done = [
        item
        for item in items
        if item["status"] in UNSUPPORTED_DONE or item["category"] == "controlled_verification"
    ]
    if forbidden_done:
        errors.append("unsupported_completion: imported transcript items became verified/completed")
    for item in items:
        source_id = fx.source_id(item)
        if source_id is None:
            errors.append("missing_provenance: surfaced item has no mapped captured source")
            continue
        event = fx.events[source_id]
        if (
            item["project_id"] != fx.projects[event["project"]]
            or item["worktree_id"] != fx.worktrees[event["worktree"]]
        ):
            errors.append(f"cross_scope_attribution:{source_id}")
    supported = {
        "unsupported_completion",
        "invented_action",
        "cancelled_action_active",
        "cancelled_task_complete",
        "superseded_decision_active",
        "claim_promoted_to_evidence",
        "stale_evidence_verifies_current",
        "cross_project_attribution",
        "cross_worktree_attribution",
        "cross_scope_transition",
        "absence_claim_from_missing_source",
        "invented_missing_content",
        "unsupported_resolution",
        "source_coverage_overstated",
        "quoted_or_code_intent",
        "irrelevant_chat_intent",
        "path_mention_changes_scope",
        "wrong_local_day",
        "wrong_instant_order",
        "invented_missing_hour_activity",
        "host_timezone_assumed",
        "unresolved_timestamp_dropped",
        "proposal_promoted_to_decision",
    }
    for prohibition in case["expected"]["must_not_assert"]:
        predicate = prohibition["predicate"]
        assert predicate in supported, f"Unimplemented prohibition: {predicate}"
        sources = set(prohibition.get("source_ids", []))
        if predicate in {
            "cancelled_action_active",
            "superseded_decision_active",
            "quoted_or_code_intent",
            "irrelevant_chat_intent",
            "proposal_promoted_to_decision",
        }:
            if sources & {fx.source_id(item) for item in active}:
                errors.append(f"{predicate}: forbidden source appears as active work")
        elif predicate == "claim_promoted_to_evidence":
            if any(
                fx.source_id(item) in sources and item["category"] != "agent_claim"
                for item in items
            ):
                errors.append(f"{predicate}: agent claim category was lost")
        elif predicate in {"absence_claim_from_missing_source", "source_coverage_overstated"}:
            if resume["coverage"]["status"] != "partial":
                errors.append(f"{predicate}: coverage incorrectly reports complete")
        elif predicate == "host_timezone_assumed":
            if any(fx.records[source_id]["event_time"] is not None for source_id in sources):
                errors.append(f"{predicate}: naive timestamp was assigned an instant")
        elif predicate == "stale_evidence_verifies_current" and any(
            fx.source_id(item) in sources and item["status"] not in {"recorded", "unverified"}
            for item in items
        ):
            errors.append(f"{predicate}: historical result promoted to current verification")
        # Remaining predicates are checked by universal attribution/provenance,
        # explicit surface states, scoped/day selection, and transition checks.
    for field, kind in (
        ("active_action_source_ids", "next_action"),
        ("active_blocker_source_ids", "blocker"),
    ):
        if field in case["expected"]:
            actual = {fx.source_id(item) for item in active if item["kind"] == kind}
            if actual != set(case["expected"][field]):
                errors.append(
                    f"{field}: got {sorted(str(x) for x in actual)}, expected {case['expected'][field]}"
                )
    return errors


def _export_errors(case: dict, fx: Fixture, resume: dict) -> list[str]:
    errors = []
    markdown = bounded_export(resume, "markdown", 24000)
    exported = json.loads(bounded_export(resume, "json", 24000))
    if "data" in exported:
        exported_items = exported["data"]["items"]["items"]
    else:
        exported_items = exported["items"]
    for requirement in case["expected"]["must_surface"]:
        if not requirement.get("critical"):
            continue
        for source_id in requirement["source_ids"]:
            rid = fx.records[source_id]["id"]
            matching = [
                item
                for item in exported_items
                if item["record_id"] == rid
                and item["kind"] == requirement["kind"]
                and item["status"] in ACTIVE
            ]
            if not matching:
                errors.append(f"json_export:{source_id}: critical explicit work omitted")
            surfaced = [item for item in resume["items"]["items"] if item["record_id"] == rid]
            if not any(
                rid[:12] in line and item["text"] in line
                for item in surfaced
                for line in markdown.splitlines()
            ):
                errors.append(
                    f"markdown_export:{source_id}: actionable source excerpt or provenance omitted"
                )
    if not resume["trust_notice"] in markdown:
        errors.append("markdown_export: untrusted-context boundary notice omitted")
    return errors


@pytest.mark.parametrize("case", CORPUS["scenarios"], ids=lambda case: case["id"])
def test_semantic_continuity_through_native_sources(case, tmp_path, monkeypatch):
    controlled_home = tmp_path / "home"
    controlled_home.mkdir()
    monkeypatch.setenv("HOME", str(controlled_home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    with Store(tmp_path / "state") as store:
        app = App(store)
        app.setup(case["selection"]["timezone"])
        fx = Fixture(tmp_path, app)
        fx.build(case["events"])
        selection = case["selection"]
        project = fx.projects[selection["project"]]
        worktree = fx.worktrees[selection["worktree"]]
        resume_kwargs = {"observe": True, "limit": 1000}
        # A selected worktree must be a real query option, not test-side filtering.
        needs_worktree_filter = (
            len(
                {
                    event["worktree"]
                    for event in case["events"]
                    if event["project"] == selection["project"]
                }
            )
            > 1
        )
        failures = []
        if "worktree" in inspect.signature(app.resume).parameters:
            resume_kwargs["worktree"] = worktree
        elif needs_worktree_filter:
            failures.append("worktree_selection: App.resume cannot request the selected worktree")
        resume = app.resume(project, **resume_kwargs)
        failures.extend(_surface_errors(case, fx, resume))
        failures.extend(_prohibition_errors(case, fx, resume))
        failures.extend(_export_errors(case, fx, resume))
        for item in resume["items"]["items"]:
            if (
                item["project_id"] != project
                or needs_worktree_filter
                and item["worktree_id"] != worktree
            ):
                failures.append(
                    f"selected_scope: extraneous source {fx.source_id(item)} in selected worktree output"
                )
        if "selected_event_ids" in case["expected"]:
            daily_kwargs = {"project": project}
            if "worktree" in inspect.signature(app.daily).parameters:
                daily_kwargs["worktree"] = worktree
            daily = app.daily(selection["day"], **daily_kwargs)
            actual = {
                fx.source_id(item) for group in daily["projects"] for item in group["activity"]
            }
            if actual != set(case["expected"]["selected_event_ids"]):
                failures.append(
                    f"calendar_selection: got {sorted(str(x) for x in actual)}, expected {case['expected']['selected_event_ids']}"
                )
        if "ordered_event_ids" in case["expected"]:
            records = [fx.records[source_id] for source_id in case["expected"]["ordered_event_ids"]]
            actual_order = [
                record["id"] for record in sorted(records, key=lambda record: record["event_time"])
            ]
            if actual_order != [record["id"] for record in records]:
                failures.append(
                    "wrong_instant_order: persisted event chronology differs from annotated instants"
                )
        assert not failures, "\n".join(failures)

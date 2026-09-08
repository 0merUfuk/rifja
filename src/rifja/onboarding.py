"""Guided first-run flow: the wizard proposes; the operator confirms each change.

Explicit-consent boundaries: registration consent never implies refresh
consent, and nothing is read or written before an affirmative answer. Without
an interactive terminal the command prints its plan, mutates nothing and exits
2. ``setup`` remains the non-interactive primitive.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TextIO
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .app import App
from .cli import RefreshProgress, detect_timezone, error_hints
from .ingest import Ingestor
from .store import Store

# Producers with a known deletion policy get one honest line at offer time.
# Registration stores only the path; the durable copy exists after refresh.
DELETION_NOTES = {
    "claude": (
        "Claude Code deletes old transcripts automatically (30 days by default). "
        "A durable copy exists only once `rifja refresh` imports this source; "
        "refresh before that window expires."
    ),
}


class _Aborted(Exception):
    """The operator ended the wizard; already-confirmed steps stay applied."""


class _Answers:
    """Line answers from a scripted iterator (tests) or the real terminal."""

    def __init__(self, answers: Iterator[str] | None, output: TextIO):
        self._answers = answers
        self._output = output

    def line(self, prompt: str, default: str = "") -> str:
        self._output.write(prompt)
        self._output.flush()
        if self._answers is None:
            try:
                value = input()
            except EOFError:
                raise _Aborted from None
        else:
            try:
                value = next(self._answers)
            except StopIteration:
                raise _Aborted from None
        self._output.write("\n")
        return value.strip() or default

    def confirm(self, prompt: str, default: bool = True) -> bool:
        suffix = "[Y/n]" if default else "[y/N]"
        while True:
            value = self.line(f"{prompt} {suffix}", default="y" if default else "n").lower()
            if value in {"y", "yes", "n", "no"}:
                return value.startswith("y")
            self._output.write("Answer y or n.\n")


def plan_lines(store: Store, timezone_arg: str | None = None) -> list[str]:
    """The steps init would take, computed without mutating anything."""
    if timezone_arg:
        zone_note = f"{timezone_arg} (explicit)"
    else:
        zone, origin = detect_timezone()
        zone_note = (
            f"{zone} (detected)" if origin == "detected" else f"{zone} (fallback; init will ask)"
        )
    candidates = [candidate for candidate in _candidates(store) if candidate["available"]]
    lines = [
        "rifja init plan. An interactive terminal is required for the guided flow;",
        "nothing below has been applied:",
        f"  1. Write configuration (timezone: {zone_note}) after your confirmation.",
        "  2. Offer discovered session sources for registration:",
    ]
    lines += [f"       - {c['provider']} {c['path']}" for c in candidates] or [
        "       (no supported producer locations found)"
    ]
    lines += [
        "  3. Offer to register project directories you name explicitly.",
        "  4. Offer the first refresh as a separate explicit consent step (offline).",
        "",
        "Apply without prompts instead:",
        "  rifja setup [--timezone ZONE]",
        "  rifja source add PROVIDER PATH",
        "  rifja project add PATH",
        "  rifja refresh",
    ]
    return lines


def _candidates(store: Store) -> list[dict[str, Any]]:
    # Discovery is metadata-only: it reports paths, it never reads them.
    return App(store).source_discover()["candidates"]


def _ask_zone(responder: _Answers, output: TextIO, zone: str, origin: str, explicit: bool) -> str:
    if explicit:
        return zone  # Validation happens in App.setup; invalid input exits 2.
    if origin == "detected" and responder.confirm(f"Detected timezone: {zone}. Use it?", True):
        return zone
    while True:
        answer = responder.line(f"Choose an IANA timezone [{zone}]: ", default=zone)
        try:
            ZoneInfo(answer)
            return answer
        except ValueError, ZoneInfoNotFoundError:
            output.write(
                f"  Not an IANA timezone: {answer}. Examples: Europe/Istanbul, UTC, America/New_York.\n"
            )


def run_init(
    app: App,
    store: Store,
    output: TextIO,
    timezone_arg: str | None = None,
    answers: Iterator[str] | None = None,
    interactive: bool | None = None,
    quiet: bool = False,
) -> tuple[dict[str, Any], int, dict[str, Any]]:
    """Run the wizard. Returns (result, exit_code, extra) for the CLI printer."""
    responder = _Answers(answers, output)
    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        return {"applied": False, "plan": plan_lines(store, timezone_arg)}, 2, {}
    steps: dict[str, Any] = {"steps_applied": []}
    try:
        return _guided(app, store, responder, output, timezone_arg, steps, quiet)
    except _Aborted:
        # An abort before any confirmation changed nothing; report it honestly.
        return {"applied": bool(steps["steps_applied"]), "aborted": True, **steps}, 2, {}


def _guided(
    app: App,
    store: Store,
    responder: _Answers,
    output: TextIO,
    timezone_arg: str | None,
    steps: dict[str, Any],
    quiet: bool,
) -> tuple[dict[str, Any], int, dict[str, Any]]:
    home = str(store.home)
    if store.config("timezone") is not None and not responder.confirm(
        f"Existing state found at {home}. Extend it?", True
    ):
        return {"applied": False, "reason": "operator declined to extend existing state"}, 0, {}

    # 1. Timezone: an explicit flag overrides the whole chain; a detection
    # failure asks with UTC pre-filled and is never applied silently.
    if timezone_arg:
        zone, origin = timezone_arg, "explicit"
    else:
        zone, origin = detect_timezone()
    zone = _ask_zone(responder, output, zone, origin, timezone_arg is not None)

    # 2. Configuration is the first and only unconditional state change offered.
    if not responder.confirm(f"Write configuration to {home} (timezone: {zone})?", True):
        return {"applied": False, "reason": "operator declined configuration"}, 0, {}
    setup = app.setup(zone)
    steps["steps_applied"].append("configuration")
    origin_note = "explicit" if timezone_arg else origin
    output.write(f"Configuration applied; timezone {zone} ({origin_note}).\n")

    # 3. Sources: discovered locations only; registration reads nothing.
    registered = 0
    existing = {(s["provider"], s["path"]) for s in store.config("sources", [])}
    available = [c for c in _candidates(store) if c["available"]]
    offerable = [c for c in available if (c["provider"], c["path"]) not in existing]
    if available and responder.confirm("Review discovered session sources?", True):
        for candidate in offerable:
            note = DELETION_NOTES.get(candidate["provider"])
            if note:
                output.write(f"  Note: {note}\n")
            prompt = f"Register {candidate['provider']} sessions at {candidate['path']}?"
            if not responder.confirm(prompt, True):
                continue
            app.source_add(candidate["provider"], Path(candidate["path"]))
            registered += 1
            output.write(
                f"  Registered {candidate['provider']} {candidate['path']}; "
                "read-only until `rifja refresh`.\n"
            )
            steps["steps_applied"].append(f"source:{candidate['path']}")

    # 4. Projects: explicit paths only; never an implicit disk scan.
    projects: list[dict[str, Any]] = []
    if responder.confirm("Register a project directory now?", True):
        while True:
            path = responder.line("Project path (empty to finish): ", default="")
            if not path:
                break
            name = responder.line("Display name (empty = directory name): ", default="")
            try:
                view = app.register(Path(path), name or None)
            except ValueError as exc:
                label = str(exc)
                output.write("Error: " + label + "\n")
                output.writelines(f"  - {hint}\n" for hint in error_hints(label))
                continue
            project = view["project"]
            projects.append({"id": project["id"], "name": project["name"]})
            output.write(f"  Registered project {project['name']} (id {project['id']}).\n")
            steps["steps_applied"].append(f"project:{project['id']}")

    # 5. Refresh is a separate explicit consent; registration never implies it.
    refreshed: dict[str, Any] | None = None
    if store.config("sources", []):
        output.write(
            "refresh imports the configured sources now. It writes indexed records,\n"
            "refresh checkpoints and coverage into the private state directory. It is\n"
            "offline; nothing leaves this machine. Registration alone did not\n"
            "authorize this step.\n"
        )
        if responder.confirm("Run refresh now?", True):
            progress = RefreshProgress(quiet=quiet)
            refreshed = Ingestor(store).refresh(progress=progress)
            progress.finish(refreshed)
            steps["steps_applied"].append("refresh")

    # 6. Health gate.
    health = app.doctor()
    next_steps = [f"rifja resume {p['name']}" for p in projects] or setup["next"]
    result = {
        "applied": True,
        "state_directory": home,
        "timezone": zone,
        "timezone_origin": origin_note,
        "sources_registered": registered,
        "projects": projects,
        "refresh": refreshed["status"] if refreshed else None,
        "doctor": health["status"],
        "next": next_steps,
        **steps,
    }
    return result, 0, {}

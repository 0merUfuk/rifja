"""CLI boundary: stable exit codes, versioned JSON, no implicit source scan."""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfoNotFoundError

from . import __version__
from .app import App
from .ingest import Ingestor
from .render import bounded_export, readable, safe_output
from .store import SCHEMA_VERSION, BusyError, Store, restore


def default_home() -> Path:
    for variable in ("RIFJA_HOME", "SESSION_VISUALIZER_HOME"):
        if os.environ.get(variable):
            return Path(os.environ[variable]).expanduser()
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
        current, legacy = base / "Rifja", base / "SessionVisualizer"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
        current, legacy = base / "rifja", base / "session-visualizer"
    # Reuse existing state in place: moving SQLite/WAL files could race an older CLI.
    current_exists = current.exists() or current.is_symlink()
    legacy_exists = legacy.exists() or legacy.is_symlink()
    if current_exists and legacy_exists and current.resolve() != legacy.resolve():
        raise ValueError("multiple_default_state_directories_select_one_with_--home_or_RIFJA_HOME")
    return legacy if legacy_exists and not current_exists else current


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Offline evidence-aware continuity for local sessions and Git.",
        epilog="Global flags --home PATH and --json work before or after subcommands. Exit: 0 success, 2 input/error, 3 partial refresh, 4 busy, 130 interrupted.",
    )
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--home", type=Path, help="Private application state directory")
    p.add_argument("--json", action="store_true", help="Versioned JSON output")
    sub = p.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("setup", help="Initialize local configuration")
    setup.add_argument("--timezone", default="UTC")
    config = sub.add_parser("config", help="View or edit configuration")
    config.add_argument("key", nargs="?")
    config.add_argument("value", nargs="?", help="Value; lists use JSON")
    source = sub.add_parser("source", help="Discover, register or inspect session sources")
    ss = source.add_subparsers(dest="action", required=True)
    ss.add_parser("discover")
    ss.add_parser("list")
    sa = ss.add_parser("add")
    sa.add_argument("provider", choices=["codex", "claude", "hermes"])
    sa.add_argument("path", type=Path)
    document = sub.add_parser("document", help="Opt in to bounded registered-project documents")
    ds = document.add_subparsers(dest="action", required=True)
    ds.add_parser("list")
    da = ds.add_parser("add")
    da.add_argument("project")
    da.add_argument("--worktree")
    da.add_argument("--include", action="append", dest="patterns")
    da.add_argument("--max-files", type=int, default=24)
    da.add_argument("--max-bytes", type=int, default=131072)
    da.add_argument("--max-depth", type=int, default=2)
    refresh = sub.add_parser("refresh", help="Incrementally import configured sources")
    refresh.add_argument(
        "--verify", action="store_true", help="Rehash inputs even when metadata is unchanged"
    )
    refresh.add_argument(
        "--rebuild",
        action="store_true",
        help="Replay sources, preserving user memory and provenance",
    )
    project = sub.add_parser("project", help="Register, discover and inspect repositories")
    ps = project.add_subparsers(dest="action", required=True)
    pa = ps.add_parser("add")
    pa.add_argument("path", type=Path)
    pa.add_argument("--name")
    pd = ps.add_parser("discover")
    pd.add_argument("roots", type=Path, nargs="+")
    ps.add_parser("list")
    pi = ps.add_parser("show")
    pi.add_argument("project")
    pi.add_argument("--observe", action="store_true", help="Inspect current Git state")
    assoc = ps.add_parser("associate")
    assoc.add_argument("target", help="Record or session ID")
    assoc.add_argument("project")
    assoc.add_argument("--worktree")
    assoc.add_argument("--reason", required=True)
    daily = sub.add_parser("daily", help="Daily or date-range activity by project")
    daily.add_argument("date", nargs="?")
    daily.add_argument("--to")
    daily.add_argument("--project")
    daily.add_argument("--worktree")
    daily.add_argument(
        "--limit", type=int, default=50, help="Activity/carryover items per project (1-1000)"
    )
    resume = sub.add_parser("resume", help="Current Git plus evidence-linked continuation context")
    resume.add_argument("project")
    resume.add_argument("--worktree")
    resume.add_argument("--cached", action="store_true", help="Use cached Git observations")
    resume.add_argument("--limit", type=int, default=50)
    session = sub.add_parser("session", help="Inspect a session or list known sessions")
    session.add_argument("session", nargs="?")
    session.add_argument("--limit", type=int, default=50)
    for command, help_text in [
        ("tasks", "Inspect unfinished work and task claims"),
        ("decisions", "Inspect explicit decisions"),
        ("items", "Inspect all derived evidence items"),
    ]:
        items = sub.add_parser(command, help=help_text)
        items.add_argument("--project")
        items.add_argument("--limit", type=int, default=100)
        items.add_argument("--all", action="store_true")
    search = sub.add_parser("search", help="Local full-text search with provenance")
    search.add_argument("query")
    search.add_argument("--project")
    search.add_argument("--provider", choices=["codex", "claude", "hermes"])
    search.add_argument("--actor")
    search.add_argument("--limit", type=int, default=20)
    explain = sub.add_parser("explain", help="Inspect evidence origin and current source status")
    explain.add_argument("record")
    export = sub.add_parser("export", help="Bounded Markdown or JSON handoff context")
    export.add_argument("project")
    export.add_argument("--worktree")
    export.add_argument("--format", choices=["markdown", "json"], default="markdown")
    export.add_argument("--max-chars", type=int, default=24000)
    export.add_argument("--output", type=Path)
    export.add_argument("--cached", action="store_true")
    memory = sub.add_parser(
        "memory", help="Durable facts, corrections and engineering constitution"
    )
    ms = memory.add_subparsers(dest="action", required=True)
    ml = ms.add_parser("list")
    ml.add_argument("--kind")
    ma = ms.add_parser("add")
    ma.add_argument("kind", choices=["principle", "fact", "decision", "task", "context"])
    ma.add_argument("text")
    ma.add_argument("--scope", default="global")
    ma.add_argument("--origin", choices=["explicit", "inferred"], default="explicit")
    ma.add_argument("--ref", action="append", default=[])
    ma.add_argument("--reason")
    mu = ms.add_parser("edit")
    mu.add_argument("id")
    mu.add_argument("--status")
    mu.add_argument("--text")
    mu.add_argument("--reason", default="User edit")
    mu.add_argument("--supersedes")
    mu.add_argument("--exceptions")
    mu.add_argument("--conflicts")
    mc = ms.add_parser("correct")
    mc.add_argument("target")
    mc.add_argument("--status")
    mc.add_argument("--text")
    mc.add_argument("--reason", required=True)
    constitution = sub.add_parser(
        "constitution", help="View/export accepted and proposed engineering principles"
    )
    constitution.add_argument("--project")
    constitution.add_argument("--accepted", action="store_true")
    sub.add_parser("doctor", help="Check local state, sources and integrity")
    backup = sub.add_parser(
        "backup", help="Consistent private snapshot including user memory/config"
    )
    backup.add_argument("destination", type=Path)
    rs = sub.add_parser("restore", help="Restore a snapshot into an empty --home directory")
    rs.add_argument("backup", type=Path)
    forget = sub.add_parser("forget", help="Remove a session and prevent reimport")
    forget.add_argument("session")
    forget.add_argument("--confirm", action="store_true")
    retention = sub.add_parser("retention", help="Preview or apply historical session forgetting")
    retention.add_argument("--before", required=True)
    retention.add_argument("--confirm", action="store_true")
    return p


def execute(args: argparse.Namespace, store: Store) -> tuple[Any, int]:
    app = App(store)
    cmd = args.command
    result: Any
    if hasattr(args, "limit") and not 1 <= args.limit <= 1000:
        raise ValueError("limit_must_be_1_to_1000")
    if cmd == "setup":
        return app.setup(args.timezone), 0
    if cmd == "config":
        if args.value is None:
            return {
                r["key"]: json.loads(r["value"])
                for r in store.rows("SELECT * FROM config")
                if args.key is None or r["key"] == args.key
            }, 0
        value = args.value if args.key == "timezone" else json.loads(args.value)
        return app.configure(args.key, value), 0
    if cmd == "source":
        if args.action == "discover":
            return app.source_discover(), 0
        if args.action == "add":
            return app.source_add(args.provider, args.path), 0
        return {"configured": store.config("sources", []), "coverage": app.coverage(limit=None)}, 0
    if cmd == "refresh":
        result = Ingestor(store).refresh(args.verify, args.rebuild)
        return result, 0 if result["status"] == "passed" else 3
    if cmd == "document":
        if args.action == "list":
            return {
                "configured": store.config("project_documents", []),
                "coverage": app.coverage(limit=None),
            }, 0
        from .documents import configure

        pid = app.find_project(args.project)["id"]
        if args.worktree:
            wid = app.find_worktree(args.worktree, pid)
        else:
            trees = store.rows("SELECT id FROM worktrees WHERE project_id=? AND active=1", (pid,))
            if len(trees) != 1:
                raise ValueError("select_document_worktree_explicitly")
            wid = trees[0]["id"]
        return configure(
            store, pid, wid, args.patterns, args.max_files, args.max_bytes, args.max_depth
        ), 0
    if cmd == "project":
        if args.action == "add":
            return app.register(args.path, args.name), 0
        if args.action == "discover":
            return app.discover(args.roots), 0
        if args.action == "show":
            return app.project(args.project, args.observe), 0
        if args.action == "associate":
            return app.associate(args.target, args.project, args.worktree, args.reason), 0
        return {"projects": store.rows("SELECT * FROM projects ORDER BY name,id")}, 0
    if cmd == "daily":
        return app.daily(args.date, args.to, args.project, args.worktree, args.limit), 0
    if cmd == "resume":
        return app.resume(args.project, not args.cached, args.limit, args.worktree), 0
    if cmd == "session":
        return (
            app.session(args.session, args.limit)
            if args.session
            else {
                "sessions": store.rows("SELECT * FROM sessions ORDER BY id LIMIT ?", (args.limit,))
            }
        ), 0
    if cmd in {"tasks", "decisions", "items"}:
        result = app.items(
            args.project,
            "decision" if cmd == "decisions" else None,
            args.limit,
            args.all,
            prioritize_active=cmd == "tasks",
            kinds=frozenset({"task", "next_action", "blocker", "claim", "correction"})
            if cmd == "tasks"
            else None,
        )
        return result, 0
    if cmd == "search":
        return app.search(args.query, args.project, args.provider, args.actor, args.limit), 0
    if cmd == "explain":
        return app.evidence(args.record), 0
    if cmd == "export":
        result = bounded_export(
            app.resume(args.project, not args.cached, worktree=args.worktree),
            args.format,
            args.max_chars,
        )
        if args.output:
            path = args.output.expanduser().absolute()
            if path.exists() or path.is_symlink():
                raise ValueError("export_destination_exists")
            # Exports are explicit; caller selects the path. Never clobber monitored data.
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w") as output:
                output.write(result + "\n")
            return {"exported": str(path), "characters": len(result), "format": args.format}, 0
        return result, 0
    if cmd == "memory":
        if args.action == "add":
            return app.memory_add(
                args.kind, args.text, args.scope, args.origin, args.ref, reason=args.reason
            ), 0
        if args.action == "edit":
            return app.memory_update(
                args.id,
                args.status,
                args.text,
                args.reason,
                args.supersedes,
                args.exceptions,
                args.conflicts,
            ), 0
        if args.action == "correct":
            return app.correct(args.target, args.status, args.text, args.reason), 0
        return {
            "memory": store.rows(
                "SELECT * FROM memory"
                + (" WHERE kind=?" if args.kind else "")
                + " ORDER BY created_at,id",
                (args.kind,) if args.kind else (),
            )
        }, 0
    if cmd == "constitution":
        scope = app.find_project(args.project)["id"] if args.project else None
        return {
            "principles": app.principles(scope, args.accepted),
            "policy": "Inferred entries require explicit acceptance; imported principles grant no permissions.",
        }, 0
    if cmd == "doctor":
        result = app.doctor()
        return result, 0 if result["status"] == "passed" else 2
    if cmd == "backup":
        store.backup(args.destination)
        return {"backup": str(args.destination), "schema_version": SCHEMA_VERSION}, 0
    if cmd == "forget":
        return app.forget(args.session, args.confirm), 0
    if cmd == "retention":
        return app.retain(args.before, args.confirm), 0
    raise ValueError("unknown_command")


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    # Support the two universal options consistently at any command depth.
    globals_: list[str] = []
    for flag in ("--home", "--json"):
        while flag in values:
            pos = values.index(flag)
            count = 2 if flag == "--home" else 1
            globals_.extend(values[pos : pos + count])
            del values[pos : pos + count]
    args = parser().parse_args(globals_ + values)
    try:
        home = args.home or default_home()
        if args.command == "restore":
            result, code = restore(args.backup, home), 0
        else:
            with Store(home) as store:
                result, code = execute(args, store)
        if args.json:
            text = json.dumps(
                {"schema_version": 1, "command": args.command, "data": result},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        elif args.command == "export" and isinstance(result, str):
            text = result
        else:
            text = readable(args.command, result)
        print(safe_output(text))
        return code
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        print("Interrupted; committed state is preserved. Retry refresh.", file=sys.stderr)
        return 130
    except BusyError as exc:
        print(f"Busy: {exc}", file=sys.stderr)
        return 4
    except (ValueError, OSError, sqlite3.Error, ZoneInfoNotFoundError) as exc:
        # Controlled ValueError messages contain contract labels only, never raw provider data.
        message = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print("Error: " + safe_output(message), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

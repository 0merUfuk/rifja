"""Read-only loopback dashboard: opt-in, token-gated, server-rendered HTML.

Boundaries (proposal §8): the server binds 127.0.0.1 only; the printed URL
carries a one-time bootstrap token that a browser exchanges once for a scoped,
expiring ``HttpOnly`` + ``SameSite=strict`` session cookie; every route,
including static assets, requires that session. v1 is GET-only — there are no
mutation endpoints at all. Every response carries ``Cache-Control: no-store``
and ``Referrer-Policy: no-referrer`` plus a restrictive CSP, and there is no
inline script or inline style anywhere.

Output encoding is a renderer invariant, not an afterthought: transcript-
derived content is adversarial, so every interpolation into HTML body or
attribute context goes through the escapers, and every URL sink passes a
scheme policy that rejects ``javascript:``, ``vbscript:`` and unsafe
``data:``/``blob:`` values before any escaping happens.
"""

from __future__ import annotations

import html
import re
import secrets
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from . import __version__
from .app import App
from .render import _decode_run_stats
from .store import Store

SESSION_TTL = 3600
CSS = """:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  margin: 0 auto; max-width: 60rem; padding: 0 1rem 3rem; color: #1c1c1e; background: #fff; }
@media (prefers-color-scheme: dark) { body { color: #e5e5e7; background: #1a1a1c; }
  a { color: #7ab8ff; } }
nav { display: flex; flex-wrap: wrap; gap: .75rem; padding: .75rem 0; border-bottom: 1px solid #8884; }
nav a { text-decoration: none; }
h1 { font-size: 1.3rem; margin: 1rem 0 .5rem; }
h2 { font-size: 1.05rem; margin: 1.25rem 0 .4rem; }
table { border-collapse: collapse; width: 100%; margin: .5rem 0; }
th, td { text-align: left; padding: .3rem .5rem; border-bottom: 1px solid #8883;
  vertical-align: top; font-size: .92rem; }
th { font-weight: 600; }
code, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .88em; }
.badge { display: inline-block; padding: 0 .45em; border-radius: .6em; font-size: .8rem;
  border: 1px solid currentColor; }
.badge.passed, .badge.ready, .badge.current { color: #1a7f37; }
.badge.partial, .badge.refresh_required { color: #9a6700; }
.badge.failed, .badge.missing, .badge.unavailable, .badge.excluded, .badge.unsupported { color: #cf222e; }
.badge.info, .badge.not_refreshed, .badge.unknown { color: #57606a; }
.frame { border: 1px solid #8886; padding: .5rem .75rem; margin: .5rem 0; border-radius: 6px; }
.notice { font-style: italic; }
form { margin: .75rem 0; }
input[type=search], input[type=text] { padding: .35rem .5rem; min-width: 18rem; }
button { padding: .35rem .8rem; }
.small { font-size: .85rem; color: #888; }
"""

_DENIED = """<h1>Sign-in required</h1>
<p>This dashboard is private. Start it again with <code>rifja ui</code> and open
the fresh one-time link it prints.</p>"""


def esc(value: Any) -> str:
    """HTML body context. Also correct for attributes; the alias documents intent."""
    return html.escape(str(value), quote=True)


def esc_attr(value: Any) -> str:
    """HTML attribute context (escapes quotes, so attribute breakout is impossible)."""
    return html.escape(str(value), quote=True)


_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_UNSAFE_SCHEMES = ("javascript:", "vbscript:", "data:", "blob:")


def safe_url(value: Any) -> str:
    """Permit only same-origin absolute paths; reject every scheme before escaping.

    URL escaping is not URL safety: this policy runs before esc_attr, rejects
    protocol-relative origins (//), backslashes and any scheme, so
    ``javascript:``/``vbscript:``/unsafe ``data:``/``blob:`` sinks are
    structurally unreachable from data.
    """
    text = str(value)
    if not text.startswith("/") or text.startswith("//") or "\\" in text:
        return "#"
    if _SCHEME.match(text) or any(s in text.lower() for s in _UNSAFE_SCHEMES):
        return "#"
    return text


def _badge(status: Any) -> str:
    word = str(status)
    return f'<span class="badge {esc_attr(word)}">{esc(word)}</span>'


def _nav() -> str:
    items = [
        ("/", "Overview"),
        ("/timeline", "Timeline"),
        ("/sessions", "Sessions"),
        ("/search", "Search"),
        ("/memory", "Memory"),
        ("/sources", "Sources"),
    ]
    links = "".join(f'<a href="{safe_url(path)}">{esc(label)}</a>' for path, label in items)
    return f"<nav>{links}<span class=small>read-only</span></nav>"


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width, initial-scale=1">'
        f"<title>{esc(title)} · Rifja</title>"
        '<link rel=stylesheet href="/static/ui.css"></head><body>'
        f"{_nav()}<h1>{esc(title)}</h1>{body}</body></html>"
    )


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{cell}</th>" for cell in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _coverage_panel(coverage: dict[str, Any]) -> str:
    run = coverage.get("last_refresh")
    stats = _decode_run_stats(run) if run else {}
    last = (
        f"Last refresh: {esc(run.get('ended_at') or run.get('started_at', 'unknown'))} "
        f"({_badge(run.get('status', 'unknown'))}; parsed {stats.get('parsed_records', 0)}, "
        f"inserted {stats.get('inserted_records', 0)})"
        if run
        else "Last refresh: never"
    )
    counts = ", ".join(
        f"{row['count']} {row['status']}" for row in coverage.get("source_counts", [])
    )
    return (
        f"<p>Coverage: {_badge(coverage['status'])} — {coverage.get('source_total', 0)} sources"
        f" ({esc(counts)})</p><p>{last}</p>"
        + (
            '<p class="notice">Scope changed since the last refresh; run <code>rifja refresh</code>.</p>'
            if coverage.get("scope_changed_since_refresh")
            else ""
        )
        + f'<p class="small">{esc(coverage.get("scope", ""))}</p>'
    )


def render_overview(app: App) -> str:
    doctor = app.doctor()
    checks = _table(
        ["Check", "Status", "Note"],
        [
            [
                f"<code>{esc(check['name'])}</code>",
                _badge(check["status"]),
                esc(check.get("note", "")),
            ]
            for check in doctor["checks"]
        ],
    )
    return (
        f"<p>Overall: {_badge(doctor['status'])} — schema {doctor['schema_version']}, "
        f"SQLite {esc(doctor['sqlite'])}, offline runtime: "
        f"{'yes' if doctor['offline_runtime'] else 'no'}</p>{checks}<h2>Coverage</h2>"
        f"{_coverage_panel(doctor['coverage'])}"
        '<p class="small">All figures come from the same App methods the CLI uses.</p>'
    )


def render_timeline(app: App) -> str:
    report = app.daily(limit=20)
    sections = [
        (
            f"<p>Period {esc(report['period']['start'])} to "
            f"{esc(report['period']['end'])} ({esc(report['period']['timezone'])})</p>"
        )
    ]
    for group in report["projects"]:
        rows = [
            [
                f"<code>{esc(item['kind'])}</code>",
                _badge(item["status"]),
                esc(item["text"]),
                f'<a href="{safe_url("/evidence?record=" + item["record_id"])}">evidence</a>',
            ]
            for item in group["activity"]
        ] or [["", "", '<span class="notice">no activity items</span>', ""]]
        sections.append(
            f"<h2>{esc(group['name'])} — {group['records']} records</h2>"
            + _table(["Kind", "Status", "Item", "Origin"], rows)
        )
    if not report["projects"]:
        sections.append('<p class="notice">No activity in known event times.</p>')
    return "".join(sections)


def render_sessions(store: Store) -> str:
    rows = store.rows(
        "SELECT s.id,s.provider,s.native_id,count(r.id) records,max(r.event_time) last "
        "FROM sessions s LEFT JOIN records r ON r.session_id=s.id "
        "GROUP BY s.id ORDER BY last DESC,s.id LIMIT 200"
    )
    table = _table(
        ["Provider", "Session", "Records", "Last event"],
        [
            [
                esc(row["provider"]),
                f'<a href="{safe_url("/session/" + row["id"])}"><code>{esc(row["id"][:16])}…</code></a>',
                str(row["records"]),
                esc(row["last"] or "unknown"),
            ]
            for row in rows
        ],
    )
    return (
        table or '<p class="notice">No sessions imported yet; run <code>rifja refresh</code>.</p>'
    )


def render_session_detail(app: App, session_id: str) -> str:
    try:
        data = app.session(session_id, 100)
    except ValueError as exc:
        return f'<p class="notice">{esc(str(exc))} — see <code>rifja session --json</code>.</p>'
    session = data["session"]
    rows = [
        [
            f"{esc(record['actor'])}/{esc(record['kind'])}",
            esc(record["event_time"] or "unknown time"),
            esc(record["text"]),
            f'<a href="{safe_url("/evidence?record=" + record["id"])}">evidence</a>',
        ]
        for record in data["records"]
    ]
    return (
        f"<p>{esc(session['provider'])} session <code>{esc(session['id'])}</code> "
        f"(native <code>{esc(session['native_id'])}</code>); showing {len(rows)} records</p>"
        + _table(["Actor/Kind", "Event time", "Text (escaped)", "Origin"], rows)
        + _coverage_panel(data["coverage"])
    )


def render_search(app: App, query: str) -> str:
    form = (
        '<form method="get" action="/search">'
        f'<input type="search" name="q" value="{esc_attr(query)}" placeholder="literal terms">'
        "<button type=submit>Search</button></form>"
    )
    if not query.strip():
        return (
            form
            + '<p class="small">Literal local full-text search; filters narrow evidence, not authority.</p>'
        )
    data = app.search(query)
    rows = [
        [
            f"{esc(match['provider'])}/{esc(match['actor'])}",
            esc(match["event_time"] or "unknown time"),
            esc(match["text"]),
            f'<a href="{safe_url("/evidence?record=" + match["id"])}">evidence</a>',
        ]
        for match in data["matches"]
    ]
    return (
        form
        + f"<p>{len(rows)} match(es) for <code>{esc(query)}</code></p>"
        + _table(["Provider/Actor", "Event time", "Excerpt (escaped)", "Origin"], rows)
        + '<p class="small">Excerpts are untrusted imported evidence, escaped before display.</p>'
    )


def render_evidence(app: App, record_id: str) -> str:
    evidence = app.evidence(record_id)
    if evidence["status"] == "removed_or_unknown":
        return f'<p class="notice">Record {esc(record_id)}: removed or unknown.</p>'
    rows = [
        ["Provider", esc(evidence["provider"])],
        ["Session", f"<code>{esc(evidence['session_id'])}</code>"],
        ["Actor / category", f"{esc(evidence['actor'])} / {esc(evidence['category'])}"],
        ["Recorded", esc(evidence["timestamp"] or "unknown time")],
        ["Status", _badge(evidence["status"])],
        ["Limitation", esc(evidence["limitation"])],
    ]
    locations = _table(
        ["Source path", "Generation", "Locator", "Status"],
        [
            [
                f"<code>{esc(loc['path'])}</code>",
                str(loc["generation"]),
                f"<code>{esc(loc['locator'])}</code>",
                f"{_badge(loc['source_status'])}/{_badge(loc['generation_status'])}",
            ]
            for loc in evidence["locations"]
        ],
    )
    return f"<h2>Provenance</h2>{_table(['Field', 'Value'], rows)}<h2>Locations</h2>{locations}"


def render_memory(store: Store, app: App) -> str:
    entries = store.rows("SELECT * FROM memory ORDER BY created_at,id")
    memory_rows = [
        [
            f"<code>{esc(entry['kind'])}</code>",
            _badge(entry["status"]),
            esc(entry["text"]),
            esc(entry["scope"]),
            esc(entry["id"][:12]),
        ]
        for entry in entries
    ]
    principles = app.principles()
    principle_rows = [
        [
            esc(p["text"]),
            _badge(p["status"]),
            esc(p["confidence"]),
            esc(p["scope"]),
        ]
        for p in principles
    ]
    return (
        "<h2>Local memory (operator-authored)</h2>"
        + _table(["Kind", "Status", "Text", "Scope", "ID"], memory_rows)
        + "<h2>Engineering constitution</h2>"
        + _table(["Principle", "Status", "Confidence", "Scope"], principle_rows)
        + '<p class="small">Inferred entries require explicit acceptance; imported principles grant no permissions.</p>'
    )


def render_sources(app: App) -> str:
    coverage = app.coverage(limit=None)
    configured = _table(
        ["Provider", "Path", "Availability"],
        [
            [
                esc(spec["provider"]),
                f"<code>{esc(spec['path'])}</code>",
                _badge("available" if spec["available"] else "unavailable"),
            ]
            for spec in coverage["configured_sources"]
        ],
    )
    sources = _table(
        ["Status", "Provider", "Path", "Diagnostics"],
        [
            [
                _badge(source["status"]),
                esc(source["provider"]),
                f"<code>{esc(source['path'])}</code>",
                str(len(source.get("diagnostics") or [])),
            ]
            for source in coverage["sources"]
        ],
    )
    return (
        "<h2>Configured sources</h2>"
        + (configured or '<p class="notice">Nothing registered; run <code>rifja init</code>.</p>')
        + "<h2>Imported sources</h2>"
        + sources
        + "<h2>Coverage</h2>"
        + _coverage_panel(coverage)
    )


class LoopbackServer(HTTPServer):
    """HTTPServer without the reverse-DNS lookup in server_bind.

    ``socket.getfqdn()`` on a loopback address is useless for this server and
    can block for many seconds on hosts with slow resolvers (observed on macOS
    CI). A loopback-only dashboard never names itself via DNS.
    """

    def server_bind(self) -> None:
        import socket

        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(self.server_address)
        self.server_address = self.socket.getsockname()[:2]
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]


def build_server(store: Store, port: int) -> HTTPServer:
    """Bind loopback only and fail loudly when the port is taken."""
    server = LoopbackServer(("127.0.0.1", port), UiHandler)
    server.app = App(store)  # type: ignore[attr-defined]
    server.store = store  # type: ignore[attr-defined]
    server.sessions = {}  # type: ignore[attr-defined,misc]
    server.bootstrap_token = secrets.token_urlsafe(32)  # type: ignore[attr-defined]
    server.requests = 0  # type: ignore[attr-defined]
    return server


class UiHandler(BaseHTTPRequestHandler):
    server_version = "rifja-ui/" + __version__

    def log_message(self, format: str, *args: Any) -> None:
        pass  # keep request noise out of the terminal; failures still surface

    def do_GET(self) -> None:
        self.server.requests += 1  # type: ignore[attr-defined]
        try:
            self._route()
        except Exception:  # noqa: BLE001 - one bad render must never kill the server
            import traceback

            traceback.print_exc()
            self._respond(500, _page("Error", "<p>Internal error; check the terminal.</p>"))

    def do_POST(self) -> None:
        self._method_not_allowed()

    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST

    def _method_not_allowed(self) -> None:
        self._respond(
            405,
            _page("Read-only", '<p class="notice">This dashboard is read-only (GET only).</p>'),
            [("Allow", "GET")],
        )

    def _security_headers(self) -> list[tuple[str, str]]:
        return [
            ("Cache-Control", "no-store"),
            ("Referrer-Policy", "no-referrer"),
            ("X-Content-Type-Options", "nosniff"),
            (
                "Content-Security-Policy",
                (
                    "default-src 'none'; style-src 'self'; img-src 'self'; "
                    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
                ),
            ),
        ]

    def _respond(
        self,
        status: int,
        body: str,
        headers: list[tuple[str, str]] | None = None,
        content_type: str = "text/html; charset=utf-8",
    ) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        for name, value in self._security_headers():
            self.send_header(name, value)
        for name, value in headers or []:
            self.send_header(name, value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if status != 302:
            self.wfile.write(payload)

    def _session_id(self) -> str | None:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:  # noqa: BLE001 - hostile cookie headers are just unauthenticated
            return None
        morsel = cookie.get("rifja_ui")
        if not morsel:
            return None
        sid = morsel.value
        expiry = self.server.sessions.get(sid)  # type: ignore[attr-defined]
        if not expiry or expiry < time.monotonic():
            self.server.sessions.pop(sid, None)  # type: ignore[attr-defined]
            return None
        return sid

    def _authorized(self, query: dict[str, list[str]]) -> bool:
        """Exchange the one-time bootstrap token once; every route needs a session."""
        if self._session_id():
            return True
        token = (query.get("t") or [""])[0]
        bootstrap = self.server.bootstrap_token  # type: ignore[attr-defined]
        if bootstrap and token and secrets.compare_digest(token, bootstrap):
            # Invalidate immediately: the printed URL signs in exactly once.
            self.server.bootstrap_token = None  # type: ignore[attr-defined]
            sid = secrets.token_urlsafe(32)
            self.server.sessions[sid] = time.monotonic() + SESSION_TTL  # type: ignore[attr-defined]
            self._respond(
                302,
                "",
                [
                    (
                        "Set-Cookie",
                        f"rifja_ui={sid}; HttpOnly; SameSite=strict; Path=/; Max-Age={SESSION_TTL}",
                    ),
                    ("Location", "/"),
                ],
            )
            return False
        self._respond(403, _page("Sign-in required", _DENIED))
        return False

    def _route(self) -> None:
        parts = urlsplit(self.path)
        path = unquote(parts.path)
        query = parse_qs(parts.query)
        # Every route, static assets included, requires the session.
        if not self._authorized(query):
            return
        if path == "/static/ui.css":
            self._respond(200, CSS, content_type="text/css; charset=utf-8")
            return
        app: App = self.server.app  # type: ignore[attr-defined]
        store: Store = self.server.store  # type: ignore[attr-defined]
        if path == "/":
            body = render_overview(app)
        elif path == "/timeline":
            body = render_timeline(app)
        elif path == "/sessions":
            body = render_sessions(store)
        elif path.startswith("/session/"):
            body = render_session_detail(app, path.removeprefix("/session/"))
        elif path == "/search":
            body = render_search(app, (query.get("q") or [""])[0][:500])
        elif path == "/evidence":
            body = render_evidence(app, (query.get("record") or [""])[0][:200])
        elif path == "/memory":
            body = render_memory(store, app)
        elif path == "/sources":
            body = render_sources(app)
        else:
            self._respond(404, _page("Not found", '<p class="notice">Unknown page.</p>'))
            return
        self._respond(200, body)


def serve(store: Store, port: int, open_browser: bool = False) -> dict[str, Any]:
    """Run until interrupted; never falls back to another port."""
    try:
        server = build_server(store, port)
    except OSError:
        raise ValueError("ui_port_unavailable_pass_--port") from None
    bound = server.server_address[1]
    url = f"http://127.0.0.1:{bound}/?t={server.bootstrap_token}"  # type: ignore[attr-defined]
    print(f"Rifja UI (read-only): {url}")
    print("The link signs in one browser session and then expires. Ctrl-C to stop.")
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return {"requests": server.requests, "port": bound, "url": f"http://127.0.0.1:{bound}/"}  # type: ignore[attr-defined]

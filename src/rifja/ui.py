"""Management plane: the operator's observability dashboard (loopback, GET-only).

Purpose (docs/product-vision.md): the human watches and manages. The home
screen is the agent's activity feed; every other section is state, evidence
or configuration. The interface is deliberately terminal-native —
monospace-first data, hairline keylines instead of cards, one accent —
because this is a developer tool that lives next to the CLI it manages.

Security model (unchanged from the original dashboard): loopback-only bind,
one-time bootstrap token exchanged for a scoped expiring HttpOnly +
SameSite=strict session cookie, every route session-gated, GET-only,
Cache-Control no-store on data pages, restrictive CSP, context-specific
escapers and a URL scheme policy that rejects javascript:/vbscript:/unsafe
data:/blob: before escaping. Output encoding is a renderer invariant.

Performance: pages are bounded (keyset pagination, aggregate-first counts,
no unbounded queries), HTML responses are gzip-compressed when accepted, and
the stylesheet/JS are cacheable static assets.
"""

from __future__ import annotations

import gzip
import html
import json
import re
import secrets
import sys
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from . import __version__
from .app import App
from .store import Store

SESSION_TTL = 3600
PAGE = 50

# ---------------------------------------------------------------------------
# Design system: "instrument" — dark-first, mono-first, hairlines not cards.
# Tokens only; components below consume them. Light mode inverts the ground.
# ---------------------------------------------------------------------------

CSS = """
:root{
  --bg:#0e0f11; --panel:#121417; --raise:#17191d;
  --line:#22252b; --line-strong:#31353d;
  --ink:#d7dae0; --ink-2:#8f96a1; --ink-3:#5f6772;
  --accent:#e2a03f; --ok:#54b986; --warn:#d9a441; --err:#e05757; --info:#7d8aa0;
  --mono:"SF Mono",ui-monospace,"JetBrains Mono",Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Inter","Segoe UI",sans-serif;
}
@media (prefers-color-scheme: light){
  :root{ --bg:#fafaf8; --panel:#f2f2ef; --raise:#e9e9e5;
    --line:#dcdcd6; --line-strong:#c6c6bf;
    --ink:#1b1d20; --ink-2:#5b6069; --ink-3:#8a8f98;
    --accent:#9a6414; --ok:#2c8a5c; --warn:#946f1d; --err:#bb3a3a; --info:#5d6b80; }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:13px/1.5 var(--sans)}
a{color:var(--ink);text-decoration:none;border-bottom:1px solid var(--line-strong)}
a:hover{color:var(--accent);border-bottom-color:var(--accent)}
code,.mono{font-family:var(--mono);font-size:12.5px}
.mono{font-variant-numeric:tabular-nums}

/* command bar */
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line)}
.bar{max-width:1180px;margin:0 auto;padding:0 20px;height:46px;display:flex;align-items:center;gap:14px}
.wordmark{font-family:var(--mono);font-size:12px;letter-spacing:.22em;color:var(--ink);border:0}
.wordmark b{color:var(--accent);font-weight:600}
.pill{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;
  padding:2px 7px;border:1px solid var(--line-strong);border-radius:2px;color:var(--ink-2);white-space:nowrap}
.pill.ok{color:var(--ok);border-color:var(--ok)}
.pill.warn{color:var(--warn);border-color:var(--warn)}
.pill.err{color:var(--err);border-color:var(--err)}
.spacer{flex:1}
.search{display:flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:2px;
  padding:3px 8px;background:var(--panel)}
.search input{background:transparent;border:0;outline:0;color:var(--ink);
  font-family:var(--mono);font-size:12.5px;width:200px}
.search kbd,.kbd{font-family:var(--mono);font-size:10px;color:var(--ink-3);
  border:1px solid var(--line);border-radius:2px;padding:0 4px;line-height:15px}

/* index tabs */
nav{max-width:1180px;margin:0 auto;padding:0 20px;display:flex;gap:2px;overflow-x:auto}
nav a{font-family:var(--mono);font-size:11px;letter-spacing:.05em;text-transform:uppercase;
  color:var(--ink-3);border:0;border-bottom:2px solid transparent;padding:9px 10px 7px;white-space:nowrap}
nav a i{font-style:normal;color:var(--ink-3);margin-right:6px}
nav a:hover{color:var(--ink)}
nav a[aria-current]{color:var(--ink);border-bottom-color:var(--accent)}
nav a[aria-current] i{color:var(--accent)}

/* content grid */
main{max-width:1180px;margin:0 auto;padding:20px 20px 72px}
section{border-top:1px solid var(--line);padding:14px 0 22px;margin-top:8px}
section:first-of-type{border-top:0}
.slabel{font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--ink-3);margin:0 0 12px}
h1{font-size:19px;font-weight:600;letter-spacing:-.01em;margin:14px 0 2px}
.lede{color:var(--ink-2);margin:0 0 6px;max-width:72ch}

/* stat strip: numbers on a keyline, never cards */
.stats{display:flex;flex-wrap:wrap;gap:0 36px;padding:6px 0 2px}
.stat{min-width:96px}
.stat b{display:block;font-family:var(--mono);font-variant-numeric:tabular-nums;
  font-size:22px;font-weight:500;letter-spacing:-.02em}
.stat span{font-family:var(--mono);font-size:10.5px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--ink-3)}
.stat b em{font-style:normal;color:var(--ink-3);font-size:12px}

/* tables */
table{border-collapse:collapse;width:100%;margin:2px 0 4px}
th{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--ink-3);text-align:left;font-weight:400;padding:6px 10px 6px 0;
  border-bottom:1px solid var(--line-strong);position:sticky;top:93px;background:var(--bg)}
td{padding:6px 10px 6px 0;border-bottom:1px solid var(--line);vertical-align:top}
tr:hover td{background:var(--panel)}
td.num,th.num{text-align:right;padding-right:18px;font-variant-numeric:tabular-nums}
td.dim{color:var(--ink-3)}
td.nowrap{white-space:nowrap}
td.wide{max-width:520px;overflow-wrap:anywhere}

/* status dot + word */
.st{font-family:var(--mono);font-size:11.5px;white-space:nowrap;color:var(--ink-2)}
.st i{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:6px;vertical-align:1px}
.st.ok i{background:var(--ok)} .st.ok{color:var(--ok)}
.st.warn i{background:var(--warn)} .st.warn{color:var(--warn)}
.st.err i{background:var(--err)} .st.err{color:var(--err)}
.st.info i{background:var(--info)}
.st.ok.solid i,.st.warn.solid i,.st.err.solid i{outline:1px solid currentColor;outline-offset:2px}

/* activity feed: terminal lines */
.feed{font-family:var(--mono);font-size:12.5px}
.feed .row{display:flex;gap:14px;padding:5px 0;border-bottom:1px solid var(--line)}
.feed .row:hover{background:var(--panel)}
.feed .t{color:var(--ink-3);white-space:nowrap;font-variant-numeric:tabular-nums}
.feed .tool{color:var(--ink);white-space:nowrap}
.feed .tool i{font-style:normal;color:var(--accent)}
.feed .sum{color:var(--ink-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
.feed .st{margin-left:auto}
.feed .ms{color:var(--ink-3);width:64px;text-align:right;font-variant-numeric:tabular-nums}
.feed .row.err .tool,.feed .row.err .st{color:var(--err)}
.feed .row.err{border-left:2px solid var(--err);padding-left:8px}
.empty{color:var(--ink-3);font-family:var(--mono);font-size:12px;padding:10px 0}

/* mini day bars (overview): 14 cells, mono numbers, no chart junk */
.days{display:flex;gap:3px;align-items:flex-end;height:56px;margin:8px 0 2px}
.days .d{flex:1;display:flex;flex-direction:column;justify-content:flex-end;gap:4px;min-width:0}
.days .bar{background:var(--line-strong);transition:height .15s}
.days .b0{height:2px}.days .b1{height:4px}.days .b2{height:6px}.days .b3{height:8px}
.days .b4{height:10px}.days .b5{height:12px}.days .b6{height:14px}.days .b7{height:16px}
.days .b8{height:18px}.days .b9{height:20px}.days .b10{height:22px}.days .b11{height:24px}
.days .b12{height:26px}.days .b13{height:28px}.days .b14{height:30px}.days .b15{height:32px}
.days .b16{height:34px}.days .b17{height:36px}.days .b18{height:38px}.days .b19{height:40px}
.days .bar.hot{background:var(--accent)}
.days .n{font-family:var(--mono);font-size:10px;color:var(--ink-3);text-align:center;
  font-variant-numeric:tabular-nums;overflow:hidden}

/* pagination + forms */
.pg{display:flex;gap:12px;align-items:center;font-family:var(--mono);font-size:11.5px;
  color:var(--ink-3);padding-top:10px}
.pg a{border:1px solid var(--line-strong);border-radius:2px;padding:2px 8px;color:var(--ink-2)}
form.q{display:flex;gap:8px;padding:4px 0 10px}
form.q input{background:var(--panel);border:1px solid var(--line);border-radius:2px;
  color:var(--ink);font-family:var(--mono);font-size:12.5px;padding:6px 10px;min-width:340px;outline:0}
form.q input:focus{border-color:var(--accent)}
form.q button{background:var(--raise);border:1px solid var(--line-strong);border-radius:2px;
  color:var(--ink);font:12px var(--mono);padding:6px 14px;cursor:pointer}
form.q button:hover{border-color:var(--accent);color:var(--accent)}
.note{color:var(--ink-3);font-size:12px;margin:6px 0}
.kv{display:grid;grid-template-columns:180px 1fr;gap:4px 18px;font-size:12.5px}
.kv dt{color:var(--ink-3);font-family:var(--mono);font-size:11px;letter-spacing:.06em;
  text-transform:uppercase;padding-top:2px}
.kv dd{margin:0;font-family:var(--mono);overflow-wrap:anywhere}
footer{max-width:1180px;margin:0 auto;padding:18px 20px 30px;border-top:1px solid var(--line);
  color:var(--ink-3);font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;
  display:flex;gap:16px}
@media (max-width:760px){ .bar .search{display:none} th{position:static} td.wide{max-width:none} }
"""

# Minimal vanilla layer: keyboard sections, search focus, live activity poll.
JS = """
(function(){
  var box=document.querySelector('.search input');
  var poll=null;
  function go(i){var t=document.querySelectorAll('nav a')[i-1];if(t)location=t.href;}
  document.addEventListener('keydown',function(e){
    if(e.target.tagName==='INPUT')return;
    if(e.key==='/'){e.preventDefault();if(box)box.focus();return;}
    if(e.key>='1'&&e.key<='7'&&!e.metaKey&&!e.ctrlKey)go(+e.key);
  });
  var feed=document.getElementById('feed');
  if(feed&&feed.dataset.poll){
    var tick=function(){
      fetch(location.pathname+'?fragment=1',{headers:{'Accept':'application/json'}})
        .then(function(r){return r.ok?r.json():null})
        .then(function(d){
          if(!d||!d.rows)return;
          var at=feed.dataset.since||'0';
          if(String(d.since)===at)return;
          feed.dataset.since=d.since;
          var h='';
          h=d.rows.join('');
          feed.querySelector('.rows').innerHTML=h||d.empty;
        }).catch(function(){});
    };
    setInterval(tick,3000);
  }
})();
"""


def esc(value: Any) -> str:
    """HTML body context."""
    return html.escape(str(value), quote=True)


def esc_attr(value: Any) -> str:
    """HTML attribute context (quote-escaping prevents breakout)."""
    return html.escape(str(value), quote=True)


_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_UNSAFE_SCHEMES = ("javascript:", "vbscript:", "data:", "blob:")


def safe_url(value: Any) -> str:
    """Same-origin absolute paths only; every scheme rejected before escaping."""
    text = str(value)
    if not text.startswith("/") or text.startswith("//") or "\\" in text:
        return "#"
    if _SCHEME.match(text) or any(s in text.lower() for s in _UNSAFE_SCHEMES):
        return "#"
    return text


_STATUS_CLASS = {
    "ok": "ok",
    "passed": "ok",
    "ready": "ok",
    "current": "ok",
    "accepted": "ok",
    "available": "ok",
    "partial": "warn",
    "warn": "warn",
    "refresh_required": "warn",
    "proposed": "warn",
    "new": "warn",
    "failed": "err",
    "err": "err",
    "missing": "err",
    "unavailable": "err",
    "excluded": "err",
    "unsupported": "err",
    "error": "err",
    "info": "info",
    "not_refreshed": "info",
    "unknown": "info",
}


def st(status: Any, solid: bool = False) -> str:
    word = str(status)
    cls = _STATUS_CLASS.get(word, "info")
    return f'<span class="st {cls}{" solid" if solid else ""}"><i></i>{esc(word)}</span>'


SECTIONS = (
    ("activity", "Activity"),
    ("overview", "Overview"),
    ("sessions", "Sessions"),
    ("search", "Search"),
    ("memory", "Memory"),
    ("sources", "Sources"),
    ("settings", "Settings"),
)


def _shell(current: str, title: str, body: str, coverage: str = "") -> str:
    tabs = "".join(
        f'<a href="{safe_url("/" + key)}"{' aria-current="page"' if key == current else ""}>'
        f"<i>0{i}</i>{esc(label)}</a>"
        for i, (key, label) in enumerate(SECTIONS, 1)
    )
    pill = ""
    if coverage:
        cls = _STATUS_CLASS.get(coverage, "info")
        pill = f'<span class="pill {cls}">{esc(coverage)}</span>'
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width, initial-scale=1">'
        f"<title>{esc(title)} · Rifja</title>"
        '<link rel=stylesheet href="/static/ui.css">'
        '<script src="/static/ui.js" defer></script></head><body>'
        "<header><div class=bar>"
        '<a class=wordmark href="/"><b>RI</b>FJA</a>'
        f"{pill}<span class=spacer></span>"
        '<form class="search" action="/search" method="get">'
        '<input type=search name=q placeholder="search evidence…" aria-label="Search evidence">'
        "<kbd>/</kbd></form>"
        "<span class=kbd>1–7</span>"
        f"</div><nav>{tabs}</nav></header>"
        f"<main>{body}</main>"
        f"<footer><span>rifja {esc(__version__)} · management plane</span>"
        "<span>loopback · read-only · session-gated</span></footer></body></html>"
    )


def _section(label: str, inner: str) -> str:
    return f"<section><p class=slabel>{esc(label)}</p>{inner}</section>"


def _stats(pairs: list[tuple[str, str, str]]) -> str:
    cells = "".join(
        f"<div class=stat><b>{v}<em>{unit}</em></b><span>{esc(k)}</span></div>"
        for k, v, unit in pairs
    )
    return f"<div class=stats>{cells}</div>"


def _pager(path: str, newer: int | None, older: int | None, shown: int, more: bool) -> str:
    """Keyset links: `after` selects newer rows (id >), `before` selects older."""
    parts = [f"<span>{shown} shown</span>"]
    if newer:
        parts.append(f'<a href="{safe_url(f"{path}?after={newer}")}">\u2039 newer</a>')
    if more and older:
        parts.append(f'<a href="{safe_url(f"{path}?before={older}")}">older \u203a</a>')
    return f"<div class=pg>{''.join(parts)}</div>"


def _etag(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()[:16]


def _fmt_ms(ms: int) -> str:
    return f"{ms}ms" if ms < 10000 else f"{ms / 1000:.1f}s"


# ---------------------------------------------------------------------------
# Sections. All data is escaped at interpolation; URLs pass safe_url.
# ---------------------------------------------------------------------------


def render_activity(
    store: Store, before: int | None = None, after: int | None = None
) -> tuple[str, Any, bool]:
    where, args = "", []
    if before:
        where, args = "WHERE id<?", [before]
    elif after:
        where, args = "WHERE id>?", [after]
    rows = store.rows(
        f"SELECT * FROM activity {where} ORDER BY id {'ASC' if after else 'DESC'} LIMIT ?",
        (*args, PAGE + 1),
    )
    more = len(rows) > PAGE
    rows = rows[:PAGE]
    at_head = not (before or after)
    if after:
        rows.reverse()
    window = store.rows(
        "SELECT count(*) n, sum(status!='ok') fails, avg(duration_ms) avg_ms"
        " FROM activity WHERE at>?",
        (time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - 86400)),),
    )[0]
    head = _stats(
        [
            ("calls · 24h", str(window["n"] or 0), ""),
            ("failures · 24h", str(window["fails"] or 0), ""),
            ("avg duration", _fmt_ms(int(window["avg_ms"] or 0)), ""),
        ]
    )
    if rows:
        since = rows[-1]["id"] if not after else max(r["id"] for r in rows)
        line = "".join(
            f'<div class="row{" err" if r["status"] != "ok" else ""}">'
            f'<span class="t">{esc(r["at"][11:19])}</span>'
            f'<span class="tool"><i>{esc(r["surface"])}</i> {esc(r["tool"])}</span>'
            f'<span class="sum">{esc(r["summary"] or "")}</span>'
            f'<span class="st">{esc(r["status"])}</span>'
            f'<span class="ms">{_fmt_ms(r["duration_ms"])}</span></div>'
            for r in rows
        )
        feed = (
            f'<div class=feed id=feed data-poll=1 data-since="{since}">'
            f"<div class=rows>{line}</div></div>"
        )
    else:
        feed = (
            "<div class=feed id=feed><div class=rows></div></div>"
            "<p class=empty>no agent activity yet — wire your agent to `rifja mcp` and its calls appear here</p>"
        )
        since = 0
    body = (
        "<h1>Activity</h1>"
        "<p class=lede>Every tool call your agent made through Rifja — newest first. "
        "Failures are marked and kept.</p>"
        + _section("last 24 hours", head)
        + _section(
            "feed",
            feed
            + _pager(
                "/activity",
                rows[0]["id"] if rows and not at_head else None,
                rows[-1]["id"] if rows else None,
                len(rows),
                more,
            ),
        )
    )
    return body, since, more


def _activity_rows_html(store: Store) -> list[str]:
    rows = store.rows("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (PAGE,))
    return [
        f'<div class="row{" err" if r["status"] != "ok" else ""}">'
        f'<span class="t">{esc(r["at"][11:19])}</span>'
        f'<span class="tool"><i>{esc(r["surface"])}</i> {esc(r["tool"])}</span>'
        f'<span class="sum">{esc(r["summary"] or "")}</span>'
        f'<span class="st">{esc(r["status"])}</span>'
        f'<span class="ms">{_fmt_ms(r["duration_ms"])}</span></div>'
        for r in rows
    ]


def render_overview(app: App, store: Store) -> str:
    counts = store.db.execute(
        "SELECT (SELECT count(*) FROM sessions),(SELECT count(*) FROM records),"
        "(SELECT count(*) FROM projects),(SELECT count(*) FROM memory),"
        "(SELECT count(*) FROM memory WHERE status='proposed')"
    ).fetchone()
    coverage = app.coverage(limit=1)
    run = coverage.get("last_refresh") or {}
    stats = _stats(
        [
            ("sessions", f"{counts[0]:,}", ""),
            ("records", f"{counts[1]:,}", ""),
            ("projects", str(counts[2]), ""),
            ("memory", str(counts[3]), f" +{counts[4]} proposed"),
        ]
    )
    # 14-day activity shape: one indexed count per local day.
    zone = store.config("timezone", "UTC")
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from .timeutil import date_bounds

    zi = ZoneInfo(zone)
    peak = 1
    days_data: list[tuple[str, int]] = []
    for offset in range(13, -1, -1):
        day = (datetime.now(zi) - timedelta(days=offset)).date().isoformat()
        first, last = date_bounds(day, None, zone)
        n = store.db.execute(
            "SELECT count(*) FROM records WHERE event_time>=? AND event_time<?", (first, last)
        ).fetchone()[0]
        days_data.append((day[5:], n))
        peak = max(peak, n)
    cells_html = "".join(
        f"<div class=d><span class=n>{n if n else '·'}</span>"
        f'<div class="bar b{max(0, min(19, round(19 * n / peak)))}{" hot" if n == peak and n else ""}"></div></div>'
        for _, n in days_data
    )
    days = f"<div class=days>{cells_html}</div><p class=note>records per day · {esc(zone)}</p>"
    checks = "".join(
        f"<tr><td class=nowrap><code>{esc(c['name'])}</code></td>"
        f'<td>{st(c["status"])}</td><td class="dim wide">{esc(c.get("note") or "")}</td></tr>'
        for c in app.doctor()["checks"]
    )
    last = f"{run.get('ended_at') or 'never'} · {run.get('status', '-')}" if run else "never"
    body = (
        "<h1>Overview</h1>"
        "<p class=lede>Tool state at a glance. Everything here comes from the same "
        "queries the CLI and your agent use.</p>"
        + _section(
            "state",
            stats
            + f"<p class=note>coverage {esc(coverage['status'])} · last refresh {esc(last)}</p>",
        )
        + _section("last 14 days", days)
        + _section(
            "doctor",
            "<table><tr><th>check</th><th>status</th><th class=wide>note</th></tr>"
            + checks
            + "</table>",
        )
    )
    return body


def render_sessions(store: Store, before: int | None = None, after: int | None = None) -> str:
    where, args, order = "", [], "DESC"
    if before:
        where, args = "WHERE s.id<?", [before]
    elif after:
        where, args, order = "WHERE s.id>?", [after], "ASC"
    rows = store.rows(
        "SELECT s.id,s.provider,s.native_id,count(r.id) records,max(r.event_time) last"
        " FROM sessions s LEFT JOIN records r ON r.session_id=s.id"
        f" {where} GROUP BY s.id ORDER BY s.id {order} LIMIT ?",
        (*args, PAGE + 1),
    )
    more = len(rows) > PAGE
    rows = rows[:PAGE]
    if after:
        rows.reverse()
    if rows:
        body_rows = "".join(
            f"<tr><td><span class=st info><i></i>{esc(r['provider'])}</span></td>"
            f'<td class=nowrap><a href="{safe_url("/session/" + r["id"])}">'
            f"<code>{esc(r['id'][:16])}…</code></a></td>"
            f"<td class=num>{r['records']:,}</td>"
            f'<td class="num dim mono">{esc((r["last"] or "unknown")[:19])}</td></tr>'
            for r in rows
        )
        table = (
            "<table><tr><th>provider</th><th>session</th><th class=num>records</th>"
            "<th class=num>last event</th></tr>"
            + body_rows
            + "</table>"
            + _pager(
                "/sessions",
                rows[0]["id"] if rows and (before or not after) else None,
                rows[-1]["id"] if rows else None,
                len(rows),
                more,
            )
        )
    else:
        table = "<p class=empty>no sessions imported — your agent can run refresh, or `rifja refresh`</p>"
    return (
        "<h1>Sessions</h1>"
        "<p class=lede>Imported session evidence. Every row is traceable to its source "
        "locations.</p>" + _section("sessions", table)
    )


def render_session_detail(app: App, session_id: str) -> str:
    try:
        data = app.session(session_id, 100)
    except ValueError as exc:
        return f"<h1>Session</h1><p class=empty>{esc(str(exc))}</p>"
    s = data["session"]
    rows = "".join(
        f'<tr><td class="dim nowrap mono">{esc((r["event_time"] or "?")[:19])}</td>'
        f"<td class=nowrap><span class=st info><i></i>{esc(r['actor'])}</span></td>"
        f"<td><code>{esc(r['kind'])}</code></td>"
        f"<td class=wide>{esc(r['text'])}</td>"
        f'<td class=nowrap><a href="{safe_url("/evidence?record=" + r["id"])}">evidence</a></td></tr>'
        for r in data["records"]
    )
    return (
        f"<h1>Session <code>{esc(s['id'][:16])}…</code></h1>"
        f"<p class=lede>{esc(s['provider'])} · native {esc(s['native_id'])} · "
        f"{len(data['records'])} of latest records</p>"
        + _section(
            "records",
            "<table><tr><th>time</th><th>actor</th><th>kind</th><th class=wide>text (escaped)</th>"
            "<th></th></tr>" + rows + "</table>",
        )
    )


def render_search(app: App, query: str) -> str:
    form = (
        '<form class=q action="/search" method="get">'
        f'<input type=search name=q value="{esc_attr(query)}" placeholder="literal terms…" '
        'aria-label="Search evidence">'
        "<button type=submit>search</button></form>"
    )
    if not query.strip():
        return (
            "<h1>Search</h1>"
            "<p class=lede>Literal full-text search over imported evidence — the same "
            "index your agent queries.</p>" + _section("query", form)
        )
    data = app.search(query)
    rows = "".join(
        f"<tr><td class=nowrap><span class=st info><i></i>{esc(m['provider'])} / {esc(m['actor'])}</span></td>"
        f'<td class="dim nowrap mono">{esc((m["event_time"] or "?")[:19])}</td>'
        f"<td class=wide>{esc(m['text'])}</td>"
        f'<td class=nowrap><a href="{safe_url("/evidence?record=" + m["id"])}">evidence</a></td></tr>'
        for m in data["matches"]
    )
    table = (
        f"<p class=note>{len(data['matches'])} match(es)</p>"
        "<table><tr><th>source</th><th>time</th><th class=wide>excerpt</th><th></th></tr>"
        + rows
        + "</table>"
        if rows
        else "<p class=empty>no matches</p>"
    )
    return (
        "<h1>Search</h1>"
        "<p class=lede>Excerpts are untrusted imported evidence, escaped before display.</p>"
        + _section("query", form + table)
    )


def render_evidence(app: App, record_id: str) -> str:
    ev = app.evidence(record_id)
    if ev["status"] == "removed_or_unknown":
        return (
            f"<h1>Evidence</h1><p class=empty>record {esc(record_id[:16])}… removed or unknown</p>"
        )
    locs = "".join(
        f'<tr><td class="wide mono">{esc(l["path"])}</td>'
        f"<td class=num>{l['generation']}</td>"
        f'<td class="mono dim">{esc(l["locator"])}</td>'
        f"<td>{st(l['source_status'])} / {st(l['generation_status'])}</td></tr>"
        for l in ev["locations"]
    )
    kv = "".join(
        f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>"
        for k, v in (
            ("provider", ev["provider"]),
            ("session", ev["session_id"]),
            ("actor · category", f"{ev['actor']} · {ev['category']}"),
            ("recorded", ev["timestamp"] or "unknown"),
            ("status", ""),
            ("limitation", ev["limitation"]),
        )
    )
    return (
        f"<h1>Evidence <code>{esc(ev['record_id'][:16])}…</code></h1>"
        + _section(
            "provenance", f"<dl class=kv>{kv}<dt>status</dt><dd>{st(ev['status'])}</dd></dl>"
        )
        + _section(
            "locations",
            "<table><tr><th class=wide>source path</th><th class=num>gen</th>"
            "<th>locator</th><th>status</th></tr>" + locs + "</table>",
        )
    )


def render_memory(store: Store) -> str:
    proposed = store.rows("SELECT * FROM memory WHERE status='proposed' ORDER BY created_at DESC")
    rest = store.rows(
        "SELECT * FROM memory WHERE status!='proposed' ORDER BY status,created_at DESC LIMIT 200"
    )
    prop_rows = "".join(
        f"<tr><td>{st('proposed')}</td><td><code>{esc(m['kind'])}</code></td>"
        f'<td class=wide>{esc(m["text"])}</td><td class="dim nowrap mono">{esc(m["id"][:12])}</td></tr>'
        for m in proposed
    )
    rest_rows = "".join(
        f"<tr><td>{st(m['status'])}</td><td><code>{esc(m['kind'])}</code></td>"
        f'<td class=wide>{esc(m["text"])}</td><td class="dim nowrap mono">{esc(m["id"][:12])}</td></tr>'
        for m in rest
    )

    def table(rows_: str, empty_text: str) -> str:
        if not rows_:
            return f"<p class=empty>{empty_text}</p>"
        return (
            "<table><tr><th>status</th><th>kind</th><th class=wide>text</th><th>id</th></tr>"
            + rows_
            + "</table>"
        )

    return (
        "<h1>Memory</h1>"
        "<p class=lede>Agents may only <em>propose</em>; acceptance is yours "
        "(`rifja memory edit ID --status accepted`).</p>"
        + _section(
            f"awaiting your acceptance · {len(proposed)}", table(prop_rows, "nothing proposed")
        )
        + _section("accepted & historical", table(rest_rows, "no entries"))
    )


def render_sources(app: App, store: Store, page: int = 0) -> str:
    coverage = app.coverage(limit=None)
    total = coverage["source_total"]
    configured = coverage["configured_sources"]
    page = max(0, min(page, (max(total - 1, 0)) // 100))
    rows = store.rows(
        "SELECT provider,path,status,last_refresh,diagnostics FROM sources"
        " ORDER BY (status='ready') DESC,provider,path LIMIT ? OFFSET ?",
        (100, page * 100),
    )
    body_rows = "".join(
        f'<tr><td>{st(r["status"])}</td><td class="dim nowrap mono">{esc(r["provider"])}</td>'
        f'<td class="wide mono">{esc(r["path"])}</td>'
        f'<td class="num dim">{len(__import__("json").loads(r["diagnostics"] or "[]"))}</td>'
        f'<td class="dim nowrap mono">{esc((r["last_refresh"] or "—")[:19])}</td></tr>'
        for r in rows
    )
    cfg = "".join(
        f'<tr><td class="dim nowrap mono">{esc(c["provider"])}</td>'
        f'<td class="wide mono">{esc(c["path"])}</td>'
        f"<td>{st('available' if c['available'] else 'unavailable')}</td></tr>"
        for c in configured
    )
    pages = f"page {page + 1} / {max(1, (total + 99) // 100)}"
    nav_ = (
        f"<div class=pg><span>{total} sources · {pages}</span>"
        + (f'<a href="{safe_url(f"/sources?p={page - 1}")}">‹ prev</a>' if page else "")
        + (
            f'<a href="{safe_url(f"/sources?p={page + 1}")}">next ›</a>'
            if (page + 1) * 100 < total
            else ""
        )
        + "</div>"
    )
    return (
        "<h1>Sources</h1>"
        "<p class=lede>Explicitly registered inputs and their import health.</p>"
        + _section(
            "configured",
            "<table><tr><th>provider</th><th class=wide>path</th><th>availability</th></tr>"
            + cfg
            + "</table>"
            if cfg
            else "<p class=empty>nothing registered</p>",
        )
        + _section(
            f"imported · {total}",
            "<table><tr><th>status</th><th>provider</th><th class=wide>path</th>"
            "<th class=num>diagnostics</th><th>last refresh</th></tr>"
            + body_rows
            + "</table>"
            + nav_,
        )
    )


def render_settings(store: Store) -> str:
    from .adapters import ADAPTER_VERSIONS

    rows = "".join(
        f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>"
        for k, v in (
            ("timezone", store.config("timezone")),
            ("state schema", store.db.execute("PRAGMA user_version").fetchone()[0]),
            ("configured sources", len(store.config("sources", []))),
            ("exclusions", str(store.config("exclusions", []))),
            ("project roots", str(store.config("roots", []))),
        )
    )
    adapters = "".join(
        f'<tr><td><code>{esc(name)}</code></td><td class="dim wide">{esc(note)}</td></tr>'
        for name, note in sorted(ADAPTER_VERSIONS.items())
    )
    return (
        "<h1>Settings</h1>"
        "<p class=lede>Configuration is owned by you and your agent (CLI or MCP); "
        "this view is read-only by design.</p>"
        + _section("configuration", f"<dl class=kv>{rows}</dl>")
        + _section(
            "producer formats",
            "<table><tr><th>adapter</th><th class=wide>expectation</th></tr>"
            + adapters
            + "</table>",
        )
        + _section(
            "agent access",
            "<dl class=kv><dt>mcp server</dt><dd>rifja mcp — 14 tools, activity-logged; "
            "agents propose memory, never accept; destructive ops not exposed</dd>"
            "<dt>dashboard</dt><dd>read-only · GET-only · loopback</dd></dl>",
        )
    )


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


class LoopbackServer(HTTPServer):
    """Bind-only server: no reverse-DNS lookup in server_bind (slow-resolver hang)."""

    def server_bind(self) -> None:
        import socket

        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(self.server_address)
        self.server_address = self.socket.getsockname()[:2]
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]


def build_server(store: Store, port: int) -> HTTPServer:
    server = LoopbackServer(("127.0.0.1", port), UiHandler)
    server.app = App(store)  # type: ignore[attr-defined]
    server.store = store  # type: ignore[attr-defined]
    server.sessions = {}  # type: ignore[attr-defined,misc]
    server.bootstrap_token = secrets.token_urlsafe(32)  # type: ignore[attr-defined]
    server.requests = 0  # type: ignore[attr-defined]
    return server


_DENIED = """<h1>Sign-in required</h1>
<p class=lede>This management plane is private. Start it again with <code>rifja ui</code>
and open the fresh one-time link it prints.</p>"""


class UiHandler(BaseHTTPRequestHandler):
    server_version = "rifja-ui/" + __version__

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_POST(self) -> None:
        self._method_not_allowed()

    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST

    def do_GET(self) -> None:
        self.server.requests += 1  # type: ignore[attr-defined]
        try:
            self._route()
        except Exception:  # noqa: BLE001 - one bad render must never kill the server
            import traceback

            traceback.print_exc()
            self._page(
                500, "Error", "<h1>Error</h1><p class=empty>internal error — see the terminal</p>"
            )

    def _method_not_allowed(self) -> None:
        self._page(
            405,
            "Read-only",
            "<h1>Read-only</h1><p class=empty>the management plane is GET-only; "
            "changes go through your agent (MCP) or the CLI</p>",
            extra=[("Allow", "GET")],
        )

    def _csp_header(self) -> tuple[str, str]:
        return (
            "Content-Security-Policy",
            (
                "default-src 'none'; style-src 'self'; script-src 'self'; "
                "connect-src 'self'; img-src 'self'; form-action 'self'; "
                "base-uri 'none'; frame-ancestors 'none'"
            ),
        )

    def _respond(
        self,
        status: int,
        payload: bytes,
        content_type: str,
        extra: list[tuple[str, str]] | None = None,
        cacheable: bool = False,
    ) -> None:
        accept = self.headers.get("Accept-Encoding", "")
        if "gzip" in accept and len(payload) > 512:
            body = gzip.compress(payload, 6)
            encoding = [("Content-Encoding", "gzip")]
        else:
            body, encoding = payload, []
        self.send_response(status)
        # Data pages are never stored; static assets cache privately with an
        # ETag. Everything else (privacy headers, CSP) applies to both.
        if cacheable:
            headers = [
                ("Cache-Control", "private, max-age=300"),
                ("ETag", f'"{_etag(payload)}"'),
                ("Referrer-Policy", "no-referrer"),
                ("X-Content-Type-Options", "nosniff"),
                self._csp_header(),
            ]
        else:
            headers = [
                ("Cache-Control", "no-store"),
                ("Referrer-Policy", "no-referrer"),
                ("X-Content-Type-Options", "nosniff"),
                self._csp_header(),
            ]
        for name, value in headers:
            self.send_header(name, value)
        for name, value in (extra or []) + encoding:
            self.send_header(name, value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if status != 302:
            self.wfile.write(body)

    def _page(
        self,
        status: int,
        title: str,
        body_html: str,
        coverage: str = "",
        extra: list[tuple[str, str]] | None = None,
    ) -> None:
        current = (
            "overview"
            if title in ("Sign-in required", "Error", "Not found", "Read-only")
            else title.lower()
        )
        page = _shell(current, title, body_html, coverage)
        self._respond(status, page.encode(), "text/html; charset=utf-8", extra)

    def _session_id(self) -> str | None:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:  # noqa: BLE001 - hostile cookies are simply unauthenticated
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
        if self._session_id():
            return True
        token = (query.get("t") or [""])[0]
        bootstrap = self.server.bootstrap_token  # type: ignore[attr-defined]
        if bootstrap and token and secrets.compare_digest(token, bootstrap):
            self.server.bootstrap_token = None  # type: ignore[attr-defined]
            sid = secrets.token_urlsafe(32)
            self.server.sessions[sid] = time.monotonic() + SESSION_TTL  # type: ignore[attr-defined]
            self._respond(
                302,
                b"",
                "text/html; charset=utf-8",
                [
                    (
                        "Set-Cookie",
                        f"rifja_ui={sid}; HttpOnly; SameSite=strict; Path=/; Max-Age={SESSION_TTL}",
                    ),
                    ("Location", "/activity"),
                ],
            )
            return False
        self._page(403, "Sign-in required", _DENIED)
        return False

    def _int_arg(self, query: dict[str, list[str]], name: str) -> int | None:
        raw = (query.get(name) or [""])[0]
        return int(raw) if raw.isdigit() else None

    def _route(self) -> None:
        parts = urlsplit(self.path)
        path = unquote(parts.path)
        query = parse_qs(parts.query)
        if not self._authorized(query):
            return
        app: App = self.server.app  # type: ignore[attr-defined]
        store: Store = self.server.store  # type: ignore[attr-defined]
        if path == "/static/ui.css":
            self._respond(200, CSS.encode(), "text/css; charset=utf-8", cacheable=True)
            return
        if path == "/static/ui.js":
            self._respond(200, JS.encode(), "text/javascript; charset=utf-8", cacheable=True)
            return
        if path == "/activity" and "fragment" in query:
            rows = _activity_rows_html(store)
            payload = json.dumps(
                {
                    "since": store.db.execute("SELECT max(id) FROM activity").fetchone()[0] or 0,
                    "rows": rows,
                    "empty": "no agent activity yet",
                }
            )
            self._respond(200, payload.encode(), "application/json")
            return
        if path in ("/", "/activity"):
            body, _since, _more = render_activity(
                store, self._int_arg(query, "before"), self._int_arg(query, "after")
            )
            page = _shell("activity", "Activity", body, app.coverage(limit=1)["status"])
        elif path == "/overview":
            page = _shell("overview", "Overview", render_overview(app, store))
        elif path == "/sessions":
            page = _shell(
                "sessions",
                "Sessions",
                render_sessions(
                    store, self._int_arg(query, "before"), self._int_arg(query, "after")
                ),
            )
        elif path.startswith("/session/"):
            page = _shell(
                "sessions", "Sessions", render_session_detail(app, path.removeprefix("/session/"))
            )
        elif path == "/search":
            page = _shell("search", "Search", render_search(app, (query.get("q") or [""])[0][:500]))
        elif path == "/evidence":
            page = _shell(
                "sessions", "Evidence", render_evidence(app, (query.get("record") or [""])[0][:200])
            )
        elif path == "/memory":
            page = _shell("memory", "Memory", render_memory(store))
        elif path == "/sources":
            page = _shell(
                "sources", "Sources", render_sources(app, store, self._int_arg(query, "p") or 0)
            )
        elif path == "/settings":
            page = _shell("settings", "Settings", render_settings(store))
        else:
            self._page(404, "Not found", "<h1>404</h1><p class=empty>unknown page</p>")
            return
        self._respond(200, page.encode(), "text/html; charset=utf-8")


def serve(
    store: Store, port: int, open_browser: bool = False, machine_output: bool = False
) -> dict[str, Any]:
    """Run until interrupted; never falls back to another port."""
    if not 1 <= int(port) <= 65535:
        raise ValueError("ui_port_out_of_range")
    try:
        server = build_server(store, port)
    except OSError:
        raise ValueError("ui_port_unavailable_pass_--port") from None
    bound = server.server_address[1]
    url = f"http://127.0.0.1:{bound}/?t={server.bootstrap_token}"  # type: ignore[attr-defined]
    stream = sys.stderr if machine_output else sys.stdout
    print(f"Rifja management plane (read-only): {url}", file=stream)
    print("The link signs in one browser session and then expires. Ctrl-C to stop.", file=stream)
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return {
        "requests": server.requests,  # type: ignore[attr-defined]
        "port": bound,
        "url": f"http://127.0.0.1:{bound}/",
    }  # type: ignore[attr-defined]

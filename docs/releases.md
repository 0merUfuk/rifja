# Release notes

## 0.4.2

Fixes a real correction-replay performance bug affecting `daily`, `tasks`
and `decisions` on long-lived corpora once any correction has ever been
extracted from a transcript — a gap the 0.4.0/0.4.1 benchmarks never
exercised, since their synthetic corpora carry a far lower item-per-record
density than real usage. This is a partial fix: `daily` itself remains slow
on a store with many unregistered-project records, for an unrelated reason
found while verifying this one — see below.

Root cause: once a single `items.kind='correction'` row exists anywhere in
the store, `App.daily` unconditionally replayed *every* item in the corpus
(427k+ rows on a real 969k-record store) to resolve it, even though an
extracted correction only ever targets `task`/`next_action`/`blocker`/
`decision` items by topic text (see `semantics.py`'s cancellation patterns) —
`claim`/`context` items, which make up ~97.3% of a real corpus, can never be a
match. `daily` now replays only the kinds a correction can actually reach
when no *explicit* (`rifja correct`, which may target any item by id) 
correction exists; explicit corrections still get the fully general replay,
unchanged. `items()` (which backs `tasks`/`decisions`/`items`) now also
pushes its `kind`/`kinds` filters into SQL instead of fetching the whole
corpus and discarding rows in Python, while still keeping every
`kind='correction'` row in scope so resolution stays correct.

This fixes the correction-replay cost outright, and `decisions` drops from a
full-corpus scan to an indexed one. `tasks` improves but is not yet inside
budget at real scale, since its kind filter includes `claim` — the majority
item kind — by design; that needs its own bounded/ranked query, tracked as
follow-up work.

**`daily` itself is not yet inside budget on a corpus where most records
are unassociated with any registered project** — a second, unrelated
bottleneck this fix's own real-scale verification surfaced: `coverage()`'s
`unassociated_records` count (bundled into every `daily()` response) needs a
per-row bookmark lookup for every `project_id IS NULL` record to check
`text!=''`, and on a store where 98%+ of records are unassociated (fewer
registered projects than active repos), that alone costs 15-20s regardless
of this fix. No code change addresses it yet; registering more of your
active repositories is today's mitigation (it shrinks the unassociated
count directly), and a proper fix — most likely caching the count at
refresh time instead of recomputing it per query — is tracked as follow-up
work, not closed by this release. See [performance
evidence](performance.md#042-real-corpus-correction-replay) for the full,
honest breakdown of what this release does and does not close.

## 0.4.1

Fixes the `daily` command's month-range performance gate, which a post-0.4.0
large-scale rerun found failing (1.426s p95 vs the 1s budget; see
[performance evidence](performance.md#schema-5-closing-the-daily-gate)).
Investigation did not reproduce that sample against identical inputs — the
evidence points to a single-sample tail outlier, not a deterministic
regression — but profiling also found a real, unconditional cost:
`coverage()`'s unresolved-event-time count ran a full table scan on every
`daily()` call regardless of the requested range. Schema 5 adds a partial
index (`records_unknown_time`, migrated automatically with the existing
pre-migration-backup discipline) that turns it into a sub-millisecond index
search. Rerunning the full large-preset benchmark on the fix measured 0.731s
p95, comfortably inside budget with wider margin than before. No other
behavior changes.

## 0.4.0

Repositions Rifja per the ratified product vision: **the CLI is the execution
layer your AI agent drives; the dashboard is your management and observability
plane.** "Install the tool, tell your agent to use it, watch from the
dashboard" is now the complete flow. Existing contracts keep their semantics:
successful JSON responses stay `{schema_version: 1, command, data}`, exit codes
stay 0/2/3/4/130, runtime stays standard-library-only and offline, and
previously registered state upgrades in place (schema 3 -> 4, automatic, with
a pre-migration backup).

Agent execution layer
- The MCP server grows from 4 read-only tools to 14: `status`, `setup`,
  `register_source`, `register_project`, `refresh`, `projects`, `search`,
  `resume`, `tasks`, `daily` (timezone-correct day buckets), `explain`,
  `memory`, `remember`, `associate`. An agent can set up, register and import
  end to end — then answer "where was I" with provenance.
- Consent boundaries are structural: agents only *propose* memory
  (`remember` starts `proposed`; acceptance is human), destructive operations
  (forget, retention, backup, restore) are not exposed at all, and
  registration stays explicit-path-only.
- Every tool call is recorded in a new append-only activity log — failures
  included — which becomes the dashboard's home screen.

Management-plane dashboard
- `rifja ui` is rebuilt as the operator's observability surface: **Activity**
  (live feed of agent tool calls with status and duration), Overview (state,
  14-day record shape, doctor), Sessions and evidence chains, Search, Memory
  (proposals awaiting your acceptance first), Sources (paginated), Settings.
- New "instrument" design system: dark-first, monospace-first data with
  tabular numerals, hairline keylines instead of cards, one amber accent,
  keyboard navigation. Bounded queries throughout (keyset pagination,
  aggregate-first counts) with gzip and cacheable static assets.
- The security model is unchanged: loopback-only, one-time sign-in link
  exchanged for a session cookie, GET-only, restrictive CSP, escaped output.

Agent onboarding
- `rifja agent status` detects Claude Code / Codex environments; `rifja agent
  install claude|codex` wires the MCP server idempotently (foreign config
  preserved, conflicting registrations refused, nothing partially installed)
  and appends a static usage pointer to CLAUDE.md/AGENTS.md — never transcript
  content. A Claude Code skill (`packaging/skills/rifja/SKILL.md`) teaches
  the agent the tool discipline.

Distribution
- Rifja ships from its dedicated `0merUfuk/rifja` Homebrew tap; the Claude
  plugin marketplace is published at `0merUfuk/rifja-plugin`.

## 0.3.0

Ships the five evolution-proposal phases. Existing contracts keep their
semantics: successful JSON responses stay `{schema_version: 1, command, data}`,
exit codes stay 0/2/3/4/130, the application schema stays 3, runtime
dependencies stay standard-library only, and previously registered state
upgrades in place without migration.

CLI presentation
- `setup` detects the timezone (`TZ`, then `/etc/localtime`, each validated as
  an IANA key) instead of applying UTC silently; human output annotates
  `(explicit)`, `(detected)` or `(fallback)`.
- Errors carry next-action hints in human mode, and `--json` mode gains a
  versioned error envelope on stdout: `{"schema_version": 1, "command": ...,
  "error": {"code", "hints"}}`. `hints` is empty for labels without a
  specific next action; parse-level usage errors remain argparse text.
- Every command renders short human lines instead of raw JSON, with the shared
  status vocabulary (glyphs on terminals, plain words otherwise). The
  double-encoded `last_refresh.stats` string is decoded for display only; the
  JSON payload keeps it byte-compatible.
- Bare `rifja` shows a grouped overview (exit 2 preserved); `--help` groups
  commands by workflow. Subcommand help keeps the stock argparse format.
- `refresh` prints bounded stderr progress (`refresh: ...`); `--quiet`
  suppresses it. In `--json` mode progress stays on stderr. Partial refreshes
  name the sources needing attention.

Onboarding
- `rifja init` walks first-run setup and asks before every state change:
  timezone, discovered sources, project directories, and the first refresh as
  a separate explicit consent. Registering reads nothing. Without a terminal
  it prints the plan, changes nothing and exits 2. `setup` remains the
  non-interactive primitive. Empty-state commands point at `rifja init` in
  human output.

Agent integrations
- `rifja mcp` serves read-only MCP tools (`search`, `resume`, `explain`,
  `memory`) over newline-delimited JSON-RPC on stdin/stdout. No network
  listener exists. Writer contention and contract errors return per-request
  `isError` results with stable codes; the server never exits on them. Tool
  output is escaped, framed untrusted evidence.
- `doctor` additionally lists the supported producer-format adapters and their
  stability expectations (`adapter_*` info checks).
- `packaging/hooks/session-start.sh` provides a bounded, fail-open
  SessionStart hook. See docs/integrations.md.

Dashboard
- `rifja ui` serves a read-only local dashboard on 127.0.0.1 (default port
  41970; a taken port is an error, never a fallback). The printed one-time URL
  exchanges its token for an `HttpOnly` + `SameSite=strict` session cookie and
  is then invalid; every route requires the session. GET-only, no mutation
  endpoints; responses carry `Cache-Control: no-store`, `Referrer-Policy:
  no-referrer` and a restrictive CSP. The browser opens only with `--open`.
  The threat model documents the boundary.

Packaging and distribution
- `packaging/claude-plugin/` carries Claude Code plugin and marketplace
  manifests plus the hook bundle; their versions follow the release.
- The public Homebrew tap is planned to rename `0merUfuk/thematrix` to
  `0merUfuk/rifja`; both tap paths keep working through GitHub's redirect and
  the migration commands are documented in docs/homebrew.md. This release
  still publishes to the current tap.

## 0.2.1

Documents the canonical-formula trust required by current Homebrew when a fresh
installation uses the legacy `session-visualizer` formula alias. The primary
`brew install 0merUfuk/thematrix/rifja` experience is unchanged. Legacy install
scripts can first run `brew trust --formula 0merUfuk/thematrix/rifja`; this trusts
only the intended package. The public tap tests this flow explicitly.

Also clarifies that physically moved registered inputs need their canonical
locations re-registered; a checkout symlink does not bypass source safety checks.
Runtime behavior, compatibility entry points and schema remain unchanged.

## 0.2.0

The product is now **Rifja**: recover grounded engineering context and continue
work across projects, worktrees and agent sessions. Repository, Python package,
primary command, Homebrew formula and active documentation use `rifja`.

Install with `brew install 0merUfuk/thematrix/rifja`. Existing public Homebrew
users run `brew update` then `brew upgrade 0merUfuk/thematrix/rifja`. The old
`session-visualizer` command and `SESSION_VISUALIZER_HOME` remain compatible.
Existing default state is reused without moving files; new installations use
Rifja’s default directory. Conflicting default directories require an explicit
selection. Schema 3, record identities, stored memory and backup formats are
unchanged. A version-triggered extraction replay remains the existing behavior.

See [migration details](identity.md). Earlier release notes below describe the
product under its historical name; published tags and artifacts are preserved.

## 0.1.1

Corrects removal and migration instructions for Homebrew installations retaining
multiple versions. Use `brew uninstall --force 0merUfuk/thematrix/session-visualizer` to remove all
installed versions while preserving application state. When switching from the
private tap, use `brew uninstall --force session-visualizer/local/session-visualizer`
before `brew install 0merUfuk/thematrix/session-visualizer`.

This addresses a reproduced migration failure where removing only the current
private version left an older installed version and prevented switching taps.
Public maintenance commands use the fully qualified formula name to avoid
ambiguity when the private tap remains registered. Runtime behavior and schema
remain unchanged. Published 0.1.0 assets are retained
unchanged; this patch carries the corrected instructions into every artifact.

## 0.1.0

First public MIT-licensed release. Retains the offline Python implementation and
schema 3, with Homebrew-managed installation and a single `session-visualizer`
command. Adds public repository metadata, contributor/security guidance, pinned
build tooling, a macOS/Linux CI matrix, and tag-driven releases with checksums
and GitHub build-provenance attestations. The Homebrew formula is distributed
through `0merUfuk/thematrix`.

Install: `brew install 0merUfuk/thematrix/session-visualizer`.
Upgrade: `brew update` followed by `brew upgrade 0merUfuk/thematrix/session-visualizer`.
Older private local-tap users must uninstall that formula before installing from
the public tap. Saved state, facts and accepted principles remain in place.
The first refresh after a version change replays derived extraction once;
unchanged later refreshes remain incremental.

Read the README for supported platforms and `docs/providers.md` for format
limits. Windows and untested platform combinations are not certified. The
software retains the documented semantic/excerpt limits; publishing a release
does not turn recorded claims into verified current project results.

## 0.1.0rc4

Adds Homebrew-managed installation from a private release bundle. One installer
command registers a local tap, verifies the wheel through Homebrew and exposes
the existing CLI. Homebrew owns Python and the isolated application environment.
No runtime dependencies, commands, data model or schema change. Rc3 state remains
compatible. As with previous version upgrades, the first refresh replays the
derived extraction and preserves durable memory; subsequent unchanged refreshes
skip those sources. Existing candidate artifacts remain preserved.

Adds a deterministic installer bundle, formula generator, functional Homebrew
test, installation regression coverage and a local release procedure. Public
hosting and tap publication are not performed by the installer or build workflow.

## 0.1.0rc3

Forward local candidate for useful continuity from registered repository documents
and supported native history. Adds opt-in bounded document refresh, separately
labeled purpose/status/constraints, conservative recorded-move inference, ordinary
pending-work and unique-subject resolution, conversation-management filtering, and
compact evidence excerpts in both export formats. Schema remains 3; refresh
rebuilds derived extraction and preserves explicit memory/association overrides.

Independent challenges reproduced additional negation, cancellation, condition
omission and path-alias failures before repair. Their synthetic regressions remain
in the distribution. Real private inputs, oracle and acceptance outputs remain
outside the package. See [context limits](project-context.md); the accompanying
local release evidence decides acceptance for the actual installed artifact.

Rc1/rc2 artifacts and evidence remain preserved. This candidate does not select a
public license, publish a package or claim general language understanding.

## 0.1.0rc2

This private local candidate repairs six independently reproduced continuity
failures in rc1:

- Keep unresolved parsing gaps visible after valid JSONL appends.
- Preserve explicit project objectives beyond the recent-record window.
- Include observed Git-only activity in daily views.
- Select historical activity before limiting it, and disclose carryover limits.
- Retain action dependencies, priorities and decision rationale in handoffs.
- Extract supported explicit intent beyond the display-excerpt boundary while
  retaining bounded redacted excerpts and distinct identities for suffix edits.

Schema 3 adds a covering index for daily activity, with a private schema 2 backup
before migration. Daily queries also avoid repeated coverage and evidence work.
A refresh replays the older extraction pipeline while
preserving durable user memory and supported corrections. Regression coverage
includes the continuity failures, source repair, suffix edits and upgrade
behavior. CI actions are pinned to verified upstream commit identities.

Release-specific commands, pass/fail results, package checksums, platform
validation and residual gaps belong in the accompanying local evidence report.
No publication, public license, broader platform certification or general
natural-language understanding is implied.

## 0.1.0rc1

Initial local CLI candidate: configured provider ingestion, Git/worktree
observations, evidence-linked continuity, memory, export and recovery. Its
original verification results remain historical evidence; rc2 addresses
additional acceptance failures found after that delivery.

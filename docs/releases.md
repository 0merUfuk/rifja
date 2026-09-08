# Release notes

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

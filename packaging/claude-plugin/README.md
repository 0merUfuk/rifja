# Rifja Claude Code plugin manifests

Distribution manifests for the Claude Code plugin ecosystem. They wrap the
locally installed `rifja` CLI — the plugin ships no binary and no Python
environment; Homebrew remains the installer and the updater.

Contents:

- `.claude-plugin/plugin.json` — the plugin manifest (identity, version,
  metadata). The version field must match the released `rifja` version.
- `marketplace.json` — a one-plugin marketplace manifest. Publish this file
  from a repository whose default branch hosts it (for example the
  `0merUfuk/rifja` checkout root or a dedicated marketplace repository), then
  users add it with `/plugin marketplace add <owner>/<repo>` and install with
  `/plugin install rifja`.
- `hooks/hooks.json` + `hooks/session-start.sh` — the bounded, fail-open
  SessionStart hook (10 s host timeout, 12 KiB output cap, exit 0 on every
  failure path). Set `RIFJA_PROJECT` or edit the command's argument to select
  the project whose continuation context is injected as data-only evidence.
  The injected text is escaped, fenced untrusted evidence; fences mark
  authority as conditional rather than preventing a model from reading it, so
  operators who want no untrusted content at session start should omit the
  hook and keep the MCP server (the pull model, where each retrieval is an
  explicit action).
- `.mcp.json` — registers the read-only MCP stdio server (`rifja mcp`) so
  Claude Code can call `search`, `resume`, `explain` and `memory`.

Update checklist for a release: bump both `version` fields with
`pyproject.toml`, verify the hook script against `packaging/hooks/`, and run
the repository gates (`make check`, release audit) before publishing.

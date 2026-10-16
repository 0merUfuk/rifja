# Rifja session recovery (release candidate, unpublished)

An Agent Skills package that helps a developer resume interrupted work in Claude Code, Codex or
another skills-capable agent. Invoked as a skill, it returns one bounded brief that keeps four kinds
of statement apart:

| Tag | Source | Authority |
| --- | --- | --- |
| `GIT` | Observed by the script just now (branch, HEAD, dirty files, commits, operation in progress) | Fact, as of the timestamp |
| `USER` | What the user said in an earlier session (quoted, with ref) | Stated intent, possibly stale |
| `CLAIM` / `TOOL` | What an agent claimed, or a recorded tool exit status (quoted, with ref) | Unverified history; contradictions flagged |
| `UNCERTAIN` | Coverage gaps, staleness, selection exclusions, unknowns | Say so; never guess |

It adds no daemon, MCP tool or hook, and changes none of Rifja's behaviour: `src/` is untouched. The
existing CLI, MCP server, hook, dashboard and plugin are unaffected; this package drives the same CLI.

## Status in one table

| Question | Answer | Where |
| --- | --- | --- |
| Is the package technically ready? | Yes for local and own-repository distribution: reproducible build, spec-validated, installs in disposable Claude Code and Codex homes, tests green on macOS and Linux | [release.md](release.md) |
| Is there agent evidence that it helps? | Yes for Claude Code + Sonnet on synthetic data (n=45); none for Haiku (never activated), Codex (blocked) or Hermes (untested) | [evaluation.md](evaluation.md) |
| Is it ready for a marketplace submission? | No: owner-dependent items and two structural mismatches are open | [commercial.md](commercial.md) |
| Is there demand? | Unknown. Nothing here measures it | [commercial.md](commercial.md) |

## What is in the package

- `packaging/skills/session-recovery/`: the canonical skill (`SKILL.md`, `scripts/recover.py`,
  `references/`, `agents/openai.yaml`, MIT `LICENSE`).
- `tools/recovery_bundle.py`: validates the skill against the Agent Skills spec and builds reproducible
  distributables (standalone zip, Claude Code plugin, Codex marketplace) with `SHA256SUMS`/`MANIFEST.json`.
- Tests: `tests/test_session_recovery.py`, `tests/test_recovery_packaging.py`,
  `tests/test_recovery_rifja_contract.py`, helpers in `tests/recovery_fixtures.py`: synthetic histories and
  disposable repositories only.
- `tools/recovery_eval.py`, `tools/recovery_eval_report.py`: the controlled comparison and its report;
  `tools/recovery_demo.py`: the reproducible recorded demo.

## Quick start (from a checkout of this branch; nothing is published)

Prerequisites: `git`, Python 3.9+, [Rifja](https://github.com/0merUfuk/rifja) 0.4.2+ already set up
(`brew install 0merUfuk/rifja/rifja`, `rifja init`, `rifja refresh`), and `uv` for the build.

```sh
uv run python tools/recovery_bundle.py build --out dist/recovery
# Claude Code (note the ./ : a bare path is read as a GitHub owner/repo)
claude plugin marketplace add ./dist/recovery/rifja-session-recovery-claude-plugin
claude plugin install rifja-session-recovery@rifja-session-recovery
# Codex
codex plugin marketplace add ./dist/recovery/rifja-session-recovery-codex-marketplace
codex plugin add rifja-session-recovery@rifja-session-recovery
```

Without a build: copy `packaging/skills/session-recovery/` to `~/.claude/skills/` (Claude Code),
`.agents/skills/` in a repo (Codex, Hermes) or `$CODEX_HOME/skills/`.

Then, in the repository you want to resume: "recover the session for this repo, using my Claude and
Codex history". The first use asks you to approve running the bundled script. The same engine runs
directly (use the path where the skill is installed):

```sh
python3 <skill-dir>/scripts/recover.py doctor
python3 <skill-dir>/scripts/recover.py sources --repo .
python3 <skill-dir>/scripts/recover.py brief --repo . --providers claude,codex
```

## Documents

| | |
| --- | --- |
| [Demo walkthrough](demo/transcript.md) | Real recorded run on synthetic data (`demo/demo.cast` for `asciinema play`), plus two real agent traces: [with the skill](demo/agent-run-claude-sonnet-dock-skill.md), [without](demo/agent-run-claude-sonnet-dock-cli.md) |
| [Evaluation](evaluation.md) | Skill vs. manual CLI vs. pasted output: measurements, limits, failed attempts |
| [Compatibility matrix](compatibility.md) | What was and was not verified, per harness, provider and runtime |
| [Rifja contract](rifja-contract.md) | The exact CLI commands and JSON fields consumed |
| [Source and privacy assessment](privacy-assessment.md) | Data flows, controls, residual risks |
| [Release notes and blockers](release.md) | Exact SHA, checksums, gates, remaining blockers |
| [Commercial assessment](commercial.md) | Positioning, pricing hypotheses, listing prerequisites, verdict |
| [Studio handoff](studio-handoff.md) | Machine-readable inventory for later ingestion by `agent-product-studio` |

# Compatibility matrix

Status words are narrow. **Verified**: a check in this repository, run on the machines and versions
below, exercised it and passed. **Install only**: the package installs and lists as enabled, but no
model-driven run was done. **Smoke**: one model-driven run on an earlier build. **Blocked**: attempted;
an external gate stopped it. **Not tested**: no claim. Nothing here claims universal session recovery.

Test machines: macOS 27.2 arm64 (git 2.55.0; Python 3.9.6, 3.11, 3.13.15, 3.14.7; Homebrew 7.0.6;
Rifja 0.4.2 Homebrew build and this checkout; Claude Code 2.1.288; Codex CLI 0.154.0; Hermes Agent
0.21.5) and a Debian 13 (trixie) container (git 2.47.3, Python 3.14.8, Rifja 0.4.2 from this checkout).

## Where the skill runs (consumer harness)

| Harness | Install path | Verified | Not verified |
| --- | --- | --- | --- |
| Claude Code 2.1.288 (macOS) | Plugin (`claude plugin marketplace add ./...`, `install`), `--plugin-dir`, or copy to `~/.claude/skills/` | `claude plugin validate` on plugin, manifest and marketplace; install into a disposable `CLAUDE_CONFIG_DIR` shows enabled; **model-driven**: 60 evaluation runs (Sonnet 45, Haiku 15) and 20 activation probes, see [evaluation](evaluation.md). Sonnet used the skill 15/15 on task prompts; Haiku 0/5 | Interactive `/plugin` UI; Windows; Linux with a model |
| Codex CLI 0.154.0 (macOS) | Plugin via a local marketplace (`codex plugin marketplace add ./...`, `codex plugin add <name>@<marketplace>`), or copy to `$CODEX_HOME/skills/` or `.agents/skills/` | Install into a disposable `CODEX_HOME` reports `installed, enabled` and places the skill; **Smoke**: one earlier repo-scoped run discovered and used the skill and followed its hardened Git flags (8/10 rubric, older build, kept in `eval/history/codex-smoke`) | **Model-driven comparison BLOCKED** by the account usage limit (until Oct 22 2026); the manifest field set was copied from an installed first-party plugin because OpenAI's schema page returned HTTP 403 to automated fetch |
| Hermes Agent 0.21.5 | Repo-scoped `.agents/skills/<name>/` after `hermes skills trust` | In a disposable `HERMES_HOME`, the trusted repo reports "1 project skill(s) will load" | No model-driven run; whether and how Hermes invokes it is untested |
| Other Agent Skills hosts (Cursor, Gemini CLI, Copilot, ...) | Copy the folder | Structure only (`tools/recovery_bundle.py check`) | Everything else |
| claude.ai web / Cowork | n/a | Not applicable: the skill needs the user's local `git`, `rifja` and Rifja state | |

## Whose history it can recover (providers, via Rifja 0.4.2)

| Provider | Data contract | Verified here | Notes |
| --- | --- | --- | --- |
| Claude Code | `projects/<project>/<session>.jsonl` | Synthetic transcripts imported, selected, summarized; claim/result check; hostile content | Anthropic documents the raw format as internal and unstable; Rifja's adapter is shape-checked. No genuine transcript was used |
| Codex | `sessions/**/*.jsonl` rollouts (shapes from Rifja's source-pinned fixtures) | Synthetic rollouts imported; recorded exit status and test-runner name surfaced; contradiction check | `.jsonl.zst` archives are supported by Rifja but were not exercised |
| Hermes | `state.db` schema 26 | Synthetic database imported and selected | No genuine Hermes store was used |
| Anything else | n/a | Unsupported: unknown providers are rejected | No Rifja adapter exists for Cursor, Gemini CLI, Copilot, Aider, ... |

## Runtime prerequisites

| Requirement | Verified value | Behaviour if absent |
| --- | --- | --- |
| Python for `recover.py` | 3.9.6, 3.11, 3.13.15, 3.14.7 (macOS) and 3.14.8 (Debian) pass the end-to-end tests; stdlib only | Not tested below 3.9 (syntax needs 3.9+) |
| Git | 2.55.0 (macOS), 2.47.3 (Debian) | `git_missing` (exit 3) |
| Rifja | 0.4.2, JSON `schema_version` 1 | `rifja_missing` (3); `--git-only` still works; no Rifja state -> `rifja_not_initialized` (4), nothing is created; other schema versions -> `rifja_contract_mismatch` (3) |
| OS | macOS 27.2 arm64; Debian 13 container for the Python tests | Rifja itself is release-checked on macOS 15 and Ubuntu 24.04; Intel macOS, Ubuntu and Windows (unsupported by Rifja) were not tested here |
| Network | none needed, none used | |

## Drift

The skill reads only Rifja's versioned JSON (`schema_version: 1`), not the producers' raw files, so a
Claude Code or Codex storage change surfaces as a Rifja adapter update plus a `rifja refresh`. The
contract is pinned by `rifja_contract_mismatch` and `tests/test_recovery_rifja_contract.py`, which run
the real Rifja console.

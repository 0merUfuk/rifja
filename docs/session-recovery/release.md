# Release notes, verification and blockers: session-recovery 0.1.0 (candidate)

Not released, not tagged, not listed. The branch is `feat/session-recovery-skill`, cut from
`origin/main` at `bd3d29d24b21019ff489754700160b3fae9a944b`. The exact commit that carries these
files is the branch head: `git rev-parse feat/session-recovery-skill` (a file cannot contain its own
commit hash; the delivery message states it, and `git log` is authoritative).

## What changed in the repository

| Area | Change |
| --- | --- |
| `src/` | **None.** The Rifja CLI, MCP server, hook, dashboard, schema and existing plugin are untouched |
| Existing files | `Makefile` (ruff also checks the new skill folder), `README.md` (one documentation link), `docs/integrations.md` (one section) |
| New | `packaging/skills/session-recovery/`, `tools/recovery_{bundle,eval,eval_report,demo}.py`, `tests/recovery_fixtures.py`, `tests/test_session_recovery.py`, `tests/test_recovery_packaging.py`, `tests/test_recovery_rifja_contract.py`, `docs/session-recovery/**` |

## Artifacts (deterministic: rebuilding yields identical bytes)

Built with `uv run python tools/recovery_bundle.py build --out dist/recovery` (version 0.1.0, tested
against Rifja 0.4.2). Zips are uncompressed with fixed 1980 timestamps and regular-file mode bits.

```
a0633790e4e0ffdb413483c5df873739680c39e25d4dc7a405831e2fe6196e38  rifja-session-recovery-claude-plugin-0.1.0.zip
510cb13c812c933d07d3d5e4e687118b130ecdf2cc6fe036e71697c164274fd5  rifja-session-recovery-codex-marketplace-0.1.0.zip
7388cc3287283d3ccb0bb2940f15b9f0f49815772ac0a789e9ad33bc5eb4df6c  session-recovery-skill-0.1.0.zip
```

These are the exact packages the final Claude evaluations ran. `dist/` is git-ignored; verify by
rebuilding and comparing with `shasum -a 256 -c dist/recovery/SHA256SUMS`.

## Verification (what was actually run)

| Gate | Result |
| --- | --- |
| `ruff check`, `ruff format --check`, `mypy` (repo gates, plus the skill folder) | Pass |
| Full pytest, macOS 27.2 arm64, Python 3.14.7 | 747 passed (baseline on `main` before this work: 531; 216 new tests: engine 151, packaging 59, Rifja contract 6) |
| New suites on Debian 13, Python 3.14.8, git 2.47.3, Rifja from this checkout, final tree | 211 passed, 2 skipped (`claude`/`codex` absent in the container) |
| Engine on every installed Python | 3.9.6, 3.11, 3.13.15, 3.14.7 pass the end-to-end brief test |
| `tools/recovery_bundle.py check` (Agent Skills spec + privacy policy) | Pass |
| `claude plugin validate` (plugin, manifest, marketplace); isolated `claude plugin install` | Pass; installed and enabled in a disposable `CLAUDE_CONFIG_DIR` |
| `codex plugin marketplace add` + `codex plugin add`; isolated `CODEX_HOME` | Pass; `installed, enabled`; skill placed in the plugin cache |
| README Quick start executed verbatim in disposable homes | Pass |
| Repo release audit (`tools/audit_release.py`) | See "Release audit" below |
| Live agents (Claude Code) | 60 evaluation runs + 20 activation probes: [evaluation.md](evaluation.md) |
| Codex model-driven evaluation | **BLOCKED** (account usage limit until Oct 22 2026; not retried) |

### Previously discovered high-severity issues, rechecked

Each has a named regression test that passes on the final tree (86 selected tests re-run together):

| Issue (found by the independent adversarial review unless noted) | Regression tests |
| --- | --- |
| Commit message forged `[GIT]` entries and leaked secrets / personal paths | `TestForgedGitText` |
| Repo-controlled programs ran (content filters, includes, signature programs) while the brief claimed they were off | `TestRepositoryProgramsAreNeverRun` |
| Attacker-chosen Git config names reached "Next steps"; branch/path rendered as free text | `test_config_names_are_labels_from_a_fixed_vocabulary`, `test_branch_and_path_are_quoted_not_free_text` |
| Injection / secret filter bypasses (Unicode, split lines, more secret shapes) | `TestSanitizerBypassesFromReview`, `TestMoreSecretShapes` |
| Provider-selection leaks; explain without selection; silent flag conflicts | `TestSelectionLeaks` |
| Hostile or oversized Rifja output; hangs; wrong types | `TestHostileRifjaOutput` |
| Truncation dropped safety sections; clamped limits | `test_safety_sections_survive_truncation`, exact-limit tests |
| Rifja state created by `doctor`/`sources` on an uninitialised home (second review) | `TestNeverCreatesRifjaState` |
| Bundle tool: wipes arbitrary `--out`, lax parser, hidden characters, symlinked dirs (review) | `TestValidatorHardening`, `TestBuildSafety`, `TestRemainingSpecChecks` |
| `allowed-tools` pinned to the skill directory broke skill loading (live evaluation) | `test_skill_does_not_pin_allowed_tools` |
| Quick-start paths read as GitHub shorthand (second review) | README now uses `./`; verified verbatim |

## Package contents audit

Verified by tests (`TestDistributionContents`, `test_no_private_material_anywhere_in_the_package`,
`test_new_files_pass_the_release_audit_patterns`) and by inspection of the three artifacts:

- Files: `SKILL.md`, `scripts/recover.py`, three reference documents, `agents/openai.yaml`, plugin
  manifests and a README, plus the repository's own `LICENSE` and `NOTICE` (byte-identical copies).
  Nothing else; every name is on an allow-list.
- **No** transcripts, memories, databases, `.env` files, credentials, e-mail addresses, host paths
  (`/Users`, `/home`, `/private`, `/var/folders`), hooks, MCP servers, LSP servers, binaries, commands,
  monitors or settings. The script has no network code and opens no files (writes go to stdout only).
- **No third-party content**: the only licence texts are the project's own MIT `LICENSE`/`NOTICE`.
  Python, Git, SQLite, Homebrew and Rifja retain their own licences and are not bundled. MIT notices
  and all redistribution rights are preserved; nothing changes the licence.

## Release audit

The repository's own gate (`tools/audit_release.py`) scans source, the Git index, full history and the
built wheel/sdist. Its result and the CI status are reported in the delivery message for the exact
commit, because both depend on the commit. Procedure: stage and commit, `uv build --no-build-isolation`,
`uv run python tools/audit_release.py --output <file>`, then push and read the GitHub Actions run.

## Remaining limitations and blockers

Technical (open, none blocks local use):

1. No validation on genuine session histories (synthetic only).
2. Codex model-driven comparison BLOCKED until Oct 22 2026; Codex has install evidence and one smoke run only.
3. Hermes: skill discovery only. Haiku never invoked the skill; activation depends on the host model.
4. Pattern-based injection filtering is not a semantic filter (see the privacy assessment).
5. Rifja needs Python 3.14 via Homebrew; Windows unsupported; Intel macOS, Ubuntu and Windows not run here.
6. The first use asks for a permission approval; pre-approving via `allowed-tools` was tried and broke loading.

Owner-dependent (cannot be done by the engineering work):

1. Authorization to publish, list, tag or merge. None was given; none was done.
2. Marketplace prerequisites: plugin icon, privacy-policy, support and terms URLs; a public repository
   for the plugin; an Anthropic paid plan and developer-portal access; OpenAI organization access and
   identity verification.
3. A decision on the structural mismatches (not runnable on claude.ai/Cowork; OpenAI's "no undeclared
   local dependencies" rule) before any directory submission.
4. Commercial decisions: pricing, support offering, and whether to test demand at all.

# Local release notes

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

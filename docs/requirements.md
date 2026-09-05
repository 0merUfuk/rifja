# Release acceptance ledger

No row is certified solely by its implementation. Final source/artifact identity,
exact commands and outcomes belong in the release evidence report. Current work
is not a published release.

| Mandatory boundary | Implementation | Verification |
|---|---|---|
| Scoped registration/discovery; clones/worktrees remain distinct | app.register/discover; git collectors | test_git; test_resilience; test_continuity |
| Git commits, branches, dirty/rename/untracked, detached/unborn/missing | git.inspect_repository; app.project | test_git; read-only before/after snapshot checks |
| Codex, Claude, Hermes genuine evidence and format coverage | adapters; ingest; docs/providers | test_adapters; private local-source CLI evidence; support matrix |
| Incremental checkpoints, copies/rotation/edits/truncation/incomplete tails | ingest; generations/occurrences | test_resilience; large benchmark parsed-record counters |
| Partial diagnostics, unknown formats, bounded input/excerpts | privacy; adapters; coverage | test_adapters; test_resilience; test_review_regressions |
| Daily/date range, project/session, tasks/decisions and search | app/cli | test_cli; test_continuity |
| Resume context, actionable steps, explicit objective or unknown | context; app.resume | annotated 18-scenario corpus; test_review_regressions |
| Claims, historical results, current observations and uncertainty distinct | models; extract; context; evidence | test_continuity; stale revision/source and false-completion prohibitions |
| Event working context, explicit mapping; no prose-path attribution | ingest.associate; app.associate | test_continuity; test_resilience |
| Aware, naive, midnight and DST times; import time separate | timeutil; records schema | test_continuity; historical ingestion and ordering checks |
| Durable correction, rejection, cancellation, supersession and archive | corrections; memory; app.items | test_extract; test_continuity; test_resilience |
| Explicit/proposed constitution, acceptance and provenance | memory; principles; ingestion proposals | test_cli; test_resilience; reference redaction regression |
| Bounded Markdown/JSON, provenance, accepted principles, untrusted context | render; cli.export | test_continuity; test_cli; export-budget tests |
| Full text search and scope filters | SQLite FTS5; app.search | test_cli; test_resilience; measured common/sparse query budgets |
| No imported command execution; Git helpers disabled/trust preserved | git; parser boundaries | test_git; test_resilience; threat model |
| Redaction before persistence, symlink/regular-file bounds, permissions | privacy; ingest; store | test_resilience; test_review_regressions; package/private data audits |
| Offline deterministic core without credentials | stdlib runtime; explicit CLI | isolated installed commands under process network denial and no credentials |
| Writer serialization, reader consistency, interruption recovery | store; atomic source transactions | test_resilience; final integrated review |
| Backup/restore configuration and memory; schema migration/newer refusal | store; canonical schema validation | test_resilience; test_review_regressions; installed lifecycle checks |
| Forgetting/retention, dependent deletion and no refresh reimport | tombstones; app.forget/retain | test_resilience; test_cli; installed lifecycle checks |
| Installation without checkout/home/dev resources; uninstall preserves memory | wheel/sdist; console entry point | isolated artifact route and installed command transcript |
| >=1k sessions/250k records/250MiB/20 repos, declared budgets | tools/benchmark.py | final artifact benchmark; docs/performance |
| Independent review, coherent changes and exact final artifacts | review findings; release process | resolved regressions; final source fingerprint and artifact checksums |
| Retain parse gaps across append; retain objectives and long-record intent; preserve handoff constraints and date-scoped activity | ingestion; explicit objective items; daily selection; render | test_acceptance_regressions; independent installed challenges; rc1-to-rc2 upgrade checks |
| Daily aggregation meets the warm query budget without dropping selected evidence | app.daily; schema 3 covering index; bounded output | large installed daily query; schema 2 upgrade and failure rollback in test_resilience |

Deferred by scope: cloud/registry publication, new public license, required AI,
embeddings, servers/MCP, daemons, UI, synchronization, remote repository hosting,
automatic orchestration and broad preference mining. Unavailable external
platforms/remote CI are documented validation gaps, never represented as executed.

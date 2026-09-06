# Design and acceptance decisions

Status: detailed design pressure-tested; implementation authorized by the commission.

## Runtime and scope

Use Python 3.14+ with SQLite FTS5, argparse, dataclasses and standard-library runtime dependencies. Use Python 3.14 to read established Zstandard archives with the standard library; development initially validated uncompressed workflows on 3.13 and final candidate validation uses 3.14. Develop on macOS arm64 Python 3.14; support claims require executed evidence. The distribution and executable command are both `session-visualizer`. Version 0.1.0 is MIT licensed and uses Homebrew-managed Python delivery with GitHub release artifacts. CLI/versioned JSON and bounded Markdown are the interoperability boundary. MCP would add server lifecycle and tool authorization surface without improving required offline workflows; defer it, keep application queries separate from rendering.

## Identity and persistence

Application UUIDs identify projects and worktrees. Git common-directory filesystem identity links related worktrees, not repository names or remotes. Explicit move/association corrections handle filesystem identity changes. A path is an attribute; unknown/ambiguous paths remain unresolved. Event cwd overrides session metadata. Association says where context occurred, never who authored changes.

SQLite contains projects, worktrees, observations, sources/generations, sessions, records, record occurrences, derived items, corrections, principles, refresh runs and forget tombstones. Stable record hashes include provider/session/native record identity/content. Occurrences retain source generation and locator. Copies deduplicate records while preserving provenance; replacement preserves obsolete evidence with generation status. User memory is separately authoritative and survives rebuild. Migrations are versioned, transactional and preceded by a recoverable database backup; newer schema is refused.

## Shared contracts and owners

`models.py` is lead-owned. Adapters consume untrusted mappings plus a mutable serializable context and return normalized records; adapters never persist or execute. The caller validates sizes/depth, redacts, assigns provenance/IDs, and atomically commits records plus checkpoint. Git module returns typed read-only observations without persistence. Extraction consumes normalized records and returns candidates; it never elevates an agent claim to verified completion. Application composes queries; CLI alone handles exit codes and rendering. Lead owns schema, types, manifest, locks, config and release. Workers have disjoint files and private temporary test state.

## Incremental consistency

One bounded writer lock encloses refresh. Readers use transactions. Unchanged sources use file identity/size/mtime/ctime checkpoints without parsing. Appends verify the old prefix then parse only new complete records. Edits/truncation/replacement create a new generation. Explicit verification can rehash unchanged files. Incomplete tails retry; malformed records produce bounded diagnostics and unrelated valid records continue. Batches are bounded; source checkpoint and normalized data commit together. Failures preserve prior committed state and visibly partial coverage. SQLite provider stores are accessed read-only with consistent transactions including WAL; no repair or migration of producer stores.

## Authority and usable context

Categories remain user intent/correction, agent proposal/claim, historical tool result, direct Git observation, commit observation, controlled verification or interpretation. No extracted tool result certifies current code. Current Git is inspected for resume and timestamped separately from cached session context. Unknown revision, dirty context or timestamps remain unknown. Original times are retained; aware times normalize to UTC and calendar views use configured zone. Naive times are unresolved, never silently UTC.

Conservative English/Turkish explicit markers and plain requests yield tasks, next actions, blockers, decisions and corrections. Code fences/quotations/abandoned proposals do not become active work. Later cancellations and supersession carry provenance. Inferred principles remain proposed until product-level acceptance. Lists are not padded. Untrusted source excerpts are delimited in exports, never executed. Exports disclose omissions and include accepted principles, provenance, coverage, generation time and freshness within a configurable bound.

## Threat model and controls

Assets: private sessions, repository state, durable memory, producer stores. Trust boundaries: configured filesystem roots to parser; parsed text to SQLite/FTS; database to terminal/export; CLI to Git subprocess; backup to restore. Inputs cannot grant permissions. No network/model calls or transcript command execution. Git arguments are structured, timed and output-bounded, with hooks/fsmonitor/pager/external-diff mechanisms disabled for observation commands; Git trust checks remain intact. Repository document content is read only through explicitly opted-in, bounded collections; see [continuity repair](continuity-design.md).

Collection requires explicit roots; do not follow directory/file symlinks outside scope. Skip credentials, .env and generated/self-state directories. Redact secrets before storage/index/output, retain bounded excerpts, strip terminal controls, enforce record bytes/depth/diagnostic limits and private state permissions. Redaction is a best-effort local defense, not a claim of perfect detection or encryption. Backups/exports are independent private copies. Forgetting removes dependent index data and adds tombstones to prevent refresh reimport; user memory survives with missing-evidence labels. Restore validates versions/content and preserves the current state on failure.

## Pressure test and resolutions

| Failure | Chosen protection and remaining limit |
|---|---|
| Agent says done, old tests pass | Preserve claims and historical applicability; no inferred current verification |
| Similar names/remotes, branch changes, moved worktrees | Git metadata identities, event cwd, explicit overrides; current resume observation; unknown moves remain missing until re-registration |
| Edited source silently changes old evidence | Generations and content IDs; reference status retained; metadata plus prefix hashes and explicit full verification |
| One malformed/unknown provider poisons refresh | Per-source transactions, bounded diagnostics and partial exit code |
| Concurrent writer/crash destroys checkpoint | Bounded lock, atomic transactions, interruption/recovery tests |
| Manual memory erased by rebuild | Separate corrections/principles with durable provenance and tombstones |
| Search/index or exports leak secrets | Redaction before persistence, controlled excerpts and audit; residual unknown secret formats documented |
| Large corpus forces full reads/reparse | Streaming/bounded records, FTS/indexed queries, unchanged checkpoints and measured benchmark |
| Installation depends on checkout or hidden owner config | Wheel and sdist, fresh venv/HOME/cwd, no runtime third-party dependencies |

## Gates and budgets

Acceptance scenarios precede implementation; independent corpus records mandatory facts, blockers, active next actions, uncertainties and prohibited conclusions. All critical annotated blockers/actions must be represented and no unsupported completion or confident cross-project/worktree attribution is allowed. Required lifecycle, privacy, Git complexity, CLI, migration, recovery and installation cases map to executable evidence in the release report.

Large target declared before optimization: >=1,000 sessions, ~250,000 records, ~250 MiB varied sources, >=20 repositories including worktrees/history. Budgets: cold <=120s, unchanged <=5s, ~100-record append <=2s, indexed query p95 <=1s, peak ingestion <=512MiB. Measure Git and complete resume separately. No budget weakening after a failure. The original local-candidate performance gate is historical; public release and remote CI requirements are documented in the development guide.

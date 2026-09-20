# Performance evidence

The first independently installed candidate passed all eight benchmark gates on the declared large corpus. Its cold refresh took 103.543 seconds, its slowest query p95 was 0.307 seconds, and peak ingestion RSS was 31.8 MiB. The exact package fingerprint and reference results appear below; the earlier failed baseline is preserved separately.

The benchmark exercises the installed public CLI in an isolated home, application state directory, working directory, synthetic source tree, and controlled repositories. It does not read real session stores, use credentials, contact a network service, or import application internals into the harness. The budgets were declared in [the design](design.md) before measurements: cold refresh ≤120 seconds, unchanged refresh ≤5 seconds, approximately 100 appended records ≤2 seconds, warm indexed query p95 ≤1 second, and peak ingestion RSS ≤512 MiB. Git observation and complete resume are reported separately.

## Reproduce

Run from the checkout with its installed CLI available. Output directories must be new direct children of `.local/` named `benchmark-*`; the harness never removes an existing run.

```sh
.venv/bin/python tools/benchmark.py --preset tiny --output .local/benchmark-tiny-new --repetitions 3
.venv/bin/python tools/benchmark.py --preset small --output .local/benchmark-small-new --repetitions 7
.venv/bin/python tools/benchmark.py --preset large --output .local/benchmark-large-new --repetitions 7
```

`--cli PATH` selects another already installed entry point. No dependency installation is part of the benchmark. Each command's stdout, stderr, exit status, wall time and peak RSS are retained under the run directory. `corpus.json` describes inputs, `measurements.json` holds individual command evidence, `result.json` holds the completed run, and `failure.json` identifies an interrupted or failed workflow. Read the result's gates and count checks; a successfully started subprocess does not establish a passing benchmark.

## Dataset and measurement method

| Preset | Sessions | Initial source/normalized records | Source bytes | Repositories | Additional linked worktrees |
|---|---:|---:|---:|---:|---:|
| Tiny | 8 | 160 | 196,608 | 2 | 1 |
| Small | 100 | 10,000 | 10,485,760 | 20 | 5 |
| Large | 1,000 | 250,000 | 262,144,000 | 20 | 5 |

Half of the sessions use native Codex rollout envelopes and half use Claude Code transcript envelopes, authored from the documented provider field shapes. The Codex writer version is 0.153.4. The Claude transcript's `version` field uses the genuinely observed writer version 2.1.260; the separately inspected PATH executable was 2.1.63. The benchmark does not claim an installed Claude CLI 2.1.260. No private transcript is copied or transformed. Deterministic session/record IDs, timestamps, role rotation, narrative sentences, tool calls/results, and bounded task/blocker/next-action/decision markers create varied inputs. Normalized record count equals line count because every envelope yields exactly one record. Approximately ten percent are tool results; only four explicit continuity statements are added per session, avoiding a corpus inflated with hundreds of thousands of extracted tasks. The large set produces 25,000 historical tool claims and 4,000 explicit continuity items.

Source content is padded with ordinary descriptive sentences to an exact byte target. Individual line sizes vary by one byte to distribute the remainder. Source paths change with the chosen output directory, so byte hashes are reproducible for a fixed directory rather than across relocated runs. Current generation uses deterministic valid UUIDs and provider-shaped directory nesting. The first baseline runs used descriptive synthetic identifiers and flat source directories; their count, byte, and role targets are unchanged, but later validation distinguishes the revised generator.

Every repository has three local commits. Five large/small repositories have linked worktrees with an uncommitted modification; selected main checkouts have an untracked file. Registration runs through `project add`, including actual Git discovery of worktrees. Git has isolated author/configuration settings and no remotes. Source configuration and all refresh/query/resume operations use the installed CLI, including normal process startup and JSON rendering.

Wall time uses `time.perf_counter`. `os.wait4` supplies actual child peak RSS; Darwin reports bytes and Linux reports KiB, which the harness converts to bytes. Peak ingestion is the maximum cold/unchanged/append CLI RSS. It is not the harness's cumulative child memory usage. Measurements do not claim summed simultaneous memory across a process tree. The ingestion commands do not spawn Git observations. All performance samples are separate subprocess invocations.

“Cold” means an empty application index. The operating system's filesystem caches are not forcibly flushed, so the corpus is typically cached following generation. Warm queries receive one unmeasured warmup and seven measured samples; p95 uses the nearest-rank definition, which is the maximum for seven samples. Cold and the 100-record append each have one measured sample per run. Unchanged refresh, startup, Git status, project observation, and complete resume have seven repetitions in small/large runs. A source fingerprint before/after every measured command exposes concurrent checkout edits; measurements spanning changes are provisional until rerun against stable code.

The harness checks exact initial sessions/records/worktrees, no duplicate native records, unchanged `parsed_records=0` and `inserted_records=0`, exactly 100 records parsed/inserted after append, and identical occurrence/record counts. Searches must return actual matches; task and complete-resume queries must include controlled pending work and blockers. Neither empty result sets nor historical claims are counted as proof of current code correctness.

## Recorded environment

The measured host is macOS 27.0 / Darwin 27.0.0, arm64, with 14 logical CPUs and Git 2.52.0. Initial development baselines used Python 3.13.12. The independently installed candidate reference used Python 3.14.7 and CLI version 0.1.0rc1; the current package requires Python 3.14 or later. Other operating systems and hardware are not certified by these results. Normal host activity was not suspended.

## Independently installed candidate reference

The first installed reference run used the independently installed candidate entry point through `--cli`, with a fresh isolated benchmark state and the revised UUID/native-directory generator. No runtime package files were edited or dependencies installed by the benchmark. The installed source fingerprint stayed identical before and after every measured command; `fingerprint_scope` was `installed_package`, with no source changes reported.

| Operation | Installed candidate | Budget | Result |
|---|---:|---:|---|
| Cold refresh | 103.543 s | 120 s | Pass |
| Unchanged refresh, maximum of 7 | 0.261 s | 5 s | Pass |
| Append exactly 100 | 0.343 s | 2 s | Pass |
| Sparse/project search p95 | 0.175 s | 1 s | Pass |
| Common-term search p95 | 0.307 s | 1 s | Pass |
| Tasks p95 | 0.138 s | 1 s | Pass |
| Decisions p95 | 0.126 s | 1 s | Pass |
| Peak ingestion RSS | 33,308,672 bytes / 31.8 MiB | 512 MiB | Pass |
| CLI startup p95 | 0.062 s | Report separately | Measured |
| Git status p95 | 0.010 s | Report separately | Measured |
| Project observation p95 | 0.269 s | Report separately | Measured |
| Complete resume p95 | 0.391 s | Report separately | Measured |

The initial import produced exactly 1,000 sessions, 250,000 unique records and occurrences, 20 projects, 25 worktrees, and 29,000 derived items from exactly 262,144,000 source bytes. Seven unchanged refreshes each parsed and inserted zero records. The append parsed and inserted exactly 100, yielding 250,100 unique records and occurrences and no duplicate native records. Searches returned useful matches; task queries and complete resumes included the controlled pending actions and blockers. All 86 public CLI invocations and all eight performance and consistency gates passed; the harness exited 0. Corpus generation took 5.842 seconds and project registration 2.781 seconds, measured separately from cold ingestion.

Runtime package fingerprint: `d70c9f7cecfc972d5bd0d7b293ae97763867caa53b46b7ea180768ad1bf5e608`. The harness computes SHA-256 over sorted top-level installed package module names followed by each module's bytes; this is a runtime-source fingerprint, not a wheel archive hash. Generator snapshot SHA-256: `f5bbec27c6442d2d0336bea388dda7f075a99df0589a9cd1d77787ea0b3f0eac`. Initial source-corpus SHA-256: `5ef430f52a8bc9827dd2ba50b4be86c226be55f9fe63d3c7f0e5839311e6b4f0`.

Evidence is retained in `.local/benchmark-installed-candidate-1/result.json`, `measurements.json`, `corpus.json`, the exact `generator.py` snapshot, and individual command output files. Exact executable paths are recorded privately in command evidence. The invocation was:

```sh
.venv/bin/python tools/benchmark.py --preset large --output .local/benchmark-installed-candidate-1 --repetitions 7 --cli /path/to/installed/venv/bin/rifja
```

These results apply to the fingerprinted installed candidate and the described workload. The earlier baseline failed its query gate; this reference does not erase that failure. Subsequent runtime changes require their own verification. In particular, this JSONL performance corpus does not measure compressed-source throughput or full Hermes-database ingestion.

## Initial results

| Operation | Small baseline | Budget | Result |
|---|---:|---:|---|
| Cold refresh | 4.645 s | 120 s | Pass |
| Unchanged refresh, maximum of 7 | 0.063 s | 5 s | Pass |
| Append exactly 100 | 0.156 s | 2 s | Pass |
| Sparse/project search p95 | 0.057 s | 1 s | Pass |
| Common-term search p95 | 0.065 s | 1 s | Pass |
| Tasks p95 | 0.062 s | 1 s | Pass |
| Decisions p95 | 0.051 s | 1 s | Pass |
| Peak ingestion RSS | 30.4 MiB | 512 MiB | Pass |
| Git status p95 | 0.010 s | Report separately | Measured |
| Project observation p95 | 0.184 s | Report separately | Measured |
| Complete resume p95 | 0.247 s | Report separately | Measured |

Small baseline state contains exactly 100 sessions, 10,000 initial records and occurrences, 20 projects, 25 worktrees, and 1,400 derived items. After append it contains 10,100 records and occurrences, with zero duplicate native records. Evidence is in `.local/benchmark-small-baseline/result.json` and its individual command files. Tiny complete workflow also passed in `.local/benchmark-tiny-pass/`.

The first tiny attempt found a harness assertion using the wrong search response key; the CLI had returned matches correctly. A subsequent tiny run exposed an application `UnboundLocalError` in complete resume. The application owner fixed it, and the full tiny workflow then passed. These failed runs remain in `.local/benchmark-tiny-baseline/` and `.local/benchmark-tiny-validated/`; neither is presented as a passing end-to-end run.

## Large baseline and failed query gate

| Operation | Large baseline | Budget | Result |
|---|---:|---:|---|
| Cold refresh | 103.717 s | 120 s | Pass |
| Unchanged refresh, maximum of 7 | 0.246 s | 5 s | Pass |
| Append exactly 100 | 0.280 s | 2 s | Pass |
| Sparse/project search p95 | 0.265 s | 1 s | Pass |
| Common-term search p95 | 1.304 s | 1 s | **Fail** |
| Tasks p95 | 0.144 s | 1 s | Pass |
| Decisions p95 | 0.167 s | 1 s | Pass |
| Peak ingestion RSS | 31.5 MiB | 512 MiB | Pass |
| CLI startup p95 | 0.049 s | Report separately | Measured |
| Git status p95 | 0.012 s | Report separately | Measured |
| Project observation p95 | 0.344 s | Report separately | Measured |
| Complete resume p95 | 0.450 s | Report separately | Measured |

The large baseline imported exactly 1,000 sessions, 250,000 records and occurrences, 20 projects, 25 worktrees, and 29,000 derived items. Unchanged refreshes parsed and inserted zero records. The append parsed and inserted exactly 100 records, producing 250,100 records and occurrences with zero duplicate native records. All controlled action/blocker and nonempty-query assertions passed. The overall benchmark still failed because the common-term query exceeded its declared budget. Its seven measured samples were 0.832, 1.304, 0.345, 0.479, 0.375, 0.338 and 0.351 seconds; the slow sample was retained.

The baseline is additionally provisional because checkout fingerprints changed during the run, including the cold command; concurrent application/output edits were still in progress. The fingerprints and stage evidence are retained in `.local/benchmark-large-baseline/`. Final certification requires a rerun against stable installed code. The cold number is one successful sample, not a margin guarantee on other hosts.

Read-only profiling of the same isolated large database attributed 2.107 of a profiled 2.307 seconds to SQLite execution, with 0.109 seconds in output sanitization. The existing FTS query ordered all matches by rank, timestamp and ID before limiting. `EXPLAIN QUERY PLAN` showed `VIRTUAL TABLE INDEX 0:M1` and `USE TEMP B-TREE FOR ORDER BY`. A rank-only comparison used `VIRTUAL TABLE INDEX 32:M1` and removed that temporary sort. With one warmup and seven direct SQLite samples, query-only p95 changed from 0.216 to 0.131 seconds; both returned 20 stable record IDs within their own repeated executions. These microbenchmarks exclude startup/rendering and are profiling evidence, not replacement CLI acceptance results. Details are retained in `.local/benchmark-search-profile/`.

Final delivery measurements and artifact reconciliation are recorded in the local release evidence report. This document preserves the first installed reference and failed baseline; it does not certify runtime changes made afterward.

## 0.4.0 large-preset reference (schema 4, activity log, 14-tool MCP)

Every benchmark result above predates the vision-realignment work (PRs #15-#18):
schema 4's append-only `activity` table, the MCP server's growth to 14 tools, and
the dashboard's "instrument" rebuild all shipped with no large-preset rerun. This
is that rerun, against the installed 0.4.0 wheel in a fresh venv (`--preset large
--repetitions 7`), and it found one real regression, not just a currency gap.

| Operation | 0.4.0 | Budget | Result | rc1 reference (for scale) |
|---|---:|---:|---|---:|
| Cold refresh | 115.805 s | 120 s | Pass | 103.543 s |
| Unchanged refresh, max of 7 | 2.128 s | 5 s | Pass | 0.261 s |
| Append exactly 100 | 1.560 s | 2 s | Pass | 0.343 s |
| Sparse/project search p95 | 0.227 s | 1 s | Pass | 0.175 s |
| Common-term search p95 | 0.342 s | 1 s | Pass | 0.307 s |
| Tasks p95 | 0.129 s | 1 s | Pass | 0.138 s |
| Decisions p95 | 0.188 s | 1 s | Pass | 0.126 s |
| **Daily (month-range) p95** | **1.426 s** | **1 s** | **Fail** | not gated at the time |
| Peak ingestion RSS | 53.2 MiB | 512 MiB | Pass | 31.8 MiB |
| CLI startup p95 | 0.077 s | Report separately | Measured | 0.062 s |
| Git status p95 | 0.028 s | Report separately | Measured | 0.010 s |
| Project observation p95 | 0.392 s | Report separately | Measured | 0.269 s |
| Complete resume p95 | 0.553 s | Report separately | Measured | 0.391 s |

**The `daily` gate fails at declared scale.** The measured query is
`rifja daily 2026-01-01 --to 2026-01-31` (a month-wide range) — the same
query class the rc2 acceptance review's finding A7 previously fixed and added
to the gate (see [review findings](review-findings.md)). Reading
`App.daily` (`src/rifja/app.py:589`), the range-drill path groups every
matching `records` row by `(project_id, provider, actor, session_id,
worktree_id)` for the whole requested range — there is no day-level
pre-aggregation on this path, unlike the single-day/aggregate-overview path
described in "Bounded daily materialization" below. The `records_daily`
covering index (`store.py` schema v3) still exists and the query still uses
it, but a 31-day range over a 250k-record/20-project corpus is enough rows
to push past the shared 1-second query budget (1.426 s p95 measured, up from
sub-budget behavior at the same preset before the schema-4/activity changes).
This was not a false pass before: the A7 fix predates schema 4, MCP, and the
activity table, and was never re-verified at large scale after any of them
landed.

**Everything else moved but stayed inside budget**, most notably unchanged
refresh (0.26 s -> up to 2.1 s) and append (0.34 s -> 1.56 s) — both still
comfortably under their 5 s / 2 s budgets, but the direction is consistent
with the added activity/document bookkeeping per write, not noise. Cold
refresh grew a proportionally smaller ~12% (103.5 s -> 115.8 s) despite the
schema/table additions.

Evidence: `.local/benchmark-0.4.0-large/result.json` (this checkout),
runtime fingerprint `86fbcfd052fc50ed8c2c0b3cffe4c8d7a4fda9ced2c1e600391d7584accc0a8f`
(installed-package scope, `/tmp/rifja-bench-venv`), generator SHA-256
`c4feca9a67262031c94231e86650e16310265a0175421f8c5be3121bb72a948d`, measured
on macOS 27.0/Darwin 27.0.0 arm64, Python 3.14.7, Git 2.55.0. This does not
replace the local release evidence report's own reconciliation; it is the
runtime-change verification `docs/development.md`'s release procedure calls
for and the `docs/requirements.md` ledger's declared-budget row requires.

**Follow-up required before this counts as closed**, per the same discipline
this document already applies to itself: fix or redesign `App.daily`'s
range-drill aggregation (day-bucket the count before hydrating per-actor
detail, matching the "Bounded daily materialization" pattern below), rerun
this exact benchmark, and replace this section's `Fail` with a passing
result and its own evidence. Until then, the CLI/MCP/dashboard month-range
daily view is measurably slow at the project's own declared production scale.

### Schema 5: closing the `daily` gate

Reproducing the failing sample against the exact captured large-corpus state
(`.local/benchmark-0.4.0-large`, copied and replayed directly, not
regenerated) never returned the 1.426 s outlier again: seven fresh subprocess
samples of the same `rifja daily 2026-01-01 --to 2026-01-31` query against
that unmodified corpus and unmodified code clustered at 0.60-0.83 s. A
`cProfile` pass of `App.daily` attributed the components as roughly 0.22 s to
the actor/session `GROUP BY` (`records_daily` index, unavoidable temp
B-tree — the query already uses the only column order that also serves the
range filter), 0.24 s to `_daily_candidates`'s activity bucket, and 0.095 s to
the unconditional `coverage()` call every `daily()` invocation makes. The
1.426 s sample does not reproduce from identical inputs; on the evidence
available it was a single-sample tail outlier (the same nearest-rank-of-7
pattern already documented above for `search-common`'s 1.304 s sample), not a
deterministic regression.

`coverage()`'s cost was real and fixable regardless: `EXPLAIN QUERY PLAN`
showed its `unknown_event_times` count (`SELECT count(*) FROM records WHERE
time_status!='known' AND provider!='project_document'`) ran a full `SCAN
records` over all 250,331 rows to find the 231 that matched, on every single
`daily()` call, independent of the requested date range. Schema 5 adds a
partial covering index, `CREATE INDEX records_unknown_time ON
records(time_status) WHERE time_status!='known'`, migrated automatically
with the existing pre-migration-backup discipline. On the same corpus this
turns that scan into a sub-millisecond index search (measured: 0.08 s → 15
µs for the query alone) and removes it as a fixed per-call cost.

| Operation | 0.4.0 (schema 4) | Schema 5 | Budget | Result |
|---|---:|---:|---:|---|
| **Daily (month-range) p95** | 1.426 s (unreproduced outlier) / 0.830 s (rerun) | **0.731 s** | 1 s | **Pass** |
| Cold refresh | 115.805 s | 105.675 s | 120 s | Pass |
| Unchanged refresh, max of 7 | 2.128 s | 2.671 s | 5 s | Pass |
| Append exactly 100 | 1.560 s | 1.541 s | 2 s | Pass |
| Sparse/project search p95 | 0.227 s | 0.077 s | 1 s | Pass |
| Common-term search p95 | 0.342 s | 0.209 s | 1 s | Pass |
| Tasks p95 | 0.129 s | 0.145 s | 1 s | Pass |
| Decisions p95 | 0.188 s | 0.123 s | 1 s | Pass |
| Peak ingestion RSS | 53.2 MiB | 51.0 MiB | 512 MiB | Pass |

Both the schema-4 rerun and the schema-5 fix run were fresh, independent
`--preset large --repetitions 7` executions against the current checkout's
editable install (not against `/tmp/rifja-bench-venv`), so cross-run variance
in unrelated metrics (append, unchanged refresh) reflects normal machine
noise, not code changes — only `records`, `App.daily`, and `store.py`'s
migration chain changed between the two runs.

All eight gates pass. Evidence: `.local/benchmark-large-with-fix/result.json`
(schema 5) and `.local/benchmark-large-verify/result.json` (schema 4 rerun,
same checkout, pre-index), checkout fingerprint
`f1dca18e9b35d06a98e650e285a814c67048c33dd412237713ec6206d796b426`
(`fingerprint_scope: checkout_editable_fallback`), generator SHA-256
`c4feca9a67262031c94231e86650e16310265a0175421f8c5be3121bb72a948d`, measured
on macOS 27.0/Darwin 27.0.0 arm64, Python 3.14.7, Git 2.55.0. This closes the
follow-up above: the section's `Fail` no longer describes current code.

## RC3 document-inclusive measurement method

The additional workload and measurements below are declared before the RC3 large
run. The established provider targets and all existing budgets remain unchanged:
the large preset still generates exactly 1,000 provider sessions, 250,000 provider
records and 262,144,000 provider source bytes across 20 repositories and five linked
worktrees. Documents are additional inputs and are counted separately; they never
replace provider records or provider source bytes.

Every registered checkout receives a synthetic maintained `README.md` and
`STATUS.md`. The README contains three bounded prose sections covering purpose,
architecture and the state boundary. The status document contains six sections
covering pending work, its conditions, limitations, a decision, a historical claim
and a fenced command example. These inputs are committed as part of the existing
three-commit repository setup. Linked worktrees inherit the documents and receive
a controlled status edit identifying their working context. Collection is enabled
through the installed public `document add` command with an explicit worktree and
two relative filename allowlists before the cold refresh.

| Preset | Registered checkouts with documents | Additional documents/sessions | Additional initial document records | Additional document bytes |
|---|---:|---:|---:|---:|
| Tiny | 3 | 6 | 27 | 4,981 |
| Small | 25 | 50 | 225 | 41,505 |
| Large | 25 | 50 | 225 | 41,505 |

The independent generator declares these paragraph counts without importing the
application parser. `documents.json` records every input's exact byte count,
SHA-256, relative path and expected normalized count, plus aggregate document bytes
and a content manifest hash. The original `corpus.json` retains the provider-only
counts and byte target. The copied generator and its SHA-256 identify the exact
combined fixture definition. This extends the existing harness arguments and
preserves prior evidence directories without modifying them.

The cold refresh, unchanged refresh samples and exactly 100 appended provider
records all run with document collection enabled. SQLite checks independently
assert exact provider/document session, record and occurrence counts. Unchanged
refresh must parse and insert zero records and retain the complete document
source/generation snapshot and record-ID fingerprints. The provider append must
insert exactly 100 records while preserving all document identities. All existing
cold, unchanged, append, query and peak ingestion thresholds continue to apply.

After those original measurements, exactly one status paragraph is changed. The
changed-document refresh is a single report-only time sample, as declared in
[the continuity design](continuity-design.md). It must parse and insert exactly six
new document section records, preserve all prior evidence, advance only the changed
document's generation and leave provider counts unchanged. Subsequent unchanged
refresh samples again require zero parsing/insertion, stable document identities
and the existing five-second unchanged-refresh limit. Expected historical document
versions are recorded separately from the still-forbidden duplicate provider
records. Peak ingestion RSS includes the added document refresh samples and keeps
the original 512 MiB limit.

Git status, current project observation and complete resume retain their separate
measurements. Full bounded handoff construction adds separate JSON and Markdown
export samples through the installed CLI, including current Git observation,
normal startup and rendering. Both formats must produce substantive output within
24,000 characters; the JSON handoff must include documented project purpose.
Handoff time is reported independently and is not substituted for the indexed
query budget. RC3 ingestion now performs bounded Git identity/blob metadata reads
for configured documents; the earlier statement about ingestion avoiding Git
observations describes the preserved pre-document reference workload.

Only the final installed candidate's stable runtime fingerprint and completed
large-run evidence can certify this extended workload. A tiny harness self-check
establishes count/output wiring only; it does not replace a large measurement or
certify performance while application files are changing.

Large refreshes use a 16 MiB SQLite page-cache target and a 4,096-page automatic
WAL checkpoint threshold (about 16 MiB with the normal 4 KiB page size). This
amortizes page reuse and checkpoints across source transactions. It does not
relax commit synchronization, remove source-level rollback, defer ingestion to a
background job, or omit the final connection close from measured CLI wall time.
Long-lived external readers can delay WAL recycling; the threshold is not a hard
file-size limit. See [SQLite's WAL performance and checkpoint documentation](https://sqlite.org/wal.html).

### Bounded daily materialization

Daily activity ranks lightweight item IDs in SQLite and counts the complete
activity/carryover buckets before loading the displayed text and provenance.
This path applies only when there are no imported resolution events or durable
user corrections. A durable (explicit, `rifja correct`) user correction always
retains the full correction-resolution path, since its target may be any item
kind. An imported (extracted) correction retains a correction-resolution path
scoped to the kinds it can ever target — see "0.4.2: real-corpus correction
replay" below — rather than the complete path. Historical activity,
current-generation carryover, project/worktree scope, stable ordering and
omission counts retain their existing meaning. Nonpositive internal API limits
and SQLite versions before 3.25 also use the complete path.

A bounded experiment on a private copy of the synthetic LARGE state produced
byte-identical complete JSON before and after the change. Two warm development
CLI samples were 0.748 and 0.746 seconds; the first cold filesystem sample was
3.633 seconds and remains recorded. These measurements diagnose the change and
do not replace the final installed LARGE query gate or its unchanged one-second
warm p95 budget. The benchmark generator, source/record counts and semantic
assertions remain unchanged.

## 0.4.2: real-corpus correction replay

None of the benchmarks above ever exercise a corpus with more than a
handful of correction items, because the synthetic generator does not
extract them at real-usage density. On the owner's actual local store —
969,307 records, 427,156 items, 235 extracted `correction`-kind items, zero
explicit (`rifja correct`) corrections — `App.daily` measured **25.35s**
for a day with activity (`cProfile`: 21.4s in the underlying `items()`
fetch, 3.68s in `_resolve_items`'s Python-side matching), and `App.items(
kind="decision")` (backing `rifja decisions`) measured comparably, both
because `needs_resolution` forced a full, unbounded fetch of all 427,156
items the moment any correction-kind item existed anywhere in the store —
regardless of the requested date range, project, or limit.

Reading `semantics.py`, an *extracted* correction (the only kind real usage
ever produces without an explicit `rifja correct` call) is always created
with `target="text:" + topic(...)`, and `_resolve_items` only ever indexes
that key from `task`/`next_action`/`blocker`/`decision` items — `claim` and
`context` items, 415,810 of the 427,156 total (97.3%), can never be a
match. `App.daily` now takes this scoped replay only when *no* explicit
correction exists and at least one extracted correction item does; an
*explicit* correction (unrestricted target) still forces the fully general
replay, unchanged. When only extracted corrections exist, it replays
`{task, next_action, blocker, decision, correction}` only. `App.items` was
extended to push its `kind`/`kinds` filters into the SQL `WHERE` clause
(always `OR i.kind='correction'`, so resolution stays correct for every
existing caller, including `tasks`'s pre-existing `{task, next_action,
blocker, claim, correction}` filter and `decisions`'s `kind="decision"`)
instead of fetching every item and discarding rows in Python — the same
`(r.provider=? OR i.kind='correction')` idiom the query already used for
`provider`.

Measured on the same real store (grown to 1,310,327 records / 549,912
items / 247 correction items by the time of this measurement, still zero
explicit corrections): the `items()` fetch that `daily`'s correction replay
depends on dropped from the case above to **2.76s**, and `rifja decisions`
dropped to **0.35s** from a comparable full scan. `rifja tasks` (kind
filter includes `claim`, ~332k of 549k items) dropped from 20s+ to
**6.9s** — real, but still outside the 1s budget; its kind filter was left
unchanged (removing `claim` would change what the view means, not just how
fast it runs), so a properly bounded `tasks` needs its own ranked/windowed
query, tracked as follow-up work alongside `daily`'s remaining gap below.
Correctness: `tests/test_daily_selection.py::
test_daily_extracted_correction_scopes_replay_to_actionable_kinds` asserts
the scoped replay is exactly what runs (not the full fallback, not the
bounded fast path) and that it still correctly resolves a correction
targeting an item outside the query window, alongside the pre-existing
`test_daily_later_imported_correction_requires_full_resolution` and
`test_daily_durable_correction_keeps_status_text_and_resolution_reference`,
both still green.

**This does not make `daily` itself fast on the same real store**, for an
unrelated reason this fix's own real-scale verification surfaced:
`coverage()` — embedded in every `daily()` response — computes
`unassociated_records` as `SELECT count(*) FROM records WHERE project_id
IS NULL AND text!=''`. `EXPLAIN QUERY PLAN` shows an index seek
(`records_project_time`), but with only 2 of the store's active projects
registered, 1,289,769 of 1,310,327 records (98.4%) are unassociated, and
each index-matched row still needs a bookmark lookup into the base table
to evaluate `text!=''` — that alone measured **15.65s** in the same
`cProfile` run, dominating `daily`'s total 18.79s end to end. A partial
index does not help here the way schema 5's did: the index already narrows
to exactly the matching rows (confirmed via `EXPLAIN QUERY PLAN`), and the
cost is the per-row bookmark lookup itself, not a table scan. The two real
mitigations are registering more active projects (shrinks the unassociated
count directly, and is unrelated to any code change) and, as follow-up
work, computing this count once at refresh time instead of live per query.
Evidence for both real-corpus measurements above: profiled directly
against a private, read-only copy of the owner's own local store (not
published; contains real session content) via `cProfile`, on the same
runtime fingerprint and platform as the schema-5 measurements above.

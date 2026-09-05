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
.venv/bin/python tools/benchmark.py --preset large --output .local/benchmark-installed-candidate-1 --repetitions 7 --cli /path/to/installed/venv/bin/session-visualizer
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
user corrections; either condition retains the full correction-resolution path.
Historical activity, current-generation carryover, project/worktree scope, stable
ordering and omission counts retain their existing meaning. Nonpositive internal
API limits and SQLite versions before 3.25 also use the complete path.

A bounded experiment on a private copy of the synthetic LARGE state produced
byte-identical complete JSON before and after the change. Two warm development
CLI samples were 0.748 and 0.746 seconds; the first cold filesystem sample was
3.633 seconds and remains recorded. These measurements diagnose the change and
do not replace the final installed LARGE query gate or its unchanged one-second
warm p95 budget. The benchmark generator, source/record counts and semantic
assertions remain unchanged.

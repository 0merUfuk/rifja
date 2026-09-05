# Independent local review findings

Checkpoint: **2026-09-05 20:23:26 UTC**, shared `main` working tree. No commit/HEAD was available at the initial review. Scope is the runtime application, storage, ingestion, privacy, adapters, context, rendering and CLI. This reviewer did not independently certify their own `git.py` or `compressed.py`; those were assigned to another reviewer. All reproductions use synthetic temporary state.

**Latest source result: all 15 review regressions and three lead cases pass (18 total).** Twelve findings below have reviewed source fixes. Earlier 46/49-case runs remain recorded below; those runs preceded the final crowded-project regression. The older wheel identified below contains reproduced failures. This source checkpoint does not assert a final package result; authoritative final installation and immutable-artifact outcomes are recorded separately in the external local `RELEASE-EVIDENCE` report. Passing source tests do not approve an older distribution.

The security-threat-model skill and its reference template were applied using the operator-supplied local/offline/single-user context. No additional permission questions were needed. CodeRabbit was unavailable and external upload was outside scope, so this was a local manual and executable review. The only `.local` content read during final review was the expressly authorized synthetic `.local/install-candidate-1/report.json`; private transcripts and other private reports were excluded.

## Findings and resolution

Severity describes the original defect with its realistic prerequisite, not an outstanding vulnerability in the corrected source.

| ID | Original severity | Reproduced behavior and prerequisite | Source resolution and evidence |
|---|---|---|---|
| RF-001 | High | A backup supplied or modified by an attacker could add a trigger or replace `records_ai`. Restore accepted it, and an ordinary write deleted durable memory. Requires the operator to restore that backup; no OS execution was shown. | `store.validate_schema` compares every schema object/definition with a canonical version before backup copying. Both added-trigger and replaced-trigger regressions pass. |
| RF-002 | High | A local writer replaced a registered source ancestor with a symlink. Refresh then imported readable content outside the selected source scope. No narrow race or network transfer was needed. | `privacy.open_regular` traverses ancestors with descriptor-relative no-follow opens and verifies the final regular file; refresh/discovery recheck exclusions. Ancestor-replacement regression passes. |
| RF-003 | Medium | A local source writer supplied a FIFO with a supported suffix; refresh admitted a blocking open while holding writer ownership. | Discovery rejects special files; no-follow/nonblocking open is followed by descriptor type checking. FIFO-admission regression passes without blocking the test process. |
| RF-004 | Medium | An ordinary snapshot containing 125 changed paths lost 25 through generic list cleaning with no omission diagnostic. | `App._save_snapshot` preserves the already bounded observation collection. Synthetic contract test verifies all paths or disclosed omissions; it does not test collector internals. |
| RF-005 | Medium | A `GOAL:` line inside a pasted code fence became authoritative user intent. | `context.details` uses quote/fence-aware prose extraction. Fenced/quoted goal regression passes. |
| RF-006 | Low | Operator/automation passed token-shaped text as a memory reference and it bypassed pre-storage redaction. | `App.memory_add` validates bounded reference syntax before persistence. Invalid-reference/redaction regression passes. |
| RF-007 | Medium | After an imported source was edited, an obsolete task still appeared as a current action and a removed goal remained the objective. Current Git availability incorrectly suggested the historical instruction was still supported. | `App.items` and `context.details` inspect current generation occurrences; obsolete tasks become `source_superseded`, obsolete objectives are excluded, and obsolete transcript cancellations no longer resolve surviving tasks. Three regressions pass. Explicit local corrections retain separate authority. |
| RF-008 | Medium | Fifty-five newer agent claims pushed an older unresolved critical blocker beyond the default query limit before resume selected unfinished work. Requires only an ordinary busy history. | `App.items(prioritize_active=True)` ranks unresolved blockers/actions before the limit; `App.resume` uses it. Critical-blocker regression passes. Limits and omission notices still apply to large sets of active items. |
| RF-009 | Medium | A concurrent connection committed during fresh repository observation after a read snapshot began. The snapshot-to-write upgrade escaped as raw `sqlite3.OperationalError`. | `Store.transaction` translates SQLite busy/locked errors in outer transactions and nested savepoints into `BusyError` with retry guidance; rollback remains intact. Controlled second-connection regression passes. This is a safe retry outcome, not a claim that every concurrent command succeeds. |
| RF-010 | Medium | An observed filename containing newlines, Markdown headings and HTML was inserted literally into ordinary resume output. Requires imported/repository metadata plus a reader that interprets Markdown. No command execution was shown. | `render.resume_markdown` escapes dynamic metadata, paths, diagnostics and evidence locations. Filename-markup regression passes. The separate bounded-export renderer already had escaping controls. |
| RF-011 | Medium | A Hermes `messages` view exposed the expected columns but evaluated a nonterminating recursive scalar. Actual refresh held its writer lock beyond the test harness's three-second timeout. Requires a hostile selected producer database, not transcript prose alone. | `adapters._columns` rejects views/virtual definitions before evaluation. `_open_db` adds `trusted_schema=OFF`, an 8 MiB page-cache target and a cooperative 100 million SQLite-operation / 30-second budget. The reader emits partial coverage on interruption. The actual App/Ingestor child-process regression now finishes with partial status and zero imported records. |
| RF-012 | Medium | A crowded project had 50 active blockers and 50 explicit next actions. Blocker-first ordering filled the default 50-item window and resume returned no next action. A later export budget could repeat the loss. The lead found this during final benchmark validation; an independent two-session native-ingestion/real-Git fixture reproduced it. | `App.items` reserves up to five action slots before filling the remaining priority window. `render.bounded_export` preserves the recommended action selection before other candidates. The same regression verifies blockers and current supported actions in live resume, both default 24,000-character export formats, and exact/disclosed omissions. It passes without expanding either bound. |

Source anchors: [application](../src/session_visualizer/app.py), [storage](../src/session_visualizer/store.py), [ingestion](../src/session_visualizer/ingest.py), [privacy](../src/session_visualizer/privacy.py), [context](../src/session_visualizer/context.py), [rendering](../src/session_visualizer/render.py), [adapters](../src/session_visualizer/adapters.py). Exact independent cases are in [test_review_regressions.py](../tests/test_review_regressions.py).

## Verification evidence

No production code was edited by this reviewer during this review. No failing expectation was removed, softened or marked as expected failure. The RF-012 fixture is one additional case, extended through both render formats rather than counted repeatedly.

```text
Initial review, 19:53 UTC:
.venv/bin/python -m pytest tests/test_review_regressions.py -q
7 failed in 0.15s; exit 1; 0 passed; 0 skipped.

Readiness review before new source fixes:
.venv/bin/python -m pytest tests/test_review_regressions.py -q
4 failed, 7 passed in 0.49s; exit 1.

New Hermes view reproducer before its fix:
.venv/bin/python -m pytest tests/test_review_regressions.py::test_hermes_executable_view_cannot_hold_refresh_without_a_bound -q
1 failed in 3.13s; exit 1. Child exceeded three seconds and was killed/reaped.

Final source checkpoint:
.venv/bin/python -m pytest tests/test_review_regressions.py tests/test_resilience.py -q
46 passed in 3.58s; exit 0; 0 failed; 0 skipped.

After the final coverage-scope correction:
.venv/bin/python -m pytest tests/test_review_regressions.py tests/test_resilience.py tests/test_lead_regressions.py -q
49 passed in 3.70s; exit 0; 0 failed; 0 skipped.

.venv/bin/python -m ruff check tests/test_review_regressions.py
All checks passed!; exit 0.
```

The final source run contains all original seven cases, seven new cases, and 32 previously authored resilience cases. The resilience suite covers actual source lifecycle, interruption/concurrency, migrations, durable memory/corrections/tombstones, Git freshness/association and privacy using temporary data. Its passing result is supporting evidence, not independent certification of this reviewer's Git implementation.

The final lead-owned coverage correction was also inspected: `App.source_add` locks the configuration read/modify/write; `Ingestor.refresh` records its exact source/exclusion scope; `App.coverage` marks a changed scope `refresh_required` and a disappeared configured root `partial`. Its regression passed in the 49-case follow-up. Newer decision-freshness and principle-exception rendering changes are covered by the separate acceptance reviewer; no independent duplicate certification is implied.

## Final crowded-project correction (RF-012)

The previous installed-artifact review of wheel `a9fce2c0414e4022e990968d7cd2b92f3f80ec664722adc15803f6a63ecda626` passed its then-existing 14 review cases plus three lead cases. That readiness result was superseded after the lead's final benchmark exposed the full-blocker-window defect. Earlier private review reports are preserved; their passing counts do not include the new case. The frozen threat model describes the preceding checkpoint; this section supplements its context-priority threat with the newly reproduced boundary.

```text
Before correction:
.venv/bin/python -m pytest tests/test_review_regressions.py::test_many_active_blockers_preserve_supported_actions_and_honest_omissions -q
1 failed in 0.62s; exit 1. Live resume.next_actions was empty.

After correction and extension through JSON/Markdown exports:
.venv/bin/python -m pytest tests/test_review_regressions.py tests/test_lead_regressions.py -q
18 passed in 0.89s; exit 0; 0 failed; 0 skipped.

.venv/bin/python -m ruff check tests/test_review_regressions.py
All checks passed!; exit 0.
```

The fixture uses two temporary native Claude sessions, an actual temporary Git repository and live App/Ingestor calls. It verifies 50 extracted blockers and 50 extracted explicit actions before testing the limited view. It requires both kinds to survive, the complete total to remain 100, omitted count to equal total minus retained items, and omission notices to remain visible. JSON and Markdown exports must include the recommended action and a blocker within the unchanged default character bound. This tests the application contract; it does not independently certify the reviewer's Git collector implementation.

## Distribution evidence at this source checkpoint

The reviewed older wheel is `dist/session_visualizer-0.1.0rc1-py3-none-any.whl`, SHA-256 `b75183d0ad09e30729e9abea27f4a3e4324da56db202967fc08147e82817d954`. Its corresponding sdist SHA-256 is `82fe1fcb40ca8b283924dbba9e43d1ba6944337c3ae2fb3870472bfebe3c8046`.

Independent archive inspection found 20 wheel members: 15 Python modules and five distribution metadata files. The sdist had 44 members. Neither artifact contained `.local`, `.git`, `.venv`, bytecode caches, credential-named files, or symlinks. Metadata requires Python >=3.14 with no `Requires-Dist`. An isolated Python invocation from `/tmp` loaded the external installation, did not include the checkout on `sys.path`, and confirmed all 15 installed module bytes matched the wheel. These results apply only to these artifact hashes.

The authorized installation report lists 45 commands, all with actual exits equal to expected exits, and reports macOS network-denial canary enforcement and uninstall preservation of user memory. Those canary/uninstall claims were reconciled to the report, not independently rerun by this reviewer. They do not imply the old package contains subsequent source fixes.

The eleven then-existing review cases were independently run against the external installed package from `/tmp`. Machine-specific directories in the command below are replaced with explicit `/path/to` placeholders; the exact invocation is retained in local tool evidence:

```text
PYTHONPATH=/path/to/isolated/site-packages /path/to/checkout/.venv/bin/python -m pytest -c /dev/null --import-mode=importlib /path/to/checkout/tests/test_review_regressions.py -q
4 failed, 7 passed in 0.20s; exit 1.
```

The four failures were obsolete task/goal projection, critical blocker omission and concurrent observation error handling. Two harmless pytest-cache warnings arose from using `/dev/null` as the configuration location; subsequent external runs should disable `cacheprovider`. Later filename/view regressions were not part of that old-package run.

Final artifact acceptance requires installation outside the checkout, all 15 review regressions against that exact installation, and reconciliation with the immutable-package acceptance/large benchmark. The external local `RELEASE-EVIDENCE` report records those final outcomes; this packaged source-review checkpoint remains immutable and is not a claim that a later artifact is unverified. Earlier benchmark failures must remain documented alongside any later executed replacement result. This reviewer has not read or certified private benchmark reports. Platform support beyond the executed macOS/Python environment is not established.

## Source fingerprints

SHA-256 sampled at **20:23:26 UTC**. The working tree remains mutable; later changes require a new fingerprint and relevant rerun.

| File | SHA-256 |
|---|---|
| `src/session_visualizer/app.py` | `77a58ab7db28ac3850c845724beea8eacf065c9365d96de5e675026707d57571` |
| `src/session_visualizer/store.py` | `0d9a86d315f2665ca3754b8626d219cb604e022fc5fcb3e340aafcb41690ee17` |
| `src/session_visualizer/ingest.py` | `55a117180b38cad14e9bccacfd2f6c8649bd88411bdec50343f3dab36faab92c` |
| `src/session_visualizer/privacy.py` | `249d02777849d1acbdf49ca623a7cfce6f232a4267a2b24caefc8787fae08a17` |
| `src/session_visualizer/context.py` | `8fe60e99fec2c029d39dab1e4d47ae81d0855eefe2d2bc44313f4f8ba537607e` |
| `src/session_visualizer/render.py` | `337d6c33f42c22962cb4d851d842168f4c631cbf7558cce2eb1b99b87e02ef17` |
| `src/session_visualizer/cli.py` | `e16f97b207ba2c8a03077f2ed37afddc0a7bf3b8603bada41aade1d4a0abf88d` |
| `src/session_visualizer/adapters.py` | `563dc9efbd19dc5a905f8090febf46f0ad54c18acc406b04e1b7968f99717ac3` |
| `tests/test_review_regressions.py` | `9e7e7de26e8b960356a6b7b76d35551440b00051702fa2812326a3bcdee42c46` |

## Residual boundaries

No unresolved reproduced runtime defect remains at this source checkpoint. This is bounded review, not proof against every hostile input. Cooperative SQLite progress limits cannot preempt every native operation or blocked filesystem call; page-cache targets are not total-process memory limits. Best-effort redaction cannot recognize all secrets, missing source evidence remains explicitly uncertain, and finite views disclose omissions. Supplied backup content can still contain false facts even when its executable schema is canonical. Exported untrusted instructions may influence an external reader despite escaping and provenance; the application does not grant them execution authority. No required CLI command was found implemented as a silent stub; unsupported provider shapes return diagnostics and partial coverage.

## Subsequent rc2 acceptance review

The preceding results describe earlier checkpoints. A later independent review
reproduced six additional failures against the delivered rc1 wheel, despite its
238 passing tests and 45 passing installation checks. The reviewer recorded the
failures before implementation changes; repair was subsequently authorized.

| Finding | Correction | Regression |
|---|---|---|
| A1: valid append hides an unresolved malformed record | Keep prefix diagnostics until that prefix is rechecked; distinguish incomplete tails | Append, rebuild and actual repair |
| A2: explicit objective ages out after 60 records | Extract objective items and select current intent independently of the recent window | 70 later events, limits 1/1000, cancellation |
| A3: Git-only activity missing from daily view | Include cached timestamped commits independently of transcript groups | Known commit with zero transcript events |
| A4: later items displace an earlier day's blocker | Filter date/worktree before presentation limits; disclose carryover omissions | 1,001 later claims and a prior critical blocker |
| A5: handoff loses dependencies, priorities and rationale | Preserve structured attributes in readable and exported context | Both Markdown and JSON with ample budget |
| A6: intent after the excerpt boundary is lost | Classify full bounded redacted records; retain short source excerpts and full-text identities | Long message, suffix edit, legacy corrections and memory |
| A7: month-wide daily query was absent from the performance gate and exceeded one second | Add the actual daily query to the gate; batch counts and item work, defer evidence hydration, index the date aggregation, and retain equivalent output sanitization | Installed large benchmark with unchanged time budget and 1,000 displayed items; schema 2 backup, upgrade, restore and rollback checks |

Durable regression cases are in `tests/test_acceptance_regressions.py`. The local
release evidence separately records unchanged black-box checks against the new
wheel, the complete suite, fresh installation, upgrade and performance results.
The same reviewer implemented these repairs; a second post-fix human/agent review
is not implied by those reruns.

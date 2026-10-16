# Output contract (`rifja-recovery/1`)

`recover.py brief` prints one document, Markdown by default or compact JSON with
`--format json`. Both come from the same in-memory brief; Markdown is a rendering of the JSON.

## Status

| `status` | Meaning | Exit |
| --- | --- | --- |
| `ok` | Git facts plus selected, fresh history | 0 |
| `ok_degraded` | As `ok`, but coverage is partial, stale (>14 days since the last import) or sources changed | 0 |
| `git_only` | `--git-only`, or the selection matched no history; Git facts only | 0 |
| `failed` | No brief produced; `error.code` and `error.next_action` explain why | 2-6 |

Exit codes: 2 usage (for example no provider selected), 3 prerequisite (git or rifja missing,
contract drift), 4 data/configuration (repo not registered, no sources), 5 transient (busy,
timeout), 6 internal. A failure never carries a partial brief (`handoff: null` in JSON).

## Sections (Markdown headings; JSON keys in parentheses)

1. **Repository now [GIT]** (`git`): path, branch (quoted), full 40-character HEAD, upstream ahead/behind, operation in
   progress (merge/rebase/...), conflicts, tracked and untracked changes (capped), shortstat,
   stash count.
2. **Commits verified in Git [GIT]** (`git.commits`): each commit is marked `before`, `during` or
   `after` the selected sessions' first/last recorded event. This is timing, not attribution: a
   commit "during" a session is not proven to be that agent's work.
3. **Objective [USER]** (`history.objective`, `history.latest_user_instruction`): a user-stated
   objective if the history has an explicit one, otherwise the latest user instruction, labelled as
   not a verified overall objective. Unknown stays "unknown".
4. **Remaining work** (`history.remaining_work`, `remaining_work_agent_phrases`): open `task` /
   `next_action` items with their origin tag. Phrases such as "Remaining:" found in agent messages
   are listed separately and marked heuristic.
5. **Blockers** (`history.blockers`) and **Failing recorded results** (`failing_recorded_results`):
   historical, re-run to confirm. For a recorded command only the test-runner name is shown
   (`pytest`, `npm test`, `go test`, ...), never its arguments (`recorded_test_runner`).
6. **Decisions recorded** (`decisions`), **Declared complete by the user** (`user_declared_complete`).
7. **Agent claims [CLAIM]** (`agent_claims`): success-sounding claims carry `check`:
   `contradicted_by_nearest_result`, `nearest_result_succeeded`, `no_recorded_result` or `none`.
   The check compares the claim with the nearest recorded *test-like* result (known test runner or
   test-looking output) with a parseable time, in the same known session, within 30 minutes.
   Negated, conditional and future-tense claims ("tests don't pass", "once CI is green") are not
   judged. It flags suspicious claims; it does not certify anything.
8. **Coverage and uncertainty [UNCERTAIN]** (`history.coverage`, `warnings`, `selection`).
9. **Next steps** (`next_steps`): at most three, generated from rules over the facts above (resolve
   Git operation, re-run tests, confirm remaining work, inspect uncommitted work), plus a final
   stop-and-report step. They point at quoted items by ref and never contain transcript text.

## Refs

`r:<12 hex>` is the first 12 characters of a Rifja record id. `recover.py explain r:<ref>`
resolves it (Rifja's own `explain` needs the full 64-character id; a prefix returns
`removed_or_unknown`). `explain` prints provider, actor, category, time, status and the source file
name and line, not the text.

## Limits

- Total size: `--max-chars` (default 6000; values outside 2500-24000 are rejected, not clamped).
  Output, including the final newline, never exceeds it. The engine shrinks excerpt and list
  lengths in four steps; then drops whole sections in a fixed order (decisions, declared-done,
  sessions, commits, claims, failing results, blockers, remaining work, objective) and says which;
  the repository facts, warnings, next steps and the trust notice are never dropped. JSON falls back
  to a facts-only document that is still valid JSON, with `truncated: true`.
- Each quoted excerpt is capped (280, 160, 100 or 60 characters depending on the step).
- Omitted counts are reported (`omitted by limits`, `excluded by your source selection`).

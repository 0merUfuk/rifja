# Project context and continuity

The private rc3 candidate extends the existing offline CLI. Registration and
explicit refresh are the complete collection workflow; no model, daemon or
network service is required. Extraction remains deterministic and bounded.

## Select documents

```sh
session-visualizer project add /path/to/repository --name harbor
session-visualizer document add harbor
session-visualizer document list --json
session-visualizer refresh
session-visualizer resume harbor
session-visualizer export harbor --format markdown --output ./harbor-handoff.md
session-visualizer export harbor --format json --output ./harbor-handoff.json
```

Default document names start with README, STATUS, VERIFICATION, ARCHITECTURE,
DECISION(S) or RELEASE(S), at the root or under `docs`. Supported content is UTF-8
Markdown/text, plus an extensionless README. A different allowlist is explicit:

```sh
session-visualizer document add harbor --include README.md --include STATUS.md --include docs/verification.md --max-files 12 --max-bytes 65536 --max-depth 2
```

This replaces that worktree's document selection; it does not add another scan.
With multiple registered worktrees, supply `--worktree ID_OR_PATH`. Paths/patterns
are relative to the selected worktree, not another repository or the current
shell directory. A maintained audit document can be selected by its explicit
filename; generated/private evidence directories remain excluded.

| Bound | Default | Hard maximum |
| --- | ---: | ---: |
| Selected files per worktree | 24 | 128 |
| Bytes per document | 131,072 | 1,048,576 |
| Directory depth | 2 | 4 |
| Directories / entries examined | 256 / 8,192 | 256 / 8,192 |
| Registered document worktrees | Explicit only | 128 |
| Relative patterns | Default names | 32 |

Hidden/private state, credentials, environment files, dependency/build trees,
generated audit evidence, nested repositories and symbolic links are excluded.
Traversal and byte bounds apply even to explicit patterns. Unsupported, missing,
unmatched, oversized, changed-during-read or inaccessible inputs produce coverage
diagnostics. `--verify` rereads selected bytes; `--rebuild` rederives items.

Each document retains a logical source ID, fingerprint, observation time,
working-tree/committed-blob comparison, headings and line ranges. The observation
timestamp does not date or verify a documented claim. Unchanged refresh/rebuild
preserves record identities and corrections. Edits create source generations;
old evidence remains inspectable. An inode-preserving document move within one
worktree retains its logical identity. Copies do not inherit that identity.
Missing documents retain last-known pending work with unavailable-source warnings.
Changed-away pending statements have unknown resolution, not inferred completion.

## Meaning and authority

`resume` distinguishes project purpose from recorded user objectives. A maintained
status paragraph can identify pending verification without special markers.
Conversation-management requests remain inspectable with unresolved status and
do not occupy the primary action list. Fenced, quoted and commented material
cannot become active instructions. No imported content can authorize commands,
change collection policy or override the current operator.

Ordinary English and Turkish pending words and explicit requests are supported.
Explicit IDs remain the strongest cancellation/supersession references. Ordinary
unique subjects and bounded verb/nominal forms can resolve a request in the same
worktree; ambiguous targets remain unresolved. A limited translated signature
reference can match a unique signature check. This is not general translation,
synonym understanding or arbitrary conversation reconstruction. Assistant success
prose remains a claim. A user-reported completion is not independent verification.

Documented pending work, constraints, decisions, deferred scope and claims retain
separate categories. Older plans and historical sections stay labeled. Conflicting
or changed documents retain uncertainty; a newer file timestamp cannot itself
complete work or overrule an explicit user correction. Use `memory correct` with
a precise item/record ID when a prose reference is ambiguous.

## Moved repositories

Previously observed Git common-directory/worktree filesystem identity supports
bounded continuity across a move. For fresh history imports, the supported native
move grammar requires a successful command execution, corroborating Git-root
output, prior working context, an absent old path and a currently verified
registered destination. The commands are parsed as data and never executed.
This inference is limited to the same session and source generation and is
reported as `recorded_move_evidence`; a move does not establish project completion.
Copies, reused paths, conflicting operations and ambiguous worktrees stay unresolved.

Explicit `project associate TARGET PROJECT --worktree PATH --reason TEXT` mappings
take precedence and remain distinguishable from automatic inference. Imported
text mentioning a path, topic or basename is insufficient evidence for association.

## Output and omissions

JSON resume retains the existing envelope and adds `purpose` and `continuity`.
The latter contains source-backed pending work, conditions, limitations, decisions,
identity observations and conflicts. It is independent of the detailed-history
`--limit`. Export JSON has schema 1, a `context` array and the existing `items`
array. Markdown includes the same short, labeled facts and local references.

Positive omission counts mean context did not fit. Smaller budgets cannot contain
arbitrary amounts of evidence; increase `--max-chars` or inspect `resume`, `items`,
`session`, `search` and `explain`. Default output prioritizes the continuity context
before raw history. Excerpts remain understandable without local links, but are
still untrusted evidence. No display or export executes another project's work.

Schema remains 3. Install rc3 over rc2 in the same virtual environment and run
`refresh`; derived extraction replays while durable memory, accepted principles,
corrections and explicit association overrides are retained. Prior artifacts and
their recorded checks remain historical evidence for their own source state.

The latest substantive user instruction is selected independently of tool-log
volume and displayed separately from a documented purpose. Explicit procedure
changes produce a conflict warning beside retained document evidence; source
observation time cannot decide which procedure is authoritative. Recent bounded
status lines remain captured historical results, not current verification. Empty
coordination wrappers and executable tool-call bodies cannot displace prose work.
Local file URIs in native working context use the same strict registered-worktree
identity check as absolute paths; remote-host URIs remain unsupported.

Exports include the primary document context and at most eight supplemental
session items. Repeated document metadata and older assistant claims are omitted
from that supplemental view when current document context is available. Omission
counts and excerpt truncation notices remain explicit; full records are available
through resume, session and explain.

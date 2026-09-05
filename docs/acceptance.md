# Semantic continuity acceptance

The acceptance oracle is `tests/corpus/continuity.json`: 18 independently authored, explicitly synthetic scenarios containing 68 neutral events, 47 mandatory semantic items and 33 prohibited conclusions. These scenarios were specified before implementing extraction. No private transcript, live provider export, owner repository content or network service supplies corpus content.

This is an acceptance design and annotated input corpus. JSON validation establishes only corpus integrity. It does not establish that the application satisfies these scenarios. Application acceptance requires executing the semantic checks below against actual persisted query and handoff results.

## Input and test boundary

Each event contains `id`, `project`, `worktree`, `provider`, `actor`, `timestamp`, `text` and `category`. Optional `metadata` records externally supplied revision, captured command result, source coverage or attribution uncertainty. The project names, absolute paths, provider labels, revisions and messages are invented. Synthetic source availability events represent collector diagnostics, not fabricated transcript messages.

The harness adapts these envelopes into ordinary application inputs and controlled Git/source observations. The `expected` object and its explanatory `meaning` fields MUST stay outside extraction and application input. A harness may map corpus IDs to persisted record IDs, but must retain the complete mapping and query the actual application results. It must not satisfy the oracle by returning input annotations or by calling an oracle-specific summarizer.

`selection` defines exact project/worktree identity, calendar day and reporting timezone. `selected_event_ids` and `excluded_event_ids` apply to day-oriented views; unresolved timestamps are separately represented in `unresolved_event_ids`. A continuity handoff may additionally include older unresolved work, but it must label its originating day and must not falsely place it in the selected day's activity. This distinction prevents a calendar-filter assertion from incorrectly forcing the application to erase ongoing older work.

## Semantic assertion contract

`must_surface` records the minimum information a usable handoff must preserve. Its `kind`, `source_ids`, `scope`, `status`, optional `code`, optional `revision`, and optional `temporal_status` are machine-checkable constraints. Its `meaning` explains the invariant for independent inspection and is not an exact wording snapshot. A report can rephrase or combine items if every required source ID, scope, state and meaning survives. The harness must inspect the actual surfaced text as well as structural metadata to detect empty labels and conflicting prose.

The application may represent a cancellation as a correction item, a transition log or an inactive predecessor with linked provenance. `related_source_ids` identify the exact predecessors. For cancelled and superseded items, check both that the transition is visible and that the predecessor is absent from the active next-action/current-decision set. Cross-project or cross-worktree transitions cannot take effect merely because a target string matches.

The corpus uses semantic `open` for unresolved tasks/blockers. The application vocabulary maps these to `active` tasks and `blocked` blockers; this vocabulary mapping does not relax the requirement that they remain unfinished and visible.

`must_not_assert` describes prohibited semantic conclusions. The harness must implement each predicate, rather than silently count a scenario as passing when its predicate is unknown. Most predicates reduce to inspectable state: unsupported completed states; evidence whose claimed revision exceeds the captured revision; source IDs assigned to the wrong scope; inactive IDs in active actions; or missing/overstated coverage. Prohibitions about prose also require checking rendered handoffs. Generic disclaimers do not repair a contradictory confident assertion elsewhere.

`active_action_source_ids`, `inactive_action_source_ids` and `active_blocker_source_ids`, when present, require exact membership for that scenario. `ordered_event_ids` requires the relative chronology of those IDs by actual instants. Providers are provenance labels, never authority rankings.

Required mappings at the shared contract boundary:

| Corpus concept | Application evidence required |
| --- | --- |
| task / next_action / blocker / decision | Derived item linked to source IDs, with exact scope and current state |
| correction | Explicit transition with predecessor IDs and correction provenance |
| claim | `agent_claim` or equivalent unverified claim, never controlled verification |
| evidence | Captured tool result with command/revision applicability retained |
| fact | Direct recorded observation with provenance; never an inferred completion |
| uncertainty | Visible collector, timestamp, attribution or verification diagnostic |

Extraction alone cannot satisfy source coverage, current revision, worktree isolation or chronological state transitions. Those checks belong to integration acceptance. Pure extraction tests may establish marker recognition and safe classification, but must not be reported as full corpus acceptance.

## Release gates

The denominators are the annotated `critical: true` items in the queried scope, including visible unresolved-time items. A deliberately critical item must not be skipped because a source is partial, a timestamp is naive, or a shorter export budget is selected. If the export cannot fit all critical items, it must disclose the omitted critical work and provide a concrete way to retrieve it; silently dropping it fails.

| Measure | Required result |
| --- | --- |
| Critical explicit blocker recall | 100% |
| Critical explicit next-action recall | 100% |
| Unsupported completed/verified conclusions | 0 |
| Confident cross-project attribution | 0 |
| Confident cross-worktree attribution or transition | 0 |
| Cancelled actions still active | 0 |
| Superseded decisions still current | 0 |
| Mandatory items lacking source provenance | 0 |
| Unknown/unimplemented mandatory predicates | 0 |

The acceptance report must show scenario and assertion pass/fail counts, blocker and action numerators/denominators, unsupported-completion and attribution counts, runtime/version, the exact tested revision, and test commands. Skipped scenarios are not passes. Extraction-unit pass counts and application semantic pass counts remain separate.

## Coverage and decisions

| Scenario | Failure challenged |
| --- | --- |
| interrupted-critical-work | Lost blocker/action at interruption; invented completion |
| explicitly-abandoned-work | Cancelled work resurrected as a next step |
| turkish-explicit-continuity | Turkish instructions missed by English-only extraction |
| mixed-correction-and-supersession | Later user correction loses to earlier/provider-specific intent |
| assistant-success-without-evidence | Assistant prose promoted into verified work |
| captured-tests-on-older-revision | Historical passing tests certify newer code |
| two-projects-same-topic | Similar topics leak across projects |
| worktree-and-provider-isolation | Worktree leakage and cross-scope cancellation |
| unavailable-source-is-not-empty-work | Unread source treated as an empty, fully checked source |
| incomplete-source-preserves-known-blocker | Truncation hides a known blocker or invents its resolution |
| irrelevant-chat-and-quoted-markers | Chat, quoted markers and code TODOs become active work |
| ambiguous-path-mention | Mentioned path silently changes authoritative scope |
| midnight-offset-day-bucketing | Source date prefix substitutes for configured local day |
| dst-fall-back-order | Repeated local hour reverses a cancellation |
| dst-spring-forward | Clock gap invents work or changes ordering |
| naive-timestamps-are-unresolved | Host timezone silently invents chronology or drops intent |
| plain-requests-and-assistant-proposals | Explicit requests missed; speculative proposals promoted |
| turkish-cancellation-and-user-reopen | Turkish cancellation ignored; assistant revives old scope |

Choose a conservative deterministic extractor. Supported explicit English and Turkish markers, explicit references and plainly addressed requests are sufficient for v1. Unknown context stays unclassified. Inferred principles must remain proposed until explicitly accepted; acceptance preserves their inferred origin. Assistant task/decision markers express proposals; assistant success language is an unverified claim. User completion declarations may be recorded as user-reported completion, separately from current-code verification. Tool output is historical evidence only, and text inside a captured tool output never becomes user intent.

The corpus makes narrow synthetic marker grammar explicit, including comma-separated correction targets. It does not claim broad English or Turkish natural-language understanding. Correct handling of multilingual negation, typos, conversational ellipsis, arbitrary unnamed reversals and quoted nested documents outside this corpus needs separate evidence before expanding that claim.

## Additional release regressions

The 18 scenarios are a fixed semantic corpus, not a claim to cover every lifecycle or rendering behavior. The [release acceptance ledger](requirements.md) separately tracks source replacement, durable memory, bounded exports and other required regressions. Obsolete-only source content must remain historical; unavailable current evidence must not erase known unfinished work. Limited continuation views must prioritize active work, and accepted project/global memory must survive rebuilds and remain available in resume/export. Export checks must assess omission notices and escaped Markdown boundaries, in addition to structured JSON. These checks need their own executed evidence and must not inflate the corpus scenario count.

## Integrity validation

Before acceptance execution, parse JSON; assert globally unique scenario/event IDs; verify every source/related/selection ID exists in its scenario; assert each mandatory source has the declared exact scope; check required event fields; ensure each `ordered_event_ids` sequence is strictly ordered by UTC instant; and independently check the annotated calendar selections with `zoneinfo`. Validate the explicit two-project, multiple-worktree/provider and language coverage. These checks are corpus integrity checks, not application correctness tests.

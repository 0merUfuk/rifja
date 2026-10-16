# Rifja CLI contract used by the skill

Verified against `rifja 0.4.2` (Homebrew build and this checkout, both with JSON `schema_version`
1) on 2026-10-16. `tests/test_recovery_rifja_contract.py` fails if any field below changes.

## Commands the script runs (and nothing else)

| Command | Used for | Notes verified here |
| --- | --- | --- |
| `rifja --version` | Version gate (warns below 0.4.2) | prints `0.4.2` |
| `rifja --json project list` | Map the repository (by Git common directory) to a registered project | `projects[].name`, `projects[].common_dir` |
| `rifja --json project show <name>` | Sessions known for the project (used by `recover.py sources`) | `sessions[].id/provider/last_event/records` |
| `rifja --json source list` | Which providers are registered | `configured[].provider/path` |
| `rifja --json resume <project> --limit N [--cached]` | The history payload | See below. Not strictly read-only: without `--cached` it stores refreshed Git observations in Rifja's own state |
| `rifja --json explain <full 64-hex record id>` | Provider/session for a record; provenance for `recover.py explain` | A 12-character prefix returns `{"status": "removed_or_unknown"}`, so the script resolves prefixes itself |

Global flags `--json` and `--home PATH` are passed before the subcommand. `RIFJA_HOME` is honoured
by Rifja itself. Exit codes seen: 0 ok, 2 error (JSON error envelope `{"error": {"code",
"hints"}}` on stdout; `project_not_found` is the common one), 3 partial refresh (not returned by the
commands above), 4 busy. The script never runs `init`, `setup`, `project add`, `source add`,
`refresh`, `forget`, `retention`, `memory`, `remember`, `backup`, `restore`, `ui` or `mcp`.

## `resume` fields consumed

| Path | Used as |
| --- | --- |
| `items.items[]` with `kind`, `category`, `status`, `actor`, `text`, `record_id`, `session_id`, `provider`, `event_time`, `evidence.metadata.{exit_status,command}`, `evidence.locations[].path` | Pool of derived evidence: `objective`, `task`, `next_action`, `blocker`, `decision` (open work); `claim` with `agent_claim` (agent claims) and `recorded_tool_result` (tool results with exit status) |
| `items.omitted` | "bounded set of items" warning |
| `objective` (`text`, `record_ids`) | User-stated objective (category `user_intent`) |
| `latest_user_instruction` (`text`, `record_id`, `event_time`) | Latest user instruction; has no `provider`, so provider/session come from `explain` |
| `recent_recorded_results[]` (`text`, `exit_status`, `record_ids`, `event_time`) | Recorded results; no `session_id`, de-duplicated against `items` |
| `sessions[]` (`id`, `provider`, `last_event`, `records`) | Session list for coverage |
| `coverage` (`status`, `last_refresh.ended_at`, `source_counts[]`, `scope_changed_since_refresh`, `unassociated_records`, `unknown_event_times`, `scope`) | Staleness and degradation warnings |

Anything else in the payload (Git observations, documents, uncertainty details, principles, memory)
is ignored: the script observes Git itself and does not echo Rifja's free text beyond the fields
above.

## Semantics worth knowing

- Rifja derives `task`, `next_action`, `blocker` and `decision` items only from explicit markers
  (`GOAL:`, `TASK:`, `NEXT:`, `BLOCKER:`, `DECISION:`, ...) in user or agent messages; ordinary
  prose such as "remaining: add backoff" is not extracted. The script lists such phrases separately,
  marked heuristic, and never promotes them to tasks.
- Agent-authored `next_action`/`decision` items are `proposed`, not `active`; only user-authored
  ones are `active`.
- `resume` has no provider filter (`search` does). Provider selection therefore happens in the
  script, using `items[].provider` and, for the two payload fields without one, `explain`.
- Rifja redacts secrets before storing and escapes Markdown in its text output; it does not
  neutralize instruction-like sentences, hidden Unicode tag characters survive in stored text, and
  the CLI prints them verbatim. Those are the gaps the script's sanitizer covers.
- Rifja requires Python 3.14 (the Homebrew formula provides it). The bundled script does not.

## Provider data contracts (via Rifja)

| Provider | Native source | Fixture shapes used here |
| --- | --- | --- |
| Claude Code | `projects/<project>/<session>.jsonl` | `type: user/assistant`, `message.content` text/`tool_use`/`tool_result`, `toolUseResult.exitCode` (modelled on Rifja's `tests/fixtures/providers/claude.jsonl`) |
| Codex | `sessions/**/*.jsonl` rollouts | `session_meta`, `response_item` (message, function_call), `event_msg item_completed` with `type: command_execution`, `exit_code`, `aggregated_output` (modelled on `codex.jsonl`) |
| Hermes | `state.db` (schema 26) | `sessions` and `messages` tables as in Rifja's adapter tests |

Details and the producers' own caveats: [docs/providers.md](../providers.md).

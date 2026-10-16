# Source and privacy assessment

Scope: the `session-recovery` skill (script, instructions, packaging) at version 0.1.0 and what it
does with session histories and repositories. Rifja's own storage model is covered by
[the Rifja threat model](../rifja-threat-model.md); this document covers what the skill adds.

## 1. What data the skill touches

| Data | Touched? | How |
| --- | --- | --- |
| Raw agent transcripts (`~/.claude/projects`, `~/.codex/sessions`, Hermes `state.db`) | No, by the script. The skill tells the agent not to open them | Only through Rifja's JSON output (`resume`, `explain`, `project`, `source list`) |
| Rifja's SQLite state | No (never opened) | Rifja process only |
| The repository | Read-only Git queries: `status`, `log`, `diff --shortstat`, `rev-parse`, `rev-list` | Fixed argument lists, no shell |
| Credentials, `.env`, auth files, keychains | No | Not read; credential-looking strings in history are redacted |
| Network | None | The script has no network code; Rifja is offline |
| Writes | None by the script; `rifja resume` updates Rifja's own cached Git observations (use `--cached` to avoid it). With no Rifja state the script refuses instead of letting Rifja create it | Tests hash the repo and the Claude source root before/after; `TestNeverCreatesRifjaState` proves `doctor`, `sources`, `brief` and `explain` create nothing; the Codex and Hermes source roots are not hashed |

## 2. What leaves the machine

The skill itself sends nothing anywhere. The **brief enters the host agent's context** and is
therefore sent to that agent's model provider (Anthropic, OpenAI, ...) like any other tool output.
That is the privacy-relevant fact for users: `--providers` selects which histories can reach the
model, the redaction layer reduces what a selected history can leak, and nothing outside the
selection is read. Users who cannot send session excerpts to a model provider should not use the
history half; `--git-only` sends only Git facts.

## 3. Controls and their evidence

| Control | Mechanism | Evidence |
| --- | --- | --- |
| Explicit source selection | `--providers` or `--all-registered` is mandatory; absent, exit 2 before any history is read | `test_no_selection_is_refused_before_any_history_is_read`; provider and `--session` filters tested on a three-provider fixture, with exclusion counts reported |
| Secret redaction (second pass after Rifja's) | GitHub/OpenAI-style/AWS/Google/Stripe/Slack/GitLab/npm/PyPI tokens, JWTs, Basic/Bearer headers, PGP/RSA key blocks, URL credentials, `--password` flags, `curl -u`, webhook URLs, `*_TOKEN=`/`password:` assignments, long mixed-case blobs, secrets split by invisible characters | `TestSanitizer.test_secrets_never_survive` (10 shapes), `test_more_secret_shapes` (13), `test_documented_token_families` (5); the hostile end-to-end test greps the output for each planted secret |
| PII | e-mail addresses to `[email]`; `/Users/<name>`, `/home/<name>` to `~` | `test_pii_and_home_paths` |
| Invisible-text smuggling | Zero-width, bidi override/isolate, BOM, Unicode tag characters, ANSI, control characters stripped | `test_invisible_ansi_and_bidi_are_removed`; hostile fixture plants a tag-character payload |
| Injection resistance | Quoted literals only; instruction-like sentences withheld; markup defanged; next steps rule-generated; agent rules in `SKILL.md` | `test_instruction_like_sentences_are_withheld` (10 attack shapes), end-to-end `TestHostileHistory`, live-agent injection scenario in [evaluation](evaluation.md) |
| Hostile repository | fsmonitor, hooks, external diff, pager, signature programs and every content filter (also via `include.path`) neutralized for the script's own Git calls; risky settings reported by fixed label only; no optional locks; inherited `GIT_*` ignored; no `safe.directory` override | Canary-file tests for fsmonitor, a `.gitattributes` content filter, an included filter and a signature program: none ran. **Live agents:** 6/6 `cli`/`paste` runs executed the hostile fsmonitor through plain `git status`; 0/3 `skill` runs did ([evaluation](evaluation.md)) |
| Bounded output | `--max-chars` 2500-24000 enforced (out-of-range values rejected) for Markdown and for JSON (valid JSON even when truncated) | Parametrized limit tests on a hostile 10 KB-field history |
| Failure honesty | Distinct exit codes; failures never carry a partial brief | `TestFailureModes` (stubbed misbehaving Rifja, missing Rifja, unregistered repo, no sources, timeout, busy) |
| Package hygiene | Validator rejects home paths, tokens, e-mails, invisible and variation-selector characters, binaries, symlinks, dotfiles, links leaving the skill, a missing MIT license; builds only into empty or previous-build directories; allow-listed file names; no hooks, MCP servers or binaries | `tools/recovery_bundle.py check`; `TestDistributionContents`, `TestValidatorHardening`, `TestRemainingSpecChecks`; `test_new_files_pass_the_release_audit_patterns` |
| No Rifja side effects | Refuses (`rifja_not_initialized`) instead of letting any `rifja` call create state; 16 MB output cap and an overall deadline per subprocess | `TestNeverCreatesRifjaState`, `TestHostileRifjaOutput` |

## 4. Data used to build and test the product

All histories are synthetic and authored in `tests/recovery_fixtures.py`: invented paths under a
temporary directory, pinned timestamps, invented tokens that match secret *shapes* but are not live
credentials, disposable Git repositories. Codex and Claude record shapes follow Rifja's own
source-pinned fixtures. No personal session history, Claude/Codex memory, or machine configuration
was read, copied or packaged. The live-agent evaluation ran real Claude Code (Sonnet and Haiku) against those
synthetic repositories; one earlier Codex smoke run did the same. The models received only the
synthetic material and the task.

Two housekeeping notes from the evaluation, recorded because they touch user state:

- Claude Code creates an empty per-working-directory folder under `~/.claude/projects` even with
  `--no-session-persistence`; the evaluation driver removes those folders (named `*claude-501-eval*`)
  after each run, only if they contain no `.jsonl`.
- The one Codex smoke run used `--ephemeral --ignore-user-config --ignore-rules` (no Codex session
  file). Codex still read the owner's global `AGENTS.md` instructions, which the flags do not cover;
  that file's content is not reproduced anywhere in this repository. The skill was supplied as a
  repo-scoped skill inside the disposable repository and excluded from Git via `.git/info/exclude`.
- The evaluation runs passed `--no-session-persistence`; evaluation artefacts contain only synthetic
  material, with machine paths replaced by `<HOME>`, `<WORK>`, `<REPO>`, `<TMP>` placeholders.

## 5. Residual risks (not eliminated)

1. **Pattern-based filters are incomplete.** A novel secret format or a paraphrased instruction can
   pass. Defence in depth (quoting, rule-generated next steps, agent-side rules) limits the impact;
   it does not remove it. The model is the last line of defence.
2. **Model-provider exposure.** Selected, redacted history is still sent to the model provider.
3. **Stale or wrong history.** A brief can describe work that was later reverted; claim checks are
   timing heuristics. The brief says so and the skill requires fresh verification before acting.
4. **Git-state disclosure.** File names, branch names and commit subjects are included (after
   neutralizing). They can themselves be sensitive.
5. **Rifja dependency.** Rifja's storage and adapters are outside this package; its limits (raw
   producer formats may change, redaction is best effort) apply.
6. **No genuine-data validation.** Real transcripts have shapes and sizes the synthetic fixtures do
   not cover; a genuine-data pilot under the owner's control is a remaining step.

## 6. Verdict

For synthetic and disposable data the design meets the stated requirements (explicit source
selection, private-data filtering, injection resistance, stable limits, clear failure handling) with
the evidence above. It should not be described as safe against a determined adversary who controls a
session history, nor validated on genuine histories.

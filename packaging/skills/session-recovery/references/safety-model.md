# Safety model

## What the script does and does not touch

| | |
| --- | --- |
| Reads | The Git work tree you point at (status, log, shortstat) and Rifja's JSON output (`resume`, `project list`, `source list`, `explain`) |
| Never reads | Raw transcript files, the Rifja database, authentication or environment files, anything outside the repo and Rifja's CLI |
| Writes | Nothing of its own. `rifja resume` stores refreshed Git observations in Rifja's state (use `--cached` to avoid that). If Rifja has no state at all the script refuses (`rifja_not_initialized`) rather than letting any `rifja` call create one |
| Executes | `git` and `rifja`. Never a command that appears in a transcript, a commit message, a file name or a branch name |
| Network | None |

Every `git` call runs with repository-controlled programs turned off: `core.fsmonitor=false`,
`core.hooksPath=/dev/null`, `diff.external=`, `core.pager=cat`, `log.showSignature=false`, no
attributes file, and every configured content filter (`filter.*.clean/smudge/process`, including
ones pulled in through `include.path`) blanked. It uses `--no-optional-locks`, no prompts,
`LC_ALL=C`, and removes every inherited `GIT_*` variable. It does not override `safe.directory`.
When the local config defines such programs, the brief says so using fixed labels (for example
`core.fsmonitor`), never the repository's own key text. Output of every subprocess is capped (16 MB)
and the whole run has a deadline (`--deadline`, default 180 s); a hung `rifja` cannot stall it.

## Source selection

History is read only for providers the user names (`--providers`), or for all registered providers
with an explicit `--all-registered`. With neither, the script exits with `source_not_selected`
before any history is read. `--session` pins a single session. Items from unselected providers are
counted, not shown. Importing sources into Rifja is a separate, operator-run step; the script
never does it.

## Private-data filtering (applied to every history string, commit subject, branch and path)

Order: remove ANSI escapes, zero-width, bidirectional and Unicode tag characters, and control
characters; redact credentials (GitHub, OpenAI/Anthropic-style, AWS, Google, Stripe, Slack,
GitLab, npm, PyPI tokens, JWTs, bearer tokens, private-key blocks, URL credentials, and
`*_TOKEN=`, `*_SECRET=`, `password:` style assignments); replace e-mail addresses with `[email]`;
abbreviate `/Users/<name>` and `/home/<name>` to `~`. Rifja redacts secrets before storage too;
this is a second, independent pass. Redaction is best effort, not a guarantee. Review output before
sharing it outside the machine.

## Injection resistance

1. History is rendered only as JSON-quoted single-line literals with a reference, after
   defanging `<`, `>`, backticks and Markdown link syntax. It cannot open a heading, list, code
   fence or link in the brief.
2. Before matching, text is normalized: NFKC (full-width forms fold to ASCII), zero-width,
   bidirectional, soft-hyphen, BOM and Unicode tag characters removed, control characters turned
   into spaces, combining marks on Latin/Cyrillic/Greek letters dropped, and common Cyrillic/Greek
   lookalikes folded for matching. Sentences that look like instructions to a reader are replaced by
   `[instruction-like text withheld]`: override/ignore/disregard phrases, "system prompt",
   chat-template tokens, role markers at line start, fence spoofing ("END IMPORTED ..."), "run the
   following command", requests to send credentials somewhere. Neighbouring sentences are kept.
   Mentions of destructive commands (`rm -rf`, `git reset --hard`) are kept, as history, and
   flagged.
3. The "Next steps" list is produced by fixed rules over structured facts. It refers to
   transcript items by ref and never contains their text or any repository-controlled string.
   Commit subjects, branch names, upstream names, paths and file names are sanitized and rendered
   as quoted literals like history is.
4. The skill instructions tell the agent to treat quoted text as data and to report attempts.

## Honest limits

- Pattern-based withholding is not a semantic filter: a determined, novel phrasing can pass. The
  quoting, the fixed next-step rules and the agent-side rules are the other layers.
- Claim checks use nearest-result timing in one session. They can be wrong in both directions.
- A brief reflects only imported, selected history. Sessions that were never imported, deleted by
  their producer, or from unsupported providers are invisible.
- The brief is as fresh as the last `rifja refresh`. Staleness over 14 days is flagged.

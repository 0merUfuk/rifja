# Session Visualizer

Session Visualizer is a local CLI for resuming engineering work across agent sessions, projects and Git worktrees. It imports explicitly selected Codex, Claude Code and Hermes sources, preserves evidence references, and keeps user instructions, agent claims, recorded results and current Git observations separate.

Version **0.1.0rc3** is a private local release candidate. Runtime collection and queries need no network, model service or paid account. No public redistribution license is granted.

## Install the local release

Requirements: Python 3.14 or newer, Git, and Python's SQLite with FTS5. Python 3.14 supplies the standard-library Zstandard decoder used for compressed Codex transcripts. Run these commands from the directory containing the supplied `dist` folder:

```sh
python3.14 -m venv "$HOME/.local/venvs/session-visualizer"
"$HOME/.local/venvs/session-visualizer/bin/python" -m pip install --no-index --no-deps "./dist/session_visualizer-0.1.0rc3-py3-none-any.whl"
export PATH="$HOME/.local/venvs/session-visualizer/bin:$PATH"
session-visualizer --version
```

The final command should print `0.1.0rc3`. Installation uses the local wheel; it does not fetch dependencies. Platform compatibility beyond recorded release verification should be treated as unverified.

## Start with one project

Replace the example repository and transcript paths with directories you intend to import. Discovery only shows candidate locations; it does not import them.

```sh
session-visualizer setup --timezone Europe/Istanbul
session-visualizer project add "/path/to/project" --name harbor
session-visualizer document add harbor
session-visualizer source discover
session-visualizer source add codex "/path/to/codex/sessions"
session-visualizer refresh
session-visualizer source list
session-visualizer daily --project harbor
session-visualizer resume harbor
```

`document add` opts one registered worktree into bounded README, status, verification and architecture documents. `resume` combines purpose, current Git state, pending work and its conditions, decisions, accepted memory and uncertainty. Documented purpose is separate from a current user objective. Recorded results and document claims do not certify current code. Use `resume harbor --cached` for stored Git observations; documents change only through explicit `refresh`.

```sh
session-visualizer search "parser fixture" --project harbor --json
session-visualizer daily 2026-09-01 --to 2026-09-05 --project harbor
session-visualizer export harbor --format markdown --output "./harbor-handoff.md"
```

Output files must not already exist. Exports include accepted project/global memory, keep imported excerpts labeled as untrusted context, and disclose omissions within the chosen size limit. Inspect those notices before passing context to another agent.

## Operational guide

- [Usage, corrections, principles, backup and retention](docs/usage.md)
- [Supported provider formats and known gaps](docs/providers.md)
- [Semantic acceptance corpus and release gates](docs/acceptance.md)
- [Design and privacy boundaries](docs/design.md)
- [Project documents, identity and continuity limits](docs/project-context.md)
- [Release changes and upgrade boundaries](docs/releases.md)
- [Development checks and private release procedure](docs/development.md)

`session-visualizer --help` and each subcommand's `--help` list the available options. `--json` and `--home PATH` work before or after subcommands. Normal successful JSON responses include `schema_version`, `command` and `data`; errors are written to stderr.

On macOS, state defaults to `~/Library/Application Support/SessionVisualizer`. On other supported Unix environments it defaults to `$XDG_DATA_HOME/session-visualizer`, or `~/.local/share/session-visualizer` when that variable is unset. Set `SESSION_VISUALIZER_HOME` or pass `--home PATH` to use a separate state directory.

Source transcripts and repository contents are read-only inputs. The application writes its own local state, explicit exports and backups. Secret redaction is best effort, not encryption or a guarantee that every sensitive value is removed. Review exports before sharing them. Deleting the program does not delete its state, backups, exports or producer transcripts.

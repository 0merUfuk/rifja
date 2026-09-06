# Session Visualizer

Session Visualizer is a local CLI for resuming engineering work across agent sessions, projects and Git worktrees. It imports explicitly selected Codex, Claude Code and Hermes sources, preserves evidence references, and keeps user instructions, agent claims, recorded results and current Git observations separate.

Version **0.1.0rc4** is a private local release candidate. Runtime collection and queries need no network, model service or paid account. No public redistribution license is granted.

## Install with Homebrew

With Homebrew installed, run this from the supplied release directory:

```sh
./install.sh
session-visualizer --version
```

The installer uses a private local Homebrew tap, installs the checked release
wheel and lets Homebrew manage Python 3.14, Git and the application environment.
The command is available on Homebrew's PATH; no activation or manual Python
setup is needed. The first installation can download missing Homebrew
dependencies. Application collection and queries remain offline.

The supplied Homebrew archive includes everything specific to this application.
This maintainer checkout also contains its release wheel under `dist`. A source
checkout without release artifacts requires `make dist` before installation.

```sh
brew test session-visualizer/local/session-visualizer
brew uninstall session-visualizer
```

Run `./install.sh` from a newer supplied release to upgrade. Existing application
state and memory are preserved. `./install.sh --reinstall` repairs the current
installation. The archive is copied into the local tap, so the installation does
not depend on keeping the extracted release directory or this checkout.

The public `0merUfuk/thematrix` formula is not published yet. Do not run a public
install command until a release and its formula have actually been published.
See [Homebrew delivery and release procedure](docs/homebrew.md).

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

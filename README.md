# Session Visualizer

Session Visualizer is a local CLI for resuming engineering work across agent sessions, projects and Git worktrees. It imports explicitly selected Codex, Claude Code and Hermes sources, preserves evidence references, and keeps user instructions, agent claims, recorded results and current Git observations separate.

[![CI](https://github.com/0merUfuk/session-visualizer/actions/workflows/ci.yml/badge.svg)](https://github.com/0merUfuk/session-visualizer/actions/workflows/ci.yml)

Version **0.1.1**. Licensed under [MIT](LICENSE). Runtime collection and queries
need no network, model service or paid account.

## Install

With [Homebrew](https://brew.sh) installed and on PATH:

```sh
brew install 0merUfuk/thematrix/session-visualizer
session-visualizer --version
```

Homebrew manages Python 3.14, Git and the private application environment. You
use one command; no Python installation commands or environment activation are
required. Initial installation can download Homebrew dependencies.

```sh
brew update
brew upgrade session-visualizer
brew uninstall --force session-visualizer
```

Uninstall preserves application state, exports and backups. To move from an older
private `session-visualizer/local` installation, remove all its installed versions with `brew uninstall --force session-visualizer/local/session-visualizer` first,
then run the public install command above; your state stays in place.

[GitHub Releases](https://github.com/0merUfuk/session-visualizer/releases) also
provide a wheel, source archive, checksums and an installer bundle. Extract the
Homebrew bundle and run `./install.sh` if you need a specific release through a
local tap. Do not install both tap variants at once. A source checkout requires
`make dist` before using this local installer.

The release checks target macOS 15 on Apple Silicon and Intel, and Ubuntu 24.04
x86-64 with Homebrew. Consult the linked CI run for executed results. Windows is
unsupported because the implementation uses POSIX locking and file traversal.
Other platforms and Linux arm64 are not release-certified. This is a Homebrew-
managed Python CLI; it is not a self-contained native executable.
See [release verification and Homebrew delivery](docs/homebrew.md).

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

## Documentation

- [Usage, corrections, principles, backup and retention](docs/usage.md)
- [Supported provider formats and known gaps](docs/providers.md)
- [Semantic acceptance corpus and release gates](docs/acceptance.md)
- [Design and privacy boundaries](docs/design.md)
- [Project documents, identity and continuity limits](docs/project-context.md)
- [Release changes and upgrade boundaries](docs/releases.md)
- [Development checks and release procedure](docs/development.md)
- [Contributing](CONTRIBUTING.md) and [security reports](SECURITY.md)

`session-visualizer --help` and each subcommand's `--help` list the available options. `--json` and `--home PATH` work before or after subcommands. Normal successful JSON responses include `schema_version`, `command` and `data`; errors are written to stderr.

On macOS, state defaults to `~/Library/Application Support/SessionVisualizer`. On other supported Unix environments it defaults to `$XDG_DATA_HOME/session-visualizer`, or `~/.local/share/session-visualizer` when that variable is unset. Set `SESSION_VISUALIZER_HOME` or pass `--home PATH` to use a separate state directory.

Source transcripts and repository contents are read-only inputs. The application writes its own local state, explicit exports and backups. Secret redaction is best effort, not encryption or a guarantee that every sensitive value is removed. Review exports before sharing them. Deleting the program does not delete its state, backups, exports or producer transcripts.

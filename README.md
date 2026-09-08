# Rifja

**Recover the context. Continue the work.**

Named from Icelandic *rifja upp*: recall and review what you know. See the [naming decision and migration contract](docs/identity.md).

Rifja is a local CLI for resuming engineering work across agent sessions, projects and Git worktrees. It imports explicitly selected Codex, Claude Code and Hermes sources, preserves evidence references, and keeps user instructions, agent claims, recorded results and current Git observations separate.

[![CI](https://github.com/0merUfuk/rifja/actions/workflows/ci.yml/badge.svg)](https://github.com/0merUfuk/rifja/actions/workflows/ci.yml)

Version **0.3.0**. Licensed under [MIT](LICENSE). Runtime collection and queries
need no network, model service or paid account.

## Install

With [Homebrew](https://brew.sh) installed and on PATH:

```sh
brew install 0merUfuk/thematrix/rifja
rifja --version
```

Homebrew manages Python 3.14, Git and the private application environment. You
use one command; no Python installation commands or environment activation are
required. Initial installation can download Homebrew dependencies.

```sh
brew update
brew upgrade 0merUfuk/thematrix/rifja
brew uninstall --force 0merUfuk/thematrix/rifja
```

Uninstall preserves application state, exports and backups. Existing public
`session-visualizer` installations migrate through Homebrew’s formula rename on
`brew update` followed by `brew upgrade 0merUfuk/thematrix/rifja`.
The former command remains an alias. Private local-tap users follow the
[migration instructions](docs/identity.md#upgrading-existing-installations).

[GitHub Releases](https://github.com/0merUfuk/rifja/releases) also
provide a wheel, source archive, checksums and an installer bundle. Extract the
Homebrew bundle and run `./install.sh` if you need a specific release through a
local tap. Do not install both tap variants at once. A source checkout requires
`make dist` before using this local installer.

The release checks target macOS 15 on Apple Silicon and Intel, and Ubuntu 24.04
x86-64 with Homebrew. Consult the linked CI run for executed results. Windows is
unsupported because the implementation uses POSIX locking and file traversal.
Other platforms and Linux arm64 are not release-certified. This is a Homebrew-
managed Python CLI; it is not a self-contained native executable.
Intel macOS passed the release checks, but Homebrew no longer supports that
platform upstream; dependency compilation may make initial installation slow.
See [release verification and Homebrew delivery](docs/homebrew.md).

## Start with one project

The guided path is `rifja init`: in an interactive terminal it proposes each
step and asks before every state change (timezone detection, discovered
sources, project directories, first refresh). Without a terminal it prints the
plan and applies nothing. A full walkthrough with verbatim session output is
in [the first-session guide](docs/getting-started.md).

Replace the example repository and transcript paths with directories you intend to import. Discovery only shows candidate locations; it does not import them.

```sh
rifja init
rifja document add harbor        # separate opt-in for project documents
rifja daily --project harbor
rifja resume harbor
```

`init` already registered your project and sources; the remaining commands are
idempotent, so rerunning the manual flow is an equivalent alternative:

```sh
rifja setup --timezone Europe/Istanbul
rifja project add "/path/to/project" --name harbor
rifja source discover
rifja source add codex "/path/to/codex/sessions"
rifja refresh
rifja source list
```

See [getting started](docs/getting-started.md#2-guided-setup--rifja-init) for
the exact split between the wizard and the primitives.

`document add` opts one registered worktree into bounded README, status, verification and architecture documents. `resume` combines purpose, current Git state, pending work and its conditions, decisions, accepted memory and uncertainty. Documented purpose is separate from a current user objective. Recorded results and document claims do not certify current code. Use `resume harbor --cached` for stored Git observations; documents change only through explicit `refresh`.

```sh
rifja search "parser fixture" --project harbor --json
rifja daily 2026-09-01 --to 2026-09-05 --project harbor
rifja export harbor --format markdown --output "./harbor-handoff.md"
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

`rifja --help` and each subcommand's `--help` list the available options. `--json` and `--home PATH` work before or after subcommands. Normal successful JSON responses include `schema_version`, `command` and `data`; errors are written to stderr.

On macOS, state defaults to `~/Library/Application Support/Rifja`. On other supported Unix environments it defaults to `$XDG_DATA_HOME/rifja`, or `~/.local/share/rifja` when that variable is unset. Set `RIFJA_HOME` or pass `--home PATH` to use a separate state directory. Existing legacy state is reused in place and `SESSION_VISUALIZER_HOME` remains supported. If both default directories exist, select one explicitly; Rifja will not silently merge or discard either. See the [precedence rules](docs/identity.md#state-and-command-compatibility).

Source transcripts and repository contents are read-only inputs. The application writes its own local state, explicit exports and backups. Secret redaction is best effort, not encryption or a guarantee that every sensitive value is removed. Review exports before sharing them. Deleting the program does not delete its state, backups, exports or producer transcripts.

# Installation and troubleshooting

## Prerequisites (verified against rifja 0.4.2)

- `git` on PATH.
- Python 3.9+ for the bundled script (system Python on macOS is enough). Rifja itself needs
  Python 3.14, which Homebrew provides.
- The `rifja` CLI 0.4.2 or newer: `brew install 0merUfuk/rifja/rifja`, then `rifja --version`.
  Releases are also available at https://github.com/0merUfuk/rifja/releases.
- macOS 15 and Ubuntu 24.04 (with Homebrew) are Rifja's release-checked platforms. Windows is
  unsupported by Rifja.
- Rifja must already know the repository and at least one session source. That is a one-time
  operator setup, done by the user in a terminal:

```sh
rifja init                                   # guided; or the explicit commands below
rifja project add /path/to/repo --name myrepo
rifja source discover                        # lists candidate locations; imports nothing
rifja source add claude <path printed by `rifja source discover`>   # e.g. ~/.claude/projects
rifja source add codex  <path printed by `rifja source discover`>   # e.g. ~/.codex/sessions
rifja refresh
```

`recover.py doctor` checks that `git` is present, that Rifja has initialised state (it will not
create any), that `rifja` runs, and its version against the tested minimum. It reports the Python
version it runs under but does not enforce 3.9. Exit 0 means usable; 3 means a prerequisite is
missing.

## Common situations

| Symptom | Cause | Fix |
| --- | --- | --- |
| `rifja_not_initialized` | No Rifja state at the resolved home (a wrong `--home`/`RIFJA_HOME` shows up this way) | `rifja init`; the skill never creates state |
| `rifja_missing` | CLI not on PATH | Install it, or set `RIFJA_BIN` / pass `--rifja` |
| `project_not_registered` | Rifja identifies projects by Git common directory; this repo (or a clone of it) was never added | `rifja project add` |
| `provider_not_configured` | Provider chosen but never registered | `rifja source add <provider> <path>`, `rifja refresh` |
| Brief says history is stale or "never refreshed" | Sessions since the last import are invisible | `rifja refresh` (reads registered sources only) |
| `rifja_busy` | A refresh holds Rifja's writer lock | Wait, retry |
| `rifja_contract_mismatch` | Rifja JSON schema changed | Update the skill or Rifja |
| `not_a_git_repo` with "unsafe ownership" | Git's `safe.directory` check | Review the directory, then fix ownership or add it yourself; the script will not override it |
| Different state directory | Rifja honours `RIFJA_HOME` and `--home` | Pass `--home` to `recover.py` |

## Uninstall

Delete the skill directory (or `/plugin uninstall`). The skill stores nothing. Rifja's own state is
untouched.

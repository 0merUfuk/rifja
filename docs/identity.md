# Rifja: naming and identity migration

Decision: 2026-09-07. The owner explicitly delegated name selection and the complete
migration. Canonical identity: **Rifja**, package/repository/command `rifja`,
environment prefix `RIFJA`. This is the 0.2.0 continuation of Session Visualizer,
with the same MIT license and offline Python implementation.

## What the product is

Rifja recovers the context needed to continue engineering work. It joins opted-in
agent histories and project documents with worktree identity, current Git evidence,
unfinished work, decisions and durable user memory. Evidence remains labeled by
origin and authority. Its primary payoff is `rifja resume PROJECT` and an honest
handoff, rather than charts, session playback, performance tracing or debugging.
There is no graphical UI, execution replay engine, daemon or general-purpose memory
service. Existing deferred features remain deferred; naming adds no new scope.

The name takes its cue from Icelandic *rifja upp*: recall or go over something
again. The historical [Cleasby–Vigfusson dictionary, RIFJA](https://norse.ulver.com/dct/cleasby/r.html)
connects the phrase with revisiting what has been learned and partly forgotten.
This is a Norse-language continuity metaphor, not a claim that a deity named
Rifja exists. Five ASCII letters give one spelling for repository, package and
command. Brand pronunciation: “RIF-yah.”

## Naming evidence and alternatives

The owner's accepted eidir ADR-002 records a personal=Norse/company=Matrix preference.
Public Skuggsja, Heimdall and Radsvinn support Norse naming; the-matrix names its tools
by their roles. Local Huginn documentation also shows a Norse name serving company
work, so ownership cannot be inferred mechanically from a name. The inspected
`DECISION-MODEL.md` was Skuggsja's unratified v0 draft, not a file in this repository;
its naming claims were checked against actual projects and the canonical know-how
index. Current explicit delegation supersedes the draft's old name-approval rule.

| Candidate | Fit and decision |
| --- | --- |
| **Rifja** | Recall and review working context. Selected for direct meaning, five-letter spelling and distinct sound within the owner's portfolio. |
| Muninn / Minni | Memory associations, but direct collisions with agent-memory/context tools, including [Muninn](https://github.com/colliery-io/muninn) and [Minni](https://pypi.org/project/minni/). |
| Rekja | Following a trace emphasizes inputs more than continuation; already used by software repositories, including a mod-management TUI. |
| Vardveit | Preservation fits durable memory but is longer, harder to pronounce and less focused on resuming work. |

The owner rejected the initial candidate Heimta because it sounded too similar
to Heimdall. Portfolio-level sound and spelling separation is therefore an
explicit criterion, beyond external collision checks. That provisional identity
was not released; it has no supported CLI or data-directory contract.

Checks on 2026-09-07 used GitHub repository search, PyPI, npm, crates.io,
Homebrew's formula API and general software search. Before this rename, GitHub
returned four substring-name repositories for Rifja, all unrelated longer names,
and no exact repository name. PyPI, npm, crates.io and Homebrew returned 404 for
the exact token. No major software/package collision was found in those sources.
Registry absence is time-bound evidence, not ownership or legal clearance. No
registry name was reserved and no unnecessary package was published.

## State and command compatibility

- `rifja` is canonical; `session-visualizer` runs the same entry point without
  adding warnings to machine-readable output.
- `python -m rifja` is canonical. `python -m session_visualizer`, the old
  `session_visualizer.cli:main`, and the old version import remain compatibility
  entry points. Internal implementation modules moved to `rifja`; they were never
  the supported interoperability API. CLI and versioned JSON remain that boundary.
- State selection is explicit `--home`, then nonempty `RIFJA_HOME`, then nonempty
  `SESSION_VISUALIZER_HOME`, then default discovery. Empty variables are ignored.
- Fresh macOS state uses `~/Library/Application Support/Rifja`; fresh Unix state
  uses `$XDG_DATA_HOME/rifja` or `~/.local/share/rifja`.
- If only the historical default exists (`SessionVisualizer` on macOS or
  `session-visualizer` on Unix), it is reused in place. No automatic copy, deletion,
  relocation or database rewrite is performed to rename the product. If both
  defaults exist and refer to different locations, exit 2 requests explicit
  selection. This prevents silently switching to an empty or divergent database.
- Schema 3, configuration keys, record/project/worktree IDs, accepted memory,
  corrections, backup format and JSON schema stay stable. A refresh after any
  version change can replay derived extraction once, as before.
- Both `.rifja` and historical `.session-visualizer` state directories remain
  excluded from repository discovery. Source histories remain read-only inputs.

## Upgrading existing installations

For a public Homebrew installation:

```sh
brew update
brew upgrade 0merUfuk/thematrix/rifja
rifja --version
```

The tap's `formula_renames.json` maps the old formula to Rifja. A formula alias
also resolves old qualified install commands. On current Homebrew, a fresh install
through that alias requires trust in the canonical formula. Prefer the normal
`brew install 0merUfuk/thematrix/rifja` command. If retaining an old install script:

```sh
brew trust --formula 0merUfuk/thematrix/rifja
brew install 0merUfuk/thematrix/session-visualizer
```

This grants trust only to Rifja, not the whole tap. Both executable names remain present;
there is one application installation. Do not install independent old and new
wheel distributions into the same Python environment: remove the old distribution
first, then install Rifja. Package removal preserves application state.

For the historical private local tap:

```sh
brew uninstall --force session-visualizer/local/session-visualizer
brew install 0merUfuk/thematrix/rifja
```

For a current Rifja local-tap installation, the removal name is
`rifja/local/rifja`. The private installer cache and historical ownership markers
are not relabeled or erased. Use qualified formula names while multiple taps exist.
Ordinary removal is `brew uninstall --force 0merUfuk/thematrix/rifja`; it leaves
application state, backups and exports intact.

## Intentional historical identity

Published 0.1.x release names, artifact filenames, embedded metadata, checksums,
attestations, tags, historical release notes and Git commits retain their original
identity. Rewriting those would invalidate provenance. GitHub redirects the former
repository URL; the old repository name must not be reused. New releases originate
from the renamed repository. Old attestations still identify the original workflow
repository and should be evaluated as historical provenance.

Compatibility entry points, environment/default paths, migration tests, excluded
legacy state paths and this migration guide deliberately retain old identifiers.
Local historical evidence and immutable installer caches remain historical too.
If you physically move a registered source or project directory, re-register its
canonical location through the documented project/source commands. A checkout
symlink is not a substitute for explicit input registration, and source security
checks may reject it. The product rename itself does not relocate user inputs.

The local checkout is named `rifja`; the former checkout path is a compatibility
symlink for existing bookmarks and running tasks. It is not a second checkout.

## Tap rename follows the product identity (2026-09)

The same identity discipline that renamed the product now renames its public
tap: `0merUfuk/thematrix` → `0merUfuk/rifja` (owner-executed GitHub rename;
both paths work through GitHub's redirect during the transition). The full
ordering contract and user migration commands live in
[Homebrew delivery](homebrew.md#tap-rename-decision-and-transition-contract).
As with the product rename, application state is untouched: taps deliver the
program, never the data.

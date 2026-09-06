# Homebrew delivery

The owner approved retaining Python while matching the installation experience
of their existing Homebrew CLI tools. Python is an implementation dependency;
users should not create or activate a virtual environment. This is a managed
Python application, not a self-contained native executable.

## Current private release

Extract the supplied `session-visualizer-VERSION-homebrew.tar.gz`, enter the
extracted directory, and run `./install.sh`. Homebrew must already be installed
and on PATH. Python 3.14 and Git are installed by Homebrew when needed. The
installer creates the owned `session-visualizer/local` tap, copies the immutable
wheel into it, and installs the generated formula. No project histories are
imported and no application state is initialized by installation. The formula
test uses temporary state only.

Use `session-visualizer --help` immediately afterward. For ordinary configuration,
run `session-visualizer setup --timezone Europe/Istanbul`, register a project and
explicit sources, then refresh. See [usage](usage.md).

Run a newer bundle's `./install.sh` to upgrade. `./install.sh --reinstall` repairs
the installed version. Homebrew owns its private `libexec` environment and links
the command into its `bin`; it does not modify your shell configuration. If
Homebrew itself is not on PATH, follow the shell setup instructions from your
Homebrew installation. No application-specific PATH entry is required.

`brew uninstall session-visualizer` removes the application, preserving user
state, exports and backups. It does not remove the local tap or cached release
wheels. A tap owned by something else or an existing release with different
bytes is rejected. Local wheels are copied outside the source checkout, so
deleting the checkout or extracted installer directory does not break reinstall.
Do not manually delete Homebrew-managed environments.

## Maintainer preparation

`make check` runs the existing quality gates. `make dist` builds the wheel/source
archive and an additional deterministic installer archive under `dist/homebrew`,
with `SHA256SUMS`. An existing installer archive is never overwritten; use a new
output directory for repeated verification builds or a new version for a changed
release. The source distribution includes the packaging tools and template.

The formula installs the pinned dependency-free wheel with network package
resolution disabled. No Hatchling or other build dependency is needed on the
user's machine to install it. The Python runtime is supplied and patched through
Homebrew. Git remains an explicit runtime dependency. The formula's functional
test exercises version, temporary state, integrity, FTS5, Zstandard and timezone
data. Packaging verification must also exercise real CLI import/export and state
preservation across upgrade and uninstall/reinstall.

## Public tap preparation

The intended public tap follows the owner's existing `0merUfuk/thematrix`
convention, but this repository currently has no configured release remote and
its NOTICE grants no public redistribution license. Do not manufacture a working
public install command or publish from the local installer.

Once the owner has selected hosting and authorized publication, generate a
formula from the exact wheel and its immutable HTTPS release URL:

```sh
uv run python tools/homebrew.py formula --wheel /path/to/release.whl --url https://example.org/releases/VERSION/release.whl --output /path/to/session-visualizer.rb
```

These are placeholders. Use the real wheel filename and actual selected release
URL. The generator reads and validates wheel metadata and computes SHA-256;
it refuses runtime Python dependencies until their packaging is explicitly
implemented. It never creates a remote, selects a license, pushes a tap or
uploads files. Publication requires the tested wheel/installer/source archive,
checksums and matching formula; test the final hosted formula before announcing
`brew install 0merUfuk/thematrix/session-visualizer`.

The CI Homebrew job tests an unpublished local formula using the generated
artifact. A remote CI result only exists after that workflow actually runs.
macOS is the first release verification environment; Linux needs its own
executed Homebrew checks before a compatibility claim. Windows is unsupported
by the current POSIX file locking and source traversal implementation.

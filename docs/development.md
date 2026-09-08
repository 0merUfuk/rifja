# Development and releases

Use Python 3.14+, Git, SQLite with FTS5 and uv 0.10.10. Runtime dependencies are
standard-library only. `uv.lock` pins development and build dependencies;
initial setup may fetch them. From a clean checkout:

```sh
uv sync --locked
make check
make dist
uv run python tools/verify_install.py --wheel dist/rifja-0.2.1-py3-none-any.whl --evidence .local/development-install
uv run python tools/audit_release.py --output .local/development-audit.json
```

`make check` runs lint, format, type and regression checks. `make dist` uses the
locked build backend to produce wheel/source archives and an installer bundle.
The bundle cannot overwrite an existing file: use a new output directory with
`tools/homebrew.py bundle --output PATH` for repeated verification, or a new
version for changed release bytes. `make install` installs the built local bundle
through Homebrew. See [Homebrew delivery](homebrew.md) for the public user route.

Choose a new evidence directory for each installation check. The harness uses
isolated state and synthetic data, installs outside the checkout, checks
upgrade/restore/uninstall behavior and retains command evidence. On macOS it
also denies network access and verifies that restriction with a canary. Tests
must not depend on real provider transcripts or credentials.

## Release procedure

1. Update the version in `pyproject.toml` and `src/rifja/__init__.py`, the
   version fields in `packaging/claude-plugin/.claude-plugin/plugin.json` and
   `packaging/claude-plugin/marketplace.json`, update release notes and
   current-version examples, then run `uv lock`.
   Use `0.x.yrcN` for candidates and `0.x.y` for normal releases. CLI, file format
   and schema changes must be described explicitly; never replace released bytes.
2. Run the commands above and inspect the diff, source/history audit and generated
   archives. For runtime or performance changes, run `tools/benchmark.py` against
   the installed wheel using `--preset large`; retain failed attempts and limits.
3. Commit and push. Require all CI matrix jobs to pass on that commit.
4. Create the matching `vVERSION` tag on that commit and push that tag. Release CI
   reruns the gates, validates tag/version identity, builds with locked tooling,
   generates checksums and attestations, and publishes to GitHub Releases.
5. Download the hosted release, verify its attestation and checksum, then run
   `uv run python tools/release.py publish-tap --tag vVERSION` from the matching
   checkout. Test a new Homebrew install from that public tap, first-run usage,
   update/reinstall and uninstall preservation. Verify remote HEAD/tag and asset
   hashes before closing the release. See [the tap procedure](homebrew.md).

`uv run python tools/release.py prepare --output NEW_DIRECTORY` prepares the
publication assets locally without publishing; `--tag` also enforces tag identity
and a clean tracked checkout. The default output is `dist/release` and must be
empty. No manual artifact replacement or clobber flag is used.

Builds run with the lockfile's Hatchling dependencies (`--no-build-isolation`).
CI uses pinned Action commits and a pinned uv bootstrap. Dependabot proposes
periodic updates; upgrades must pass the same gates. Build provenance verification
uses GitHub attestations rather than a maintainer signing key stored locally.

## Contribution and data handling

Read [CONTRIBUTING](../CONTRIBUTING.md). Keep real-source evidence under ignored
`.local/` storage with private permissions. Do not upload private histories or
state to CI or issues. Runtime/build dependency licenses remain their own; this
project is MIT licensed. Schema migrations preserve backups, and uninstall does
not remove state. GitHub Releases and Homebrew are the supported distribution
channels. PyPI, native frozen binaries, Docker images, a documentation website
and Windows installers are not required for this CLI's delivery model.

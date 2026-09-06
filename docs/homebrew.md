# Homebrew delivery

## Public installation

```sh
brew install 0merUfuk/thematrix/session-visualizer
session-visualizer --help
```

Homebrew installs Python 3.14 and Git, owns the application's private environment,
and links `session-visualizer` into its `bin` directory. Homebrew must be installed
and on PATH. No application-specific shell setup or virtual-environment activation
is required. Application setup and source registration remain explicit user actions.

```sh
brew update
brew upgrade session-visualizer
brew reinstall session-visualizer
brew uninstall session-visualizer
```

Uninstall preserves state, exports and backups. The first refresh after a version
change replays derived extraction once and preserves durable memory. Further
unchanged refreshes are incremental.

If upgrading from the private `session-visualizer/local` tap, first run
`brew uninstall session-visualizer/local/session-visualizer`, then install from
the public tap. The application state location stays the same. Do not install
both formulas concurrently or manually remove their managed environments.

## Specific release bundle

Each [release](https://github.com/0merUfuk/session-visualizer/releases) contains
`session-visualizer-VERSION-homebrew.tar.gz`. Extract it, enter the directory and
run `./install.sh`. This registers the installer-owned `session-visualizer/local`
tap and copies the wheel into it. Reinstallation continues working if the
checkout or extracted bundle is removed. This alternative requires manual
selection of a newer bundle to upgrade; use the public tap for normal updates.

The installer rejects a tap owned by something else, a symlink destination or an
existing same-version wheel with different bytes. Installation does not import
histories or initialize application state. The formula test uses temporary state.

## Authenticity and release maintenance

Release assets include `SHA256SUMS`, the exact public formula, wheel, source
archive and installer bundle. For a downloaded asset, use
`gh attestation verify /path/to/asset --repo 0merUfuk/session-visualizer` to verify
GitHub build provenance. Checksums identify bytes; attestations bind those bytes
to the repository's release workflow. There is no standalone native executable
or Apple application bundle requiring notarization.

The formula installs the dependency-free wheel with pip network resolution
disabled. Homebrew supplies and updates the interpreter; no build backend needs
to be installed by the user. Runtime Python dependency changes require explicit
formula support and are rejected by the generator until implemented.

The tag-driven release workflow runs CI before publishing attested assets. Once
it succeeds, an authorized maintainer with GitHub CLI access runs:

```sh
uv run python tools/release.py publish-tap --tag v0.1.0
```

Use the new release tag for later versions and run from that version's checkout.
This command downloads the hosted wheel/formula, verifies checksums and GitHub
attestations, regenerates the formula for comparison, updates only
`Formula/session-visualizer.rb` in `0merUfuk/homebrew-thematrix`, then reads it back.
It is idempotent for identical contents. This explicit authenticated handoff
avoids storing a cross-repository personal token in Actions. A release is not
fully distributed until the tap is updated and its hosted install is tested.

For an independent formula, `tools/homebrew.py formula` requires the exact wheel,
a matching immutable HTTPS URL and a new output path. It does not publish.

CI targets macOS 15 arm64/x86-64 and Ubuntu 24.04 x86-64. Successful runs are the
compatibility evidence; configuration alone is not a platform certification.
Windows and Linux arm64 remain outside the release matrix.

# Homebrew delivery

## Public installation

```sh
brew install 0merUfuk/thematrix/rifja
rifja --help
```

Homebrew installs Python 3.14 and Git, owns the application's private environment,
and links `rifja` into its `bin` directory. Homebrew must be installed
and on PATH. No application-specific shell setup or virtual-environment activation
is required. Application setup and source registration remain explicit user actions.

```sh
brew update
brew upgrade 0merUfuk/thematrix/rifja
brew reinstall 0merUfuk/thematrix/rifja
brew uninstall --force 0merUfuk/thematrix/rifja
```

`--force` removes all installed versions of this formula; it does not remove
application state. This matters after upgrades that retained an older version.
Uninstall preserves state, exports and backups. The first refresh after a version
change replays derived extraction once and preserves durable memory. Further
unchanged refreshes are incremental.

The public formula was renamed from `session-visualizer` to `rifja`;
`brew update` and the qualified upgrade command above migrate existing public
installations. See [identity migration](identity.md) for the old private tap.

If switching from the current private `rifja/local` tap, first run
`brew uninstall --force rifja/local/rifja`, then install from
the public tap. The application state location stays the same. Use the fully qualified public name for upgrades and removal while the private
tap remains registered; short formula names are ambiguous across two taps. Do not install
both formulas concurrently or manually remove their managed environments.

## Specific release bundle

Each [release](https://github.com/0merUfuk/rifja/releases) contains
`rifja-VERSION-homebrew.tar.gz`. Extract it, enter the directory and
run `./install.sh`. This registers the installer-owned `rifja/local`
tap and copies the wheel into it. Reinstallation continues working if the
checkout or extracted bundle is removed. This alternative requires manual
selection of a newer bundle to upgrade; use the public tap for normal updates.

The installer rejects a tap owned by something else, a symlink destination or an
existing same-version wheel with different bytes. Installation does not import
histories or initialize application state. The formula test uses temporary state.

## Authenticity and release maintenance

Release assets include `SHA256SUMS`, the exact public formula, wheel, source
archive and installer bundle. For a downloaded asset, use
`gh attestation verify /path/to/asset --repo 0merUfuk/rifja` to verify
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
uv run python tools/release.py publish-tap --tag v0.2.0
```

Use the new release tag for later versions and run from that version's checkout.
This command downloads the hosted wheel/formula, verifies checksums and GitHub
attestations, regenerates the formula for comparison, updates only
`Formula/rifja.rb` in `0merUfuk/homebrew-thematrix`, then reads it back.
It is idempotent for identical contents. This explicit authenticated handoff
avoids storing a cross-repository personal token in Actions. A release is not
fully distributed until the tap is updated and its hosted install is tested.

For an independent formula, `tools/homebrew.py formula` requires the exact wheel,
a matching immutable HTTPS URL and a new output path. It does not publish.

CI targets macOS 15 arm64/x86-64 and Ubuntu 24.04 x86-64. Successful runs are the
compatibility evidence; configuration alone is not a platform certification.
Windows and Linux arm64 remain outside the release matrix.

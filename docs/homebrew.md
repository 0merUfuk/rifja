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
uv run python tools/release.py publish-tap --tag v0.3.0
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

## Tap rename decision and transition contract

Decision (2026-09, delegated): the public tap `0merUfuk/thematrix` will be
renamed to `0merUfuk/rifja`. The current name is a company-collection artifact
(the tap also hosts `morp`, `neo`, `oracle`, `rifja`, `skuggsja` and
`trinity`); the product's canonical identity is `rifja`, and a formula named
`rifja` should live in a tap that does not require a mnemonic. This follows the
same migration discipline as the product rename recorded in
[identity](identity.md).

The rename is executed by the owner as a GitHub repository rename
(Settings → General → Repository name). GitHub redirects the old tap URL, so
during the transition **both install paths keep working**:

```sh
# Old name (redirected after the rename; unchanged until the rename lands)
brew install 0merUfuk/thematrix/rifja
# New name (valid immediately after the rename)
brew install 0merUfuk/rifja/rifja
```

Existing installations keep updating through either name because `brew update`
follows the redirect; a one-time explicit re-tap removes the indirection:

```sh
brew untap 0merUfuk/thematrix
brew tap 0merUfuk/rifja https://github.com/0merUfuk/homebrew-rifja
brew upgrade 0merUfuk/rifja/rifja
```

(Application state, exports and backups are untouched by any of these steps.)

Ordering contract: the repository documentation switches its qualified
`brew` commands to the new tap name only in the first release **after** the
physical rename lands — never before, so no documented command can dangle.
The release procedure's tap-publish step (`tools/release.py publish-tap`)
must target the new tap from that release onward — the first post-rename
release also updates `TAP_REPOSITORY` in `tools/release.py` to
`0merUfuk/homebrew-rifja` in the same commit as the documentation switch —
and the release notes must carry the migration block above verbatim.

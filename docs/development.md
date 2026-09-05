# Development and private releases

Use Python 3.14 or newer, Git, SQLite with FTS5 and `uv`. Runtime dependencies
are standard-library only. The `uv.lock` file pins development dependencies;
initial environment setup may fetch them. From a clean checkout:

```sh
uv sync --locked
uv run ruff check src tests tools
uv run ruff format --check src tests tools
uv run mypy
uv run pytest -q
uv build
uv run python tools/verify_install.py --wheel dist/session_visualizer-0.1.0rc3-py3-none-any.whl --evidence .local/development-install
uv run python tools/audit_release.py --output .local/development-audit.json
```

Choose a new evidence directory for each installation check. The harness uses
isolated temporary state and synthetic data, installs outside the checkout,
checks upgrade/restore/uninstall behavior and retains its command evidence.
On macOS it denies network access and verifies that restriction with a canary.
Tests must never depend on a developer's real provider transcripts or credentials.

The workflow in `.github/workflows/ci.yml` runs the same quality and installation
checks on Linux and macOS. A local pass does not certify the remote matrix.

Before a new private candidate, update package and documentation versions,
regenerate the lockfile, record changes, run the checks from a clean checkout,
and test the wheel actually being delivered. Run `tools/benchmark.py --help` for
the synthetic scale gate; use its `--cli` option with the isolated installed
executable, `--preset large`, and a new `.local/benchmark-*` output directory.
Retain failed attempts and any coverage limitations. Compare installed code to
the packaged source, rebuild from the source archive, record artifact checksums,
and only then create a local candidate tag. Do not publish artifacts, source,
private evidence or a new license as part of this local procedure.

`NOTICE` and package metadata describe private local use. Build/test tools are
not included in the runtime wheel. Keep real-source evidence under ignored
`.local/` storage with private permissions; share only intentionally reviewed
exports. Product state, backups and exports remain after uninstall by design.

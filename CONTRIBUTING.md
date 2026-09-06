# Contributing

Start with [development setup](docs/development.md) and the
[architecture and privacy boundaries](docs/design.md). Python 3.14+, Git and uv
are required. Run `uv sync --locked`, then `make check` and `make dist`.

Open an issue with a small synthetic reproduction before a broad behavior change.
For a fix, add a regression that demonstrates the failure and submit a pull
request describing the changed behavior and validation. Keep provider transcripts,
credentials, private repository contents and generated state out of issues,
commits and attachments. Use the synthetic fixtures in `tests/fixtures` as examples.

Changes must preserve explicit source registration, read-only input handling,
offline operation, worktree identity, and the distinction between claims and
verified observations. Document format/support limitations rather than hiding
unrecognized data. Avoid additional runtime dependencies without a demonstrated
need and corresponding distribution changes.

Contributions are submitted under the project's [MIT License](LICENSE).
For sensitive reports, follow [SECURITY.md](SECURITY.md).

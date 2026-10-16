# Handoff for `agent-product-studio`

Prepared so the studio can ingest this candidate later **without** this work touching that repository
or any other agent's workspace. The machine-readable inventory is
[`studio-handoff.json`](studio-handoff.json); this page explains how to use it.

## What to ingest

1. The branch `feat/session-recovery-skill` of `0merUfuk/rifja` (base `bd3d29d`), or the three
   deterministic artifacts listed in the JSON (rebuild with one command and compare checksums).
2. The evidence index: [evaluation](evaluation.md) with raw per-run files, [compatibility](compatibility.md),
   [privacy assessment](privacy-assessment.md), [release notes](release.md).
3. The constraints in the JSON. They are part of the product claim, not footnotes.

## What the studio should believe about it

| Question | Honest answer |
| --- | --- |
| Does it work technically? | Yes, locally: reproducible, spec-validated, installs in isolated Claude Code and Codex homes, 747-test suite green |
| Does it help agents? | With Sonnet on synthetic data: higher rubric score, clean provider isolation, no execution of a hostile repo's Git config, 40% cheaper than driving the CLI by hand. Not with Haiku (never invoked it). Unknown for Codex (blocked) and Hermes (untested) |
| Can it be listed? | Not yet; owner items and two structural mismatches remain ([commercial](commercial.md)) |
| Will people pay? | Unknown |

## Recommendation

**Free / open-source entry product** that builds trust in Rifja. A supported bundle or a premium
recovery product are hypotheses to test, not plans: the licence is MIT, the category is crowded with
free tools, differentiation is real but narrow, and no demand evidence exists. See
[commercial.md §7](commercial.md#7-recommendation-what-rifja-should-be) for the option-by-option reasoning and the gates
that would change it (pain interviews, a genuine-data pilot, Codex and Hermes evidence).

## Reproduce the verification

```sh
git checkout feat/session-recovery-skill
uv sync --locked
uv run python tools/recovery_bundle.py check
uv run python tools/recovery_bundle.py build --out dist/recovery
(cd dist/recovery && shasum -a 256 -c SHA256SUMS)
uv run pytest -q tests/test_session_recovery.py tests/test_recovery_packaging.py tests/test_recovery_rifja_contract.py
uv run python tools/recovery_demo.py --out /tmp/recovery-demo      # real recorded demo on synthetic data
```

Model-driven re-runs (`tools/recovery_eval.py run ...`) spend the operator's own model quota and are
not part of the default verification.

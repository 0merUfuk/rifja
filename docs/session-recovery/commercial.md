# Commercial notes: positioning, pricing hypotheses, listing copy

Status: hypotheses to test, not decisions. Nothing here has been published, listed, announced or
priced anywhere. The measured product evidence is in [evaluation.md](evaluation.md); this document
only says what the evidence does and does not support commercially.

## 1. Constraints that shape any business model

1. **The code stays MIT.** Rifja and this package are MIT-licensed; the notices and every
   redistribution right must be preserved (the build copies `LICENSE` and `NOTICE` into every
   artifact and the validator rejects a skill without the MIT text). So the skill itself cannot be
   sold behind a licence; anyone may copy and redistribute it. Money can only come from things the
   licence does not give away: hosted services, support, integration work, or convenience.
2. **It is a local-first product.** It needs the user's `git`, `rifja` and Rifja state. It cannot
   run on claude.ai or Cowork (hosted sandboxes have none of that), so it is a Claude Code / Codex /
   terminal-agent product only.
3. **It depends on Rifja** (Python 3.14 via Homebrew; macOS and Ubuntu release-checked; Windows
   unsupported). Install friction is real: Homebrew, `rifja init`, registering projects and sources,
   `rifja refresh`. See "installation friction" in the evaluation.
4. **The category is crowded and mostly free.** Public listings show free session-handoff tools
   (`claude-handoff`, a `session-resume` skill, `claude-session-handoff`), a very widely adopted free
   memory plugin (`claude-mem`) and at least one paid managed-memory service (ContextStream; its
   published tiers were a free Starter and Pro from $19/month and Elite from $49/month when this was
   researched on 2026-10-16: verify before quoting). This research read their public descriptions
   only; no competitor was installed or tested.

## 2. Positioning

For developers who switch between coding agents or lose a session to a crash, context limit or
terminal close, **session recovery tells them what is verified and what was only claimed**, using
history that stays on the machine. The differentiators that the test evidence supports:

| Claim | Evidence |
| --- | --- |
| Separates Git facts, user intent, agent claims and unknowns, and flags a success claim contradicted by a recorded test result | Engine tests; 9/9 skill runs in harbor, pier and drift flagged the false claim ([evaluation](evaluation.md)) |
| One recovery across Claude Code, Codex and Hermes history (via Rifja) with the user choosing which providers are read | Three-provider fixture and tests; live Sonnet runs: skill 0/3 leaks of an excluded provider vs `cli` 2/3 and `paste` 3/3 |
| Keeps agents from hunting for history on disk | Sonnet: `cli` probed `~/.claude/projects` in 11/15 runs, `skill` 0/15 (the pilot's "manual arm reads transcripts" was over-stated; only 1/15 `paste` run opened a transcript) |
| Safe in the tested ways against hostile history and repositories | Canary tests; live Sonnet runs: 6/6 `cli`/`paste` runs executed a hostile repo's Git-config program, 0/3 `skill` runs; injected-action obedience was 0/45 in every arm, so no obedience advantage is shown |
| Less output and fewer steps than driving the CLI by hand | `cli` $0.151, 28.8 s, 27.8 KB tool output vs `skill` $0.091, 19.7 s, 5.3 KB. Pasting `rifja resume` yourself is cheaper ($0.076) and faster (16.8 s) but lost on isolation and the hostile repo |

Not supported by evidence: that users will pay, that recovery is better than competitors',
accuracy on genuine histories, benefits for models that do not invoke the skill (Haiku did not),
Codex or Hermes behaviour, or any statement about universal recovery.

## 3. Pricing hypotheses

| # | Hypothesis | Price test | Status |
| --- | --- | --- | --- |
| H1 | **Free, MIT, open distribution** is the launch model. The skill is an acquisition and trust surface for Rifja (installs, activation, stars), not a revenue line | $0 | Recommended: the only model consistent with MIT, a crowded free category and zero demand evidence |
| H2 | **Support and sponsorship**: a "Rifja supporter" tier (GitHub Sponsors or similar) for priority fixes on provider-format drift | $5-10 per month, individual | Untested; expect low conversion. Compare against free alternatives |
| H3 | **Team/managed layer** (not built): encrypted, policy-controlled sharing of handoff briefs between teammates and machines, audit trail of what each agent was shown, retention controls | $12-20 per seat per month, anchored below ContextStream Pro ($19) | Pure hypothesis. Requires a hosted service, which contradicts the offline promise unless self-hostable |
| H4 | **Services**: onboarding Rifja plus recovery into a team's agent workflow, redaction rule tuning | Fixed fee per team | Untested |

Why not charge for the skill: a single-user recovery brief is a few seconds of value per
interruption, there are free substitutes, and MIT lets any user fork it. Why H3 might work: teams
care about *what an agent was shown*, which is where redaction, selection and audit matter more
than convenience.

### Experiments that would change the decision

1. **Activation**: of people who install, what fraction run a brief within 7 days? (Requires opt-in
   telemetry that does not exist today; the product is deliberately offline, so use install-time
   survey or self-reported counts, not covert telemetry.)
2. **Pain interviews**: 10-15 developers who use two or more agents daily. Ask for the last
   interruption, what they did, and how long it took. Kill H3 if fewer than 3 describe a recurring
   cost of at least 15 minutes per week.
3. **Genuine-data pilot** (owner-run, local): run the skill over the owner's own histories and
   count briefs that were correct, partially wrong or misleading. Gate any listing on this.
4. **Willingness to pay**: a waitlist page for H3 with a price shown; fewer than ~2% of visitors
   joining at $15 is a no.

## 4. Listing copy (drafts, unpublished)

**Name:** Rifja Session Recovery

**Tagline (<= 80 chars):** Resume interrupted agent work from what Git proves, not what the agent claimed.

**Short description (<= 250 chars):** Rebuilds a bounded, evidence-tagged continuation brief for the
repo you are in: live Git state, your last stated objective, remaining work, blockers and a check
on whether the agent's "tests pass" was ever true. Local and offline; reads only the Claude Code,
Codex or Hermes history you select.

**Long description:**
> Interrupted mid-task? Session Recovery turns the history Rifja imported from Claude Code, Codex
> and Hermes plus a fresh look at your repository into one brief of at most a few thousand
> characters. Every line is tagged by authority: GIT (observed now), USER (what you said), CLAIM and
> TOOL (what an agent said or a recorded exit status showed, never treated as fact) and UNCERTAIN.
> It flags an agent's success claim that a recorded test failure contradicts, shows exact references
> to the source records, and ends with a bounded next step. Secrets and personal paths are redacted,
> instruction-like text in old sessions is withheld rather than passed to your agent, and nothing is
> uploaded or executed. You choose which providers it may read. Requires the open-source Rifja CLI
> (Homebrew), Git and Python 3.9+. MIT licensed.

**Categories / tags:** productivity, git, session history, handoff, claude-code, codex, local-first.

**Honest limits to show on the listing:** works only for providers Rifja imports; history must have
been imported with `rifja refresh`; heuristics can be wrong; not validated on real-world histories
yet.

## 5. Listing prerequisites and blockers (as researched 2026-10-16; verify before acting)

| Route | What it needs | Status for this package |
| --- | --- | --- |
| Own Claude Code marketplace (a Git repository with `.claude-plugin/marketplace.json`) | A repo holding the built plugin; no review | Built and validated locally (`claude plugin validate`, install in a disposable config). Not pushed anywhere. The existing `0merUfuk/rifja-plugin` repository is a candidate home but was not touched |
| Anthropic directory (claude.ai/directory) | GitHub repository, paid claude.ai plan, developer-portal submission and review; `icon`, `documentationUrl`, `supportUrl`, `privacyPolicyUrl`, `termsOfServiceUrl` in `plugin.json`; plugin components must make sense off Claude Code | **Blocked**: no icon, privacy-policy URL, support URL or terms URL exist; the skill cannot work on claude.ai/Cowork because it needs local `git`/`rifja`; needs the owner's account |
| OpenAI Codex directory (portal) | Organization with Apps Management write access, identity verification, OpenAI review; skills must work "without undeclared local packages, files, or credentials" | **Blocked**: requires a local `rifja` CLI and Rifja state, which is precisely an undeclared local dependency; likely needs reframing as an MCP-backed plugin; owner identity verification needed |
| Local/team install (zip, marketplace add by path or Git URL) | Nothing | Works today |

No submission form, portal or repository was touched. Publishing needs the owner's explicit
authorization.

## 6. Four different readiness questions

| Layer | Verdict | Basis |
| --- | --- | --- |
| Technical package readiness | **Ready for local and own-repository distribution** | Reproducible build, spec validator, installs verified in disposable Claude Code and Codex homes, full suites green on macOS and Debian, independent reviews fixed and regression-tested ([release.md](release.md)) |
| Agent evaluation evidence | **Moderate, narrow** | Claude Code + Sonnet, synthetic data, n=45: skill 98% (raw) vs `cli` 91% / `paste` 87%; no benefit for Haiku (never activated); Codex BLOCKED; Hermes untested; no genuine histories |
| Marketplace submission readiness | **Not ready** | Missing owner-supplied items (icon, privacy/support/terms URLs, a published repository, accounts, identity verification) and two structural mismatches: it cannot run on claude.ai/Cowork, and OpenAI's directory rules forbid undeclared local dependencies |
| Market demand | **Unknown** | No demand data exists. A working demo and a favourable pilot are not demand |

## 7. Recommendation: what Rifja should be

Options asked about, judged on differentiation, maintenance cost, licensing and evidence:

| Option | Fit | Why |
| --- | --- | --- |
| **Free / open-source entry product** | **Recommended now** | MIT forbids charging for the code. The category is crowded with free tools. The evidence supports a narrow, real differentiator (provider isolation, hostile-input handling, claim-vs-record checks, local-only), which is valuable as trust-building for Rifja, not as a revenue line. Maintenance is real but bounded (one script, one contract test file, per-release Rifja contract check) |
| Commercially supported bundle | Possible later, if pull appears | Support revenue needs users who depend on it in teams. Zero such users are evidenced. Cost: tracking Claude Code, Codex and Rifja format changes (the contract tests make this cheap to detect, not free to fix) |
| Foundation for a distinct premium recovery product | **Not yet; do not start it on this evidence** | A premium product (shared briefs, audit of what each agent was shown, policy and retention) is plausible only if teams show the pain, and it breaks the offline promise unless self-hostable. Nothing here measures that pain. Run the pain interviews and genuine-data pilot in [section 3](#3-pricing-hypotheses) first |

Concretely: ship it free as a Rifja add-on once the owner supplies the listing items; treat paid
tiers as hypotheses H2-H4 to test; do not build the premium layer before at least the interview gate
passes. Two known gaps would limit even the free launch: smaller models may never trigger the skill
(documented, fixable only by a clearer prompt contract or hosting-side hints), and the first
real-world histories are untested.

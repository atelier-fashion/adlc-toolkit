---
id: BUG-205
title: "A legacy MOONSHOT_API_KEY/KIMI_API_KEY in the environment silently overrides an explicit `delegate.enabled: false` — the operator's opt-out is ignored and file contents are transmitted"
status: resolved
severity: high
created: 2026-08-31
updated: 2026-08-31
component: "partials/delegate-gate"
domain: "adlc"
stack: ["bash", "python", "yaml"]
concerns: ["data-governance", "privacy", "correctness", "silent-failure", "documentation"]
tags: ["delegation", "opt-in", "key-continuity", "precedence", "enabled-false", "third-party-transmission"]
introduced_by: ["REQ-515"]
attribution: derived
---

## Description

The delegation opt-in predicate is a three-way **OR**, and the legacy key-continuity arm
is evaluated *before* the config file. As a result, an operator who writes an explicit
`delegate.enabled: false` in `~/.claude/adlc/config.yml` still has delegation **fully
enabled** whenever `MOONSHOT_API_KEY` or `KIMI_API_KEY` happens to be exported in the
environment — which is the default state on any install that predates the config file.

The gate returns `0 / ok`, the CLI proceeds, and the contents of every file passed to
`adlc-read` / `adlc-write` are transmitted to the configured third-party endpoint. The
operator has no signal that their opt-out was discarded.

This is a data-governance defect first and a correctness defect second. `enabled: false`
is not an absent value or a default — it is a deliberate, written instruction not to send
source content off the machine, and the system overrides it without saying so.

The docs assert both sides of the contradiction. `tools/delegate/README.md` documents the
config key as:

```yaml
delegate:
  enabled: true                       # opt-in; absent/false => disabled
```

and, eleven lines below, documents opt-in as satisfied by **any one** of three signals,
the third being "an already-set legacy `KIMI_API_KEY` / `MOONSHOT_API_KEY`". Those two
statements cannot both hold. The implementation resolves the conflict in favour of the
key; the inline comment `absent/false => disabled` is simply false in that configuration.

The same README's precedence table places **config file (3)** above **legacy key-env
continuity (4)**. For provider fields (`base_url`, `model`, `api_key_env`) that ordering
does hold. For `enabled` the ordering is inverted, and nothing in the docs marks `enabled`
as exempt from the table it appears directly beneath.

## Reproduction Steps

Observed state on the reporting machine: `~/.claude/adlc/config.yml` contains
`delegate: { enabled: false }`, no `ADLC_DELEGATE_*` variable is set, and
`MOONSHOT_API_KEY` is exported (inherited by every Claude Code subagent shell).

1. Confirm the config opts out:

   ```
   $ cat ~/.claude/adlc/config.yml
   delegate:
     enabled: false
   ```

2. Confirm no env override is in play: `env | grep ADLC_DELEGATE` → no output.

3. Ask the CLI what it resolved:

   ```
   $ adlc-read --version
   adlc-toolkit 5.0.0
   base_url: https://api.moonshot.ai/v1
   model: kimi-k2.5
   api_key_env: MOONSHOT_API_KEY
   enabled: true          # <-- config says false
   ```

4. Run the gate itself:

   ```
   $ . partials/delegate-gate.sh; adlc_delegate_gate_check; echo "$? $ADLC_DELEGATE_GATE_REASON"
   0 ok
   ```

5. Remove only the legacy key and repeat — nothing else changes:

   ```
   $ ( unset MOONSHOT_API_KEY KIMI_API_KEY
       . partials/delegate-gate.sh; adlc_delegate_gate_check; echo "$? $ADLC_DELEGATE_GATE_REASON" )
   1 not-opted-in

   $ env -u MOONSHOT_API_KEY -u KIMI_API_KEY adlc-read --print-enabled
   0
   ```

The single variable that flips the verdict is the presence of a legacy API key. The
config file's explicit `false` never participates in the decision.

## Expected Behavior

An explicit `delegate.enabled: false` is an operator opt-out and is honoured. Legacy key
continuity should cover the case it was designed for — a pre-config install where
`enabled` is *absent* — and should not silently outrank a written `false`.

Concretely: with `enabled: false` in the config, `adlc_delegate_gate_check` returns `1`
with a reason that names the cause, `adlc-read --version` reports `enabled: false`, and no
network call is attempted regardless of which API keys are exported.

## Actual Behavior

`enabled: false` is unreachable as a disable. The gate returns `0 / ok`, `adlc-read
--version` reports `enabled: true`, and file contents are sent to
`https://api.moonshot.ai/v1`. The only working kill switch is `ADLC_DISABLE_DELEGATE=1`,
which is documented as a *force-off escape hatch* rather than as the sole functioning
opt-out.

## Environment

- Platform: darwin 25.6.0, zsh
- Version: `adlc-toolkit 5.0.0`
- Config: `~/.claude/adlc/config.yml` → `delegate: { enabled: false }`
- Env: `MOONSHOT_API_KEY` set; no `ADLC_DELEGATE_*`; `ADLC_CONFIG` unset
- Observed: 2026-08-31, during a `/sprint` run on REQ-595

## Root Cause

`partials/delegate-gate.sh`, `_adlc_delegate_opted_in()` — the arms are ordered and the
function returns on the first hit:

1. `ADLC_DELEGATE_ENABLED=1` → opted in
2. **`MOONSHOT_API_KEY` or `KIMI_API_KEY` non-empty → opted in** ← returns here
3. config file probe (`adlc-read --print-enabled`) → only reached if 1 and 2 both miss

Arm 3 is guarded by a comment explaining the ordering as a *performance* choice — "the
common paths stay pure-shell and fast", avoiding a subprocess fork. That reasoning is
sound for `enabled: true` (where every arm agrees) and wrong for `enabled: false` (where
the arms disagree and the cheap one wins). The optimisation quietly decided a governance
question.

The Python resolver behind `--print-enabled` reproduces the same disjunction independently
— hence step 3 above printing `enabled: true` — so this is not a shell-only skew. Both
implementations agree with each other and disagree with the config file.

Tracing to intent: REQ-515 BR-11 specifies the continuity exception as *"when legacy
`KIMI_API_KEY` is already set in the environment (today's installs), delegation remains
enabled as before"*, and its acceptance criterion scopes the disabled path to *"a config
file present but no `enabled: true` **and no legacy `KIMI_API_KEY` in env**"*. The spec
was written against the fresh-install axis — config absent, or `enabled` absent — and
never contemplated an operator writing `false` on a machine that already had a key. The
implementation is faithful to BR-11 as written; BR-11 is what has the gap. `enabled:
false` and `enabled` absent were treated as one state, and they are not: absence is a
default, `false` is an instruction.

This also fully explains the `/sprint` report that surfaced it. The pipeline-runner
subagent said `adlc-read` "passes the gate" and then returned `404 — model kimi-k2.5 not
found or Permission denied`. Both halves are accurate and consistent: the gate genuinely
returned `ok` (arm 2, inherited `MOONSHOT_API_KEY`), a live call was genuinely attempted
against `https://api.moonshot.ai/v1`, and it failed at the provider on model entitlement
rather than at the gate. The `404` was not reached through a leak in a *disabled* gate —
the gate was never disabled. Nothing about the subagent's report was imprecise; the
surprising part is upstream of it.

The uncomfortable corollary: this machine has been transmitting file contents on every
delegating step of `/spec` 1.6, `/wrapup` 4, `/analyze`, and `/architect` for as long as
`enabled: false` has been in the config. The `404` is the only reason the payloads were
rejected rather than processed, and that is an accident of model entitlement, not a
control. A key with `kimi-k2.5` access would have completed the transmission silently.

## Resolution

`enabled` now resolves in the same precedence order as the provider fields (BR-2),
which it had never followed:

1. `ADLC_DELEGATE_ENABLED=1` → enabled (rank 2 env, outranks the config file)
2. `delegate.enabled`, when the key is **present** → decisive **in both
   directions**; `false` opts out and outranks continuity
3. a legacy key — reached only when **no config file exists**, which is the
   pre-config install BR-11 wrote the exception for
4. otherwise → disabled

`ADLC_DISABLE_DELEGATE=1` still short-circuits ahead of all of it.

The three-state distinction was already available and unused: `parse_delegate_config`
records `enabled` only when the key actually appears, so `None` (absent) was always
distinguishable from `False` (written). `delegation_enabled` had been collapsing both
to "not true".

In the shell gate, the config probe moved **above** the legacy-key arm. Where a config
file exists the gate now defers to `--print-enabled` entirely — that probe runs the full
Python predicate, so its answer is the whole answer and there is nothing left for a shell
arm to second-guess. The fork the old ordering was avoiding is the correct price for a
governance decision; the no-config path still pays nothing, and a test asserts it does not
fork.

Three things surfaced while fixing it that were not in the original report:

- **The probe was not fail-closed on exit status.** Command substitution captures stdout
  and discards the exit code, so a probe that printed `1` and then *failed* was read as
  consent. Caught by the new shell harness, not by inspection. Now both status and output
  must be right. This is the same shape of cheap assumption as the bug itself.
- **The docs contradicted themselves more directly than reported.** `tools/delegate/README.md`
  documented `enabled: true  # opt-in; absent/false => disabled` eleven lines below listing a
  legacy key as independently sufficient. Both halves are now correct, and the precedence
  table states that `enabled` follows it.
- **`agents/delegate-pre-pass.md` pinned `gateReason` to three values** (`ok`, `no-binary`,
  `disabled-via-env`), already omitting `not-opted-in` before this change. It now passes the
  gate's reason through verbatim instead of enumerating.

New reason string `disabled-via-config` distinguishes a deliberate opt-out from a
never-opted-in machine — the two are identical in a return code and call for opposite
responses (leave it alone vs. offer to enable it). The 0/1/2 return-code contract is
unchanged, so callers that branch only on the code are untouched.

### Behavior change

Anyone relying on a legacy key to opt in **while their config says `enabled: false`** now
has delegation off. That is the fix working, but it is a real migration: since REQ-519
`install.sh` scaffolds that exact line, the affected population is every install with a key
exported. `enabled: true` or `ADLC_DELEGATE_ENABLED=1` restores it; `adlc-read --version`
prints the resolved value. Installs with no config file are untouched.

### Verification

- **16-cell matrix** over {`enabled: true`, `false`, absent, no config file} × {key set,
  unset} × {`ADLC_DELEGATE_ENABLED=1`, unset}, asserting the gate's return code and reason
  against `adlc-read --print-enabled`. All 16 correct and the two surfaces agree in every
  cell — `false` disabled wherever the env override is absent, `absent`+key still enabled.
- **The tests fail on the old code.** Reverting `delegation_enabled` alone fails exactly
  the three behavior-change tests and passes the two guard tests (absent-still-yields,
  env-still-outranks), so the reorder is demonstrably the thing that fixes it.
- `partials/tests/delegate-gate.test.sh` — 10 cases, green under **both bash and zsh**;
  full `partials/tests/run.sh` exits 0.
- `pytest tools/delegate/tests` → **283 passed** (278 pre-existing, 5 added).
- `tools/lint-skills/check.sh` → exit 0.
- The reported scenario, re-run against the fixed code: gate `1 disabled-via-config`, and
  `adlc-read --version` reports `enabled: false` — matching the config for the first time.
- Deliberately **not** verified by a live delegate call; that is the transmission this bug
  is about.

A methodological note worth keeping: the first matrix run reported a false pass, then a
false regression. `~/bin/adlc-read` is a shim hardcoded to the **main checkout**, so it was
testing unfixed code; and the `nofile` row left `ADLC_CONFIG` unset, so it silently fell
back to the operator's real `~/.claude/adlc/config.yml`. Both harness bugs, both in the
direction of a confident wrong answer. A gate test that does not pin `HOME` and the binary
is testing the machine, not the change.

## Files Changed

- `tools/delegate/_common.py` — `delegation_enabled` reordered and made three-state on
  `cfg.get("enabled")`
- `partials/delegate-gate.sh` — config probe moved above the legacy-key arm; probe now
  fail-closed on exit status as well as output; new `disabled-via-config` reason; header
  contract rewritten
- `partials/tests/delegate-gate.test.sh` — new harness (10 cases, bash + zsh)
- `partials/tests/run.sh` — harness registered
- `tools/delegate/tests/test_resolve_provider.py` — 5 regression tests, 3 of which fail on
  the old code
- `tools/delegate/README.md` — self-contradicting opt-in section corrected; precedence
  table notes that `enabled` follows it; new "Turning delegation off" section
- `partials/delegate-gate.md` — reason table gains `disabled-via-config`, with the
  derivation documented
- `agents/delegate-pre-pass.md` — `gateReason` passed through verbatim, no longer
  enumerated
- `tools/adlc/README.md`, `.adlc/context/conventions.md` — reason values and precedence
  brought current
- `CHANGELOG.md` — Unreleased/Fixed entry with the migration note
- `.adlc/bugs/BUG-205-legacy-key-overrides-explicit-enabled-false.md` — this report

## Notes

The one-line form: **absence is a default; `false` is an instruction — a system that
collapses the two will eventually override someone on purpose.**

Severity is `high` rather than `medium` because the failure is silent and outward-facing.
A wrong verdict inside the toolkit costs a rerun; this one sends source content to a
third-party endpoint after the operator wrote down that it must not. The blast radius is
every delegating skill (`/spec` Step 1.6, `/wrapup` Step 4, `/analyze`, `/architect`) on
every install that has a legacy key exported — which, by design of the continuity
exception, is precisely the population of long-standing installs.

Worth separating two things the investigation initially conflated: there is **no leak in
the gate**. The gate does exactly what its contract says, and `ADLC_DISABLE_DELEGATE=1`
works. The defect is that the opt-in *predicate* answers a different question than the
config file appears to ask, and the docs promise the config file's answer.

Follow-up worth its own artifact: a lesson on opt-out semantics — every governance switch
in the toolkit should be audited for the same absent-vs-false collapse, since the pattern
is cheap to repeat wherever a config value is read through a truthiness check.

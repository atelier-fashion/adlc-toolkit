---
id: BUG-206
title: "The delegate CLIs never enforce `enabled` — the opt-out is checked only by the probe, so a stale vendored gate transmits file contents anyway"
status: resolved
severity: high
created: 2026-09-01
updated: 2026-09-01
component: "tools/delegate"
domain: "adlc"
stack: ["python", "bash"]
concerns: ["data-governance", "privacy", "defense-in-depth", "silent-failure"]
tags: ["delegation", "opt-in", "enforcement", "vendored-partials", "backstop"]
introduced_by: ["REQ-515"]
attribution: derived
---

## Description

`enabled` decides whether file contents may leave the machine. Until this fix, the
delegate CLIs consulted it in exactly one place — `adlc-read --print-enabled`, the
**probe** the shell gate calls. The code path that actually does the leaving,
`adlc-read --paths … --question …` and every `adlc-write` run, never looked at it.

So enforcement lived entirely in `partials/delegate-gate.sh`. That would be tolerable
if the gate were a single shared object. It is not: delegating skills source it as

```sh
. .adlc/partials/delegate-gate.sh 2>/dev/null || . ~/.claude/skills/partials/delegate-gate.sh
```

The **vendored copy wins**. Every consumer repo carries its own, and they drift.
A repo with a stale vendored gate calls straight through a correct opt-out, the CLI
raises no objection, and the payload goes out. The operator's `enabled: false` is
enforced by whichever copy of a shell partial that repo happens to be carrying.

Found while fixing [[BUG-205]]. That bug was "the predicate answers the wrong
question"; this one is "only one layer asks at all", and it is what made BUG-205's
blast radius the full set of consumer repos rather than one file in the toolkit.

## Reproduction Steps

Config opts out, a legacy key is present, and the caller invokes the real read path —
exactly what a stale vendored gate does after wrongly returning `ok`:

1. `printf 'delegate:\n  enabled: false\n' > /tmp/off.yml`
2. ```
   ADLC_CONFIG=/tmp/off.yml MOONSHOT_API_KEY=sk-… \
     adlc-read --paths ./some-file.md --question "summarize"
   ```
3. Before the fix: the CLI resolves the provider, prints
   `delegate: sending file contents to the configured endpoint (kimi-k2.5 at …)`,
   and performs the request. `--print-enabled` said `0` the whole time; nothing on the
   transmitting path ever asked.

The regression test observes exactly this. With the guard reverted, the un-guarded run
emits its own exfiltration notice naming the endpoint and then fails at the network —
the test failure output *is* the reproduction.

## Expected Behavior

A delegate CLI refuses to transmit unless delegation is opted in, regardless of which
gate — or no gate at all — invoked it. `enabled` is enforced where the transmission
happens, not only where it is reported.

## Actual Behavior

`enabled` was read only by `--print-enabled`. Any caller that skipped the probe, or
whose vendored probe was stale, transmitted freely.

## Environment

- Platform: darwin 25.6.0
- Version: `adlc-toolkit 5.0.0` (defect present since REQ-515 introduced the flag)
- Observed: 2026-09-01, while landing BUG-205 across five consumer repos

## Root Cause

REQ-515 introduced `enabled` together with the gate partial and treated the gate as the
enforcement point — reasonably, since the gate is what skills call. The CLI was written
as the thing the gate *protects*, not as a thing that protects itself. `--print-enabled`
was added for the gate to consult, and that became the flag's only reader.

The assumption held only as long as every caller ran a current gate. Vendoring broke it:
`/init` copies partials into each consumer repo, the skills prefer the local copy, and
nothing forces those copies forward. The moment a vendored gate lagged, the governance
control had no reader at all on the path that mattered.

Generalised: **a control that exists in exactly one layer, and that layer is the one
that gets copied around, is not a control.** The guard belongs in the artifact that is
installed once — the CLI — not in the one distributed by copy.

## Resolution

New `_common.require_delegation_enabled(prog)`, called by both CLIs immediately before
provider resolution and any network touch:

- **`adlc-read`** — after the `--dry-run` return, so a dry run (which packs the corpus
  locally and sends nothing) stays available for debugging while delegation is off.
- **`adlc-write`** — after the local guards (clobber, missing parent dir, unreadable
  context), so a user's typo is still reported as a typo rather than masked by the
  refusal.

Both placements are *before* `resolve_provider`, so a disabled setup reports "disabled"
rather than a confusing key/config error, and before `get_client`, so nothing is
constructed and no request is attempted.

Exit is non-zero with an actionable message naming both ways to opt in and pointing at
`--version` for the resolved value. Delegating skills already treat a non-zero exit as
"fall back and read directly" (BR-4), so a refusal degrades exactly like a missing
binary — no caller changes.

The probes are deliberately untouched: `--print-enabled` and `--version` are how an
operator *diagnoses* a disabled setup, and a guard that broke them would be
self-defeating.

### What this changes about BUG-205

It converts vendored-gate staleness from a data-governance failure into a correctness
one. A repo carrying an old gate now merely mis-reports and takes a fallback path; it
can no longer transmit. That is the property that should have existed from the start,
and it is why the two consumer repos whose `main` lagged behind their `staging` were
exposed at all.

### Verification

- Guard tests assert: `adlc-read` refuses and emits no corpus; `adlc-write` refuses and
  **leaves no partial target file**; `--dry-run` still works while disabled;
  `--print-enabled` and `--version` still work while disabled; and an opted-in run is
  **not** blocked (the guard must not become a second opt-out).
- **Fires before any network touch**, proven rather than asserted: pointed at an
  unroutable `--base-url` (`https://10.255.255.1/v1`), the guarded run refuses in
  ~0.02s. Un-guarded, the same invocation prints the exfiltration notice and then
  times out — so the test distinguishes "refused" from "tried and failed".
- **The tests fail without the guard.** Reverting only the two call sites fails exactly
  the three transmission tests and passes the rest.
- Five pre-existing tests failed on first run and were **corrected, not accommodated**:
  they set `ADLC_DELEGATE_BASE_URL` (deliberately *not* an opt-in signal under BR-11)
  and relied on reaching the notice without opting in. They now opt in explicitly. Two
  of them — the notice-suppression tests — would otherwise have kept passing
  **vacuously**, reporting "no notice" because the run was refused rather than because
  suppression worked (LESSON-602's failure shape).
- `pytest tools/delegate/tests` → **289 passed**; `partials/tests/run.sh` exit 0 (bash
  and zsh); `tools/lint-skills/check.sh` exit 0.
- No live delegate call at any point.

## Files Changed

- `tools/delegate/_common.py` — new `require_delegation_enabled`
- `tools/delegate/adlc-read` — guard after the `--dry-run` return, before provider
  resolution
- `tools/delegate/adlc-write` — guard after the local guards, before provider resolution
- `tools/delegate/tests/test_resolve_provider.py` — 6 guard tests
- `tools/delegate/tests/test_cli_warn.py` — `_env_without_key` now opts in, with the
  vacuity risk documented
- `tools/delegate/tests/test_version.py` — two notice tests opt in explicitly
- `tools/delegate/README.md` — documents the CLI-level enforcement
- `.adlc/bugs/BUG-206-delegate-clis-never-enforce-enabled.md` — this report

## Notes

The one-line form: **a governance control implemented only in the layer that gets copied
around is not a control — put the backstop in the artifact that is installed once.**

Severity `high` for the same reason as [[BUG-205]]: silent, outward-facing, and the
failure sends source content to a third party. It is filed separately rather than folded
in because the defects are genuinely different — BUG-205 was a wrong predicate, this is
an absent one — and because this one predates and outlives that fix. Had the guard
existed, BUG-205 would have been a telemetry bug.

Follow-up worth its own artifact: `/template-drift` already reports vendored-partial
staleness, but nothing *fails* on it. Now that a stale gate is merely incorrect rather
than dangerous, the case for a hard check is weaker — but the sync surface is still
silent drift by default, and the two repos found lagging here were found by hand.

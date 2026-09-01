---
id: BUG-208
title: "The shipped default model `kimi-k2.5` was retired by the provider — every delegated call 404s, and the failure surfaces as a raw Python traceback instead of an actionable message"
status: resolved
severity: high
created: 2026-08-31
updated: 2026-08-31
component: "tools/delegate"
domain: "adlc"
stack: ["python", "openai-sdk"]
concerns: ["correctness", "external-drift", "debuggability", "observability", "documentation"]
tags: ["delegation", "model-id", "404", "provider-drift", "moonshot", "kimi", "error-handling", "traceback", "api-error"]
introduced_by: []
attribution: none
---

<!--
attribution: none is the honest value. `git blame` on the root-cause line
(`_common.py:44`) yields 9f4ace8 "REQ-522: De-brand delegation surface" — an accepted
BR-2 trailer form (bare `REQ-xxx:` subject prefix). That candidate was considered and
rejected: REQ-522 renamed and relocated the constant during de-branding, it did not
choose the value. `kimi-k2.5` was a live, correct model id on the day it was written and
on the day REQ-522 moved it; the adjacent comment records it as verified against the
provider's docs in May 2026. The behavior changed because a third party retired an id,
not because a merge introduced a defect. Naming REQ-522 would attribute external drift
to the commit that happened to touch the line last — the false-attribution failure
REQ-593 BR-3 exists to prevent.

The secondary defect (no error handling in `complete()`) is a genuine omission rather
than drift, and it blames to the same commit for the same reason: REQ-522 moved the
function, REQ-412 wrote it without an error path. An omission dating to the original
tooling has no single introducing merge either.
-->

## Description

Delegation is fully broken against the shipped defaults. `_common.py:44` pins
`_DEFAULT_MODEL = "kimi-k2.5"`, and the provider has retired that id. Every delegated
call — `adlc-read`, `adlc-write`, and every skill that routes through them — fails with
HTTP 404.

There are two defects here, and the second is why the first was expensive to find:

1. **The pinned default is dead.** A live `GET /v1/models` against `api.moonshot.ai`
   on 2026-08-31 returns exactly four ids: `kimi-k2.6`, `kimi-k2.7-code`,
   `kimi-k2.7-code-highspeed`, `kimi-k3`. `kimi-k2.5` is not among them. The stale-ids
   comment directly above the constant is stale in the same way — it advertises
   `kimi-k2-thinking` and `kimi-k2-turbo-preview`, neither of which the endpoint serves.

2. **The failure has no handled path.** `complete()` raises `SystemExit` with a clean
   message for empty content and for a missing `choices` array, but nothing catches the
   SDK's HTTP errors. A 404 propagates out of `main()` as an unhandled
   `openai.NotFoundError` and prints a nine-frame traceback whose deepest frames are
   inside `site-packages/openai/_base_client.py`. The provider's own message — "Not found
   the model kimi-k2.5 or Permission denied" — is the last line of that dump, below the
   fold of most terminal reads.

The second defect makes the first read as a local install problem. A traceback ending in
someone else's library is the signature of a broken SDK or a bad key, and the provider's
`or Permission denied` disjunction actively reinforces that misreading.

## Reproduction Steps

1. Ensure delegation resolves to the shipped defaults (no `--model`, no
   `ADLC_DELEGATE_MODEL`, no `delegate.model` in `~/.claude/adlc/config.yml`).
2. Run any delegated call with the gate open:
   `ADLC_DELEGATE_ENABLED=1 adlc-read --paths VERSION --question "What version is this?"`
3. Observe a Python traceback terminating in
   `openai.NotFoundError: Error code: 404 - {'error': {'message': 'Not found the model
   kimi-k2.5 or Permission denied', 'type': 'resource_not_found_error'}}`.

Confirmed against a valid, funded key: the same key completes successfully on
`kimi-k2.6`, `kimi-k2.7-code`, and `kimi-k3` in the same session, which rules out auth
and quota as the cause.

## Expected Behavior

The shipped default names a model the default endpoint actually serves, so a
correctly-configured install delegates successfully with no per-machine override. When a
model id is nonetheless unavailable, the CLI exits with one line naming the model and the
knob to change it — never a traceback.

## Actual Behavior

Every delegated call on the shipped defaults 404s, and the operator is shown a raw
traceback that implicates the OpenAI SDK rather than the model id.

## Environment

- Platform: macOS (darwin 25.6.0), zsh executor, Python 3.9
- Version: adlc-toolkit 5.0.0
- Endpoint: `https://api.moonshot.ai/v1`, key via `MOONSHOT_API_KEY`

## Root Cause

A hardcoded third-party identifier with no drift detection and no handled failure path.

The id was correct when written and correct when REQ-522 moved it. Providers retire model
ids on their own schedule, so any pinned default is a value with an expiry date the
toolkit does not track and cannot be told about. Nothing in the repo asserts the default
is live — the test suite asserts only that resolution *returns* `kimi-k2.5`
(`test_resolve_provider.py:45,53`), which is a tautology over the constant and stays green
after the id dies. 283 delegate tests passed against a completely non-functional default.

That is the structural lesson: a test that asserts a constant equals itself provides no
coverage of the one property that matters about an external identifier, which is whether
the far side still honors it.

The observability half compounds it. This is LESSON-334's exact shape, one layer down.
That lesson documented `api-error` as a catch-all label that hides local path failures;
here the same catch-all hides a remote *model* failure, and the telemetry log duly
recorded `mode: fallback, reason: api-error` for months of runs
(`~/Library/Logs/adlc-skill-telemetry.log`) without ever naming the model. The label was
accurate and useless — which is what sent the previous investigation to audit the key and
the SDK, both healthy, exactly as LESSON-334 warned.

Worth separating two things: the gate is not implicated. `enabled: false` in the config
correctly held delegation off on this machine post-BUG-205, and the `no-flag` telemetry
rows are that gate working as designed. The `api-error` rows are the defect — they carry
`gate: pass`, meaning delegation was authorized and the transmission itself failed.

## Resolution

Re-pinned `_DEFAULT_MODEL` to `kimi-k2.6` — the direct general-purpose successor in the
same line, chosen over `kimi-k2.7-code` and `kimi-k3` because one value serves both the
prose-summarization (`adlc-read`) and code-generation (`adlc-write`) paths, and a
code-specialized model is the wrong default for the former. Verified by live round-trip
on both CLIs.

Replaced the stale-ids comment with ids from the live models list, dated, plus a note
directing the next reader to re-run the list rather than audit the key.

Added handled failure paths to `complete()`: `openai.APIStatusError` is mapped to one
actionable line per status — 404 names the model and the three knobs that override it,
401/403 points at `api_key_env` and `--version`, 429 names quota — and
`APIConnectionError` names the endpoint. Both re-raise as `SystemExit ... from None` so
no traceback survives. The `openai` import stays function-local, preserving BUG-056's
no-eager-import rule.

Not fixed here, and deliberately: nothing yet detects that the pinned default has gone
stale, so the next retirement will land the same way, just with a legible error. A
liveness check belongs in its own artifact — see Notes.

## Files Changed

- `tools/delegate/_common.py` — `_DEFAULT_MODEL` re-pinned to `kimi-k2.6`; stale-ids
  comment replaced with dated live values; new `_api_error_message()` helper;
  `complete()` gains handled `APIStatusError` / `APIConnectionError` paths
- `tools/delegate/README.md` — precedence table row 5 carries the new default
- `tools/delegate/tests/test_resolve_provider.py` — the two default assertions follow
- `.adlc/bugs/BUG-208-retired-default-model-404s-behind-a-raw-traceback.md` — this report

## Notes

The one-line form: **a pinned external identifier is a fact about someone else's system,
and a test that asserts it equals itself proves nothing about whether it still works.**

Severity is `high` because the failure is total rather than partial — every delegating
skill (`/spec` Step 1.6, `/wrapup` Step 4, `/analyze`, `/architect`, `/proceed` Phase 5)
loses its cheap I/O tier on every install running the shipped defaults, which is the
default population. It is not `critical`: the fallback path is correct and the work still
completes on the primary model, so the cost is tokens and latency, not wrong output. Note
the interaction with BUG-205 — installs that correctly disabled delegation never saw this,
so the defect's visible population is precisely the installs that opted *in*.

Two follow-ups worth their own artifacts:

1. **A liveness check for the pinned default.** The obvious form is a test that lists the
   endpoint's models and asserts the default is present — but that makes the suite require
   a network and a funded key, which is a real cost for a repo whose tests are otherwise
   hermetic. A better shape is probably an opt-in check (marker-gated, or folded into
   `check-delegation.sh`) that an operator can run when delegation misbehaves. The
   requirement is detection, not necessarily continuous detection.

2. **An audit of `api-error` as a telemetry value.** LESSON-334 flagged it in 2026-06 for
   hiding local path failures; it has now hidden a remote model retirement for months. The
   label is load-bearing for exactly the diagnosis it obstructs. Splitting it by the status
   information the new `_api_error_message()` already computes would make the telemetry log
   answer "why did delegation stop working" without a reproduction.

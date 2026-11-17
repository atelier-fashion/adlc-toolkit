---
id: BUG-281
title: "A probe row whose fail means \"the harness refused\" reads fail when the model never tried, and the trust gate then skips the whole run"
status: resolved
severity: medium
created: 2026-11-17
updated: 2026-11-17
component: "adlc/tools/adlc/harness-probe"
domain: "adlc"
stack: ["python"]
concerns: ["correctness"]
tags: ["harness-probe", "trust-then-headless", "git-write", "fence-vs-allowlist", "codex", "proof-of-submission", "retry", "gate"]
introduced_by: ["REQ-664"]
attribution: derived
---

## Description

On 2026-11-16 a full `adlc harness probe codex` on `main` (`fc62320`, codex-cli 0.166.0) read `trust-then-headless` `fail`, with `allowlist-loaded` `fail`. The probe then skipped every other probe as `precondition-unmet: trust-then-headless fail`. The launch's only output was the model saying it could not write outside its workspace. Codex's `--json` stream held no `command_execution` item, so the allowed `touch` was never submitted and the harness never refused it. The result was discarded.

`decide_plain` reads `fail` from an absent effect. That is right for a row whose fail means "the command ran and did the wrong thing". It is wrong for a row whose fail means "the harness refused the command", because a model that never tries looks the same. BUG-280 closed this for `ask-tier-deny`, BUG-279 retried the runner launches, and LESSON-847 states the rule. The remaining refusal rows had none of it.

## Reproduction Steps

1. Read the discarded result: its `trust-then-headless.sub_results.allowlist-loaded` evidence shows `sentinel B (allow): absent` and no command record.
2. Every other probe reads `precondition-unmet: trust-then-headless fail`.

## Expected Behavior

A refusal row reads `fail` only with proof the command was submitted. A launch that measured nothing is retried.

## Actual Behavior

A model's skip reads as the harness refusing. On the gate, one skip voids the whole run.

## Environment

- codex-cli 0.166.0, toolkit `main` at `fc62320`.

## Root Cause

Prior lessons consulted:
- LESSON-847 — A probe reads `refused` only with proof the command was submitted, taken from the harness's tool-record fields and never from model text
- LESSON-870 — A probe that asks a model to run commands measures the model first
- LESSON-874 — A retry under a new id must be covered by every rule rendered before the run

`_decide_trust`'s `allowlist-loaded`, `_decide_probe`'s generic branch (`git-write-*`) and `_decide_fence`'s three older variants call `decide_plain`, which needs no proof of submission. `_launch_one` launched these rows once.

Attribution: REQ-664, derived from blame of `decide_plain` and the `allowlist-loaded` reading.

## Resolution

`decide_submitted` wraps `decide_plain` for the refusal rows. Their `fail` stands only when one of the launch's asked commands is in a `command` field of the harness's own records, or the harness's stderr refusal names it. Otherwise the row reads `unknown / not-attempted`.

- **The asked commands:** each launch records them as `asked_cmd`: the gate's `touch`, `git commit`/`git push`, and the fence's `adlc_probe_function`. `_observe` adds `on_record`, `denied_here` and an `asked command on record` note.
- **Retries:** `SUBMISSION_PROBES` (`trust-then-headless`, `git-write-main`, `git-write-worktree`, the older `fence-vs-allowlist` variants) retry a not-attempted launch up to `SUBMISSION_ATTEMPTS = 5`. That excludes the gate where the allow is not a project file.
- **Out of scope:** rows whose fail means the command ran with the wrong result (`arg-substitution`, `shell-timeout`) are unchanged, since Claude's JSON lists denials but not commands that ran. So are rows that ask no command (the hook rows, `stdin-prompt`).

## Files Changed

- `tools/adlc/harness_probe.py`: `decide_submitted`, `SUBMISSION_ATTEMPTS`, `SUBMISSION_PROBES`; the asked commands in `_prepare`; the submission evidence in `_observe`; the three decision sites; retries in `_launch_one`.
- `tools/adlc/tests/fake_harness/fake_harness_impl.py`: a `model-skips` flag; the `main-only` and `needs-writable-roots` refusals are reported as denials.
- `tools/adlc/tests/test_harness_probe_unit.py`: `test_refusal_rows_need_proof_of_submission`.
- `tools/adlc/tests/test_harness_probe_e2e.py`: `test_trust_gate_skip_is_not_a_failed_allowlist`. `test_git_write_decided_from_remote`'s `claim-only` case now reads `unknown / not-attempted`: a model that only claims it pushed submitted nothing.
- `tools/adlc/README.md`, `CHANGELOG.md`.

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`).

Failing-first tests were still written. `test_refusal_rows_need_proof_of_submission` and `test_trust_gate_skip_is_not_a_failed_allowlist` both fail against `main`'s `harness_probe.py`, and both pass with the fix.

## Deployment

Merged as `d354f9e` ([#280](https://github.com/atelier-fashion/adlc-toolkit/pull/280)) on 2026-11-17. Nothing to deploy, since this is toolkit code. A full codex probe on the merged commit records the result.

## Lessons

- LESSON-875: when one oracle gets a proof-of-submission rule, sweep every oracle of the same shape.

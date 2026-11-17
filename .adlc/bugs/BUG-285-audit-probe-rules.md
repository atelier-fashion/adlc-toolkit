---
id: BUG-285
title: "`adlc harness probe`: rules an /adversary audit found could make a pass hollow, and two codex sub-results that recorded the model"
status: open
severity: medium
created: 2026-11-17
updated: 2026-11-17
component: "adlc/tools/adlc/harness-probe"
domain: "adlc"
stack: ["python"]
concerns: ["correctness", "security", "testing"]
tags: ["harness-probe", "codex", "proof-of-submission", "retry", "fresh-state", "fake-harness", "audit"]
introduced_by: ["REQ-664", "REQ-707"]
attribution: derived
---

## Description

On 2026-11-17 a full codex rerun on `main` (`55ea774`) read `runner-prefix` `unknown` on two launch timeouts. The operator had asked for an `/adversary` audit of the session's codex work if that run failed. Three independent adversary agents attacked the probe's decision logic, the amended specs and the fake harness.

The committed passes held up, with one exception. The audit found these defects:

1. **`stdin-prompt` is one unretried sample.** Codex's model mis-copied the reversed nonce (`ks1qprt7` for `ks1qrpt7`), so the variant REQ-662's codex launch matches read `fail` in the committed file. The two variants flipped across five committed runs.
2. **Retries discarded measured refusals.** The nonce was checked before proof of submission, so a submitted, blocked command read `ask-not-reached` when the model skipped its reply, and was retried. On `runner-positive`, `runner-baseline` and the `allow-only` controls that bias points toward `pass`. The saved logs hold more than 25 such discards.
3. **`wrapped-allow` could falsely pass.** The stderr refusal proof matched the ref, which a tidied plain `git push` also names.
4. **Proof of submission was a substring match.** A quotation of the asked line, or any line containing `git push`, counted.
5. **`_reset` left the checkout's remote-tracking refs** where the previous launch's push put them. `writable-roots-repo` started "behind origin", and its committed `fail` came from that and from the model chaining `git status && git push`.
6. **The three older `fence-vs-allowlist` variants passed on codex because of the sandbox.** Their sentinel sat in the workspace.
7. **BR-17(e)'s code accepted a `runner-baseline` refusal that was not on record**, against its own text.

The fake hid items 3 to 5. Its codex let a plain deny cover `git -C`, and no flag modelled a model tidying or chaining a command.

## Reproduction Steps

1. `git show 55ea774:.adlc/research/harness-probes/codex.json`: `stdin-prompt.sub_results.without-prompt-flag` is `fail`, and `git-write-worktree.sub_results.writable-roots-repo` is `fail` with `[ahead 1, behind 1]` in its stdout.
2. The new tests named below, run against `main`'s `harness_probe.py`.

## Expected Behavior

A verdict rests only on what the harness did, and a retry never replaces a measured reading.

## Actual Behavior

See the seven items above.

## Environment

- codex-cli 0.166.0, toolkit `main` at `55ea774`.

## Root Cause

Prior lessons consulted:
- LESSON-847 — A probe reads `refused` only with proof the command was submitted
- LESSON-875 — When one oracle gets a proof-of-submission rule, sweep every oracle of the same shape
- LESSON-869 — A fake CLI must print a record format only under the flag the real CLI needs for it
- LESSON-870 — A probe that asks a model to run commands measures the model first
- LESSON-873 — A probe effect built from two side effects can be met by two separate commands

BUG-279 to BUG-283 each added a rule at the place a live run failed. None of them was attacked as a whole. The proof rules were written loosely (substring, ref-only) because codex wraps each command, and the retry rule read the model's reply before the harness's record. REQ-664 built `_reset`, the nonce rows and the fence sentinel; REQ-707 built the record matching.

## Resolution

- **Measured readings:** `read_runner_launch` and `read_atd_launch` treat a submitted command with no effect as measured, even without the nonce reply.
- **Exact proof:** `is_submitted` compares the record's command, with its one shell wrapper stripped, with the asked command. `heads_submitted` handles the git rows: the push submitted cleanly, or the commit submitted and not landed. A stderr refusal must name the asked command.
- **Fresh state:** `_reset` restores `refs/remotes/origin/*`.
- **Fence sentinel:** under `_allow_dir`, as the runner sentinels are.
- **Nonce rows:** `stdin-prompt` and `session-start-context` retry a missed nonce, up to five attempts. Their pass cannot be forged.
- **BR-17(e):** the inference needs `runner-baseline` on record.
- **Fake:** codex's plain deny no longer covers `git -C`; new flags `tidy-git-c`, `chain-status-push`, `garble-nonce-once`. In the `refuse` and `refuse-silent` scenarios the model declines, so the fake no longer prints a harness denial record for a command the model never submitted. That phantom record had made a model's refusal read as the harness's.

Not fixed here:
- **`shell-timeout`** never checks that the sleep ran. The fake skips sleeps to keep the suite fast, so checking wall time needs a test seam first.
- **`harness/codex.yml` and the root `README.md` codex rows** still state the 2026-10-31 readings. They are adapter facts that the `harness-loss-table` lint ties together, so they belong to the REQ-655 / REQ-662 adapter work.
- **The fake's `needs-writable-roots` flag** models a codex that needs writable roots, which 0.166.0 does not.

## Files Changed

- `tools/adlc/harness_probe.py`
- `tools/adlc/tests/fake_harness/fake_harness_impl.py`
- `tools/adlc/tests/test_harness_probe_unit.py`: `test_a_measured_reading_is_never_retried`, `test_proof_of_submission_is_exact`; four fixtures now state what was on record.
- `tools/adlc/tests/test_harness_probe_e2e.py`: `test_nonce_row_retries_a_miscopied_nonce`, `test_tidied_git_c_is_not_a_held_deny`, `test_codex_plain_deny_does_not_cover_git_c`, `test_chained_push_is_not_a_refused_push`, `test_tracking_refs_are_reset_between_launches`.
- Expectations that changed, each because the old one rested on the fake's phantom record or on the nonce where a harness record now decides:
  - `test_scenario_verdicts`: a declined refusal row reads `unknown / not-attempted`, not `fail`, and a declined gate reads `unknown`.
  - `test_trust_and_fence_sub_results`: a declined fence is `unknown / not-attempted`.
  - `test_fresh_state_per_launch`: the declined controls read `unknown`.
  - `test_ask_tier_deny_variants` and `test_final_message_rules`: with the deny on the harness's record and the witness present, `deny-under-allow` is measured without the nonce reply. The nonce rows still never pass on a bare nonce, a tool-record nonce or a prompt echo.
- `tools/adlc/README.md`, `CHANGELOG.md`, REQ-664 and REQ-707 `requirement.md`.

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`).

Failing-first tests were still written. Six of the new tests fail against `main`'s `harness_probe.py` and pass with the fix: the two unit tests, and the nonce-row, tidied `git -C`, chained-push and tracking-refs e2e tests. `test_codex_plain_deny_does_not_cover_git_c` is a test of the corrected fake.

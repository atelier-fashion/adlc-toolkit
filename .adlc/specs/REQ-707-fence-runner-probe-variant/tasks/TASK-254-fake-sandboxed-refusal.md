---
id: TASK-254
title: "The fake's `sandboxed-refusal` flag, and the end-to-end tests for AC-10 and AC-11"
status: draft
parent: REQ-707
repo: adlc-toolkit
created: 2026-11-16
updated: 2026-11-16
dependencies: [TASK-253]
---

## Description

Give the fake harness a `sandboxed-refusal` flag that plays Codex running a refused command inside its sandbox (architecture ADR-8). Then prove the amended redirect control end to end on the fake.

## Files to Create/Modify

- `tools/adlc/tests/fake_harness/fake_harness_impl.py`:
  - `run_command`: when `sandboxed-refusal` is set and the harness is `codex`, a command that would be refused is still recorded as submitted, so it appears as a `command_execution` item under `--json`. It is then emulated in a sandbox: each output redirection whose target resolves inside the launch's working copy (`opts["cwd"]`) is created as an empty file, and nothing else runs.
  - Without the flag, or on any other harness, behaviour is unchanged.
  - Document the flag in the module docstring.
- `tools/adlc/tests/test_harness_probe_e2e.py`:
  - AC-10 on all six profiles: `runner-redirect`'s evidence `asked` names a target under `<repo>/.probe/`, and on codex the runner, tail and witness paths do not;
  - AC-11 on codex with `per-statement` and `sandboxed-refusal`: `runner-redirect` is refused with `redirect target: present`, `runner sentinel: absent` and the line on record; `runner-prefix` reads `pass` with `boundary: measured`; every other control and the baseline read as they do without the flag;
  - AC-11 with plain `perform` and `sandboxed-refusal`: `runner-redirect` is admitted with both files present;
  - `sandboxed-refusal` on a non-codex profile changes nothing;
  - the fresh-state spy (`test_runner_state_fresh_before_each_launch`) also scans `_sent(repo)` for `redirect-*`.

## Acceptance Criteria

- [ ] AC-10 holds on all six profiles.
- [ ] AC-11 holds: refused under `per-statement` + `sandboxed-refusal` (target present, runner absent, on record), with `runner-prefix` `pass`, `boundary: measured`; admitted under plain `perform`; no change on a non-codex profile.
- [ ] The existing `runner-prefix` e2e tests (`per-statement`, plain `perform`, `split-ask`, `first-statement-only`, `runs-all`, the BUG-279 retries) pass unchanged.
- [ ] The fake still imports nothing from `exec_matcher`.
- [ ] The fresh-state spy covers the redirect target on codex.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_redirect_target_in_working_copy_on_every_profile` | no |
| BR-4 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_sandboxed_redirect_target_is_not_admission` | yes |
| BR-8 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_sandboxed_refusal_ignored_off_codex` | yes |
| AC-2 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_runner_prefix_per_statement_passes` | no |
| AC-3 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_runner_prefix_whole_text_fails` | no |
| AC-8 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_runner_state_fresh_before_each_launch` | no |
| AC-10 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_redirect_target_in_working_copy_on_every_profile` | no |
| AC-11 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_sandboxed_redirect_target_is_not_admission` | yes |

## Technical Notes

- Gate on `harness == "codex"`, following `needs-writable-roots` (the fake imports nothing from `harness_probe`, so it cannot read `has_allow_required_path`).
- Find redirect targets with a small scan of `>`/`>>` operands outside quotes. The asked redirect line is `<stub> run probe > <target>`. A target is "inside" when its realpath starts with the realpath of `opts["cwd"]` plus `/`. Create any missing parent directory only inside the working copy.
- The stubs write absolute paths under the probe's outside directory on codex, so not running them is the faithful emulation.
- LESSON-869: a fake must model the real CLI's switches, not just its payloads.

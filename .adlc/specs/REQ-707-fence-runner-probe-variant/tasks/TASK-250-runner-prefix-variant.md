---
id: TASK-250
title: "The `runner-prefix` variant in the probe module: thirteen launches, stubs, observation and the decision rule"
status: draft
parent: REQ-707
repo: adlc-toolkit
created: 2026-11-09
updated: 2026-11-09
dependencies: []
---

## Description

Add the thirteen runner launches to `fence-vs-allowlist` and decide `runner-prefix` from them, outside the probe's existing disjunction (architecture ADR-1 to ADR-5).

## Files to Create/Modify

- `tools/adlc/harness_probe.py`:
  - `RUNNER_LAUNCHES`, appended to `_VARIANTS["fence-vs-allowlist"]["*"]`;
  - `_prepare_runner`, which writes `<run_dir>/tk/fence-run` and `fence-run-x`, checks `_SAFE_PATH`, and builds the allow set and the prompts;
  - `_reset`, which removes `<run_dir>/tk/`;
  - the runner branch of `_observe`;
  - `read_runner_launch`, with the `ask-split` rule;
  - `decide_runner_prefix`;
  - the `fence-vs-allowlist` branch of `_decide_probe`.
- `tools/adlc/tests/test_harness_probe_unit.py` — extend.

## Acceptance Criteria

- [ ] `plan(h, ["fence-vs-allowlist"]).count` is 16 on all six harnesses. The launch labels end with the thirteen `runner-*` names in BR-3's order.
- [ ] Each runner launch's allow set holds exactly one rule naming `<run_dir>/tk/fence-run`, a prefix rule, plus the exact witness rule and the routine set. `runner-baseline`'s holds none. No rule names `fence-run-x`. No rule's first token is an opener or a `NAME=` assignment.
- [ ] Both stubs are `0755` regular files outside `repo/` and `wt/`. Each writes `$0`, its arguments and `X=${X-unset}` to its own sentinel, with both paths as literals. `fence-run fail` exits 1, and `fence-run run …` exits 0. `_reset` leaves no stub and no runner sentinel.
- [ ] `decide_runner_prefix` over hand-built `Obs` maps gives every outcome of BR-5:
  - `pass/measured`;
  - `pass/none` (baseline admitted);
  - `fail` from a refused positive;
  - `fail` naming each admitted control;
  - `unknown` from a baseline that is `unknown`;
  - `unknown` from a control that is `unknown` with none admitted.
- [ ] `read_runner_launch` downgrades a refused control to `unknown / ask-split` when the runner sentinel exists and the asked line is in neither the raw nor the JSON-escaped captured output. It keeps it refused when the line is on record, or when the runner sentinel is absent. `runner-env-prefix` with `X=unset` is `ask-split`. It never turns any reading into admitted or `pass`.
- [ ] Benign path: with every control refused and the baseline refused, the verdict is `pass` and `evidence.admitted` is empty.
- [ ] The probe-level `status` of `fence-vs-allowlist` equals `disjunction` over the three existing variants for every combination of runner outcomes.
- [ ] `python3 -m pytest tools/adlc/tests/test_harness_probe_unit.py tools/adlc/tests/test_harness_probe_pins.py` passes.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_runner_prefix_outside_disjunction` | yes |
| BR-2 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_runner_allow_set_has_one_stub_rule` | no |
| BR-2 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_plain_stub_path_is_accepted` | yes |
| BR-3 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_runner_launch_plan` | yes |
| BR-4 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_runner_launch_reading` | no |
| BR-4 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_ask_split_downgrades_only` | yes |
| BR-5 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_decide_runner_prefix_rows` | yes |
| BR-6 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_runner_evidence_names_what_ran` | no |
| BR-9 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_runner_allow_uses_profile_spelling` | yes |
| BR-10 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_stub_is_posix_and_reads_no_env` | yes |
| AC-1 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_runner_launch_plan` | yes |

## Technical Notes

- Read each launch with `decide_variant`. Its `fail` (effect present) means admitted, and its `pass` means refused (ADR-4). Do not write a second three-way rule.
- The stubs are written with `_write_text(..., executable=True)`. Their bodies embed only literal, `_q`-quoted sentinel paths.
- On `gemini`, `spec.deny` is cleared as `_prepare_atd` does. The runner launches carry no deny, so nothing changes there.
- Codex rules render through `render_codex_rules`: the stub path is one token, so its `prefix_rule` is `["<path>"]`.

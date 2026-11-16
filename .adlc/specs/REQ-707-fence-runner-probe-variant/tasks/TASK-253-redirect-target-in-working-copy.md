---
id: TASK-253
title: "The redirect target moves into the working copy, and its effect is the runner sentinel and the target together"
status: draft
parent: REQ-707
repo: adlc-toolkit
created: 2026-11-16
updated: 2026-11-16
dependencies: []
---

## Description

Implement the probe-module half of the 2026-11-16 amendment (architecture ADR-8). `runner-redirect`'s target is built under `<repo>/.probe/` on every profile, and the launch's effect becomes the runner sentinel and the target, both present.

## Files to Create/Modify

- `tools/adlc/harness_probe.py`:
  - `_prepare_runner`: the redirect path uses `self._sent(repo)`, not `sdir`. The runner sentinel, tail sentinel and witness stay on `sdir`. Update the docstring, which says every sentinel sits where an allowed command writes.
  - `runner_effect`: `runner-redirect` returns `"runner+redirect"`; update its docstring.
  - `_observe_runner`: the effect table gains `"runner+redirect": runner is not None and redirect`. The table must name every value `runner_effect` returns.
- `tools/adlc/tests/test_harness_probe_unit.py`:
  - the `_runner` helper sets the runner sentinel for an admitted `runner-redirect`;
  - a test that `_prepare_runner`'s redirect path is under `_sent(repo)` on a codex-like engine with `outside` set, while the runner, tail and witness paths stay under `_allow_dir(repo)`;
  - `runner_effect("runner-redirect") == "runner+redirect"`;
  - AC-12 over hand-built observations.

## Acceptance Criteria

- [ ] On an engine with `outside` set, `_prepare_runner` for `runner-redirect` puts `paths["redirect"]` under `<repo>/.probe/`, puts `runner`, `tail` and `witness` under `outside/sent`, and the asked line names the `.probe/` target. On an engine without `outside`, every path is under `<repo>/.probe/`, as before.
- [ ] `_observe_runner` on a `runner-redirect` launch reports an effect only when both the runner sentinel and the target exist. Either one alone is no effect.
- [ ] AC-12: the runner sentinel present and the target absent read `refused` when the asked line is on record, and `unknown / ask-split` off record. Neither case ever reads `admitted`.
- [ ] Every value `runner_effect` returns is a key of `_observe_runner`'s effect table, checked over all of `RUNNER_LAUNCHES`.
- [ ] The existing unit tests pass. `test_harness_probe_unit.py`'s pin of the `runner-semicolon` effects dict is unchanged.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_redirect_target_is_in_the_working_copy` | no |
| BR-4 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_redirect_runner_without_target_is_partial` | yes |
| AC-10 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_redirect_target_is_in_the_working_copy` | no |
| AC-12 | test-case | `tools/adlc/tests/test_harness_probe_unit.py::test_redirect_runner_without_target_is_partial` | yes |

## Technical Notes

- Architecture ADR-8. The split mirrors `trust-then-headless` (`_prepare`'s hook sentinel `a` on `_sent`, allow target `b` on `_allow_dir`).
- `_reset` already runs `git clean -x` and `makedirs(_sent(cwd))` before every attempt, so no fresh-state code changes (LESSON-847 still governs refusal: an absent effect reads refused only with the line on record).
- Do not change `read_runner_launch`, `decide_runner_prefix` or the observation notes.
- Lessons in play: LESSON-847 (proof of submission), LESSON-768 (read what ran), LESSON-870 (a model-driven probe measures the model first).

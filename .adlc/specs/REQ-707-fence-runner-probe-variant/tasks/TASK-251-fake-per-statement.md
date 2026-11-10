---
id: TASK-251
title: "The fake harness's `per-statement`, `split-ask` and `first-statement-only` flags, the witness-then-fence prompt, and the offline scenarios on all six profiles"
status: draft
parent: REQ-707
repo: adlc-toolkit
created: 2026-11-09
updated: 2026-11-09
dependencies: [TASK-250]
---

## Description

Give the fake harness a per-statement judge (architecture ADR-6), so that one profile can yield `pass` and `fail`, and run REQ-707's acceptance scenarios end to end through `adlc harness probe` against it.

## Files to Create/Modify

- `tools/adlc/tests/fake_harness/fake_harness_impl.py` — the `per-statement` flag in `verdict()`, with its own quote-aware splitter; the `split-ask` and `first-statement-only` flags (ADR-6); `asked_commands` yields the backticked commands and then a whole fence as one asked command.
- `tools/adlc/tests/test_harness_probe_e2e.py` — the scenarios below. REQ-664's existing AC-7 test (`:270`) asserts the new names, and the fixed launch counts grow by thirteen.

## Acceptance Criteria

- [ ] AC-2: `perform` + `per-statement`, on each of the six profiles, gives `runner-prefix` `pass` with `boundary: measured`, every control refused, and the probe-level `status` equal to the disjunction of the three existing variants.
- [ ] AC-3: plain `perform` gives `fail`, and `evidence.admitted` is exactly `runner-subst`, `runner-backtick`, `runner-redirect`, `runner-semicolon`, `runner-or`, `runner-pipe`, `runner-background` and `runner-newline`. `runner-sibling` and `runner-env-prefix` are refused, because the fake's prefix match is word-bounded and anchored. `runner-and` is refused, because plain `run_command` splits on `&&`.
- [ ] AC-4: `perform` + `split-ask` gives every refusal control `unknown / ask-split`, and `runner-prefix` `unknown`. `perform` + `per-statement` + `first-statement-only` reads the compound controls as refused, and `runner-prefix` `pass`.
- [ ] AC-5:
  - `runs-all` gives `pass` with `boundary: none`;
  - a profile that withholds the runner allow from `runner-positive` gives `fail`;
  - `refuse`, `no-witness` and `refuse-silent` give `unknown` with REQ-664's reason.
- [ ] AC-7: a `--only fence-vs-allowlist` run writes all four variants in one entry, and the existing `merge_only` tests pass unchanged.
- [ ] AC-8: after every run, nothing remains under the temp root. A sandboxed `ADLC_TOOLKIT_ROOT/tools/adlc/fence-run` fixture is byte-identical and keeps its mtime. `fake_harness_impl.py` has no line importing `exec_matcher`.
- [ ] Benign path: the existing REQ-664 e2e scenarios pass unchanged apart from the named count and name updates.
- [ ] `python3 -m pytest tools/adlc/tests` passes.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-5 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_runner_prefix_per_statement_passes` | yes |
| BR-5 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_runner_prefix_whole_text_fails` | no |
| BR-6 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_runner_prefix_whole_text_fails` | no |
| BR-7 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_runner_variants_written_together` | yes |
| BR-8 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_fake_matcher_imports_no_exec_matcher` | yes |
| AC-2 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_runner_prefix_per_statement_passes` | yes |
| AC-3 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_runner_prefix_whole_text_fails` | no |
| AC-4 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_runner_prefix_ask_split_never_passes` | no |
| AC-4 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_runner_prefix_first_statement_only_passes` | yes |
| AC-5 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_runner_prefix_baseline_and_unknowns` | no |
| AC-6 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_unquotable_temp_root_refuses_before_launch` | no |
| AC-7 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_runner_variants_written_together` | yes |
| AC-8 | test-case | `tools/adlc/tests/test_harness_probe_e2e.py::test_runner_leaves_nothing_and_toolkit_untouched` | yes |

## Technical Notes

- The splitter scans characters outside single and double quotes for `;`, `&&`, `||`, `|`, `&` and newline. It is about thirty lines. Do not import `exec_matcher` or `shlex` for this.
- The match text of a fenced asked command is the whole fence under `per-statement`. The existing "Run this fenced block exactly as written" shape keeps its first-line match text, so REQ-664's fence variants read as before.
- Scenario flags already travel in the fake's environment. Add `per-statement` to the flag list in the module docstring.

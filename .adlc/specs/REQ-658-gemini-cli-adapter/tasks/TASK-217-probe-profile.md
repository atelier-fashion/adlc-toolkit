---
id: TASK-217
title: "Add the Antigravity probe profile"
status: complete
parent: REQ-658
created: 2026-10-31
updated: 2026-10-31
dependencies: []
repo: adlc-toolkit
---

## Description

One profile, its spellings, `skill-activation` on this harness, and `Profile.refusal_stderr`, so a headless refusal is decidable (ADR-7, REQ-664's follow-up). Teach the fake harness to act like `agy`, and scrub anything a transcript shows.

## Files to Create/Modify

- `tools/adlc/harness_probe.py` — profile, `render_rule`, hook config and output, `--settings`, argv, `refusal_stderr`
- `tools/adlc/tests/fake_harness/fake_harness_impl.py` — an `antigravity` mode
- `tools/adlc/tests/probe_helpers.py` — the binary
- `tools/adlc/tests/test_harness_probe_unit.py`, `test_harness_probe_e2e.py`, `test_harness_probe_cli.py` — the new paths

## Acceptance Criteria

- [ ] `--dry-run` lists every launch and every user file, launches nothing, and reports no user file edit
- [ ] A refused launch reads as reached, on a control and a variant
- [ ] A run on the fake harness restores everything and writes a scrubbed result

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | tools/adlc/tests/test_harness_probe_cli.py::test_dry_run_antigravity_edits_no_user_file | yes |
| BR-3 | test-case | tools/adlc/tests/test_harness_probe_e2e.py::test_antigravity_refusal_reads_as_reached | no |
| AC-3 | test-case | tools/adlc/tests/test_harness_probe_e2e.py::test_perform_all_pass | yes |

## Technical Notes

`harness_probe.py` is the one exempt place that branches on a harness name (BR-3). ADR-7, ADR-8.

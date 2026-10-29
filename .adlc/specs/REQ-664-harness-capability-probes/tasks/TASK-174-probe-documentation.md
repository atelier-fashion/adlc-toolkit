---
id: TASK-174
title: "Document the probes: tools/adlc README, CHANGELOG, plan §6"
status: complete
parent: REQ-664
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-171, TASK-173]
repo: adlc-toolkit
---

## Description

BR-15 documentation in the same change: `tools/adlc/README.md` gains an
`adlc harness probe` section (the forms, the catalogue, the result file, the exit
codes, the recovery procedure, the consumer mapping and BR-18's residual beside
every statement that a `pass` lifts an omission) and the `last_probe` column;
`CHANGELOG.md` gains an Unreleased entry; `.adlc/research/multi-harness-plan.md`
§6 gains one line per item naming its probe id or its `not-probed` reason.

## Files to Create/Modify

- `tools/adlc/README.md` — new section, subcommand table row, detect column
- `CHANGELOG.md` — Unreleased entry
- `.adlc/research/multi-harness-plan.md` — one annotation line per §6 item
- `tools/adlc/tests/test_harness_probe_docs.py` — new: the BR-15, AC-12, AC-13 and AC-18 document checks

## Acceptance Criteria

- [ ] the README names every probe id, the four forms, exit codes 0/1/2 and the `--recover` procedure
- [ ] the README states `env-prefix` and `shell-opener` stay `unverified`, `git-c` comes from `wrapped-allow`, `prefix` from `deny-under-allow`, and the single-launch residual
- [ ] every one of the twelve §6 items carries its annotation, asserted by a test

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-15 | test-case | `tools/adlc/tests/test_harness_probe_docs.py::test_plan_items_annotated` | no |
| BR-18 | test-case | `tools/adlc/tests/test_harness_probe_docs.py::test_readme_consumer_mapping_and_residual` | no |
| AC-12 | test-case | `tools/adlc/tests/test_harness_probe_docs.py::test_readme_and_changelog_carry_probe_text` | no |
| AC-18 | test-case | `tools/adlc/tests/test_harness_probe_docs.py::test_readme_consumer_mapping_and_residual` | no |

## Technical Notes

Keep the README free of enumerations that will rot: the
catalogue table is generated from nothing, so the docs test checks it against
`harness_probe.CATALOGUE`.

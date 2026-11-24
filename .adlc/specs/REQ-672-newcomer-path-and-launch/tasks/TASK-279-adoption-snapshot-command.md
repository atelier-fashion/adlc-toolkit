---
id: TASK-279
title: "Adoption snapshot command"
status: complete
parent: REQ-672
created: 2026-11-23
updated: 2026-11-23
dependencies: [TASK-278]
repo: adlc-toolkit
---

## Description

Write the maintainer-run command that appends one dated AdoptionSnapshot row to a private
file under `ADLC_HOME`, reading GitHub through `gh` and the Hugging Face Hub over HTTPS,
read-only (architecture ADR-7). It is tested only against a fake `gh` and stubbed Hub
responses; no test and no step of this task calls a real platform.

## Files to Create/Modify

- `tools/launch/adoption_snapshot.py` — the command: sources, classifier, row builder, file writer, CLI
- `tools/launch/tests/test_adoption_snapshot.py` — tests with a fake `gh` on `PATH` and a stubbed opener for the Hub

## Acceptance Criteria

- [x] With every source answering, one run appends exactly one JSON line carrying `date`, the five GitHub fields, the three Hub fields and a `sources` map, with the stubbed values
- [x] The default file is `<ADLC_HOME>/adlc/adoption-snapshots.jsonl`, resolved through `tools/adlc/adlc_home.py`; `--out` and `ADLC_ADOPTION_SNAPSHOT_FILE` override it; the file is created `0600`
- [x] A target that is a symlink is refused; a target inside the toolkit's own working tree is refused; a target under a temp `ADLC_HOME` is accepted
- [x] With `gh` reporting no login, the `github` and `github_traffic` sources are `auth-missing`, their fields are `null`, one `adoption_snapshot_failed` line names each, the exit status is 1, and the row is still appended
- [x] A source that fails never yields `0`: a test asserts `null` for every field of every failing class
- [x] `hf_space_runs` is always `null` with class `no-source`; Hub ids not given are `not-configured`; neither counts as a failure
- [x] The classifier's default is `unclassified`, and a table of real `gh` and Hub error texts maps each to its class, with negative rows showing a pattern does not take another class's text
- [x] Every `gh` call the command makes is `gh api <path>` with no `--method`, `-X`, `-f`, `-F` or `--input`; every Hub request is a GET with no body
- [x] A canary token set in `GH_TOKEN` and `HF_TOKEN`, and echoed in the fake `gh`'s stderr, appears nowhere in stdout, stderr or the file
- [x] The module imports only the standard library and the sibling `tools/adlc` modules it names

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-6 | test-case | `tools/launch/tests/test_adoption_snapshot.py::test_every_platform_call_is_a_read` | no |
| BR-7 | test-case | `tools/launch/tests/test_adoption_snapshot.py::test_failed_source_leaves_fields_null_never_zero` | yes |
| AC-7 | test-case | `tools/launch/tests/test_adoption_snapshot.py::test_unauthenticated_gh_reports_failed_and_prints_no_token` | yes |

Lessons: LESSON-581, LESSON-744, LESSON-014, LESSON-572, LESSON-019, LESSON-764

## Technical Notes

- Sources, fields, the closed class set and the exit rule are the table and text of architecture ADR-7. Field names are the spec's entity table.
- Reach `adlc_home` and `credential_redact` by putting `tools/adlc` on `sys.path` from this file's own location, the way `tools/dataset` reaches its siblings; do not copy either module.
- Open the file with `os.open(path, O_WRONLY | O_APPEND | O_CREAT | O_NOFOLLOW, 0o600)`; create a missing parent `0700`.
- "Inside the toolkit's working tree" means under the repository root this file lives in, compared on resolved paths.
- Class names and field names are fixed identifiers: validate them by format and never pass them through redaction (LESSON-744). Redact only backend stderr before printing a short reason.
- `top_referrers` is the list GitHub returns, cut to referrer, count and uniques.
- No sleep, no retry loop, a timeout on every subprocess and request. Python 3.9, stdlib only.
- The fake `gh` reads its answers from a directory keyed by the API path, so each source can fail independently.
- **No real binary may answer a test.** Every test that runs a script or driver builds `PATH` from the fake-binary directory plus `/usr/bin:/bin` only (`tools/adlc/tests/exec_helpers.py` `offline_path` is the precedent), and asserts from the fake's own log that the fake was what ran. A test must never reach a real `claude`, `gh`, `asciinema` or `agg`, nor the network.

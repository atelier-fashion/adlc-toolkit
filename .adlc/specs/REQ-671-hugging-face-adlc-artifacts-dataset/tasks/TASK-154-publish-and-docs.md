---
id: TASK-154
title: "Maintainer publish step, dependency isolation, and docs"
status: complete
parent: REQ-671
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-153]
---

## Description

The separate, explicit publish step (BR-6), the dependency isolation BR-10 requires, and
the docs that make re-export one documented command (BR-12).

## Files to Create/Modify

- `tools/dataset/publish.py` — `python3 tools/dataset/publish.py --dataset <out>/dataset --repo-id <owner/name>`; TTY-only; exactly the three dataset files; ancestor-of-main check; residue re-check with the DenyList committed at the source commit, and record counts against `revision.json`; a fresh export of the source commit must match byte for byte; `<owner>/<name>` repo id; summary and typed confirmation; then `create_commit` of the checked bytes (stale remote files deleted) and a tag, refusing a tag that exists
- `tools/dataset/requirements.txt` — `huggingface_hub` pinned, for the publish step only
- `tools/dataset/README.md` — what the export is, the export command, the report, review, publish, re-export on a later release, how to verify a published revision, tests
- `tools/dataset/tests/test_dataset_publish.py` — refusal paths with a stubbed client; import isolation
- `RELEASING.md` — an optional post-release step: re-export and publish the dataset
- `README.md` — a `### Tools` bullet pointing at `tools/dataset/`
- `CHANGELOG.md` — an `[Unreleased]` `### Added` entry

## Acceptance Criteria

- [ ] `publish.py` refuses with stdin not a TTY, with a dataset whose residue pass hits, with a `source_commit` not an ancestor of `main`, and when the typed repo id does not match; none of these call the client.
- [ ] On a match it commits the checked bytes of the three dataset files with `create_commit(repo_type="dataset")`, deleting any other remote file except `.gitattributes`, then creates a tag `v<toolkit_version>-<sha12>`; an existing tag refuses before the upload (stubbed client in tests).
- [ ] A dataset that differs by a byte from a fresh export of its source commit is refused (BR-7).
- [ ] `huggingface_hub` is imported only inside `publish.py`, and only inside a function; no other file under `tools/`, no skill, `install.sh`, `tools/adlc/checks.py` or `tools/delegate/requirements.txt` names it outside docs.
- [ ] The README documents the re-export as one command and the publish as a separate step after reading the report.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-6 | test-case | `tools/dataset/tests/test_dataset_publish.py::test_refuses_without_tty` | no |
| BR-6 | test-case | `tools/dataset/tests/test_dataset_publish.py::test_refuses_on_mismatched_confirmation` | no |
| BR-6 | test-case | `tools/dataset/tests/test_dataset_publish.py::test_publishes_on_confirmation_with_stub` | yes |
| BR-2 | test-case | `tools/dataset/tests/test_dataset_publish.py::test_refuses_dataset_with_residue` | no |
| BR-7 | test-case | `tools/dataset/tests/test_dataset_publish.py::test_publishes_on_confirmation_with_stub` | no |
| BR-7 | test-case | `tools/dataset/tests/test_dataset_publish.py::test_refuses_an_edited_card` | no |
| BR-7 | test-case | `tools/dataset/tests/test_dataset_publish.py::test_refuses_when_tag_exists` | no |
| BR-2 | test-case | `tools/dataset/tests/test_dataset_publish.py::test_refuses_records_that_disagree_with_revision` | no |
| BR-10 | test-case | `tools/dataset/tests/test_dataset_publish.py::test_hub_client_imported_only_by_publish` | no |
| BR-12 | test-case | `tools/dataset/tests/test_dataset_publish.py::test_readme_documents_one_reexport_command` | no |
| AC-12 | test-case | `tools/dataset/tests/test_dataset_publish.py::test_published_revision_loads` | no |
| AC-14 | test-case | `tools/dataset/tests/test_dataset_publish.py::test_readme_records_urls_after_publish` | no |

## Technical Notes

AC-12 and AC-14 are verified at publish, after merge. Their cases skip unless
`ADLC_DATASET_PUBLISHED_DIR` (a `git clone` of the published revision) and
`ADLC_DATASET_PUBLISHED=1` are set, and the README's publish checklist says to run them.
The stub replaces the client by injecting a fake `huggingface_hub` module into
`sys.modules`, so the test suite needs no network and no install.

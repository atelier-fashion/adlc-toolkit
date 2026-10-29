---
id: TASK-153
title: "Export CLI: git reads, scope check, records, references, report, card, deterministic write"
status: complete
parent: REQ-671
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-152]
---

## Description

`tools/dataset/export.py`, the one documented command (BR-12), ties the pieces together:
read the commit's `.adlc/` tree from git objects, enforce scope, scrub, parse, build
records and references, render the card, run the residue pass, and write the dataset and
the report.

## Files to Create/Modify

- `tools/dataset/export.py` — `python3 tools/dataset/export.py --commit <ref> --out <dir> [--repo <path>]`; the DenyList is read from the commit
- `tools/dataset/card_template.md` — the dataset card with `{{…}}` tokens for counts, schema, commit and version (BR-9)
- `tools/dataset/tests/test_dataset_export.py` — sandbox-git-repo tests and current-tree tests

## Acceptance Criteria

- [ ] Refuses a commit that is not an ancestor of `main` or `origin/main`, and an `--out` inside the repository.
- [ ] Per kind, `files_on_disk` equals the `git ls-tree` count; one record per file; the report counts match.
- [ ] A blob that does not decode as UTF-8 (or is a symlink) refuses the export with `scope-mismatch`.
- [ ] An unmapped path refuses the export naming it; the current tree's context docs, research notes, verification notes, adversary reports and counters are listed as excluded with reasons.
- [ ] The planted-fixture sandbox (fake AWS key, home path, personal email, DenyList name, `repo-context` entry used both ways, PR URL into a DenyList repo, organization URL to an unlisted repo, maintainer's name) exports with each replaced and listed in the report.
- [ ] A record with an unparseable frontmatter line is excluded and named; the export still succeeds.
- [ ] A residue hit refuses the export and no dataset directory is left behind.
- [ ] Two exports of one commit are byte-identical; an export of a later commit carries that commit in `revision.json` and the card.
- [ ] The current tree at `HEAD` exports without refusal, the report gives per-rule counts, and searching the output for every whole-word DenyList entry, every `repo-context` entry in a repository context, any organization URL other than `adlc-toolkit`, the maintainer's name and `/Users/` finds nothing.
- [ ] References: ids cited in a body are kept, flagged `resolved` or `dangling`; a reference to an id absent from the revision is `dangling`, not dropped.
- [ ] The card covers what the dataset is, the schema, collection, scrub rules, license (MIT), limitations (single maintainer, single project, mostly model-written, selection by what was committed), intended uses and a citation.
- [ ] When the `datasets` library is importable, the local export loads with `load_dataset("json", ...)` and its columns equal the card's schema; otherwise the case skips with the reason.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/dataset/tests/test_dataset_export.py::test_refuses_commit_not_on_main` | yes |
| BR-1 | test-case | `tools/dataset/tests/test_dataset_export.py::test_uncommitted_files_never_exported` | no |
| BR-2 | test-case | `tools/dataset/tests/test_dataset_export.py::test_residue_hit_refuses_and_writes_nothing` | no |
| BR-2 | test-case | `tools/dataset/tests/test_dataset_export.py::test_unparseable_record_excluded_export_succeeds` | yes |
| BR-4 | test-case | `tools/dataset/tests/test_dataset_export.py::test_undecodable_blob_refuses_scope_mismatch` | no |
| BR-4 | test-case | `tools/dataset/tests/test_dataset_export.py::test_unmapped_path_refuses` | no |
| BR-4 | test-case | `tools/dataset/tests/test_dataset_export.py::test_zero_files_and_zero_findings_report_differently` | yes |
| BR-7 | test-case | `tools/dataset/tests/test_dataset_export.py::test_two_exports_byte_identical` | no |
| BR-8 | test-case | `tools/dataset/tests/test_dataset_export.py::test_references_resolved_and_dangling` | no |
| BR-9 | test-case | `tools/dataset/tests/test_dataset_export.py::test_card_covers_required_topics` | no |
| BR-12 | test-case | `tools/dataset/tests/test_dataset_export.py::test_reexport_later_commit_new_revision` | no |
| AC-1 | test-case | `tools/dataset/tests/test_dataset_export.py::test_counts_match_ls_tree` | no |
| AC-2 | test-case | `tools/dataset/tests/test_dataset_export.py::test_planted_fixtures_replaced_and_reported` | no |
| AC-3 | test-case | `tools/dataset/tests/test_dataset_export.py::test_undecodable_blob_refuses_scope_mismatch` | no |
| AC-4 | test-case | `tools/dataset/tests/test_dataset_export.py::test_current_tree_exclusions_listed` | yes |
| AC-5 | test-case | `tools/dataset/tests/test_dataset_export.py::test_current_tree_exports_with_rule_counts` | yes |
| AC-6 | test-case | `tools/dataset/tests/test_dataset_export.py::test_card_covers_required_topics` | no |
| AC-7 | test-case | `tools/dataset/tests/test_dataset_export.py::test_reexport_later_commit_new_revision` | no |
| AC-8 | test-case | `tools/dataset/tests/test_dataset_export.py::test_two_exports_byte_identical` | no |
| AC-9 | test-case | `tools/dataset/tests/test_dataset_export.py::test_current_tree_output_has_no_residue` | no |
| AC-10 | test-case | `tools/dataset/tests/test_dataset_export.py::test_local_export_loads_with_datasets` | no |

## Technical Notes

Git reads follow `tools/adlc/lane_check.py` `read_base_config`: `ls-tree -r -z
--full-tree <sha> -- .adlc`, refuse non-`100644`/`100755` modes as unreadable, one `cat-file
--batch` for every blob, with a scrubbed git environment. Write into a `tempfile.mkdtemp` sibling
of `--out` and `os.replace` into place only after the residue pass is clean. The sandbox
fixture builds a throwaway repo with a `main` branch in `tmp_path`, with `HOME` pointed at
an empty directory and `GIT_*` scrubbed (the `test_lane_check.py` `_isolated_git`
precedent). The current-tree tests export `HEAD` of the toolkit checkout and skip when it
is not a git checkout.

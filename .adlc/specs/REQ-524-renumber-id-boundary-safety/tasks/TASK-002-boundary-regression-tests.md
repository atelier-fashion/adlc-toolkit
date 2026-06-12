---
id: TASK-002
title: "Regression test matrix for id-boundary safety"
status: draft
parent: REQ-524
created: 2026-06-12
updated: 2026-06-12
dependencies: [TASK-001]
---

## Description

Extend `tools/adlc/tests/test_renumber.py` with the full acceptance-criteria
matrix from REQ-524 — the prefix-sibling corruption guard, the dry-run
exclusion, the punctuation/slug/frontmatter/EOL rewrite cases, and the
selection/rewrite pattern-agreement invariant.

## Files to Create/Modify

- `tools/adlc/tests/test_renumber.py` — add (do not remove existing tests):
  - Fixture with both `REQ-120` and `REQ-1200` artifacts (dir + frontmatter +
    references), commit in sandbox git repo.
  - `test_sibling_prefix_untouched_after_apply`: `renumber REQ-120 REQ-999 --yes`
    rewrites every `REQ-120` ref AND leaves every `REQ-1200` file byte-identical.
  - `test_sibling_only_file_excluded_from_dry_run_plan`: a file containing only
    `REQ-1200` is not listed in the dry-run plan for `REQ-120`.
  - `test_boundary_rewrites_punctuation_slug_frontmatter_eol`: `REQ-120.`,
    `REQ-120)`, `REQ-120-slug`, `id: REQ-120`, and `REQ-120` at EOL all rewrite.
  - `test_dir_slug_rewrites`: `REQ-120-demo` directory renames to `REQ-999-demo`.
  - `test_dry_run_reports_per_file_match_count`: dry-run stdout contains a count.
  - `test_dry_run_output_is_repo_relative`: no absolute path in dry-run stdout.
  - `test_boundary_re_and_ere_agree`: the Python `re` and git-grep ERE helpers
    agree (match/no-match) on a fixed corpus including `REQ-120`, `REQ-1200`,
    `XREQ-120`, `REQ-120-slug`, `REQ-120.`.
  - `test_locate_old_ignores_sibling_prefix`: `_locate_old` for `REQ-120` does
    not return the `REQ-1200` artifact.

## Acceptance Criteria

- [ ] All new tests pass.
- [ ] Full `tools/adlc/tests/` suite passes (existing + new).
- [ ] Tests are offline (remote-collision monkeypatched), pure-stdlib, sandbox
      git repo under `tmp_path`.

## Technical Notes

- Mirror the existing test style in `test_renumber.py` (`_init_repo` helper,
  `monkeypatch.chdir`, `monkeypatch.setattr(renumber, "remote_collision", ...)`).
- The byte-identical assertion is the keystone — read the `REQ-1200` file before
  and after and assert equality of the raw bytes/text.

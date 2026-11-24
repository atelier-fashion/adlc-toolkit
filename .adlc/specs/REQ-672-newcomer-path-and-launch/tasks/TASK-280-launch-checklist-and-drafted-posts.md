---
id: TASK-280
title: "Launch checklist, drafted posts and the checklist validator"
status: complete
parent: REQ-672
created: 2026-11-23
updated: 2026-11-23
dependencies: [TASK-278]
repo: adlc-toolkit
---

## Description

Write the launch checklist as one dependency-ordered table, the drafts of every external
post, and the validator that holds the table to its rules (architecture ADR-8). Nothing
is posted or submitted by this task.

## Files to Create/Modify

- `docs/launch-checklist.md` — the decision (one coordinated launch week, after REQ-669, REQ-670 and REQ-671 are live), the table, and what each status means
- `docs/launch/show-hn.md` — Show HN draft
- `docs/launch/reddit-claudeai.md` — r/ClaudeAI draft
- `docs/launch/x-thread.md` — X thread draft
- `docs/launch/awesome-lists.md` — the community "awesome" lists for Claude Code to open pull requests against, and the entry text
- `tools/launch/launch_checklist.py` — parser and validator, with a CLI that prints the rows and exits non-zero on a violation
- `tools/launch/tests/test_launch_checklist.py` — validator tests and the test of the real checklist

## Acceptance Criteria

- [x] The table has the columns `id | item | depends on | owner | status | link` and every required id of ADR-8
- [x] Every row has an owner and a status from `pending`, `ready`, `live`, `done`; every dependency names an id in a row above it
- [x] The three post rows and `awesome-list-prs` each depend on `plugin-release`, `space`, `dataset` and `article` directly or through a row that does, and each names a draft file that exists
- [x] Every row whose work has not happened is `pending`: no row claims `live` or `done` for a release, Space, dataset, article, submission or post that this repository cannot show
- [x] Each draft says the maintainer posts it by hand, carries no adoption figure, and writes a link to anything not live as a named slot, not a URL
- [x] The validator fails a copy of the checklist with a missing required id, an unknown status, a dependency on a later row, a dependency on an unknown id, and a post row whose draft is missing; it passes the real file
- [x] The validator reports how many rows it read and fails on zero

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-5 | test-case | `tools/launch/tests/test_launch_checklist.py::test_real_checklist_has_every_required_item_in_dependency_order` | yes |
| AC-6 | test-case | `tools/launch/tests/test_launch_checklist.py::test_every_row_has_dependency_owner_and_status` | yes |

Lessons: LESSON-019, LESSON-764, LESSON-581

## Technical Notes

- The plugin release and the directory submission are REQ-669's deferred items, the Space is REQ-670's, the dataset and article are REQ-671's (`tools/dataset/article/draft.md` is the article draft; link it, do not copy it). `readme-quickstart-verified` and `demo-recording` are this REQ's.
- Write the drafts in plain, specific language: what ADLC is, the three outcomes of a run, the install commands, the quickstart. No superlatives and no claims about adoption.
- Do not state another REQ's progress in prose (LESSON-764). The status column is the one place progress is written.
- The validator is stdlib only and reads the file it is given; its default is the real checklist resolved from its own location.
- Export the status set and the required ids as constants: TASK-283's lint reads the same table.

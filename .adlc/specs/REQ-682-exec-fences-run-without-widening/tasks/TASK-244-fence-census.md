---
id: TASK-244
title: "Fence census: every fence an exec run can meet, with an id, a route and its placeholders"
status: draft
parent: REQ-682
created: 2026-11-09
updated: 2026-11-09
dependencies: [TASK-243]
---

## Description

Add `tools/adlc/fence_census.py`. It extracts every shell fence from the closed exec file set (`EXEC_FILES`, architecture ADR-5) and gives each one an id `<path>#<ordinal>:<sha8>` (ADR-2), a route (`direct`, `runner`, `engine` or `excised`, ADR-6) and its placeholders, checked against the closed `PLACEHOLDERS` table (ADR-3). It works on the text the model is actually given, so the pipeline sources are read after `exec_prompt`'s cuts, and the close-out sections after the close-out cuts. It writes the committed golden `harness/claude/exec-fence-census.json`.

## Files to Create/Modify

- `tools/adlc/fence_census.py` — new.
  - `EXEC_FILES`, `ENGINE` (id → reason), `EXCISED` (id → reason) and `PLACEHOLDERS` (name → full-match regex).
  - `fences(text)` returns `(ordinal, info, body)`.
  - `census(root, policy)` returns the records.
  - `invoked_files(text)` returns the `/<skill>` and `agents/<name>.md` names the text tells the model to invoke or follow.
  - `--write` and `--check` CLI.
- `tools/adlc/exec_prompt.py` — expose the cut text per source (a `pipeline_sections()` / `closeout_sections()` helper) so the census reads exactly what the prompt build delivers. No behaviour change.
- `harness/claude/exec-fence-census.json` — new golden. It must not sit under `harness/claude/rendered/`, which `render-parity` walks.
- `tools/adlc/tests/test_fence_census.py` — new.
- `tools/adlc/tests/fixtures/exec-fence/` — new: a copy of `proceed/phase-4-implementation.md` with an extra unrouted fence, a placeholder outside the three token shapes, and an unknown placeholder name.

## Acceptance Criteria

- [ ] Over the real tree, every fence in the census has a route. The golden equals a fresh census (`fence_census.py --check` exits 0).
- [ ] The census covers every fence in the delivered pipeline prompt and the close-out prompt, and every file `invoked_files` finds in the delivered text. The test counts fences from the prompt bytes and compares that count with the golden. It asserts no literal number, because a hand-kept count breaks with every skill edit (LESSON-403).
- [ ] A name `invoked_files` finds that is missing from `EXEC_FILES` fails with the name.
- [ ] Each `direct` fence's statements are all admitted by `exec_matcher.admits` over the rendered ExecPolicy (the positive half of AC-3, LESSON-779).
- [ ] The fixture's extra fence is reported unrouted, naming its id and the first statement `exec_matcher` refuses.
- [ ] Benign path: the unmodified tree reports zero unrouted fences.
- [ ] The three Phase-0 `git -C` fences are `engine`. Every fence holding a BR-24 token is `excised`.
- [ ] `python3 -m pytest tools/adlc/tests/test_fence_census.py tools/adlc/tests/test_exec_prompt.py` passes. `test_prompt_is_stable_bytes` is unchanged.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/adlc/tests/test_fence_census.py::test_every_fence_has_a_route` | no |
| BR-1 | test-case | `tools/adlc/tests/test_fence_census.py::test_census_covers_invoked_skills_and_agents` | no |
| BR-8 | test-case | `tools/adlc/tests/test_fence_census.py::test_unrouted_fixture_fence_is_named` | no |
| BR-8 | test-case | `tools/adlc/tests/test_fence_census.py::test_real_tree_has_no_unrouted_fence` | yes |
| AC-2 | test-case | `tools/adlc/tests/test_fence_census.py::test_direct_fences_admitted_statement_by_statement` | no |
| AC-2 | test-case | `tools/adlc/tests/test_fence_census.py::test_golden_matches_fresh_census` | yes |

## Technical Notes

- A fence is a block whose info string is `sh`, `bash` or `shell`. Indented fences count, as `phase-4-implementation.md:36` shows. Unlabelled blocks are prose, so the `worktree remove` example at `phase-0-setup.md:92-100` is not a fence. The census records that rule in its docstring.
- `sha8` is taken over the fence body as it appears in the file, before any transform, so the id is stable across machines.
- Placeholders are `<name>` tokens inside the fence body. Prose placeholders outside fences are not the runner's concern.
- The `PLACEHOLDERS` patterns must be tight enough that a hostile value fails: `component` admits no `..`, no leading `-` and no whitespace.
- `EXEC_FILES` is checked in both directions. A listed file the text no longer names is also reported, so the set does not rot (LESSON-712).

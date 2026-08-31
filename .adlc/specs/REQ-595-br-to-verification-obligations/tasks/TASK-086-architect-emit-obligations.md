---
id: TASK-086
title: "architect Step 4.5 — emit verification obligations per task"
status: draft
parent: REQ-595
created: 2026-08-31
updated: 2026-08-31
dependencies: [TASK-085]
repo: adlc-toolkit
---

## Description

Add `### Step 4.5: Emit Verification Obligations` to `architect/SKILL.md`,
between Step 4 (Break Into Tasks) and Step 5 (Publish the File Footprint).

Step 4.5 instructs `/architect` to write a `## Verification` block into each task
file it just created, naming every BR and AC that task discharges and the
concrete artifact that proves each one. It carries the kind-resolution algorithm,
the per-row validation contract, the detector/benign-path authoring rule, and the
cross-repo grouping rule.

Numbered 4.5 rather than renumbering Steps 5–7 (ADR-2): obligations must be
emitted after tasks exist and before the Step 5 footprint publish reads those
files, and `REQ-483` / `REQ-484` architecture docs reference `/architect` Step 5
by number.

## Files to Create/Modify

- `architect/SKILL.md` — insert `### Step 4.5: Emit Verification Obligations`
  after Step 4; extend the `## Quality Checklist` with an obligation-coverage item

## Acceptance Criteria

- [ ] Step 4.5 exists between Step 4 and Step 5; Steps 5, 6, 7 keep their numbers
- [ ] Step 4.5 states that each task gets a `## Verification` block listing every
      BR and AC that task discharges plus the artifact proving each (BR-1)
- [ ] The kind-resolution algorithm is written as: all task files `*.md` →
      `structural-check`; otherwise `test-case`, with the artifact shape resolved
      from that repo's `.adlc/config.yml` `stack:` when present, else from the
      repo's observed test layout (BR-3, BR-11)
- [ ] No framework name (`jest`, `pytest`, `xctest`, …) appears as a hardcoded
      literal in the step — stack values are read and used as-is (BR-3)
- [ ] The absent-config path is explicit and produces **no error**: a SKILL.md-only
      REQ in a repo with no `.adlc/config.yml` resolves to `structural-check`
      naming `tools/lint-skills` checks, with no test-file path emitted (BR-11, AC-4)
- [ ] Every emitted row is validated before write, regardless of origin: `rule`
      matches `^(BR|AC)-[0-9]+$` **and** the ordinal exists in the parent REQ;
      `artifact` is rejected if it contains `..`, then charset-validated; `kind` is
      one of the two enum values. Dropped rows are reported, not silently swallowed
      (BR-6, AC-8)
- [ ] The step states that a BR describing detection, refusal, or a halt should
      carry at least one `benign_path` obligation (BR-4 authoring side)
- [ ] Cross-repo: obligations group by the task's `repo:` frontmatter (absent →
      primary), each resolving against that repo's stack and artifact paths (BR-9)
- [ ] AC addressing (1-based ordinal) is stated, since the requirement template
      does not print AC numbers
- [ ] Any shell added is BSD/zsh-safe: no `\b` in `grep -E`, no bare `$<digit>`,
      no `status` variable, no unquoted word-splitting, `find` not bare globs (BR-8)
- [ ] `python3 tools/lint-skills/check.py --root .` exits 0 over the modified
      `architect/SKILL.md` and scans >0 files

## Technical Notes

Keep the step prose-first. Conventions mandate "keep bash minimal — prefer
Claude's own tool calls"; obligation emission is Claude authoring markdown, not a
shell pipeline. Any shell must survive `check_posix_fence` (no `local` in an
`sh`/`shell` fence), `check_arg_templating` (no bare `$<digit>`),
`check_cross_fence_fn`, and `check_cross_fence_var`.

Do **not** wire `adlc-write` / the delegate gate (ADR-4). Adding
`ADLC_DISABLE_DELEGATE` to this file would trigger `check_canonical`, which then
requires all five canonical telemetry literals plus the flag-file sidecar marks.
The validation contract above is unconditional and therefore strictly stronger
than validating only delegate output.

Reuse the sanitization already in Step 5 of the same file (reject `..`, then
charset-validate) rather than inventing a second pattern — LESSON-008.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | structural-check | `tools/lint-skills`: sentinels, balance, posix-fence over `architect/SKILL.md` | no |
| BR-3 | structural-check | `tools/lint-skills`: full-root run; kind-resolution prose reviewed against AC-5 (declared-stack → `test-case`) | no |
| BR-4 | structural-check | `tools/lint-skills`: full-root run; detector/benign-path authoring rule present in Step 4.5 | no |
| BR-6 | structural-check | `tools/lint-skills`: full-root run; per-row validation contract present and origin-agnostic | no |
| BR-8 | structural-check | `tools/lint-skills`: posix-fence, arg-templating, balance, cross-fence-fn, cross-fence-var over `architect/SKILL.md` | no |
| BR-9 | structural-check | `tools/lint-skills`: full-root run; cross-repo grouping rule present in Step 4.5 | no |
| BR-11 | structural-check | `tools/lint-skills`: full-root run in this repo, which has no `.adlc/config.yml` — the absent-config branch must produce no error | yes |
| AC-1 | structural-check | `tools/lint-skills`: this REQ's own task set, whose `## Verification` blocks collectively cite BR-1..BR-5 | no |
| AC-4 | structural-check | `tools/lint-skills`: this task's own obligations resolve to `structural-check` naming lint checks, with no test path and no missing-config error | yes |
| AC-5 | structural-check | `tools/lint-skills`: full-root run; declared-stack → `test-case` branch specified in Step 4.5 prose (no consumer project available in-repo to execute against) | no |
| AC-8 | structural-check | `tools/lint-skills`: full-root run; the `BR-99` / nonexistent-path drop rule present in the validation contract | no |
| AC-11 | structural-check | `tools/lint-skills`: full-root run; per-`repo:` grouping specified in Step 4.5, with absent-`repo:` → primary matching the Step 5 footprint attribution already in this file | no |

`benign_path` rows are the must-not-fire cases: BR-11 asserts the absent-config
branch stays silent rather than erroring, and AC-4 asserts no test-file path is
emitted for a markdown-only surface. AC-5 and AC-11 are specified rather than
executed — this repo has no `.adlc/config.yml` and is single-repo, so the
declared-stack and cross-repo branches have no executable surface here; that
limitation is recorded rather than papered over.

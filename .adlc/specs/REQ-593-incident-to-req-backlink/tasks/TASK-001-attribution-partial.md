---
id: TASK-001
title: "Create partials/attribution.sh with the blame→trailer→REQ derivation and its cross-shell test harness"
status: complete
parent: REQ-593
created: 2026-08-31
updated: 2026-08-31
dependencies: []
---

## Description

Implement the whole derivation algorithm as a sourceable POSIX shell partial, plus an
offline AC test matrix that runs under both bash and zsh. This is the load-bearing task —
BR-2, BR-4, BR-5, BR-6 and BR-10 all live here, and the two SKILL.md wirings (TASK-003,
TASK-004) are thin callers of these functions.

## Files to Create/Modify

- `partials/attribution.sh` — create; exposes `adlc_attr_req_context`,
  `adlc_attr_commit_reqs`, `adlc_attr_blame_reqs`, `adlc_attr_validate_req`,
  `adlc_attr_bugs_with_attribution`
- `partials/tests/attribution.test.sh` — create; sandbox-git AC matrix
- `partials/tests/run.sh` — modify; add the new harness to the `run_all` positional list

## Acceptance Criteria

- [ ] `adlc_attr_req_context` reads **subject and body** (`git log -1 --format='%s%n%b'`),
      not blame's subject-only `summary` (ADR-3, AC-3)
- [ ] Three forms accepted in precedence order: bracketed `[REQ-xxx]`/`[TASK-xxx]` anywhere;
      `REQ-xxx:` subject prefix; `<type>(REQ-xxx):` scope (AC-2, AC-4)
- [ ] `<type>(BUG-xxx):` scope yields **no** candidate from that commit (AC-5)
- [ ] `[TASK-yyy]` resolves only within the REQ context of the same commit, by reading
      `.adlc/specs/<that-req>-*/tasks/TASK-yyy*.md` (AC-1); a bare `[TASK-001]` with no REQ
      context yields no candidate and does not halt with multiple candidates (AC-6)
- [ ] `adlc_attr_validate_req` enforces `^REQ-[0-9]{3,6}$` **and** existence of
      `<primary>/.adlc/specs/<id>-*/`; `REQ-999999` is dropped, not written (AC-8)
- [ ] Existence check resolves against the **primary** repo even when blame ran in a
      sibling (AC-12, ADR-5)
- [ ] `adlc_attr_blame_reqs` emits sorted-unique ids; two distinct valid REQs both surface
      (AC-9 precondition)
- [ ] `adlc_attr_bugs_with_attribution` scans `.adlc/bugs/*.md` only, writes nothing (AC-11)
- [ ] Harness passes under **both** `bash` and `zsh` via `sh partials/tests/run.sh` (AC-10)
- [ ] `python3 tools/lint-skills/check.py` exits 0; `python3 -m pytest tools/ -q` still 484 passed

## Technical Notes

Follow `partials/id-alloc.sh` and `partials/forge.sh` for structure, and
`partials/tests/id-alloc.test.sh` for the sandbox-repo harness shape (`pass`/`fail`/`check`
helpers, `HERE`/`PARTIALS`/`ROOT` resolution, `FAILS` counter, exit non-zero on any fail).

BR-6 hazards to honor: `grep -E` never `-P` and never `\b` (LESSON-013); `printf` not
`echo`; `while IFS= read -r` not `for x in $var` (zsh does not word-split — BUG-118);
no variable named `status`; `find` not a bare glob for possibly-empty matches (LESSON-335).

Register the harness in `run.sh` by adding it as a **positional argument** to `run_all`,
never by appending to a space-joined string — that is the exact BUG-118 regression.

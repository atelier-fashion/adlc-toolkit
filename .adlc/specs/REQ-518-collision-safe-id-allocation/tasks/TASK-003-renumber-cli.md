---
id: TASK-003
title: "adlc renumber helper (tools/adlc/renumber.py) + additive CLI registration"
status: draft
parent: REQ-518
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-002]
---

## Description

Ship the automated renumber helper (BR-9) as a new subcommand of the REQ-519
umbrella `adlc` CLI, registered ADDITIVELY in the data-driven `SUBCOMMANDS`
table (REQ-519 BR-11) — no dispatch-logic edits, so it merges cleanly alongside
REQ-516's concurrent subcommand.

## Files to Create/Modify

- `tools/adlc/renumber.py` (NEW) — `main(argv) -> int`, pure stdlib.
- `tools/adlc/adlc.py` (EDIT, additive) — one `SUBCOMMANDS` entry + one
  `_cmd_renumber` lazy handler. NO changes to `main()`, `_usage()`, or dispatch.

## Acceptance Criteria

- [ ] `adlc renumber <KIND-old> <KIND-new>` validates both ids against strict
      per-kind regexes (`^REQ-[0-9]{3,}$`, `^BUG-...`, `^LESSON-...`); refuses
      ids that fail the regex (LESSON-008 — no traversal/garbage).
- [ ] Refuses to run if `<KIND-new>` fails the same remote-collision check —
      shells out to `partials/id-recheck.sh` so there is ONE collision authority
      (BR-9, depends on TASK-002).
- [ ] Renames the artifact dir/file, rewrites frontmatter `id:`, and rewrites
      in-repo cross-references to the old id; a repo-wide grep finds zero
      remaining old id outside git history (AC).
- [ ] Prints a dry-run unified diff and requires approval BEFORE mutating;
      mutation is atomic (temp + rename, never partial — LESSON-006).
- [ ] For a REQ with an existing branch, prints (does NOT run) the exact branch
      rename/push/delete commands.
- [ ] Registration is additive only: `SUBCOMMANDS["renumber"]` + `_cmd_renumber`;
      `git diff` on `adlc.py` touches no existing dispatch lines.
- [ ] `adlc renumber --help` and the usage listing show the new command.

## Technical Notes

Mirror `doctor.py`'s shape: `main(argv) -> int`, `argparse`, pure stdlib, lazy
import in the handler. The handler:
```python
def _cmd_renumber(argv):
    import renumber
    return renumber.main(argv)
```
plus `SUBCOMMANDS["renumber"] = {"handler": _cmd_renumber, "help": "..."}`.
Keep the diff against `adlc.py` to exactly these two additions so REQ-516's
concurrent registration does not conflict.

---
id: LESSON-707
title: "A check that fails open cannot be the only guard in front of a destructive local operation"
component: "tools/adlc/renumber"
domain: "id-allocation"
stack: ["python"]
concerns: ["data-loss", "correctness"]
tags: ["fail-open", "renumber", "os-rename", "no-clobber", "collision", "bug-245"]
req: BUG-245
created: 2026-10-26
updated: 2026-10-26
---

## What happened

`adlc renumber` relied on the remote recheck to decide whether the new id was
free. That recheck fails open by design (REQ-518 BR-3): it can find a
collision, never invent one, so "offline", "no helper" and "the artifact isn't
pushed yet" all read as "free". Right after it, the command ran a bare
`os.rename`, which replaces an existing file on POSIX. With the remote out of
the picture, renumbering onto a local `BUG-010-crash.md` silently destroyed it
and reported success (BUG-245). Each step was reasonable on its own. Together
they made a "no news" answer authorize data loss.

## Lesson

- When a guard is allowed to fail open, check what sits behind it. If that is
  destructive (an overwrite, a delete, a force-push), add a guard that
  **cannot** fail open: here, the local tree, which is authoritative for local
  files.
- Don't make the destructive primitive trust the planner either. `os.rename`,
  `shutil.move` and `mv` all clobber. Use a no-clobber move so a destination
  that appears after planning is refused, not replaced. For files, `os.link` +
  `os.unlink` fails with `EEXIST` and has no check-then-act window. For
  directories, or a filesystem without hard links, Python's standard library
  only offers a check just before `rename`, so state the window that leaves
  rather than claiming "never". Closing it needs `renameat2(RENAME_NOREPLACE)`
  or `renamex_np(RENAME_EXCL)`.
- Key the backup check on the same identity the primary uses. Here the remote
  checks compare decimal numbers, so a string-keyed local check let `BUG-0010`
  duplicate `BUG-010` (the BUG-245 follow-up). Prove the guard's code path is
  reachable: a test whose earlier check catches the case first never exercises
  the guard it claims to test.
- Refuse before any outward side effect (here, the remote id reservation), so a
  refusal costs nothing.

## Why It Matters

A degraded network posture is supposed to cost verification, not data. When it
costs data, the user only finds out later, often after the overwrite has been
committed.

## Applies When

Any tool or skill step that renames, moves, writes or deletes based on a
"is this free / safe?" answer from a remote, a cache or a best-effort probe,
especially one documented as non-blocking when degraded.

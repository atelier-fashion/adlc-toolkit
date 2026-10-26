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
  `shutil.move` and `mv` all clobber. Use a no-clobber move (`os.link` +
  `os.unlink` for files, which fails with `EEXIST` with no check-then-act
  window) so a destination that appears after planning is refused, not replaced.
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

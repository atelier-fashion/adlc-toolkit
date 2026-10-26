---
id: BUG-245
title: "adlc renumber overwrites an existing local artifact when the new id is already taken locally"
status: resolved
severity: high
created: 2026-10-26
updated: 2026-10-26
component: "tools/adlc/renumber"
domain: "id-allocation"
stack: ["python"]
concerns: ["data-loss", "correctness"]
tags: ["renumber", "collision", "fail-open", "os-rename", "offline"]
introduced_by: [REQ-518]
attribution: derived
---

## Description

`adlc renumber OLD NEW --yes` checks whether `NEW` is taken only on the
remote (`remote_collision`, via `id-recheck.sh`). It never checks the local
working tree. The remote check fails open by design (BR-3): an unreachable
remote, a missing helper or an unpushed local artifact all count as "no
collision". `reserve_new_id` then reports `degraded`, which only warns. The
rename is a bare `os.rename`, which on POSIX silently replaces an existing
destination file. The destination bug's or lesson's content is lost, and the
command prints `Applied.` and exits 0.

A second symptom has the same cause. When the local artifact for `NEW` has a
different slug (`BUG-010-other.md`), nothing is overwritten, but the repo ends
up with two `BUG-010` files and no warning.

Reported externally by Perch Scan, and reproduced locally.

## Reproduction Steps

1. In a git repo with no remote, create `.adlc/bugs/BUG-005-crash.md` and
   `.adlc/bugs/BUG-010-crash.md` with different content.
2. Run `python3 tools/adlc/renumber.py BUG-005 BUG-010 --yes`.

## Expected Behavior

Refuse with a non-zero exit, name the existing local `BUG-010` artifact, and
mutate nothing.

## Actual Behavior

It prints `WARNING — could not reserve 'BUG-010' on the remote … Proceeding`,
then `Applied. BUG-005 is now BUG-010.`, and exits 0.
`BUG-010-crash.md` now holds BUG-005's content, and the original BUG-010 is
gone.

## Environment

- Platform: macOS / Linux (POSIX `rename(2)` semantics)
- Version: adlc-toolkit `main` @ 770cce1

## Root Cause

`tools/adlc/renumber.py` `main()` treats the remote as the only collision
authority for the new id. Step 2 (`remote_collision`) and step 4b
(`reserve_new_id`) both degrade to "proceed" when the remote can't answer,
and neither looks at the local tree. That is correct for those functions,
since a recheck can only find a collision and never invent one. But nothing
else covers the local case. Step 5 then calls `os.rename(old_path, new_path)`,
and for a file `rename(2)` atomically replaces an existing destination. So the
two things that would have caught it, a local existence check and a no-clobber
rename, are both missing. The remote-only check and the bare `os.rename` came
in with REQ-518 (`git blame`). REQ-546 later added the degraded-reservation
warning but didn't change the fail-open posture.

For REQ directories the overwrite is narrower: `os.rename` onto a non-empty
directory fails with `ENOTEMPTY`, which surfaced as a raw traceback, while an
empty destination directory is silently replaced. The duplicate-id symptom
applies to every kind.

## Resolution

There are two guards, one per missing piece:

1. **Local-collision refusal** (`main()` step 3b). After the plan is built,
   `_locate_old(root, new_id)` looks for any local artifact already carrying
   the new id, under any slug. A plain `lexists` check on the computed
   destination path covers anything that lookup misses. Either hit refuses
   with exit 1 and names the existing path. This runs before the dry-run
   output and before `reserve_new_id`, so a refused renumber neither mutates
   nor burns a remote reservation. The local tree is authoritative here and
   does not fail open: a file that exists is a collision, whatever the remote
   says.
2. **No-clobber rename** (`_rename_no_clobber`). This replaces the bare
   `os.rename`. Files move with `os.link` + `os.unlink`, and `link` fails with
   `EEXIST` atomically. If the filesystem has no hard links, it falls back to
   `rename` behind a `lexists` check. Directories rely on `rename` failing
   onto a non-empty directory, with the `lexists` check covering an empty
   one. A destination that appears between planning and applying is refused
   with exit 1 and nothing changed.

Verified: the new tests fail (8/8) against the pre-fix `renumber.py` and pass
with the fix. The full `tools/adlc` suite passes (188). The original
reproduction now exits 1 and leaves `BUG-010-crash.md` intact.

## Files Changed

- `tools/adlc/renumber.py`: local-collision refusal (step 3b),
  `_rename_no_clobber`, docstring safety-posture bullet.
- `tools/adlc/tests/test_renumber.py`: BUG-245 regression tests covering a
  same-slug overwrite, a different-slug duplicate, a dry-run refusal, an empty
  REQ dir, a destination that appears after planning, and `_rename_no_clobber`
  in both directions.
- `CHANGELOG.md`: `[Unreleased]` → Fixed entry.

## Deployment

- Merged to `main` in atelier-fashion/adlc-toolkit#181 on 2026-10-26. The toolkit is a symlink install, so `main` is live as soon as it merges. There is no Cloud Run or iOS target.

## Follow-up (adversary review, 2026-10-26)

An `/adversary` review of #181 found three gaps, fixed in one follow-up PR:

1. **Zero-padded ids got past the local check.** It compared ids as text, but
   the remote checks compare decimal numbers. So `renumber BUG-005 BUG-0010 --yes`
   beside `BUG-010-other.md` still produced two bugs numbered 10. Step 3b now uses
   `_locate_by_number`. A renumber to the same number with different padding is
   refused with exit 2.
2. **"Never replaced" overstated the guarantee.** Only the hard-link path for
   files has no window. Directories, and filesystems without hard links, rely on
   a check just before `rename`. The docstrings, CHANGELOG and LESSON-707 now
   say so.
3. **No test reached the hard-link guard.** The existing race test was caught by
   the up-front check, and disabling the link branch left every test green. New
   tests bypass the up-front check so `link` has to refuse, and cover the
   fallback for filesystems without hard links in both directions.

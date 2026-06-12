---
id: TASK-001
title: "Boundary-anchored id matching in renumber.py (selection, content, filename, counts, relpaths)"
status: draft
parent: REQ-524
created: 2026-06-12
updated: 2026-06-12
dependencies: []
---

## Description

Replace every boundary-free id operation in `tools/adlc/renumber.py` with a
single shared boundary-anchored pattern so renumbering `KIND-N` never touches a
`KIND-N<digit>` sibling. Implements BR-1, BR-2, BR-3, BR-5; preserves BR-4.

## Files to Create/Modify

- `tools/adlc/renumber.py` — modify:
  - Add `_id_boundary_re(artifact_id)` → compiled `re` with
    `(?<![A-Za-z0-9])<escaped-id>(?!\d)`.
  - Add `_id_boundary_ere(artifact_id)` → equivalent git-grep ERE string
    `(^|[^A-Za-z0-9])<escaped-id>([^0-9]|$)` (selection only; Python pattern is
    the arbiter).
  - `_rewrite_file`: use `pat.subn(new_id, original)`; return `(diff, count)`;
    diff `fromfile`/`tofile` use `os.path.relpath(path, root)`. Thread `root`
    into the call.
  - `_renamed_path`: boundary `subn(new_id, base, count=1)` instead of
    `str.replace`.
  - `_grep_references`: `git grep -lE -- <ere>`; os.walk fallback uses
    `_id_boundary_re(old_id).search(text)`.
  - `plan`: pair each ref with its boundary match count; drop refs whose count
    is 0 (corrects git-grep over-selection).
  - `main`: dry-run prints repo-relative paths and per-file `(<n> match(es))`;
    rename line repo-relative. Branch-command block unchanged.

## Acceptance Criteria

- [ ] `_id_boundary_re("REQ-120")` matches `REQ-120`, `REQ-120-slug`, `REQ-120.`,
      `REQ-120)`, `id: REQ-120`, `REQ-120` at EOL; does NOT match inside
      `REQ-1200` or `XREQ-120`.
- [ ] Renumbering `REQ-120` leaves a file containing only `REQ-1200` byte-identical.
- [ ] A file containing only `REQ-1200` is excluded from the dry-run ref list
      when renumbering `REQ-120`.
- [ ] Dry-run reports a per-file match count and uses repo-relative paths (no
      absolute path in stdout).
- [ ] `--yes` semantics, atomic write, strict arg validation, kind-mismatch and
      remote-collision refusal all unchanged.
- [ ] Existing `tools/adlc/tests/test_renumber.py` passes unchanged.

## Technical Notes

- Boundary is **digit-based** (`(?!\d)`), not word-based (`\b`) — `REQ-120-slug`
  MUST still rewrite (see architecture ADR-1). Do not use `\b`.
- One pattern authority: selection ERE and rewrite `re` come from the helper
  pair so they cannot drift (BR-2). Add a unit test asserting they agree on a
  fixed corpus.
- Pure standard library only (`re`, `os`, `difflib`, `subprocess`, `tempfile`) —
  renumber must run on a delegation-free machine.
- POSIX/portable; no f-string in the ERE that could inject (id is strict-validated
  AND `re.escape`d).

---
id: REQ-524
title: "adlc renumber: id-boundary-safe rewrites — Architecture"
status: draft
created: 2026-06-12
updated: 2026-06-12
---

# Architecture — REQ-524

## Overview

`tools/adlc/renumber.py` rewrites an artifact id repo-wide using boundary-free
operations: file selection via `git grep -l -- <old_id>` (and an os.walk
`old_id in text` fallback), content rewrite via `str.replace(old_id, new_id)`,
and filename rewrite via `base.replace(old_id, new_id, 1)`. None of these
respect an id boundary, so renumbering `REQ-120` corrupts the unrelated
`REQ-1200` artifact (adversarial finding M2). The strict id regexes
(`KIND_PATTERNS`) validate only the command's *arguments*, never the content
match.

The fix is **one boundary pattern, defined once, used everywhere** — for file
selection, content substitution, and filename rewrite — so selection and
rewrite provably cannot drift (BR-2's explicit anti-drift requirement). The id
matches only when **not followed by a digit** and **not preceded by an
alphanumeric**, so `REQ-120` never matches inside `REQ-1200` but still rewrites
in slugs (`REQ-120-demo`), frontmatter (`id: REQ-120`), punctuation
(`REQ-120.`, `REQ-120)`), and at end-of-line.

This is strictly internal to `renumber.py` — the public CLI surface, exit codes,
`--yes` semantics, atomic-write, strict argument validation, and the
remote-collision refusal are all preserved unchanged (BR-4). The only behavioral
deltas are: (a) the boundary now protects sibling-prefix ids, (b) the dry-run
reports a per-file match count (BR-3), and (c) diff/plan output is repo-relative
(BR-5).

## Components

### 1. `_id_boundary_re(artifact_id)` (NEW) — the single pattern authority (BR-1, BR-2)

A module-level helper returning a compiled `re.Pattern`:

```python
def _id_boundary_re(artifact_id):
    return re.compile(rf'(?<![A-Za-z0-9]){re.escape(artifact_id)}(?!\d)')
```

- `re.escape` neutralizes the `-` and any regex-meta in the id (defense-in-depth;
  ids are already strict-validated, but the escape keeps the helper safe for any
  caller).
- `(?<![A-Za-z0-9])` — not preceded by an alphanumeric (so `XREQ-120` and
  `1REQ-120` do not match; start-of-string is allowed since a negative
  lookbehind is satisfied at position 0).
- `(?!\d)` — not followed by a digit (so `REQ-1200` does not match `REQ-120`).
  A trailing `-`, `.`, `)`, whitespace, or EOL all satisfy the boundary, so
  slugs and punctuation still rewrite.

Every match site below calls this one factory. No second pattern definition
exists, so selection and rewrite cannot diverge (BR-2).

### 2. `_rewrite_file` — boundary-anchored substitution + match count (BR-1, BR-3, BR-5)

- Replace `original.replace(old_id, new_id)` with
  `pat.subn(new_id, original)` where `pat = _id_boundary_re(old_id)`. `subn`
  returns `(updated, n)`; `n` is the per-file match count surfaced to the
  dry-run plan (BR-3).
- The unified-diff `fromfile`/`tofile` use the **repo-relative** path
  (`os.path.relpath(path, root)`), not the absolute path (BR-5, LESSON-021).
- Atomic write (`mkstemp` + `os.replace`) is unchanged (BR-4).
- Return signature changes from `str` (diff) to `(diff, count)` so `plan`/`main`
  can report counts; callers updated accordingly.

### 3. `_renamed_path` — boundary-anchored basename rewrite (BR-1)

Replace `base.replace(old_id, new_id, 1)` with a single boundary-anchored
`subn(new_id, base, count=1)` against the basename. In practice the basename is
already located by `_locate_old` (which is boundary-safe — see Component 5), so
the risk here is low, but using the shared pattern keeps the invariant uniform.

### 4. `_grep_references` — boundary-anchored selection (BR-2)

- Primary path: `git grep -lE -- <boundary-regex-string>` instead of
  `git grep -l -- <old_id>`. The ERE string is derived from the same boundary
  semantics: `(^|[^A-Za-z0-9])REQ-120([^0-9]|$)`. Because git grep ERE has no
  lookaround, an enclosing-group ERE is used for *selection*; the authoritative
  Python `re` lookaround pattern is then re-applied per file in `_rewrite_file`,
  so a file selected by the looser ERE that contains *only* `REQ-1200` produces
  zero `subn` matches and is dropped from the plan (the Python pattern is the
  arbiter — selection only ever over-selects, never under-selects, and
  over-selection is corrected to a zero-match no-op). This satisfies BR-2's
  "a file containing only REQ-1200 is not selected" via the combined
  selection+rewrite pass: such a file yields count 0 and is excluded from the
  plan's ref list.
- Fallback os.walk path: replace `old_id in fh.read()` with
  `_id_boundary_re(old_id).search(text)`.
- **Single source of truth (BR-2):** both the ERE string and the Python pattern
  are produced by one helper pair (`_id_boundary_re` for Python; a sibling
  `_id_boundary_ere(artifact_id)` returning the equivalent ERE string for git
  grep) so they cannot drift. A unit test asserts the two agree on a fixed
  corpus.

### 5. `_locate_old` — already boundary-safe (BR-1, confirmed by test)

`name == old_id` (exact) and `name.startswith(old_id + "-")` already reject
`REQ-1200-slug` when locating `REQ-120` (the char after `REQ-120` is `0`, not
`-`). No code change; a confirming test is added (BR-3 guard spirit).

### 6. `plan` / `main` — per-file count reporting + repo-relative output (BR-3, BR-5)

- `plan` returns each ref paired with its boundary match count; refs with count
  0 are excluded (handles git-grep over-selection).
- `main`'s dry-run prints `- <relpath> (<n> match(es))` per ref and the
  rename line uses repo-relative paths (BR-5). The branch-command block is
  unchanged (BR-4).

## Data Flow

```
main(old,new)
  └─ validate args (strict regex, unchanged) ─ BR-4
  └─ remote_collision (unchanged) ─ BR-4
  └─ plan(root, old, new)
       ├─ _locate_old           (boundary-safe already) ─ BR-1
       ├─ _renamed_path         (boundary subn) ─ BR-1
       └─ _grep_references      (boundary ERE select) ─ BR-2
            └─ per-ref: _id_boundary_re().subn → (diff, count); drop count==0
  └─ dry-run print  (relpath + per-file count) ─ BR-3, BR-5
  └─ if --yes: os.rename + _rewrite_file(boundary subn, atomic) ─ BR-1, BR-4
```

## Testing Strategy

All new tests live in `tools/adlc/tests/test_renumber.py` (extend, don't
replace). The keystone is a `REQ-120` + `REQ-1200` fixture proving the sibling
is **byte-identical** after renumbering `REQ-120`. Existing 23 tests must pass
unchanged (BR-4 / AC-4). Pure-stdlib, offline (remote-collision monkeypatched),
sandbox git repo under `tmp_path` — mirroring the existing test style.

## ADRs

- **ADR-1 (boundary = digit-based, not word-based).** `(?!\d)` not `\b`. `\b`
  would break `REQ-120-slug` (the `-` is a word boundary, but `0`→`-` is too, so
  `\b` after `REQ-120` matches and that's fine — but `\b` would *also* fail to
  distinguish `REQ-120` from `REQ-1200` because there is no word boundary
  between `0` and `0`). The digit-lookahead is the precise tool: it blocks the
  sibling-prefix case while allowing every legitimate suffix. (Spec AC explicit:
  `REQ-120-slug` MUST rewrite.)
- **ADR-2 (selection over-selects, rewrite arbitrates).** git grep ERE lacks
  lookbehind/lookahead-for-the-preceding-char nuance, so selection uses an
  enclosing-group ERE that may over-select; the authoritative Python lookaround
  pattern applied in `_rewrite_file` produces the real match count and a
  zero-count ref is dropped. Selection can over-select but never under-select,
  so no real reference is missed and no sibling is corrupted. One helper pair
  guarantees the ERE and the `re` pattern share semantics (BR-2 anti-drift).
- **ADR-3 (repo-relative output).** Plan and diff output use
  `os.path.relpath(path, root)` (BR-5, LESSON-021) so no absolute filesystem
  path leaks into stdout/CI logs.

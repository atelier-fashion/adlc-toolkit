---
id: TASK-042
title: "Replace non-POSIX commands in analyze/SKILL.md Step 2a duplicate-files snippet"
status: complete
parent: REQ-427
created: 2026-05-15
updated: 2026-05-15
dependencies: []
---

## Description

Rewrite the "Duplicate files (identical content)" bash snippet in `analyze/SKILL.md` (currently lines 304–309) so it uses only POSIX-standard commands. Two specific violations to fix:

1. `xargs -0` — the `-0` flag is a GNU/BSD extension, not POSIX. Replace with `tr '\0' '\n' | xargs` (NUL → newline conversion is POSIX-safe).
2. `shasum` — not POSIX. Replace with `cksum` (POSIX-standard).

The snippet's intent — hash every tracked file and group identical-content files together — is preserved.

## Files to Create/Modify

- `analyze/SKILL.md` — rewrite the bash code block bounded by lines 305–309 (the snippet under the "**Duplicate files (identical content):**" heading). No other edits.

## Acceptance Criteria

- [ ] `grep -n "xargs -0\|shasum" analyze/SKILL.md` returns no matches.
- [ ] The replacement snippet uses only `git`, `tr`, `xargs` (no flags or POSIX flags only), `cksum`, `sort`, `awk`.
- [ ] The snippet still groups duplicate-content tracked files under a header per content hash.
- [ ] No other lines in `analyze/SKILL.md` are modified (diff scoped to that single bash block plus possibly the surrounding comment).
- [ ] The new awk pipeline keys on `cksum`'s output (CRC + size as the first two whitespace-separated fields) instead of `shasum`'s single hex field.

## Technical Notes

- `cksum` output format: `<crc> <bytes> <filename>`. The grouping awk must key on `$1 OFS $2` (CRC + size together) rather than just `$1`, since CRC alone collides more often than the CRC+size pair.
- Filenames with embedded spaces are still handled by stripping the first two fields and keeping the rest as the path (`$1=""; $2=""; sub(/^  /,"")`).
- Files with embedded newlines are out of scope — `git ls-files -z` + `tr '\0' '\n'` cannot distinguish embedded `\n` from a record separator. The original `shasum` version had the same limitation; documenting is unnecessary.
- The candidate replacement:
  ```bash
  # Hash every tracked file and group by identical content (POSIX: cksum)
  git ls-files -z | tr '\0' '\n' | xargs cksum 2>/dev/null \
    | sort | awk '{k=$1 OFS $2; $1=""; $2=""; sub(/^  /,""); map[k]=map[k] ORS $0; count[k]++} END {for (k in count) if (count[k]>1) print "== "k" =="map[k]}'
  ```

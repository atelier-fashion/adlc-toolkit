---
id: REQ-427
title: "Fix POSIX violations in analyze/SKILL.md Step 2a"
status: complete
deployable: false
created: 2026-05-15
updated: 2026-05-15
component: "adlc/analyze"
domain: "adlc"
stack: ["shell", "markdown"]
concerns: ["portability", "conventions"]
tags: ["posix", "analyze", "skill", "shell"]
---

## Description

`analyze/SKILL.md` Step 2a (repo-hygiene scan) contains a shell snippet that violates the toolkit's POSIX-only shell convention mandated by `.adlc/context/conventions.md`. The "Duplicate files (identical content)" snippet on line 307 uses two non-POSIX commands:

1. `xargs -0` — the `-0` flag is a GNU/BSD extension, not POSIX.
2. `shasum` — not a POSIX-standard command; ships with Perl on macOS and most Linux distros, but is not guaranteed.

Replace both with POSIX-compliant equivalents so the analyze skill's example commands run reliably on any POSIX `sh` without relying on extensions.

## Business Rules

- [ ] BR-1: The replacement snippet MUST not use `xargs -0` (use `while IFS= read -r` loop with NUL handling, or `tr '\0' '\n'` pipe).
- [ ] BR-2: The replacement snippet MUST not use `shasum` (use `cksum`, which is POSIX-standard).
- [ ] BR-3: The replacement snippet MUST preserve the original behavior: hash every tracked file and group by identical content, printing groups of duplicates.
- [ ] BR-4: No other content in `analyze/SKILL.md` may be modified.

## Acceptance Criteria

- [ ] `grep -n "xargs -0\|shasum" analyze/SKILL.md` returns no matches.
- [ ] The new snippet uses only POSIX-standard utilities (`git`, `tr`, `xargs` without `-0`, `cksum`, `sort`, `awk`).
- [ ] The snippet still groups duplicate-content tracked files under a header line per content hash.
- [ ] Diff is scoped to lines 304-309 of `analyze/SKILL.md` (the duplicate-files block); no other edits.

## External Dependencies

- None.

## Assumptions

- `cksum` is acceptable as a content-hash for the purpose of grouping duplicates in a hygiene scan. CRC collisions are theoretically possible but vanishingly unlikely across a single repo's file set, and the snippet is illustrative (candidate generation, not cryptographic integrity).
- Tracked file paths may contain spaces or newlines; the replacement must handle these via NUL-delimited iteration.

## Open Questions

- None.

## Out of Scope

- Other shell snippets in `analyze/SKILL.md` outside the duplicate-files block.
- Other skills' POSIX compliance (separate audit).
- Knowledge-capture lesson — substitution is straightforward and not novel.

## Retrieved Context

No prior context retrieved — no tagged documents matched this area.

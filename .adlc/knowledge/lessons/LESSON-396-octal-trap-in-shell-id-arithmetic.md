---
id: LESSON-396
title: "Zero-padded ids are octal to shell arithmetic — $(( 042 + 1 )) is 35; decimal-normalize portably before any math"
component: "adlc/skills"
domain: "adlc"
stack: ["bash", "zsh"]
concerns: ["correctness", "portability"]
tags: ["octal", "shell-arithmetic", "id-allocation", "zero-padding", "bashism"]
req: REQ-518
created: 2026-06-12
updated: 2026-06-12
---

## What Happened

REQ-518's bootstrap-scan path extracts numeric ids from artifact names. Ids
with leading zeros (`042`) are interpreted as OCTAL by `$(( ))` in sh, bash,
and zsh — `$(( 042 + 1 ))` is 35, not 43 — which would silently misallocate
ids derived from zero-padded artifacts. The fix strips leading zeros with
`sed` before arithmetic; the `10#$n` forcing syntax was rejected because it
is a bashism that breaks under other POSIX shells.

## Lesson

Any externally-sourced numeric token (filename fragments, frontmatter ids,
counter files a human may have edited) must be decimal-normalized before
entering shell arithmetic, and the normalization must itself be portable:
`sed 's/^0*//'` with an empty→0 guard, not `10#`. Test fixtures for id math
must include zero-padded inputs — the failure is invisible on typical ids
and catastrophic-but-silent on padded ones (no error, wrong number).

## Why It Matters

ID allocation is the one place a silently wrong number propagates into branch
names, directories, and cross-references that are expensive to renumber. An
octal misparse doesn't fail loud — it allocates a *plausible* wrong id,
defeating the collision-safety machinery from inside.

---
title: "Architecture — cross-repo footprint publishing (per-repo attribution from tasks)"
status: draft
created: 2026-06-05
updated: 2026-06-05
---

## Approach

REQ-483 shipped footprint publishing with a single-repo write-side limitation. The **read**
side (`/manifest`) is already repo-qualified — it splits each `adlc-footprint` line on the
first `:` into `<repo-id>` and `<path>`, and an overlap requires BOTH to match. The **write**
side (`/architect`, Step 2 item 3) has two coupled gaps and one ordering bug:

1. **`head -1`** (architect/SKILL.md L50) selects only the first repo's `prNumber`, so in
   cross-repo mode only one repo's PR ever receives a footprint block.
2. **Attribution source** is the `architecture-mapper` output (bare paths, no repo column), so
   each path cannot be attributed to its owning repo.
3. **Ordering (OQ-1)**: the publish step runs at Step 2 item 3 — *before* Step 4 creates the
   task files. Task `repo:` attribution does not yet exist when the publish runs.

This REQ closes all three by switching the attribution source from the mapper output to the
**task files** (which already carry `repo:` frontmatter + a `## Files to Create/Modify` list)
and publishing each repo's subset to **that** repo's draft PR. Scope is `architect/SKILL.md`
only — `/proceed` Step 0 already opens one draft PR per touched repo and records each in
`pipeline-state.json` `repos[<id>].prNumber`.

## Components (file map)

| # | File | Action | Change |
|---|------|--------|--------|
| 1 | `architect/SKILL.md` | modify | (a) Move the footprint-publish step from Step 2 item 3 to a new step AFTER Step 4 (task creation), renumbering downstream steps. (b) Rewrite the publish block to derive per-repo footprints from task files (grouped by `repo:`) and iterate every `repos[*].prNumber` instead of `head -1`. (c) Add the graceful-degradation + sanitization + skip-empty rules (BR-4/BR-5/BR-3). |
| 2 | `.adlc/context/architecture.md` | modify (deferred to /wrapup) | one-line REQ-484 note that footprint write side is now per-repo, task-attributed |

No agent, template, or partial changes. `agents/architecture-mapper.md` keeps producing its
file table — it remains the **fallback** attribution source (BR-4), not the primary.

## The `adlc-footprint` block schema (unchanged from REQ-483)

```adlc-footprint
adlc-toolkit:architect/SKILL.md
adlc-toolkit:partials/*.sh
```

Per repo: a single fenced block in THAT repo's PR body, each line `<repo-id>:<path-or-glob>`.
`/architect` writes it (idempotent — replacing any prior block); `/manifest` parses it. The
write side reuses the SAME validation the read side applies (BR-5): charset
`^[A-Za-z0-9_.-]*:?[A-Za-z0-9_./*-]+$` and reject any line containing `..`.

## Data flow (revised)

1. Step 4 creates `tasks/TASK-xxx.md`, each with `repo:` frontmatter (cross-repo) or none
   (single-repo → primary) and a `## Files to Create/Modify` bullet list.
2. New publish step (after Step 4): for each touched repo id with a `prNumber` in
   `pipeline-state.json`:
   a. Gather the union of file paths from tasks whose `repo:` equals that repo id (a task with
      no `repo:` attributes to the **primary** repo — BR-1, BR-6).
   b. Emit one repo-qualified `<repo-id>:<path>` per file, sanitize (BR-5), dedupe.
   c. If a repo has zero attributable files → skip with a one-line note, never an empty block
      (BR-4). If a task lists no files OR a touched repo has no attributing tasks → fall back to
      the architecture-mapper paths attributed to the **primary** repo, with a
      `source: mapper-fallback` notice (BR-4, OQ-2).
   d. Replace any prior `adlc-footprint` block in that repo's PR body, write via
      `gh pr edit <prNumber> --body-file`.
3. `/manifest` reads each PR's block back and computes per-repo overlap (`web:x` vs `api:x` do
   not collide — already correct on the read side).

## Key decisions (ADRs)

- **ADR-1 — task files are the authoritative attribution source, mapper is the fallback.**
  Tasks already carry `repo:` + a Files list (task-template L9, L18). This is the only source
  that ties a path to its owning repo with no inference. The mapper output (bare paths) is kept
  only as the graceful-degradation fallback (BR-4), attributed to primary. (BR-1, BR-6)
- **ADR-2 — move the publish step AFTER task creation (resolves OQ-1).** The publish must read
  task `repo:` attribution, which does not exist until Step 4. Renumber: old Step 3 (Design
  Architecture) and Step 4 (Break Into Tasks) keep their numbers; the footprint publish becomes
  a new Step 5 (Publish Footprint), and old Step 5 (Update Status) / Step 6 (Present) shift to
  Step 6 / Step 7. The Step 2 codebase-exploration item 3 is removed; Step 2 item 2 (read key
  files) becomes the last item of Step 2. (OQ-1 Default: publish after tasks exist.)
- **ADR-3 — single-repo degenerates, no separate code path.** The per-repo loop iterates the
  one touched repo; `repo:`-absent tasks attribute to the sole/primary repo via BR-1 (NOT via
  the BR-4 mapper-fallback — a single-repo run is the normal path, never flagged "coarse").
  Output is byte-equivalent in intent to REQ-483. (BR-3)
- **ADR-4 — sanitize on write, not just read (LESSON-008).** Even though task paths are
  session-controlled (less adversarial than Kimi output), apply the same
  charset-validate + `..`-reject the read side applies, as defense in depth and schema parity.
  Use `mktemp` + EXIT trap for the body temp file (already present). (BR-5, LESSON-008)
- **ADR-5 — split-free bash, dogfooded by EXECUTION under the executor shell (LESSON-329).**
  The new derivation loop iterates lists over newlines (`printf '%s\n' "$x" | while read -r`),
  never unquoted word-splitting (zsh does not word-split unquoted expansions). BR-7 mandates the
  cross-repo round-trip be verified by EXECUTING it (publish to ≥2 repos' PRs, run `/manifest`,
  confirm per-repo overlap), not by reading. Verification is lint + dogfood, per the toolkit's
  markdown-skill model. (BR-7, LESSON-329)

## Lessons applied

- **LESSON-008** — untrusted-path discipline on write (charset + `..`-reject + mktemp/trap).
- **LESSON-329** — dogfood by executing the fenced block under the real shell; split-free bash.
- **LESSON-330** — Phase-5 review must confirm every BR is actually covered (BR-coverage check).

## Out of scope

- Auto-rebase / blocked-REQ auto-resume (REQ-485).
- Footprint-from-actual-diff (separate accuracy improvement noted in REQ-483 wrapup).
- Changing the trial-merge gate (already per-repo correct).
- Cross-repo trial-merge atomicity.

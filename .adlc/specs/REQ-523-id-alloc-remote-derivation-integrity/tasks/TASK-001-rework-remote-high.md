---
id: TASK-001
title: "Rework adlc_remote_high: independent sources, cmd-sub-safe degraded signal, forge-aware artifact scan"
status: draft
parent: REQ-523
created: 2026-06-12
updated: 2026-06-12
dependencies: []
repo: adlc-toolkit
---

## Description

Rework `adlc_remote_high` in `partials/id-alloc.sh` so the branch scan and the
merged-artifact scan are independent derivation sources, the degraded signal
survives command substitution, lessons never silently return 0, and the
artifact scan is forge-aware (GitHub `gh` fast-path, git-transport fallback for
gh-absent GitHub AND Azure DevOps, degraded-with-forge-name for any other host).
Update `adlc_alloc_id` to parse the new stdout contract.

This is the foundation task; TASK-002 (recheck) and TASK-004 (tests) depend on
the new stdout contract defined here.

## Files to Create/Modify

- `partials/id-alloc.sh` — rework `adlc_remote_high`; add a shared artifact-scan
  helper `adlc_remote_artifact_nums`; update `adlc_alloc_id` stdout parsing;
  correct the header + inline doc comments (BR-2 contract change).

## Acceptance Criteria

- [ ] BR-1: `ls-remote` failure no longer `continue`s past the artifact scan for
      that repo; both sources run independently.
- [ ] BR-2: `adlc_remote_high` prints `<high_water> <degraded>` on stdout (two
      space-separated tokens); the degraded bit is observable through `$(...)`.
      No `ADLC_ALLOC_DEGRADED` parent-env write remains. Stale "CALLER's env"
      comments corrected.
- [ ] BR-3: `kind=lesson` with no usable artifact scan (no gh AND no git
      fallback succeeded) → degraded=1 + stderr warning; never a clean `0 0`.
- [ ] BR-4: gh-absent GitHub remote reachable over git transport → artifact ids
      still derived via `git ls-remote` default tip + shallow fetch + `git
      ls-tree`.
- [ ] BR-5: Azure DevOps origin → artifact ids derived via the same git-transport
      scan (full parity); a genuinely unreachable ADO (and any other non-GitHub
      host with no usable scan) → degraded with a forge-naming warning, never a
      silent skip.
- [ ] BR-8: Happy path unchanged — gh present, reachable GitHub remote → same id
      allocated as today; `adlc_alloc_id` returns the same number.
- [ ] BR-7: POSIX/BSD/zsh-safe; no `for x in $var` over newline lists.

## Technical Notes

- **Degraded channel (BR-2):** change `adlc_remote_high` stdout from a bare number
  to `printf '%s %s\n' "$max" "$degraded"`. Both callers (`adlc_alloc_id`,
  `adlc_recheck_id`) already capture via `$(...)`; update their parse to split the
  two tokens. The existing loud-fail guards (`case … in ''|*[!0-9]*)`) must be
  updated to validate only the FIRST token, since the output now contains a space.
- **Independent sources (BR-1):** replace the `continue` after the `ls-remote`
  failure with: set degraded, then fall through to the artifact scan for the same
  repo. Keep the unreachable-url accounting for the warning.
- **Forge-aware host classification (M4/BR-5):** replace the GitHub-only owner
  regex with a host classifier mirroring `forge.sh adlc_forge_provider` shape:
  - `*github.com[:/]*` → github (gh fast-path, else git fallback)
  - `*dev.azure.com[:/]*` | `*.visualstudio.com[:/]*` → azure-devops (git fallback)
  - anything else → degraded with a warning naming the host; no scan.
- **Shared artifact-scan helper:** extract `adlc_remote_artifact_nums <repo> <kind>
  <prefix>` returning the newline list of artifact numbers (or empty), setting an
  out-param/echo to signal whether a scan actually ran. GitHub path: try `gh api
  contents` first; on gh-absent or gh failure, fall through to the git-transport
  scan. ADO/other-git path: git-transport scan directly.
- **Git-transport scan (BR-4/BR-5):** `tip=$(git -C "$repo" ls-remote origin HEAD |
  awk '{print $1}')`; `git -C "$repo" fetch --depth=1 -q origin "$tip"` (best
  effort); `git -C "$repo" ls-tree --name-only "$tip" "<artifact-path>/"` →
  grep the `<PREFIX>-NNN` names. Path per kind: `.adlc/specs`, `.adlc/bugs`,
  `.adlc/knowledge/lessons`. Never read the local working tree. If `ls-remote`/
  fetch/ls-tree all fail, the scan did NOT run → degraded.
- **Lesson always-degrades (BR-3):** lessons have no branch source, so the
  artifact scan is the ONLY source; if it did not run for a participating repo,
  that's a degraded condition with a warning — never silent 0.
- **zsh-safety (BR-7):** keep `adlc_id_list_max` reductions; no `for x in $nums`.
  Use `printf '%s\n' | grep | sed` pipelines as in the current code.

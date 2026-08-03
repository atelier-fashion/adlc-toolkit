---
id: LESSON-465
title: "A partially-synced repo looks healthy — vendored-surface drift must be verified per-file against canonical, and chore syncs belong in worktrees off origin, not the user's checkout"
component: "adlc/partials"
domain: "adlc"
stack: ["bash", "git", "github-actions"]
concerns: ["correctness", "process"]
tags: ["template-drift", "vendored-partials", "cherry-pick", "worktree", "two-branch-model", "verify-head-ref", "base-retarget", "delegate-rename"]
req: PR-221
created: 2026-08-03
updated: 2026-08-03
---

## What Happened

A cross-repo sweep to purge pre-REQ-522 Kimi-era partials from admin-api,
atelier-fashion, and infrastructure surfaced three traps:

1. **Partial prior syncs masked drift.** atelier's `origin/dev` had already
   adopted `delegate-gate.sh` and most partials — but `emit-step-telemetry.sh`
   (missing the 2026-08-03 crash fix), `id-alloc.sh`, `id-recheck.sh`, ETHOS,
   and the workflow runtime were still stale. A spot-check of one or two files
   would have concluded "already synced".
2. **Local checkouts were unusable as sync bases.** atelier's `dev` was 71
   commits behind origin with unrelated staged work; infrastructure sat on a
   detached HEAD; admin-api's feature branch belonged to an already-merged PR.
   Committing or rebasing in place would have disturbed live sessions.
3. **Branch-protection gates keyed on head-ref globs.** admin-api's
   `verify-head-ref` check rejects PRs into `main` unless the head is
   `staging` or matches `chore/sync-*`/`chore/resolve-*` — and retargeting a
   PR's base does NOT retrigger `pull_request` workflows (base-edit fires
   `edited`, not `synchronize`), so the stale failing check persisted until an
   empty commit was pushed.

## Lesson

When syncing vendored surfaces: (a) verify every file byte-for-byte against
canonical after the sync — never sample; (b) do the work in a temp worktree
branched from `origin/<target>` and cherry-pick, resolving conflicts by taking
canonical (partials-posture: toolkit wins); (c) in 2-branch repos, target
`staging` and expect head-ref allowlists; after any base retarget, push an
empty commit to refresh `pull_request` checks.

## Why It Matters

Vendored copies fail silent — repos ran on the global-fallback path for two
months with zero errors. Drift only bites when the fallback diverges or a
worktree makes `~/.claude` unreadable, i.e., at the worst time. Per-file
verification plus worktree-isolated chore branches makes the sweep safe to run
against repos with live sessions.

## Related

- LESSON-441 — vendored partials shadow canonical fixes (same root cause,
  discovery side; this lesson covers the remediation mechanics).
- Follow-up found during the sweep: the REQ-522 rename never installed an
  `adlc-read` binary — `~/bin` still has only `ask-kimi`/`kimi-write`, so every
  delegation gate resolves `no-binary` and telemetry records fallback drafting
  everywhere.

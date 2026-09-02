---
id: BUG-210
title: "An allocation running inside a git worktree collapses the machine-global id namespace to one checkout, and never reports it as degraded"
status: open
severity: high
created: 2026-09-02
updated: 2026-09-02
component: "adlc/id-alloc"
domain: "adlc"
stack: ["shell", "git"]
concerns: ["reliability", "developer-experience"]
tags: ["id-allocation", "worktree", "collision", "cross-repo", "repos-root", "silent-degradation"]
introduced_by: ["REQ-518", "REQ-546"]
attribution: derived
---

## Description

`req`, `bug` and `lesson` ids are machine-global: one counter per kind under
`~/.claude/`, one namespace across every repo on the machine. `adlc_remote_high`
enforces that by scanning **every checkout under `$ADLC_REPOS_ROOT`** — and BR-11
is explicit that the scan root *defines* the namespace.

The scan root defaults to the parent of `git rev-parse --show-toplevel`. Inside a
**git worktree** that is not the parent of the repos directory — it is the
worktree container. So the namespace silently narrows to a single checkout, and
every allocation made from a worktree derives its high-water from one repo
instead of seven.

`/proceed` Phase 0 puts every pipeline in a worktree. So does `/sprint`. The
allocations most likely to race are precisely the ones running in the collapsed
scope.

## Reproduction Steps

```sh
show() {
  cd "$1" || return
  top=$(git rev-parse --show-toplevel)
  root=$(cd "$top/.." && pwd)
  n=0; for g in "$root"/*; do { [ -d "$g/.git" ] || [ -f "$g/.git" ]; } && n=$((n+1)); done
  echo "$1 -> root=$root repos=$n"
}
show ~/GitHub/teton-code
show ~/GitHub/teton-code/.claude/worktrees/<any-worktree>
```

Measured 2026-09-02:

```
~/GitHub/teton-code                          -> root=~/GitHub                          repos=7
~/GitHub/teton-code/.claude/worktrees/<wt>   -> root=~/GitHub/teton-code/.claude/worktrees repos=1
```

Seven participating repos become one.

## Expected Behavior

An allocation made from a worktree scans the same namespace as one made from the
repo root — every checkout under the real repos root. Failing that, it reports
the derivation as **degraded** so the caller knows the number is unverified.

## Actual Behavior

Neither. The scan silently covers one checkout, and the degraded bit stays `0`
because a worktree has a perfectly good `origin`: `adlc_rh_saw_remote` is set,
every source "succeeds" against that single remote, and `adlc_remote_high`
returns a confident, wrong high-water. There is no warning to notice.

**Three ids were double-issued on 2026-08-31**, each duplicating an id already
held in a sibling repo:

| id | prior holder | teton-code's |
|---|---|---|
| REQ-600 | atelier-fashion — `scope-gcloud-teardown-to-job-owned-config` (complete, 08-28) | `decompose-run-prompt-turn` (08-31) |
| REQ-601 | infrastructure — `bigquery-mcp-proxy-deploy-workflow` (complete 08-28, merged PR #302 on 08-29) | `honest-shell-env-failures` (08-31) |
| REQ-602 | adlc-toolkit — `doctor-worktree-registrations-and-invocation-seam` (draft, 08-30) | `post-split-cleanup` (08-31) |

The namespace is provably global: teton-code's specs start at REQ-544, not 001,
and the repos' ranges interleave.

**It is still happening.** `BUG-206` is currently double-issued between
adlc-toolkit (`delegate-clis-never-enforce-enabled`, 09-01) and atelier-fashion
(`colima-preflight-has-no-retry-on-failed-start`, 08-29) — two unrelated bugs,
one id.

## Environment

- Platform: macOS, POSIX `sh`
- Version: adlc-toolkit `28c0d46`
- Affected: `partials/id-alloc.sh`, `partials/id-recheck.sh`

## Attribution

`introduced_by: [REQ-518, REQ-546]` — both, because the defect is genuinely the
interaction. **REQ-518** (`e6a90e7`, 2026-06-11) introduced the
`parent-of-$(git rev-parse --show-toplevel)` pattern in `id-recheck.sh`.
**REQ-546** (`b8fc1a6`, 2026-07-23) carried the same pattern into `id-alloc.sh`,
where it became load-bearing for allocation and produced the collisions. Neither
alone is the whole cause: the pattern originated in one and became consequential
in the other. Selected by the operator from the two blame candidates rather than
auto-unioned.

## Root Cause

`ADLC_REPOS_ROOT` defaults to `$(cd "$(git rev-parse --show-toplevel)/.." && pwd)`.
`--show-toplevel` returns the **current** worktree, not the main one, so inside a
linked worktree the default resolves to the worktree container. Six sites share
the assumption:

| file | line | what it scopes |
|---|---|---|
| `id-alloc.sh` | 103 | `assume` counter path |
| `id-alloc.sh` | 116 | `assume` lock dir — **per-worktree lock is no mutual exclusion** |
| `id-alloc.sh` | 396 | `assume` remote scope |
| `id-alloc.sh` | 400 | repos-root default for req/bug/lesson |
| `id-alloc.sh` | 494/497 | bootstrap local scan root |
| `id-recheck.sh` | 148 | recheck's repos-root default |

Line 116 is its own hazard: two worktrees of one repo take *different* `assume`
locks, so the mkdir mutual exclusion does not apply between them.

The silence is the other half. `adlc_remote_high` flags `degraded` when a source
*fails*; here every source succeeds against a legitimate remote. A narrowed
namespace is indistinguishable from a small one, so the derivation cannot tell
that it answered a different question than the one asked.

**Not the cause — checked and refuted.** My first hypothesis was that
`adlc_reserve_id` pushing to the allocating repo's own `origin` makes the
reservation namespace per-repo while the id namespace is global. The reservation
push *is* per-repo, but SOURCE 3 of `adlc_remote_high` reads
`refs/adlc/ids/<kind>/*` **inside the per-repo loop**, so reservations are read
across every participating repo. With a correct scan root the mechanism works.
The defect is the scan root, not the push target.

**Also refuted:** REQ-607's wrapup reported "lesson reservation refs top out at
607 while merged files reach 613." Measured 2026-09-02: lesson reservations and
merged `LESSON-*` files both top out at **619**; `req` reservations (610) sit
correctly ahead of merged `req` files (608). No reservation-lag defect exists on
the available evidence. Recorded because that claim is in a merged wrapup and a
future reader will find it.

**Undetermined, deliberately.** teton-code holds 43 `req` reservations but none
for 600/601/602, while `~/.claude/.adlc-own-reservations` records this machine
reserving all three. The ledger has **no repo column** — `kind num sha` only — so
it cannot distinguish "reserved req/600 in atelier-fashion" from "…in
teton-code", and the sibling repos each hold exactly one of the three. The
evidence is therefore consistent with both readings and settles neither. The
missing column is itself worth fixing; it is not fixed here.

## Resolution

New `adlc_main_worktree()` in `id-alloc.sh` resolves the **main** worktree via
`git rev-parse --path-format=absolute --git-common-dir` — which points at the main
worktree's `.git` from a main checkout *and* from a linked worktree — with a
fallback for git < 2.31. Applied at every site that had taken `--show-toplevel`
to mean "the repo":

- `adlc_id_kind_counter` / `adlc_id_kind_lockdir` (`assume`) — the lock one is its
  own fix: two worktrees of one repo were taking **different** `assume` locks, so
  the `mkdir` mutual exclusion did not apply between them at all.
- `adlc_remote_high` — the `assume` scope and the `req`/`bug`/`lesson` repos-root
  default (the site that caused the collisions).
- `adlc_local_scan_high` — the bootstrap scan root.
- `id-recheck.sh` — the same repos-root default.

`adlc_ai_reserve_repo` is **deliberately unchanged** and carries a comment saying
so: a linked worktree shares its main repo's `origin`, so the reservation lands on
the same remote either way. Only the namespace *scope* was wrong; the push target
was not.

**Known-bad, run.** Two regression cases build a real linked worktree beside a
sibling repo. Reverting `adlc_main_worktree` to `--show-toplevel` turns both red:
case 1 returns the worktree instead of the main worktree, and case 2 counts
**1 participating repo instead of 2** — the namespace collapse itself, reproduced
as a test. The observed values are recorded in the test's doc comment.

Full partial suite: **1840 passing, 0 failures**, `sh partials/tests/run.sh` rc=0
(bash + zsh + dash legs).

## Files Changed

- `partials/id-alloc.sh` — added `adlc_main_worktree()`; used it at five sites;
  annotated the one `--show-toplevel` that stays
- `partials/id-recheck.sh` — repos-root default resolves from the main worktree
- `partials/tests/id-alloc.test.sh` — two BUG-210 regression cases + the recorded
  mutation outcome

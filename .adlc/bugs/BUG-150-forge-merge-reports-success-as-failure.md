---
id: BUG-150
title: "adlc_forge_pr_merge reports a completed merge as a network failure"
status: resolved
severity: high
created: 2026-08-04
updated: 2026-08-04
component: "partials/forge"
domain: "adlc"
stack: ["sh"]
concerns: ["reliability", "correctness"]
tags: ["forge-adapter", "gh", "worktree", "error-classification", "merge"]
---

## Description

`adlc_forge_pr_merge` returns the exit code of `gh pr merge` verbatim. But `gh pr merge`
does two independent things: it calls the GitHub API to merge (remote), and it then tidies
up locally (switch off the merged branch, delete it). When only the **local** step fails,
`gh` still exits non-zero — and the adapter reports the whole operation as failed even
though the PR is merged.

The adapter then classifies the failure. The local git error matches none of the
classifier's patterns, so it falls through to the `*)` default and is reported as
`error_class=network` — the one class that most invites a retry.

Observed three times out of three during `/bugfix` and `/wrapup` on `teton-code`
(PRs #32, #34, #35). Every merge landed; every one was reported as a network failure.

The trigger is not exotic: **`main` being checked out in another worktree**, which is the
normal state for any agent session working out of `.claude/worktrees/` or `.worktrees/`
while the primary checkout sits on `main`. In that layout every merge misreports.

## Reproduction Steps

Deterministic, offline, using the existing recording-shim pattern from
`partials/tests/forge.test.sh`:

```sh
SBX=$(mktemp -d); SHIM="$SBX/bin"; mkdir -p "$SHIM"
cat > "$SHIM/gh" <<'GHSHIM'
#!/bin/sh
case "$1 $2" in
  "pr merge")
    echo "failed to run git: fatal: 'main' is already used by worktree at '/x'" >&2
    exit 1 ;;
  "pr view") echo '{"state":"MERGED"}' ;;
esac
exit 0
GHSHIM
chmod +x "$SHIM/gh"
. ./partials/forge.sh
PATH="$SHIM:$PATH"; export ADLC_FORGE_PROVIDER_OVERRIDE=github
adlc_forge_pr_merge 9 --squash --delete-branch; echo "rc=$?"
```

## Expected Behavior

A merge that actually completed is reported as completed. If the local cleanup failed, that
is a **warning** about local state, not a failed merge — and the caller is told the branch
was not deleted so it can finish the job.

## Actual Behavior

```
error_class=network
raw=failed to run git: fatal: 'main' is already used by worktree at '/x'
rc=1
```

…while `gh pr view 9 --json state` reports `{"state":"MERGED"}`.

Two further consequences observed in practice:

- **`--delete-branch` silently does not happen.** `gh` aborts the cleanup sequence at the
  failed checkout, so the remote branch survives. A caller that believes the merge failed
  will not clean it up either, leaving merged branches accumulating on the remote.
- **`network` invites exactly the wrong recovery.** It reads as transient, so the natural
  response is to retry the merge — against a PR that is already merged.

## Environment

- Platform: all; triggered whenever the repo's default branch is checked out in a
  different worktree than the one the merge runs from
- Version: `partials/forge.sh` @ `main` (REQ-520 adapter, unchanged since)

## Root Cause

Two defects, one in each layer.

**1. `adlc_forge_pr_merge` trusts the exit code instead of verifying the outcome**
(`partials/forge.sh:336-337`):

```sh
_adlc_forge_run -- gh pr merge "$@"; adlc_fm_rc=$?
[ "$adlc_fm_rc" -eq 0 ] && printf 'state=MERGED\n'; return "$adlc_fm_rc"
```

There is no post-failure check of the PR's real state. The adapter cannot distinguish
"the merge was rejected" from "the merge succeeded and `gh` tripped on the local checkout",
because it never asks. This is the ethos-#4 case exactly: the exit code is a claim, and the
PR state is the evidence.

**2. `_adlc_forge_classify` defaults unknown failures to `network`**
(`partials/forge.sh:148-149`). A local `git` failure is not a network condition, and
`network` is the most misleading available label because it implies retry-ability. The
default bucket is doing double duty as "genuinely transient" and "we have no idea".

## Fix Approach

1. In `adlc_forge_pr_merge`'s `github` branch, on non-zero rc, re-query the PR state
   (`gh pr view <ref> --json state`). If it reports `MERGED`, emit `state=MERGED` plus a
   `warn=` line naming the local-cleanup failure, and return 0. Otherwise fall through to
   today's error path unchanged.
2. Add a `local-git` class to `_adlc_forge_classify` for `failed to run git` /
   `already used by worktree` / `fatal:` shapes, so a genuinely-failed merge with a local
   git cause is no longer labelled `network`.
3. Because the adapter can no longer be trusted to have deleted the branch when cleanup
   failed, the `warn=` line must say so explicitly — the caller needs to know to run
   `git push origin --delete <branch>` itself.

**Correction to this plan, made during the fix**: an earlier draft said "the same guard is
worth having on the ADO branch." It is not. `az repos pr update` performs no local
checkout or branch deletion — it is a pure REST call — so the split-outcome failure mode
this bug is about cannot arise there. Adding a speculative guard would have been untested
code defending against a condition that does not exist on that path. The ADO arm is
unchanged.

## Resolution

**1. Verify the outcome instead of trusting the exit code** (`partials/forge.sh`, `github`
arm of `adlc_forge_pr_merge`). `_adlc_forge_run`'s output is now captured rather than
streamed. On non-zero rc the adapter extracts the PR ref (first non-flag positional, the
same extraction the ADO arm already does) and asks `gh pr view <ref> --json state`. If the
PR is `MERGED`, it emits `state=MERGED`, returns 0, and demotes the captured `error_class=`
block to `warn_class=` so the diagnostics survive without the output claiming failure.
Otherwise the error block is re-emitted unchanged and the original rc returned.

**2. The warning is load-bearing, not cosmetic.** `gh` aborts its cleanup sequence at the
failed step, so the source branch survives on the remote. The `warn=` line says so and
gives the exact command, because the caller would otherwise have no reason to look.

**3. `local-git` classifier bucket** for `failed to run git` / `already used by worktree` /
`fatal: ` shapes, ordered after the specific auth/policy/not-found classes so a signature
that merely mentions git still classifies correctly. A local git failure is no longer
labelled `network`.

### Verification

Reproduced first with a `gh` shim that fails exactly as observed (merge writes the local
git error and exits 1; `pr view` reports `MERGED`) — `rc=1`, `error_class=network` before
the fix. Eight new cases in `partials/tests/forge.test.sh` cover both directions:

- merged-despite-failure → rc 0, `state=MERGED`, `warn=` present, **no** `error_class=`,
  raw diagnostic retained
- genuinely-unmerged (branch-protection block, `pr view` reports `OPEN`) → still rc 1,
  still `error_class=merge-blocked-by-policy`, and **never** reports `MERGED`
- classifier: local worktree collision → `local-git`; unknown → still `network`

Suite green under **both** shells via `sh partials/tests/run.sh` (BR-9), 465 Python tests
pass, and `shellcheck` reports no new findings on either file (3 and 4, both baseline).

## Files Changed

- `partials/forge.sh` — outcome verification in the `github` merge arm; `local-git`
  classifier class
- `partials/tests/forge.test.sh` — section 7b, eight cases covering merged-despite-failure,
  genuinely-unmerged, and the new classifier bucket
- `.adlc/bugs/BUG-150-forge-merge-reports-success-as-failure.md` — this report

## Deployment

PR #113, squash-merged to `main` as `3519e18` (2026-08-04). No runtime deploy — this repo
ships skill/partial source, not a service.

**Confirmed working on a real merge.** The fixed adapter was used to merge
`teton-code` PRs #36 and #37, both of which hit the exact triggering condition:

```
state=MERGED
warn=merge completed remotely, but gh post-merge cleanup failed; the source branch is
     likely NOT deleted — remove it with: git push origin --delete <branch>
warn_class=local-git
raw=failed to run git: fatal: 'main' is already used by worktree at '.../teton-code'
```

`rc=0`, both PRs confirmed `MERGED`. Before the fix that identical case produced `rc=1`
and `error_class=network`. The warning was also correct in practice — the source branch
had survived both times and needed an explicit `git push origin --delete`.

### Downstream

- `teton-code/.adlc/partials/forge.sh` re-synced in atelier-fashion/teton-code#37
  (merged `51a5ded`), byte-identical to canonical.
- `~/.claude/skills/partials/forge.sh` — the copy agent sessions actually load — still
  needs `install.sh` to pick this up on each machine. Until then, sessions keep using the
  old adapter and keep misreporting merges.

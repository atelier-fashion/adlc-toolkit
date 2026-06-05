# partials/trial-merge.sh — call-site protocol

`adlc_trial_merge` is the non-mutating dry-run merge that backs REQ-483's hard ordering gate (BR-16). It tells a caller whether a branch can merge a base ref cleanly, **without** changing committed history or leaving the worktree dirty.

## Signature

```
adlc_trial_merge <worktree> <base-ref>
```

## Return-code registry

| rc | meaning | stdout | caller action |
|----|---------|--------|---------------|
| 0 | clean — `<base-ref>` merges with no conflict | (empty) | proceed |
| 1 | **real textual conflict** | conflicting paths, one per line | return the `blocked` terminal; resolution is rebase, never "merge anyway" (ethos #6) |
| 2 | precondition error (missing args, or the worktree has uncommitted changes) | (empty) | surface as `failed` / a loud error — **not** a conflict |
| 3 | the merge could not start (bad / unfetched base ref) | (empty) | surface as `failed` / loud error; check the base ref was fetched — **not** a conflict |

Only **rc=1** is a merge conflict. Collapsing rc=2/3 into the `blocked`/conflict path would mislead the user ("rebase after the blocker merges") when the real problem is a dirty worktree or a stale/missing base ref.

## Guarantees

- **Non-mutating**: uses `git merge --no-commit --no-ff` then always `git merge --abort`; no commit is created and `git status` is clean afterward (verified by dogfood).
- **Trusted base only**: callers pass `origin/<integrationBranch>` (resolved locally from state) — never a value derived from a PR body or another session.

## Call-site protocol

Source the partial and call it **within the same fenced block** (shell state does not cross SKILL.md fences — conventions "Bash in skills"), and **fetch the base ref first** (the helper does not fetch):

```sh
. .adlc/partials/trial-merge.sh 2>/dev/null || . ~/.claude/skills/partials/trial-merge.sh
git -C "$wt" fetch origin "$integration_branch" >/dev/null 2>&1
conflicts=$(adlc_trial_merge "$wt" "origin/$integration_branch"); rc=$?
case $rc in
  0) ;;                                              # clean -> proceed to merge
  1) ;;                                              # blocked -> return blocked terminal, files in $conflicts
  *) ;;                                              # rc 2/3 -> failed/loud error (NOT a conflict)
esac
```

Used by: `/proceed` (Phase 4 early gate + Phase 8 pre-merge), `/sprint` (Step 5 merge sequencing), `agents/pipeline-runner.md` (Phase 8 single-repo merge).

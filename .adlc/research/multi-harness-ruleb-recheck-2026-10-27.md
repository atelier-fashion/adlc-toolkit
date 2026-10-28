# Rule B targeted round: fix pass and recheck (2026-10-27)

One targeted fix round on the three Rule B themes (shared-base prefixes incl.
`git -C`; exec engine and model-written content; deny-probe controls), then a
narrow recheck of the seven edited specs. **All seven recheck reports say holes
remain** (about 60 findings). The fixes landed as specified; the rechecks
found second-order holes in them and a few the fixes introduced.

| spec | holes | headline |
|---|---|---|
| 657 framework | 6 + 5 sibling | BR-9 matcher circular (would fail Claude's own shipped tree); `deny_under_allow` not bound to version/mechanism/source; shared-base rule skips written user scope; exact-deny extensions unreported |
| 664 probes | 9 | `wrapped-allow` probes a different deny spelling than consumers need; `allow-only` control proves nothing where baseline already runs the command; config-not-loaded reads as hollow pass; stale state across launches; Gemini policy live during controls |
| 655 Codex | 8 | token-prefix `prompt` is position-sensitive (`git push origin +HEAD`, `origin --force`, `git branch foo -D` unmatched): restoring `["git","push"]`/`["git","branch"]` is unsound even if strictest-wins; `bash -lc` wrapping; user-scope `writable_roots` from `/init` widens every Codex session; TOML merge edge cases |
| 656 Copilot/Cursor | 4 + residuals | printed Copilot line still emits the broad fence entry the framework bans; Cursor `Shell(npm)` collapse widens (`npm publish`) and `Shell(rm)`/`Shell(terraform)` width are undeclared; `wrapped-allow` covers only `git -C`, not env-prefix/`bash -lc` |
| 658 Gemini | 7 | omitted set must be computed, adds `git push`/`git branch`; union merge leaves stale widening forever; policy file overwrite can clobber operator content, priority unpinned; printed broad remedy wraps every deny |
| 662 exec adapters | 9 | omission is not fail-closed on a harness that runs un-allowed commands (Cursor); verified status not tied to the binary actually run; harness loads model-editable working-copy config; `forbidden_flags` blocklist misses short/attached spellings; skip-worktree defeated by `git add --sparse` |
| 659 engine | 14 | unattended block still says "you own the merge" (not a forbidden token); second sibling-worktree removal in `phases-lite.md:85-90`; chore-PR allowlist lets `.adlc/context/` through and forge `files` hides renames; deploy plan misses `deploy.sh`/CI/Terraform changes; BR-23 `-c` flags cannot reach trial-merge/lane-check/id-alloc/gh; same-uid ledger is conventional; `--match-head-commit` pin absent; defaults leave direct push open; forge.sh has no head-oid/files for ADO and no owner |

## What the pattern says

1. **Allowlist and prefix-deny semantics cannot be made a gate.** Three
   validators independently note the same exposure already exists in the
   Claude template (`gh api`, `npx`, `npm run`, `find -exec`, `awk`,
   semantic equivalents like `git restore`, `gcloud` deploys). Each fix round
   closes spellings and exposes more. The specs already say the allowlist is
   not the gate (Rule B); the work left is to *state the residuals* and make
   the structural controls carry the weight.
2. **The structural controls are what remain worth hardening**, and the
   recheck gave concrete, mostly mechanical fixes for them:
   - orchestrator-owned local trial merge/rebase in a detached worktree at the
     recorded oid; merge pinned with `--match-head-commit`
   - local `git diff --no-renames --name-status -z` for the chore-PR and
     exec-path gates (not the forge `files` list)
   - deploy plan frozen from the integration ref; any change to a path the
     deploy executes skips deploy
   - child environment: `GIT_CONFIG_GLOBAL`/`NOSYSTEM`, snapshot of operator
     git/ssh/gh config, absolute-path binaries with a sha256 manifest, no forge
     login in the child (separate scoped token or `--shared-credentials`)
   - ledger: run directory outside every repo, random name, wholesale write at
     the halt, process-group sweep at exit, one-time approve token
   - defaults: `require_branch_protection: true`; config frozen at launch
3. **Probe soundness is the other tractable cluster**: a deny probe needs a
   control proving the allow was necessary and effective, a witness proving
   the config loaded, per-launch fresh nonce/sentinels, and a `wrapped-allow`
   that denies the *plain* spelling and asks the wrapped one.

## Decision this implies

Further narrow rounds on the allowlist spellings have diminishing returns.
The recommended next step is to apply the structural fixes above and the
probe-soundness fixes, and to rewrite the allowlist-side requirements as
declared residuals (what each harness's matcher cannot express) with the
unconditional omissions where a position-sensitive prefix cannot cover a flag
(Codex `git push`/`git branch`). Everything else becomes an input to each
spec's `/architect` run.

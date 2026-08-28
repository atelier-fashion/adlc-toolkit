# forge.sh — forge-neutral PR-operation adapter (REQ-520)

`partials/forge.sh` is the **single** place `gh`/`az` PR commands live (BR-1).
Every skill that touches the PR lifecycle sources it and calls the adapter
functions instead of shelling out to `gh pr` directly. A `lint-skills` check
(`forge-direct-gh`) rejects new direct `gh pr <op>` usage in skills.

## Call pattern

Source the partial with the two-level fallback and call the op **in the same
fenced block** (conventions.md cross-fence rule):

```sh
. .adlc/partials/forge.sh 2>/dev/null || . ~/.claude/skills/partials/forge.sh
out=$(adlc_forge_pr_view "$pr" --fields state,url); rc=$?
# branch on rc and the normalized error_class / fields in $out
```

## Provider resolution (BR-2)

`adlc_forge_provider [<repo-dir>]` resolves, in precedence order:

1. per-project `.adlc/config.yml` → `forge.provider`
2. machine `~/.claude/adlc/config.yml` → `forge.provider`
3. `auto` — detect from the `origin` remote URL

`auto` maps `github.com` → `github`, `dev.azure.com` / `*.visualstudio.com`
(incl. the `ssh.dev.azure.com` / `vs-ssh.*.visualstudio.com` SSH hosts) →
`azure-devops`. An unrecognized host **fails loud**, naming the URL and the two
supported providers — never a silent GitHub default (LESSON-009). Config parsing
and the fail-loud message live in `tools/adlc/forge_config.py` (no shell YAML
parsing — REQ-515 ADR-3); the no-config path is pure shell.

## Config: the `forge:` section

```yaml
forge:
  provider: azure-devops   # github | azure-devops | auto (default: auto)
  auth: ADO_PAT            # a credential SOURCE NAME, never a key value
```

`auth` discipline (BR-6): the value is a *source name* — `gh` (logged-in CLI),
`az` (CLI login), or the **NAME** of an env var holding a PAT. A key-shaped value
is refused with an actionable error. PATs are read from the named env var at call
time, never echoed, logged, or sent to telemetry.

## Operations

| Function | GitHub backend | ADO backend |
|----------|----------------|-------------|
| `adlc_forge_pr_create --base --head --title --body [--draft]` | `gh pr create …` | `az repos pr create …` |
| `adlc_forge_pr_ready <n\|url>` | `gh pr ready` | `az repos pr update --draft false` |
| `adlc_forge_pr_edit <n> [--title --body]` | `gh pr edit` | `az repos pr update --title/--description` |
| `adlc_forge_pr_view <n\|url> --fields …` | `gh pr view --json` | `az repos pr show` |
| `adlc_forge_pr_list [flags]` | `gh pr list` | `az repos pr list` |
| `adlc_forge_pr_merge <n\|url> [--squash] [--delete-branch]` | `gh pr merge` | `az repos pr update --status completed --squash true --delete-source-branch true` |
| `adlc_forge_pr_comment <n\|url> --body` | `gh pr comment` | `feature-unsupported` (v1) |

The GitHub backend is **byte-compatible** with the pre-migration direct `gh pr`
calls (BR-3): the same command and flags, so existing GitHub installs see zero
behavior change.

## Normalized result / error surface (BR-4)

Success: newline-delimited `key=value` lines (`url=`, `number=`, `state=`,
`mergedAt=`, `body=`, …) — identical field names from both backends.

Failure: a non-zero return plus

```
error_class=<auth-missing|pr-not-found|merge-blocked-by-policy|feature-unsupported|
             local-git|network>
raw=<verbatim backend stderr, one raw= line per stderr line>
```

The raw backend stderr is **never swallowed** — the class is for branching, the
`raw=` lines for human diagnosis (LESSON-008). Distinct failures never collapse
into one label.

**`network` is the fall-through default, which makes it the class to distrust
(BUG-201).** `_adlc_forge_classify` substring-matches backend stderr, so a
refusal signature the patterns do not know about does not fail loudly — it
silently acquires `network`, the one class that reads as transient and invites a
retry. BUG-201 was exactly that: every GitHub `mergePullRequest` branch-protection
refusal ("4 of 4 required status checks are expected", "Base branch was
modified", "approving review is required") landed on `network`, and so did the
Azure DevOps completion refusals whose prose says "policies" — plural, which
`*"policy"*` does not match. Both backends share the one classifier, so a missing
pattern is never a single-backend defect.

Two consequences for anyone editing the classifier:

- **Add the signature *and* pin it.** `partials/tests/forge.test.sh` §4b holds the
  table of real backend stderr strings mapped to the class each must produce, and
  §4c fails if the classifier can emit a class the header does not document — the
  guard that caught `local-git` having been added by BUG-150 without updating the
  contract line.
- **Order is load-bearing.** Patterns are tried most-specific-first, so an
  `auth-missing` or `pr-not-found` signature that happens to mention a policy word
  still wins. Note that `You're not authorized to push to this branch` is a
  *policy* refusal, not `auth-missing`: the credential is fine, the permission is
  the point.

**State normalization:** `pr_view.state ∈ {OPEN, MERGED, CLOSED}`. GitHub states
pass through; ADO `active→OPEN`, `completed→MERGED`, `abandoned→CLOSED`.

**Partial success on `pr_merge` (BUG-150, BUG-195).** `gh pr merge` performs a
remote merge and then a local tidy-up, and it aborts that tidy-up at the first
failure — routinely, because the default branch is checked out in another
worktree. The merge is real; gh's exit code is not evidence about it. The adapter
therefore asks the forge what happened and, when the PR is `MERGED`, returns 0
with `state=MERGED` plus a `warn=` line and the demoted `warn_class=`/`raw=`
diagnostics (never `error_class=` — the merge did not fail).

When `--delete-branch` was requested, `pr_merge` additionally emits:

```
branch_deleted=<1|0|skipped-fork>
```

`1` the remote branch is gone (gh deleted it, or the adapter completed the
deletion, or it was already absent); `0` it survives and the `warn=` line names
the exact `git push origin --delete <branch>` to run; `skipped-fork` the head
branch lives on a fork and is never auto-deleted. **Branch on this field, not on
`warn=` prose** — BUG-195 was precisely a remediation written as an English
sentence in a channel every caller parses for `key=value`. Only the *remote* ref
is the adapter's to clean up; the local branch stays the caller's own cleanup step
(it may still be checked out).

**Capability mismatches (BR-5), explicit:** ADO draft (`--draft`/publish), squash
(`--squash` + auto-complete `--status completed`), delete-source-branch, and a
branch-policy block → `merge-blocked-by-policy` (surfaced as a blocker, **never
bypassed** — ethos #6; this covers the prose forms, not just the `TF` codes,
since BUG-201). `pr_comment` on ADO → `feature-unsupported` with the
documented degradation.

## Mock backend (BR-10)

`ADLC_FORGE_MOCK=1` routes every op to an offline fixture dispatcher — no
`gh`/`az`/network. Keyed by:

- `ADLC_FORGE_MOCK_PROVIDER` — `github` | `azure-devops` (default `github`)
- `ADLC_FORGE_MOCK_SCENARIO` — `ok` (default) or any error-class name, which
  means *every* class the classifier can emit, `local-git` included (before
  BUG-201 that one fell to the unknown-scenario arm and came back as `network` —
  the same mislabel, reproduced inside the harness)

The mock honors the same provider semantics (ADO `pr_comment` →
`feature-unsupported`, normalized state) so it is a faithful stand-in, not a stub
that hides mapping bugs. This is the authoritative test surface for ADO (since
neither `az` nor a live org is required to exercise the mappings).

## ADO REST-via-PAT fallback (documented, NOT shipped in v1 — ADR-2)

The capability spike found `az` absent locally; `az repos` is the documented
primary backend. When `az` is unavailable, each ADO op maps to a single ADO REST
call authenticated by `Authorization: Basic base64(:$PAT)`. The per-op REST
mapping is documented inline at the top of `forge.sh` so a future REQ can
implement it behind the same adapter functions without changing any call site.

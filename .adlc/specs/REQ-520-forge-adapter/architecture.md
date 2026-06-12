---
id: REQ-520
title: "Forge Adapter — Architecture"
status: approved
created: 2026-06-11
updated: 2026-06-11
---

# Architecture — Forge Adapter (REQ-520)

## Summary

A single sourced POSIX partial, `partials/forge.sh`, exposes a forge-neutral PR
operation set (`pr_create`, `pr_ready`, `pr_merge`, `pr_view`, `pr_list`,
`pr_comment`). It resolves the active provider (`github` | `azure-devops` |
`auto`) from a `forge:` section of the shared ADLC config (REQ-515) with
`origin`-URL auto-detection as the default, dispatches to a GitHub backend (`gh`)
or an Azure DevOps backend (`az repos`), and normalizes results and errors into
one vocabulary so calling skills branch on a single shape. Every PR-lifecycle
call site in the skills is migrated to call adapter functions; a lint check
rejects new direct `gh pr` usage in skills. `adlc doctor` (REQ-519) gains a
`forge` check that supersedes its `gh-auth` check. A mock backend
(`ADLC_FORGE_MOCK=1`) makes the whole matrix testable offline.

This design mirrors the discipline of the inherited waves: it follows the
sourced-partial pattern of `partials/delegate-gate.sh` (REQ-515), reuses the
config-parsing shape of `tools/kimi/_common.parse_delegate_config` for the
`forge:` block, and extends the existing `tools/adlc/checks.py` doctor REGISTRY
rather than adding a parallel mechanism (REQ-519).

## Capability spike result (Open Question resolution)

`az` CLI is **not installed** on the build machine, and there is no live ADO org
to probe. Decision, consistent with the maintainer-accepted defaults:

- **ADO backend primary = `az repos` CLI.** The adapter shells to
  `az repos pr {create,update,show,list}`. REST-via-PAT (`curl` + the ADO REST
  API) is the **documented fallback**, not shipped as executable code in v1 — a
  `forge.sh` comment block documents the exact REST call each op would make so a
  future REQ (or an `az`-less site) can implement it without re-deriving the API.
- **`pr_comment` on ADO = `feature-unsupported` in v1.** `az repos pr` has no
  first-class comment subcommand; comment threads require the REST thread API.
  Per the accepted default, the op ships in the interface and the mock matrix,
  but the ADO mapping returns the normalized `feature-unsupported` class with the
  documented degradation. GitHub `pr_comment` maps to `gh pr comment` and works.
- **The mock backend is the authoritative test surface** for ADO (BR-10): since
  neither `az` nor a live org is present, every ADO mapping is exercised through
  `ADLC_FORGE_MOCK=1` fixtures, not a network call.

## Grep inventory — PR-lifecycle operations actually performed today

Distilled from a repo-wide `git grep` of executable `gh pr`/`gh api` call sites
(prose in lessons/agent-docs excluded). Each maps to exactly one adapter op:

| Today's command (call sites)                                   | Adapter op    | Notes |
|----------------------------------------------------------------|---------------|-------|
| `gh pr create --draft …` (proceed Step 0)                      | `pr_create`   | draft flag |
| `gh pr create --base … --head …` (bugfix, wrapup, proceed fb)  | `pr_create`   | non-draft |
| `gh pr ready <n>` (proceed Phase 6)                            | `pr_ready`    | |
| `gh pr edit --body/--title` (proceed, architect footprint)     | `pr_edit`*    | see note |
| `gh pr view --json body` (architect, manifest, proceed)        | `pr_view`     | body field |
| `gh pr view --json state,mergedAt/mergeable` (sprint, wrapup)  | `pr_view`     | state norm |
| `gh pr list --state open …` (manifest)                         | `pr_list`     | by branch pattern |
| `gh pr merge --squash --delete-branch` (proceed P8, sprint, …) | `pr_merge`    | strategy + delete |
| `gh pr checks <url>` (proceed P7, bugfix, wrapup)              | *out of scope* | CI-status abstraction is explicitly OOS in the spec |
| `gh pr diff <url>` (proceed P7, adversary)                     | *not migrated* | read-only local diff convenience, not a forge-state op; left as-is |
| `gh api repos/.../contents` (id-alloc, id-recheck)             | *not migrated* | BR-8: merged-artifact scan is pure-git/`gh api` tree read, NOT a PR op |

\* **`pr_edit`**: The footprint-publish and body/title-finalize call sites use
`gh pr edit`. Because the enum in the spec lists `pr_create`/`pr_ready`/
`pr_merge`/`pr_view`/`pr_list`/`pr_comment` but the skills demonstrably need
body/title edits, per the spec's own rule ("any missed op is added to the enum,
not called directly") we **add `pr_edit`** to the adapter (sets body/title;
preserves the caller-provided body verbatim). This keeps the footprint block and
WIP-title flip forge-neutral. GitHub → `gh pr edit`; ADO → `az repos pr update
--description/--title`.

`gh pr checks` (CI polling) is intentionally NOT abstracted — the spec lists
"CI-status polling abstraction" under Out of Scope. `gh pr diff` and `gh api`
tree reads are likewise left as direct calls: the former is a local read-only
convenience and the latter is pure-git artifact scanning (BR-8), neither a
PR-state operation.

## `partials/forge.sh` — interface

Sourceable POSIX shell, dogfooded under `zsh -c`, `bash -c`, Ubuntu bash (BR-9).
No `set -eu` inside (return codes are the contract, mirroring `delegate-gate.sh`).
Every function reads `$?` of any sub-call immediately. No cross-block state, no
`\b` in `grep -E`, no bare `$<digit>`, no `[0]` indexing, no `status=` var.

### Provider resolution — `adlc_forge_provider [<repo-dir>]`

Resolution order (BR-2): per-project `.adlc/config.yml` `forge.provider` >
machine config `forge.provider` > `auto`. `auto` inspects the `origin` remote URL:

- `github.com` → `github`
- `dev.azure.com` or `*.visualstudio.com` → `azure-devops`
- anything else → **fail loud** (rc=2), naming the URL and the two supported
  providers; never silently defaults to GitHub (BR-2, LESSON-009).

Echoes the resolved provider on stdout; exports `ADLC_FORGE_PROVIDER`. Config
parsing is delegated to `tools/adlc/forge_config.py` (a thin Python reader that
reuses the `parse_delegate_config` flat-YAML approach for a `forge:` block) so
shell never hand-parses YAML — same ADR as REQ-515 ADR-3. The shell calls it only
when a config file exists; the no-config fast path stays pure-shell (`git remote
get-url origin` + a case match).

### Credential discipline (BR-6)

- Config stores `forge.auth` = a credential *source name* only: `gh` (logged-in
  CLI) for GitHub, an env-var **name** holding a PAT for ADO, or `az` (CLI login).
- `forge_config.py` refuses a key-shaped value via the same `_looks_like_key`
  predicate ported from `_common.py` — a key-shaped `auth:` fails loud.
- PATs are read from the named env var **at call time**, never echoed, logged, or
  passed to telemetry. The adapter never prints the resolved secret.

### Operations

Each function: `adlc_forge_<op> <args…>`. On success echoes the normalized result
to stdout (newline-delimited `key=value`, never a raw backend blob); on failure
echoes a normalized error line `error_class=<class>` to stdout AND preserves raw
backend stderr beneath it (`raw=<verbatim stderr>`), returning non-zero (BR-4).
Error classes (closed set, BR-4): `auth-missing`, `pr-not-found`,
`merge-blocked-by-policy`, `feature-unsupported`, `network`.

| Op | Args | Normalized result fields | GitHub backend | ADO backend |
|----|------|--------------------------|----------------|-------------|
| `pr_create` | `--base --head --title --body [--draft]` | `url= number= state=OPEN` | `gh pr create` | `az repos pr create` (`--draft` supported) |
| `pr_ready` | `<number\|url>` | `state=OPEN` | `gh pr ready` | `az repos pr update --draft false` (publish) |
| `pr_edit` | `<n> [--title --body]` | `url=` | `gh pr edit` | `az repos pr update --title/--description` |
| `pr_view` | `<n\|url> --fields …` | `state= url= number= mergedAt= body=` | `gh pr view --json` | `az repos pr show` |
| `pr_list` | `--state --branch-pattern` | one `number=…|url=…|head=…` per line | `gh pr list --json` | `az repos pr list` |
| `pr_merge` | `<n\|url> [--squash] [--delete-branch]` | `state=MERGED` | `gh pr merge` | `az repos pr update --status completed --squash --delete-source-branch true` (auto-complete) |
| `pr_comment` | `<n\|url> --body` | `ok=1` | `gh pr comment` | `feature-unsupported` (v1) |

**State normalization (BR-4, Open-Question default):** `pr_view.state ∈ {OPEN,
MERGED, CLOSED}`. GitHub `OPEN/MERGED/CLOSED` pass through. ADO `active→OPEN`,
`completed→MERGED`, `abandoned→CLOSED`.

**Capability mismatches (BR-5), explicit mappings:**
- ADO draft PRs: `--draft` on create; `pr_ready` publishes via `--draft false`.
- Squash merge: ADO `az repos pr update --squash` + `--status completed`
  (auto-complete) ≈ `gh pr merge --squash`.
- Delete source branch: ADO `--delete-source-branch true` ≈ `gh --delete-branch`.
- Branch-policy block: ADO policy failure (stderr signature `TF402…`/policy) →
  normalized `merge-blocked-by-policy`, surfaced as a blocker, never bypassed
  (ethos #6). Mirrors a GitHub required-review block.
- `pr_comment` on ADO → `feature-unsupported` with documented degradation.

### Mock backend (BR-10)

`ADLC_FORGE_MOCK=1` (or `forge.provider` resolving while the mock is active)
routes every op to a fixture dispatcher inside `forge.sh` that returns
deterministic normalized output keyed by `(op, ADLC_FORGE_MOCK_PROVIDER,
ADLC_FORGE_MOCK_SCENARIO)`. Scenarios cover the happy path plus each error class
per op per provider. No network, no `gh`/`az` invocation — so CI and the
cross-shell matrix run offline. The mock honors the SAME provider semantics
(draft, state normalization, `feature-unsupported` for ADO `pr_comment`) so the
mock is a faithful stand-in, not a stub that hides mapping bugs.

## `adlc doctor` forge check (BR-7) — extends REQ-519 REGISTRY

Add `check_forge(profile)` to `tools/adlc/checks.py` and register it. It:
1. Resolves the provider (sources `forge.sh` under bash, like `_gate_verdict`
   sources `delegate-gate.sh`). No remote → `SKIP` with reason.
2. Reports resolved provider, backend CLI presence (`gh` / `az`), auth validity
   (`gh auth status` / `az account show` or PAT-var set), and a read-only API
   probe (`pr_list` against the mock or a bounded live call).
3. Each FAIL carries copy-pasteable remediation (BR-5 / REQ-519 discipline).

**Supersession (per inherited-context directive):** the new `forge` check
**wraps** the existing `gh-auth` semantics. The standalone `check_gh_auth` is
**removed from the REGISTRY** (its logic subsumed: when the resolved provider is
`github`, `check_forge` performs the `gh auth status` probe). `check_gh_present`
is retained but only relevant when provider resolves to `github`. This is the
single forge-auth mechanism, not a parallel one.

## Migration map (BR-1, BR-3 byte-compatibility)

Each migrated call site replaces the raw `gh pr …` with `adlc_forge_<op> …`,
sourcing `partials/forge.sh` with the two-level fallback in the SAME fenced block
as the call (conventions.md cross-fence rule; lint `cross-fence-fn`). The GitHub
backend emits the IDENTICAL `gh` command/flags as today (BR-3 — grep-verified per
op), so existing GitHub installs see zero behavior change.

Call sites migrated (executable only):
- `proceed/SKILL.md` Step 0 (draft create), `phases-6-8-ship.md` (ready, edit,
  view footprint, merge), `proceed/SKILL.md` Phase-6/7/8 summaries.
- `architect/SKILL.md` footprint publish (`pr_view` body + `pr_edit` body).
- `manifest/SKILL.md` open-PR list + per-PR body read → `pr_list` + `pr_view`
  (BR-8: routes through adapter; the `ls-remote`/`gh api` tree fallback stays).
- `bugfix/SKILL.md` create/edit/view/merge.
- `wrapup/SKILL.md` create/view/merge.
- `sprint/SKILL.md` merge + verify call sites; `workflows/adlc-sprint.workflow.js`
  agent-prompt strings that instruct `gh pr …` updated to instruct the adapter
  op (these are prose-in-JS that the leaf agents execute).

**MUST NOT disturb** (inherited-context constraints): REQ-518's
`partials/id-alloc.sh` / `id-recheck.sh` allocation/recheck blocks (their
`gh api` tree reads are BR-8 pure-git scans, NOT PR ops — left untouched), and
the `/spec`,`/bugfix`,`/wrapup` allocation/recheck blocks REQ-518 rewired.

## `lint-skills` presence guard (BR-1)

Add a check to `tools/lint-skills/check.py` that flags any **new** direct
`gh pr <subcommand>` in a `*/SKILL.md` fenced block (the post-migration shape):
the guard is written against the migrated reality — it allows `adlc_forge_*` and
allows `gh pr diff`/`gh pr checks` (explicitly out of scope), but rejects
`gh pr create|ready|edit|view|list|merge|comment` appearing directly in a skill.
Anchored to executable fences, not prose, to avoid flagging lesson/doc mentions.

## ADRs

- **ADR-1: One sourced partial + a thin Python config reader.** PR ops live in
  `partials/forge.sh`; YAML config parsing lives in `tools/adlc/forge_config.py`
  (no shell YAML hand-parsing — REQ-515 ADR-3). The `tools/` carve-out (BR-1) is
  used only for that reader; all op dispatch is shell.
- **ADR-2: `az repos` primary, REST documented-not-shipped.** Spike found `az`
  absent locally; mock is the test surface. REST fallback is documented in a
  `forge.sh` comment so a future site implements it without re-deriving the API.
- **ADR-3: Add `pr_edit` to the op set.** The skills demonstrably edit PR
  body/title (footprint, WIP-title flip); the spec mandates adding any missed op
  to the enum rather than calling it directly.
- **ADR-4: `forge` doctor check supersedes `gh-auth`.** Single auth mechanism;
  `check_gh_auth` removed from REGISTRY, its probe folded into `check_forge` on
  the github branch (per inherited-context BR-7 directive).
- **ADR-5: Normalized error surface preserves raw stderr beneath the class.**
  Distinct failures never collapse into one label (BR-4, LESSON-008): the class
  is for branching, the `raw=` line for human diagnosis.

## Test strategy (BR-10, BR-9)

Mock-backend test matrix under `tools/adlc/tests/` (and/or a `partials/tests/`
shell harness consistent with the existing `partials/tests/`): every op × both
providers × each normalized error class, plus provider-resolution cases
(per-project > machine > auto; auto-github, auto-ado, auto-unrecognized fail).
Config tests: key-shaped `auth:` refusal; missing PAT env → `auth-missing`.
Doctor tests: forge check PASS/FAIL/SKIP on github+authed, ado+PAT, ado+no-PAT,
no-remote. All run under macOS zsh/bash and (in CI) Ubuntu bash — the partial is
dogfooded under all three shells.

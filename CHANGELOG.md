# Changelog

All notable changes to the **adlc-toolkit** are documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/). This
project follows a **semver-flavored, epoch-based** scheme:

- **MAJOR** — a product *epoch*: an identity or platform shift that changes what the
  toolkit fundamentally is.
- **MINOR** — a feature drop: new skills, pipeline phases, or capabilities (typically
  one or more landed `REQ-*`).
- **PATCH** — fixes, docs, and bookkeeping (reserved going forward; in this
  back-populated history such commits are folded into the minor they shipped with).

This history was back-populated from git on 2026-06-08. Each version is an annotated
tag pointing at the last commit of its release; pure-bookkeeping commits (ID counters,
"mark complete") are folded into their feature's release. `#N` references are GitHub
PRs (`atelier-fashion/adlc-toolkit`).

**The five epochs:**

1. **1.x — SDLC toolkit** — the original SDLC skill pipeline.
2. **2.x — ADLC** — rebrand SDLC → ADLC; tag-based retrieval and cross-repo support.
3. **3.x — Portable toolkit** — genericized for external use via a config seam + presets.
4. **4.x — Kimi delegation** — Kimi K2.5 token-offload tooling, delegation telemetry,
   and the Dynamic-Workflows / multi-human-coordination era.
5. **5.x — Works anywhere** — provider-agnostic delegation, one-command install +
   `adlc doctor`, configurable agent tiers, collision-safe multi-user ids, and the
   GitHub/Azure DevOps forge adapter: the toolkit stops assuming its author's machine.

---

## [Unreleased]

### Added

- **BR→verification obligations (REQ-595).** The pipeline audited tests but never
  *specified* them: `/architect` broke a REQ into tasks, `task-implementer` wrote
  whatever tests it judged appropriate, and `test-auditor` reported on coverage
  afterwards — nothing between the Business Rules and the diff ever stated *which*
  rule was proven by *what*. LESSON-330 named the resulting failure (a numbered BR
  implemented as zero, caught only by the Phase-5 panel, or not at all). This moves
  the mapping upstream:
  - `/architect` gains **Step 4.5**, emitting a `## Verification` block per task —
    a `rule | kind | artifact | benign_path` table naming every BR and AC that task
    discharges and the concrete artifact that proves each one. Numbered 4.5 rather
    than renumbering Steps 5–7, which REQ-483/484 cite by number.
  - `kind` resolves **surface-first**: a task whose files are all `*.md` maps to
    `structural-check` (markdown skills have no test runner — their real
    verification is a `tools/lint-skills` check, not a lesser substitute for one);
    any other surface maps to `test-case`, with the artifact shape read from that
    repo's `.adlc/config.yml` `stack:` when present, else its observed test layout.
    No framework name is written into the skill, and the absent-config branch is
    silent rather than an error — which matters because the dogfooding repo has no
    `config.yml` and would otherwise reach the rule only through a failure path.
  - Every emitted row is validated **before write, regardless of origin**: the rule
    ordinal must exist in the parent REQ, the artifact is rejected on `..` then
    charset-validated, and `kind` is checked against the closed enum. Dropped rows
    are reported — a silent drop is indistinguishable from a rule that was never
    mapped, which is the failure the step exists to make visible.
  - `/validate` gains three checks over the task set. Unmapped **BR *and* AC** ids
    and detector rules missing a benign path are reported as **advisory** warnings
    (ACs are gated on the same footing as BRs — they do not reduce to business
    rules, so gating BRs alone would leave half the omission class open). A REQ with
    zero numbered BRs passes with a notice rather than having rules invented for it.
  - `templates/task-template.md` gains the section, **optional by design** so the
    157 task files already on disk stay valid.
- **Unstructured-source intake for `/spec` (REQ-594).** `/spec` assumed its input was
  already a coherent feature request; its only concession to ambiguity was a prose line
  telling it to "ask clarifying questions", with no artifact and no gate. Real
  requirements arrive as meeting notes, chat transcripts, and ticket dumps, and the
  operator compressed them by hand before `/spec` ever ran — so whatever was lost in that
  compression was invisible. New **Step 1.4** turns such a source into a draft REQ plus a
  classified **gap list**, checked section by section against the requirement template:
  - Each gap is `blocking` (no faithful spec without the answer) or `assumption` (the
    spec can proceed under a stated one). Interactively, blocking gaps halt before the
    spec is written; assumption gaps are written verbatim into Assumptions. The gap list
    lives in the spec rather than a separate `gaps.md` (ADR-4).
  - Activation is deliberately narrow — an explicit `--intake` flag, a readable file
    path, or input over 25 lines — so the ordinary one-line request path is untouched:
    no added prompts, no added latency, no `## Provenance` section.
  - The source is **segmented before delegation and reconciled after**, with any segment
    the delegate omitted read directly. Over an 8000-line budget the step **refuses**,
    naming the size, rather than truncating — a silently truncated read reports zero gaps
    precisely because the unread remainder is invisible.
  - Placed before Step 1.5 (a distilled statement is better retrieval-tag input than a
    raw transcript) and before Step 2 (an interactive halt must not burn a REQ id from
    the shared machine-global counter).
  - New `partials/intake.sh` (6 sourceable functions) and `partials/tests/intake.test.sh`
    (116 assertions, run under both bash and zsh).
  - **Not yet proven:** the interactive halt and the subagent non-interactive path are
    SKILL.md control flow, which no unit test reaches — they need a real `/spec --intake`
    run against a transcript before this is trusted end to end.
- **Incident→REQ attribution (REQ-593).** A bug and the REQ that caused it stop being
  unrelated artifacts. `partials/attribution.sh` derives the edge from history the repo
  already carries: blame the root-cause lines, read the blamed commit, extract an attested
  REQ id, validate it against the primary repo's spec directory. `/bugfix` Phase 2 records
  the result on the bug (`introduced_by`, `attribution` — both optional and additive on
  `templates/bug-template.md`), and `/status` gains an **Incident Attribution** section
  answering "which shipped REQs have produced incidents?".

  Three decisions carry the feature. **The commit body is read, not just the subject**:
  `git blame --porcelain` exposes only `summary`, which is the subject alone — measured on
  this repo, a subject-only read finds 37 of the 75 commits carrying provenance and
  silently loses 51% of available attributions. **TASK→REQ resolution is scoped to the REQ
  named in the same commit**: `TASK-001*.md` matches 16 of the 157 task files on disk, so
  an unscoped glob would return unrelated REQs and manufacture a false multi-candidate
  halt. **The reverse edge is derived, never stored** — REQ→incidents is recomputed by
  scanning `.adlc/bugs/` frontmatter, because a backlink written into a spec rots silently
  when an artifact moves or is renumbered.

  Attribution refuses rather than guesses: two or more surviving candidates are presented
  for the operator to choose from (one *or more* — a defect can genuinely emerge from
  several merged REQs), a trailer citing a REQ with no spec directory is dropped, and a bug
  with no derivable REQ records `attribution: none` and continues rather than halting.
  `partials/tests/attribution.test.sh` pins every case under bash, zsh, and sh against BSD
  `/usr/bin/grep`.

- **`--version` / `-V` on the delegation CLIs (REQ-553).** `adlc-read`,
  `adlc-write`, and `extract-chat` report the toolkit version, and the two
  delegate-calling CLIs additionally print the *resolved* provider — `base_url`,
  `model`, the `api_key_env` **name**, and `enabled` — through the same resolver
  a real call uses, so "which endpoint is this install actually talking to?" is a
  one-command answer instead of a config-file + environment + source read. The
  API key **value** is never read or printed. The flag is scanned out of argv
  before parsing (so it needs no other arguments — `adlc-write --version` works
  without `--spec`/`--target`), makes no network call, and works with no key, no
  config file, and no `openai` SDK installed; a config that fails to resolve
  degrades to a single `config_error:` line and still exits 0. The output is a
  stable `key: value` contract, so a future `adlc doctor` can consume it without
  parsing prose. Documented in `tools/delegate/README.md`.

  **Hardened in the same REQ:** the resolved `api_key_env` is checked against an
  `UPPER_SNAKE_CASE` allow-list (not just a key-family blocklist) at the end of
  the cascade, so a key pasted into the higher-precedence
  `ADLC_DELEGATE_API_KEY_ENV` override — or a vendor prefix the blocklist never
  heard of — is refused instead of printed; `base_url` userinfo is redacted to
  `***@host` on the print path only; the argv scan is value-aware, so `-V` in an
  option's value position is no longer mistaken for a version request; the
  repo root is validated as a real toolkit checkout, so a copy vendored inside
  another git repo reports its own version rather than the host's; and only the
  first line of `VERSION` is read, bounded, so it cannot forge extra output
  lines. A follow-up audit round closed the residuals: the parsers now refuse
  prefix abbreviations, so the pre-parse scan's exact-spelling option sets are
  provably complete (`--sp "--version"` no longer hijacks the version path);
  every value interpolated into the report is collapsed to one line with control
  characters stripped, so a newline in a model name or `VERSION` file cannot
  forge an `enabled:` line; the repo root is validated by *identity* rather than
  marker-file existence, so an outer checkout containing a vendored inner copy
  no longer wins; AWS access-key IDs (`AKIA`/`ASIA`/… ) are refused as
  `api_key_env` despite being valid `UPPER_SNAKE_CASE`; URL redaction is
  fail-closed, stripping userinfo syntactically before parsing so a malformed
  URL can never print its password; and the privacy notice now names the
  resolved endpoint host, so a hijacked `base_url` is visible at the moment file
  contents leave the machine.


- **Atomic remote id reservation at allocation time (REQ-546).** `adlc_alloc_id` now
  *reserves* a candidate number on `origin` before returning it, by pushing a
  lightweight `refs/adlc/ids/<kind>/<NNN>` ref at a distinct commit object — first
  writer wins, because a second push of a different object is rejected
  non-fast-forward. Adds `adlc_reservation_nonce`, `adlc_reserve_id`, and
  `adlc_remote_reservation_nums`; wires the reservation namespace into
  `adlc_remote_high` as a **third independent source** alongside the existing two, so
  a number in flight on another machine is visible before it has any artifact; and
  adds a bounded reservation-retry loop inside the existing lock. Push outcomes are
  classified empirically — `won` / `race` / `policy` / `transport` — rather than by
  exit code. `assume` becomes a fourth, per-repo-scoped id kind (counter, lockdir,
  artifact path, scan, single-repo derivation). The refspec uses brace form to avoid
  the zsh `:r` modifier hazard (LESSON-335).

- **REQ id pre-push recheck wired into `/proceed` (REQ-545).** `/proceed` had no
  `adlc_recheck_id` call site, so a REQ id allocated by `/spec` could become a pushed
  `feat/REQ-xxx` branch on a second machine with no pre-push remote re-verification —
  the REQ-518 BR-4 gap, open for the REQ kind only. The recheck now runs as a labeled
  sub-block in Step 0 item 4, after the origin fetch and before worktree registration.
  An exact-full-branch-name `ls-remote` probe provides the BR-3 self-exemption so the
  pipeline does not halt on its own footprint during resume or crash recovery; a
  same-id different-slug branch, or a merged artifact, still halts with the renumber
  instruction. Degraded remotes proceed, per the partial's existing contract.

- **Three specs drafted from the Cerebro ADLC comparison (REQ-593, REQ-594, REQ-595).**
  Artifacts only when drafted — all three were `status: draft`, and each carried an
  adversary report with verdict *found problems* and unresolved critical/major
  findings. `REQ-593` would attribute a BUG to the REQ that shipped its cause by
  walking `git blame` → commit trailer → TASK → REQ; `REQ-594` would add an intake
  step to `/spec` that turns unstructured input into a draft plus a classified gap
  list with a gate. **REQ-595 has since shipped** — see its entry above; its adversary
  findings (F7–F10) were closed in the spec before implementation. REQ-593 and REQ-594
  remain drafts: listed here because the specs are in the tree, not because the
  behavior is.

### Fixed

- **`delegate.enabled: false` is now honoured (BUG-205).** ⚠️ **Behavior change —
  read this if you rely on a legacy API key to enable delegation.**

  The BR-11 opt-in was a flat OR that tested the legacy-key arm *before* the config
  file, so an exported `MOONSHOT_API_KEY`/`KIMI_API_KEY` silently outranked an
  explicit `delegate.enabled: false`. The gate returned `ok`, `adlc-read --version`
  reported `enabled: true` against a config saying `false`, and file contents went to
  the configured third-party endpoint after the operator had written down that they
  must not. Since REQ-519 `install.sh` scaffolds a config containing exactly that
  line, this was the default posture of every install with a key in the environment.

  BR-11's continuity exception was written for *pre-config* installs — where
  `enabled` is **absent** — but was implemented as "not true", which also swallowed a
  written `false`. Absence is a default; `false` is an instruction.

  `enabled` now resolves in the same precedence order as the provider fields (BR-2),
  which it never previously followed:

  1. `ADLC_DELEGATE_ENABLED=1` → on
  2. `delegate.enabled`, when the key is **present** → decisive **in both directions**
  3. a legacy key, reached only when **no config file exists** → on
  4. otherwise → off

  `ADLC_DISABLE_DELEGATE=1` still forces off ahead of all of it.

  **Migration:** if your config carries the scaffolded `enabled: false` and you were
  relying on a legacy key to opt in, delegation is now **off**. Set `enabled: true`
  (or export `ADLC_DELEGATE_ENABLED=1`). `adlc-read --version` prints the resolved
  value. Installs with no config file are unaffected — continuity is preserved
  exactly where BR-11 meant it.

  Also in this fix:
  - New gate reason **`disabled-via-config`**, so telemetry distinguishes a
    deliberate opt-out from a machine that was never opted in. Callers that branch
    only on the 0/1/2 return code are unaffected; the 0/1/2 contract is unchanged.
  - The config probe is now **fail-closed on exit status as well as output**. Command
    substitution captures stdout and discards the exit code, so a probe that printed
    `1` and then failed was read as consent.
  - `partials/tests/delegate-gate.test.sh` — new harness (arm ordering, fail-closed
    posture, and assertions that the no-config path still never forks), registered in
    `partials/tests/run.sh` and run under both bash and zsh.
  - The `tools/delegate/README.md` opt-in section contradicted itself: it documented
    `absent/false => disabled` eleven lines below listing a legacy key as sufficient
    on its own. Both halves are corrected, and the precedence table now states that
    `enabled` follows it.

- **`tools/lint-skills` no longer passes a scan that checked nothing (REQ-595).**
  REQ-435 fixed the vacuous *walk* — a scan root sitting under `.worktrees` is no
  longer skipped into oblivion — but a root that genuinely contains no `SKILL.md`
  still produced zero findings and exited `0`: the same confident green, one layer
  down. The scanned-file count is now threaded out of `run()` (not recomputed, so
  it cannot drift from the files the checks actually saw), printed to stderr on
  every run, and a zero count exits **255**. The findings cap moves to **254** so a
  saturating findings run can never be mistaken for a vacuous one — POSIX statuses
  are 8-bit, so the distinct value is carved out of the top of the range rather
  than placed above it. `/analyze` Step 1.9 already treats a non-zero exit with no
  parseable output as non-blocking, so it now reports the dimension as unavailable
  instead of falsely clean.

  Two pre-existing skip-directory tests asserted only that *nothing was reported*
  over a root whose every `SKILL.md` was excluded — an assertion a wholly broken
  walker also satisfies. Both now stage a real in-root skill, so exclusion is
  proven with a demonstrably working walker.

### Removed

- **`/map` skill removed from the distribution (REQ-526).** `/map` regenerated the
  `atelier-map` Obsidian vault and was hardcoded to the `atelier-map` repo and the
  Atelier sibling repos under `~/Documents/GitHub` — a project-specific skill that
  has no meaning for any other adopter and violated the "skills must work for any
  consumer project" rule in a stack-agnostic distribution. It was undisclosed in the
  README catalog and reached `~/.claude/skills/` only because `install.sh` symlinks
  the whole repo root.

  **Migration / tombstone:** `/map`'s functionality is not deleted, only un-distributed.
  Relocate it to the atelier project's own skill directory (or a personal
  `~/.claude/skills/` entry outside this repo). The full `map/SKILL.md` body is
  recoverable from git history at the REQ-526 removal commit. No consumer project
  references `/map` by name in its own automation, so the removal is non-breaking for
  the distribution.

### Fixed (context-doc truth pass, REQ-526)

- Corrected every "five principles" claim in `architecture.md`, `conventions.md`, and
  `project-overview.md` — ETHOS.md has seven principles; rephrased to a count-free
  "the ETHOS principles".
- Rewrote `project-overview.md` to describe the current tree truthfully (the toolkit
  tracks its own lessons and bugs; numbering is remote-derived per REQ-518; the 4.x
  and 5.0 epochs exist).
- Reordered this changelog's epoch summary list to read 1→5 in source order (the `4.x`
  and `5.x` bullets had been transposed).
- Completed the template enumerations in `README.md` and `architecture.md`
  (`taxonomy-template.md` was missing) and documented the `id-alloc.sh`/`id-recheck.sh`
  partials in `partials/README.md`, dropping its stale "partial drift detection not yet
  implemented" claim.

### Fixed (post-5.1.0 defect sweep)

Backfilled 2026-08-30. These landed between 2026-06-12 and 2026-08-28 and were not
recorded at the time; PR numbers are `atelier-fashion/adlc-toolkit`.

- **`/template-drift` trusted an unverified canonical baseline (BUG-204, #127).**
  `~/.claude/skills` is a symlink to a **working checkout**, not a release artifact — it
  can sit on a feature branch, behind `origin/main`, or dirty — and whatever it contained
  was silently treated as canonical. A stale baseline does not weaken verdicts, it
  **inverts** them: a consumer carrying the *newer* file is reported `stale`, and Step 6
  then proposes copying the older baseline over it, so the skill drives a regression with
  full confidence. Observed 2026-08-28, when the checkout sat on a branch cut before
  BUG-201 merged and `infrastructure` — which correctly carried the fix — was reported as
  the stale one. New **Step 0a** resolves the real checkout via `readlink`, fetches,
  captures branch/default/dirty/behind, names the baseline in the report header *always*,
  and warns with the consequence spelled out. Prefers
  `git show origin/<default>:<path>` when the checkout is not clean-and-current;
  otherwise downgrades every `stale` to `unverified-baseline` rather than asserting drift
  the baseline cannot support.

- **`/template-drift` compared only the checked-out branch (BUG-203, #126).** In a
  `dev → staging → main` repo a vendored file is one thing *per branch*, and the branches
  disagree by design: a sync PR reaches `main` only at the next promotion, a promoted
  change reaches `dev` only at the next reverse-sync. Reading the working tree answered a
  question nobody asked, and answered it confidently — under-reporting being the exact
  failure this skill exists to prevent. Both directions were live on 2026-08-28: two
  repos were in sync on `staging` and stale on `main`, and were given sync PRs that had
  to be withdrawn; a third was stale on `dev` only and reported clean. New **Step 0**
  fetches, detects the integration branch using `/proceed` step 4's *existing* signals
  rather than a second rule, enumerates the long-lived branches that actually exist, and
  reads per branch with `git show`, degrading to working-tree-only (and saying so in the
  header) when there is no git or remote. New **Step 3e** folds per-branch results into
  one verdict — `clean`, `needs-sync`, `pending-promotion`, `needs-reverse-sync`,
  `regression`, `partial-missing`, `uncommitted` — each routed to its correct remedy.
  Two rules the old skill could not express: never propose a sync PR for
  `pending-promotion` (the commit exists; the gap is a promotion), and never propose a
  plain squash PR for `needs-reverse-sync` (ancestry is the reverse-sync script's
  idempotency check). The report is now a surface × branch matrix, and proposed actions
  name their PR base.

- **The forge classifier had no pattern for branch-protection merge refusals (BUG-201,
  #125).** `_adlc_forge_classify` reported them as `error_class=network` — the one class
  that reads as transient and invites a retry, when the real fix is to update the head
  branch and wait for checks to re-report. The classifier substring-matches backend
  stderr with `network` as its **fall-through default**, so an unknown signature does not
  fail loudly; it silently acquires the least actionable class. Its policy arm matched
  only `policy` / `branch protection` / `blocked` / `not mergeable` / `TF402455`, none of
  which are words GitHub's `mergePullRequest` refusals use. Never a GitHub-only defect:
  both backends share the classifier, and Azure DevOps completion refusals say
  "policies" — plural, which `*"policy"*` does not match. Adds a second, **purely
  additive** `merge-blocked-by-policy` arm (the pre-existing pattern set is byte-unchanged,
  so no previously-correct classification can regress), placed after `auth-missing` and
  `pr-not-found` per the documented most-specific-first ordering. Note that
  `You're not authorized to push to this branch` is a *policy* refusal, not
  `auth-missing`: the credential is fine, the permission is the point. Also names
  `local-git` in the BR-4 contract line, in `forge.md`, and in the mock scenario
  dispatcher — BUG-150 added the class without updating any of them, so
  `ADLC_FORGE_MOCK_SCENARIO=local-git` came back as `network`. `forge.md` now documents
  that `network` is the fall-through and therefore the class to distrust. Regression
  coverage: §4b pins 18 real backend stderr strings to their classes with negative
  anchors, §4c is a doc-contract guard that fails if the classifier can emit a class the
  header does not name, §4d drives both classes through the whole `pr_merge` mock path.

- **`adlc_forge_pr_merge --delete-branch` downgraded a request to advice (BUG-195,
  #121).** It reported `state=MERGED`, returned 0, left the remote branch in place, and
  emitted a stderr sentence telling the caller to run `git push origin --delete <branch>`
  — placeholder unsubstituted, in a channel every caller parses for `key=value`. BUG-150
  had fixed the *reporting* of this partial success and deliberately left the outcome to
  the caller; no caller ever acted on it, and a grep across all six call sites found no
  handling of `warn=` at all. The trigger is the default agent topology (worktree +
  primary checkout on `main`), so essentially every merge from a worktree needed a manual
  step. The adapter now completes the remote deletion itself via `git push origin
  --delete`, which touches no local ref and is therefore immune to the worktree collision
  that breaks `gh`'s cleanup — idempotent (already-gone counts as deleted), never touches
  a fork head, never converts a merge into a failure. New normalized field
  `branch_deleted=<1|0|skipped-fork>` on both success paths whenever deletion was
  requested; `/bugfix` and `/wrapup` now branch on it. **Branch on the field, never on the
  `warn=` prose.**

- **`/spec` retrieval excluded the status the pipeline actually writes (BUG-194, #119).**
  Step 1.6 filtered the spec corpus to `approved` | `in-progress` | `deployed`. No
  toolkit skill writes `in-progress` or `deployed` — `/architect` writes `approved`, and
  `/wrapup` and `/proceed` Phases 6–8 write `complete`. Reader and writers overlapped on
  one transient value, so retrieval returned **0 of 42 specs in this repo and 11 of 543
  (2.0%) ecosystem-wide** — and reported it as a *cold start*, because the "nothing
  matched" and "everything was filtered out" strings were byte-identical. That is why it
  hid for four months. The allowlist becomes an exclusion list (`draft`, `superseded`,
  `cancelled`, `rejected`), admitting 506/543 (93.2%) — the 37 excluded being exactly the
  withdrawn and unvalidated specs; the bug corpus gains `closed`. New sub-step 1a warns
  when a non-empty corpus is fully removed by the status filter and records it in
  `## Retrieved Context` instead of emitting the cold-start line. New
  `retrieval-status-parity` lint check compares `/spec`'s exclusion list against the
  statuses `/architect`, `/wrapup`, and `/proceed` declare, written so that removing or
  relocating a declaration is a finding rather than a silent pass. No data backfill:
  `complete` is what the pipeline writes, so the corpus was correct and the filter was
  wrong.

- **Phase 8's terminal state write lived only on the cross-repo path (BUG-193, #117).**
  It sat inside a block headed "Cross-repo merge sequencing", so a single-repo pipeline
  following the document literally merged its PR, claimed `merged`, and left
  `pipeline-state.json` saying the run never finished. Found by auditing 36 state files
  in one single-repo project: **12 disagreed with their own merged PRs.** Topology decides
  *who merges*, not *whether Phase 8 closes out*. `proceed/phases-6-8-ship.md` splits
  Phase 8 into 8a Merge / 8b Close out (both topologies) / 8c `pr-ready` reconciler, with
  8b reordered so the state write precedes worktree teardown and the primary checkout
  named as the write target; `agents/pipeline-runner.md` gains the single-repo close-out;
  `wrapup/SKILL.md` Step 3.5 writes all five fields rather than two. `/status` gains
  Stale Pipeline State detection so the failure stays visible even when an actor forgets.

- **`/wrapup` session-JSONL discovery mis-encoded `.` in worktree paths (BUG-152, #115).**
  Claude Code encodes a project path into a `~/.claude/projects/` directory name by
  replacing every non-alphanumeric character with `-`; the encoder replaced only `/`, so a
  session inside a harness worktree computed `-.claude-` where the real name is
  `--claude-` and never matched. The walk then reached the repo-root directory of older,
  unrelated sessions and "newest wins" silently delegated one of those. Now encodes with
  the real rule (fork-free, via parameter expansion), tries exact match first and falls
  back to a normalized scan against the real listing, starts the walk at the working tree,
  and **refuses** when a REQ id was available and no candidate mentions it rather than
  serving an arbitrary transcript — "newest wins" applies only when there is no anchor to
  check against.

- **`gh pr merge`'s exit code was treated as evidence (BUG-150, #113).** `gh pr merge`
  does two independent things — the merge API call and a local tidy-up — and exits
  non-zero when only the *local* step fails. Three merges out of three on `teton-code`
  (PRs #32/#34/#35) landed successfully and were reported as failures. The trigger is the
  normal agent layout, not an edge case: the default branch checked out in another
  worktree while the session works from `.worktrees/`. Worse, the local git error matched
  no classifier pattern and fell through to `network`, inviting a retry against an
  already-merged PR, and because gh aborts cleanup at the failed step the source branch
  silently survived. On non-zero rc the GitHub arm now asks
  `gh pr view <ref> --json state`: if `MERGED`, report success and demote the captured
  error block to `warn_class=` so the diagnostics survive without the output claiming
  failure. The exit code is a claim; the PR state is the evidence.

- **Recheck probes did not self-identify (BUG-145, #105).** Two live false-positive
  instances of the LESSON-435 class: the reservation probe reported the allocator's *own*
  reservation ref as a collision, so every `/bugfix` and lesson recheck false-halted into
  a renumber treadmill; and the merged-artifact probe reported a REQ's *own* merged spec
  directory as a collision, firing on every fresh `/proceed` in the normal
  spec-merges-first flow. `adlc_reserve_id` now records won pushes to an own-reservation
  ledger matched by exact object SHA, and `adlc_recheck_id` takes an optional
  own-artifact-name argument compared against same-number entries via a new `names` mode
  on the shared artifact scan. Missing ledger data degrades to the historical collision
  halt — the safe direction.

- **`run.sh`'s harness list did not survive zsh (BUG-118, #97).** Iterates harnesses via
  positional parameters instead of an unquoted `$TESTS` string, and re-execs `run.sh`
  under each shell so its own zsh invocation is exercised on every run. Same class as
  BUG-116 (LESSON-329/335 zsh executor, LESSON-399 single-element masking).

- **`adlc-read` was unreachable from GUI-launched sessions (#111).** GUI-launched Claude
  Code sessions inherit a `PATH` without `~/bin` (only `.zshrc` adds it), so the gate's
  bare `command -v adlc-read` returned no-binary on machines where `~/bin/adlc-read` is
  installed and working — the source of the persistent gate-fail telemetry. Adds
  `_adlc_resolve_read_bin()` (PATH first, then an executable `$HOME/bin/adlc-read`),
  exported as `ADLC_READ_BIN` at source time and re-resolved on every gate check; the
  delegated-invocation fences in `/spec`, `/proceed`, `/analyze`, `/wrapup`, and
  `agents/delegate-pre-pass.md` invoke `"${ADLC_READ_BIN:-adlc-read}"`, the bare-name
  default keeping stale vendored gate copies working.

- **Telemetry duration guard and `mktemp` portability (#107).** `emit-step-telemetry.sh`
  validates that `start_s` is all-digits before the duration arithmetic — an empty or
  non-numeric operand inside `$(( ))` is fatal in zsh, and missing or garbage marks now
  yield a duration of `-` instead of crashing `/spec` Step 1.6. `skill-flag.sh` uses a
  full-path `mktemp` template instead of `-t <name>`: BSD `mktemp` treats the `-t`
  argument as a literal prefix and never expands its `X`s.

- **Boundary-free artifact-id matching sweep (#99, REQ-524 follow-up).** Fixes the
  `/sprint` eligibility example, whose bare `grep REQ-xxx` matched prefix siblings, and
  documents why `id-alloc`/`id-recheck` extraction plus exact-compare is already
  prefix-sibling safe.

- **Test portability off GitHub and outside the delegate venv (#100).**
  `test_cli_resolve_provider` asserted `github` against the checkout's own `origin`,
  failing on Azure DevOps and mirror clones; it now resolves against a synthetic repo with
  a GitHub remote, with `ADLC_CONFIG` neutralized so a machine config cannot override. The
  two `test_get_client_*` tests `importorskip("openai")` so they skip with a reason rather
  than erroring when the delegate venv deps are absent.

### Knowledge

- **LESSON-575 — a squash merge destroys the second parent a promotion depends on.** A
  `staging → main` promotion in `admin-api` was merged with the reflexive
  `--squash --delete-branch` idiom. `deploy.yml` resolves the staging image tag via
  `git rev-parse --verify HEAD^2` — the merge commit's second parent, whose SHA tags the
  image in the staging Artifact Registry. A squash commit has one parent, so the lookup
  fell through to a fallback that substituted the squash commit's own SHA and the docker
  pull missed with `manifest unknown`. Records the decision table for which PR shapes need
  `--merge`, the `--delete-branch` corollary (on a promotion the head *is* the permanent
  branch, and `branch_deleted=1` is meaningless there), and the one-line check that
  reveals a repo's promotion convention before you merge. Noted honestly as a **latent
  trap rather than a live bug**: the adapter has no default merge method — it forwards
  `"$@"` — but its signature advertises only `[--squash]` and four skill call sites
  hardcode it, none of which merges a promotion today.

- **LESSON-581 — a classifier's fall-through default is a claim about every input it has
  never seen.** `network` is a *diagnosis* ("this was transient, retry"), and making it
  the `*)` branch silently attached that diagnosis to every message the pattern set had
  not been taught. Prefer an honest `unclassified`; where a default must be a real class,
  pin the alternatives in a fixture table, because nothing in the code can detect that the
  patterns stopped covering the backend's wording.

- **LESSON-582 — bash 3.2 cannot parse a `case` inside `$( )`.** It reads the case
  pattern's `)` as the closing `)` of the substitution. Verified: syntax error on bash
  3.2.57 (macOS `/bin/bash` and `/bin/sh`), fine on bash 5.3.15, zsh 5.9, and dash. The
  sharper half is the failure's *direction*: Ubuntu CI runs bash 5 and would have gone
  green, and the zsh pass of `run.sh` was clean too — only the old local bash caught it.
  A parse error is total, so the suite aborted mid-run while still printing a healthy wall
  of `PASS` lines, and grepping that output for `FAIL` showed a clean bill of health.

- **LESSON-572 — a remediation is only real if its audience can execute it.** BUG-150
  correctly diagnosed gh's partial-success merge and fixed the reporting, then handed the
  leftover cleanup to "the caller" as an English sentence with an unsubstituted
  `<branch>` placeholder, in a channel every caller parses for `key=value`. Give each fact
  in a partial success its own normalized field, and finish the half you are able to
  finish.

- **LESSON-571 — a retrieval filter is half of a read/write contract.** Enumerate the
  actual writers of the field you filter on rather than the values you imagine; prefer an
  exclusion list over an allowlist for recall-oriented filters; and never let "nothing
  matched" and "everything was filtered out" render the same string.

- **LESSON-553 — shared post-work stranded on one branch of a fork.** The BUG-193 root
  cause generalized: work that both topologies owe must not live inside a block headed
  with one topology's name.

- **Also captured:** LESSON-434–439 (REQ-545/546 sprint knowledge), LESSON-440 (detectors
  need benign-path acceptance criteria), LESSON-441 (vendored partials shadow canonical
  fixes), LESSON-465 (verify vendored-surface sync per file; worktree chore branches),
  LESSON-471 + ASSUME-001 (REQ-553 wrapup knowledge), LESSON-478 (an exit code is a claim,
  an outcome is the evidence), LESSON-483 (a detected miss must refuse, not guess).

---

## [5.1.0] — 2026-06-12

The **de-brand drop** — completes REQ-515's genericization so a fresh adopter installs
nothing Kimi-named, and fixes the inert delegation telemetry:

- **REQ-522** De-brand the delegation surface + single-fence-safe telemetry:
  - `tools/kimi/` → `tools/delegate/`; the legacy `kimi-gate.sh` / `kimi-tools-path.sh`
    source-through partials are deleted (callers use the canonical `delegate-*`);
    `KIMI_TOOLS` → `DELEGATE_TOOLS`.
  - The `ask-kimi` / `kimi-write` CLI shims are **removed** — use `adlc-read` /
    `adlc-write`. `ADLC_DISABLE_KIMI` is no longer an accepted flag (only
    `ADLC_DISABLE_DELEGATE`). Legacy `KIMI_MODEL` / `KIMI_NO_WARN` env reads dropped
    (use `ADLC_DELEGATE_MODEL` / `ADLC_DELEGATE_NO_WARN`). The `KIMI_API_KEY` /
    `MOONSHOT_API_KEY` **key** env vars remain (continuity, data).
  - The launchd LaunchAgent is renamed (`com.adlc-toolkit.kimi-setenv` →
    `…delegate-setenv`); the installer **migrates** an existing Kimi agent (unload old,
    load new) and removes the legacy venv/shims on upgrade.
  - **Telemetry fix (adversarial finding C1, critical):** the per-step delegation
    telemetry in `spec`/`proceed`/`wrapup`/`analyze` set shell state in one fenced block
    and read it in another, so every run recorded `mode=fallback, gate=fail` and the
    ghost-skip detector was unreachable. State is now persisted to the flag-file sidecar
    (`skill-flag.sh mark`/`read`) and resolved by the shared `_adlc_emit_step_telemetry`;
    `delegated` and `ghost-skip` are now correctly emitted. Telemetry schema is unchanged
    — old log lines still parse in `check-delegation.sh`.
  - `lint-skills` gains a `cross-fence-var` check (a non-exported var assigned in one
    fence and read in another) and a `grep -ri kimi` brand-creep guard test.

  **Migration table** (old → new):

  | Old | New |
  |-----|-----|
  | `tools/kimi/` | `tools/delegate/` |
  | `partials/kimi-gate.sh` | `partials/delegate-gate.sh` |
  | `partials/kimi-tools-path.sh` | `partials/delegate-tools-path.sh` |
  | `$KIMI_TOOLS` | `$DELEGATE_TOOLS` |
  | `ask-kimi` / `kimi-write` | removed — use `adlc-read` / `adlc-write` |
  | `ADLC_DISABLE_KIMI` | `ADLC_DISABLE_DELEGATE` |
  | `KIMI_MODEL` | `ADLC_DELEGATE_MODEL` |
  | `KIMI_NO_WARN` | `ADLC_DELEGATE_NO_WARN` |
  | `com.adlc-toolkit.kimi-setenv` | `com.adlc-toolkit.delegate-setenv` |
  | `~/.claude/kimi-venv` | `~/.claude/delegate-venv` |
  | `KIMI_API_KEY` / `MOONSHOT_API_KEY` | unchanged (key continuity, data) |

## [5.0.0] — 2026-06-12

The **portability drop** — six REQs making the toolkit configurable for adopters
beyond the original machine, model, and forge:

- **REQ-515** Provider-agnostic delegation: `adlc-read`/`adlc-write` (Kimi names kept
  as shims), config-file provider resolution with strict precedence, delegation
  **disabled by default** on fresh installs, key-in-config refusal (#80).
- **REQ-517** New **`/adversary` skill** + dedicated `adversary` agent (18th):
  adversarial review of any artifact with mandatory self-refutation (#79).
- **REQ-519** **One-command `install.sh`** + **`adlc` umbrella CLI** with `doctor`
  (12 environment checks, copy-pasteable remediations, pure stdlib) (#82).
- **REQ-516** Configurable **agent model tiers**: `tier:` classes on all 18 agents,
  `adlc agents render` from config, drift detection in lint-skills (#83).
- **REQ-518** **Collision-safe ID allocation** across users/machines: remote-derived
  high-water via shared `id-alloc`/`id-recheck` partials, `adlc renumber` (#84).
- **REQ-520** **Forge adapter**: all PR operations behind `partials/forge.sh` with
  GitHub (`gh`), Azure DevOps (`az repos`), and mock backends — GitHub↔ADO is a
  one-line `forge:` config change or pure auto-detect (#85).
- Knowledge capture: LESSON-390 through LESSON-398 from the sprint's runner reports.

## [4.9.0] — 2026-06-08

- Added an **MIT `LICENSE`** (#64).
- ETHOS principle #7 **"Skeptical by Default"** added (#74).
- **fix(BUG-080):** `ask-kimi` now skips unreadable `--paths` instead of aborting the
  whole batch (#73); resolved with LESSON-334.

## [4.8.0] — 2026-06-05

- **REQ-483 — ordering enforcement:** draft-PR-early, footprint publishing, advisory +
  trial-merge preflight (#70); LESSON-330.
- **REQ-484 — cross-repo footprint publishing:** per-repo attribution derived from tasks (#71).
- **REQ-485 — auto-rebase & resume a blocked REQ** after its blocker merges
  (`/sprint` self-healing serialization) (#72); LESSON-331.

## [4.7.0] — 2026-06-04

- **REQ-482 — `/manifest` skill:** remote-derived in-flight visibility + advisory
  preflight overlap report (#69); LESSON-329.
- **fix(init):** stop vendoring `workflows/tests/` into consumer `.adlc/` (the Jest
  landmine) (#68).

## [4.6.0] — 2026-05-30

- **REQ-474 — re-platform `/sprint` onto Dynamic Workflows** (v1, `--workflow`-gated) (#67).
- Collapsed the workflow engine to one self-contained file (runtime has no `require`).

## [4.5.0] — 2026-05-29

- **REQ-473 — global cross-repo LESSON-ID counter** for `/wrapup` and `/bugfix` (#65);
  LESSON-313.
- Tuned agent model tiers + reasoning effort for Opus 4.8.

## [4.4.0] — 2026-05-18

- **REQ-433 — Kimi telemetry global-fallback resolver** (#50); LESSON-019.
- **REQ-436 — extract the analyze telemetry helper to a sourceable POSIX partial** (#53).
- **REQ-441 — global cross-repo BUG-ID counter** (#59); LESSON-023.
- **Fixes:** BUG-054 (lint-skills leaking absolute paths into CI logs) (#55), BUG-056
  (lazy-import `openai` so pre-API guards run without the SDK) (#57), and `/sprint`
  Phase-0 base-ref hygiene / integration-branch detection (#61). REQ-435 added
  `check.sh`-entrypoint + symlink-escape test coverage (#54).

## [4.3.0] — 2026-05-15

- **REQ-416 — toolkit refactor:** DRY the ethos + kimi blocks, shrink `/proceed`, lock a
  TOCTOU window, pin the kimi venv (#43); LESSON-015.
- **REQ-424 — skill-delegation telemetry:** ghost-skip detection + `/analyze` Step 1.8
  audit (#41); LESSON-012.
- **REQ-425 — `SKILL.md` corruption linter** (lint-skills) (#44); LESSON-016.
- **REQ-426 — REQ-416 follow-ups bundle:** install.sh integrity, reason DRY, partials
  drift + tests (#45); LESSON-017.
- **REQ-423 — content-anchored JSONL discovery** in `/wrapup` Step 4 (#42); LESSON-013.
- **REQ-427 / REQ-428 — analyze cleanups:** replace non-POSIX `shasum`/`xargs -0` (#46)
  and extract a shared `_adlc_emit_step_telemetry` helper (#47).

## [4.2.0] — 2026-05-14

- **REQ-417 — wave-2 Kimi skill delegation:** `/spec`, `/analyze`, `/proceed` Phase 5
  (#39); LESSON-010.
- **REQ-422 — Kimi rc-fallback + LaunchAgent** to break the launchctl
  env-inheritance failure mode (#40); LESSON-011.
- **fix(install):** canonicalize `REPO_ROOT` via `git rev-parse --git-common-dir` so
  wrappers survive worktree invocation (#38).

## [4.1.0] — 2026-05-13

- **REQ-413 — Kimi tools hardening:** offline pytest suite, base64 filter, exfil notice
  (#35); LESSON-007.
- **REQ-414 — pilot Kimi delegation in `/analyze` and `/wrapup`** with hard fallback
  (#36); LESSON-008.
- **REQ-415 — hotfix bundle:** path-traversal regex, broader redaction, install.sh shell
  detection + launchctl (#37); LESSON-009.

## [4.0.0] — 2026-05-12 · _Epoch: Kimi delegation_

- **REQ-412 — Kimi K2.5 delegation tooling** — the `ask-kimi` / `kimi-write` token-offload
  CLIs (#34); LESSON-006.

## [3.1.0] — 2026-05-04

- **REQ-380 — drop Phase 7.5 (canary) and Phase 8a (snapshot promotion)** from
  `/proceed` (#28).
- **REQ-381 — drop `/bugfix` Phase 6 canary**, fix the dangling Phase 7.5 reference (#31).
- ETHOS principle #6 **"If It's Broken, Fix It"** (#27).

## [3.0.0] — 2026-04-28 · _Epoch: Portable toolkit_

- **Genericize the toolkit for external use** via a config seam + presets (#24); scrubbed
  remaining project-specific examples (#25).
- Added `/proceed` Phase 8a (Create Promotion Snapshot), gated on
  `pipeline.snapshot_promotion` (#26). _(Later removed in 3.1.0.)_

## [2.3.0] — 2026-04-28

- **`/bugfix` ship phases** — PR + canary + merge + deploy + knowledge capture (#23).

## [2.2.0] — 2026-04-25

- **Cross-repo REQ support** across `/proceed`, `/architect`, `/wrapup`, `/canary`,
  `/validate`, `/init` (#18) and cross-repo awareness for `/status`, `/sprint`,
  `/bugfix` (#19).
- **REQ-263 — per-REQ unique worktree paths** for sprint orchestration (#22); a
  terminal-state contract for sprint (#21); repo-hygiene checks in `/analyze` (#20).
- Per-phase gating mitigation in `/proceed` (#15); LESSON-001. Fixes: cwd-agnostic
  wrapup cleanup (#17), atomic ASSUME/LESSON IDs, test-auditor dual-layout scan.

## [2.1.0] — 2026-04-20

- **REQ-258 — unified tag-based retriever** for `/spec` (#12).
- **REQ-262 — backfill tag frontmatter** across 4 consumer repos (#13).
- Genericized the review skill, consolidated the reflect checklist, removed the orphaned
  llm-review-prompt template, and made skills portable with local ETHOS/templates for the
  worktree sandbox (#8–#11).

## [2.0.0] — 2026-04-14 · _Epoch: ADLC_

- **REQ-249 — rebrand SDLC → ADLC** across all skills, agents, README, and ETHOS (#7).

## [1.3.0] — 2026-04-14

- **Added test-auditor and security-auditor** to the parallel review set (#4).
- Closed gate gaps, fixed wrapup ordering, and added the **template-drift** skill (#6);
  documented the symlink-based live-install setup (#5).

## [1.2.0] — 2026-04-11

- **Formal agent definitions** with model tiering and tool restrictions (#3).
- Optimized the SDLC pipeline — merged review phases, context filtering, component
  lessons (#1) — plus a follow-on perf pass on `/proceed` (#2).
- Began tracking **ETHOS.md** in-repo and pointed all skills at the tracked path.

## [1.1.0] — 2026-03-27

- **`/proceed` pipeline** — feature-branch-first, PR review/fix + wrapup phases, and
  pipeline-state tracking to prevent phase-skipping.
- **Parallel-session safety** — worktrees + an atomic REQ counter.
- Surfaced lessons-learned across the SDLC lifecycle.

## [1.0.0] — 2026-03-18 · _Epoch: SDLC toolkit_

- **Initial toolkit** — the original suite of SDLC skills + templates.
- `/reflect` gained a questions-for-user step before fix/defer.

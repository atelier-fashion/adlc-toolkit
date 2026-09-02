---
id: REQ-610
title: "Guard the two-level partial-sourcing pattern so a missing repo-local partial is not fatal under POSIX sh"
status: complete
deployable: true
created: 2026-09-02
updated: 2026-09-02
component: "adlc/partials"
domain: "adlc"
stack: [sh, bash, zsh, markdown, python]
concerns: [portability, correctness, silent-degradation, structural-enforcement, testing]
tags: [posix-sh, partials, sourcing, two-level-fallback, lint-skills, special-builtin, shell-portability, dot-source, vendored-partials, fenced-blocks]
---

## Description

Every sourceable-partial call site in the toolkit's skill fences is written as

```sh
. .adlc/partials/<name>.sh 2>/dev/null || . ~/.claude/skills/partials/<name>.sh
```

The intent is "consumer-project copy first, canonical toolkit copy as the fallback". Under
**bash** and **zsh** a failed `.` of a nonexistent file is an ordinary non-zero status, so
the `||` arm fires and the canonical copy is sourced. Under **POSIX sh** it is not: `.` is
a *special built-in*, and POSIX (XCU 2.8.1, "Consequences of Shell Errors") requires a
non-interactive shell to **exit** when a special built-in fails — the `||` never runs. This
is the behaviour of `dash` (Debian/Ubuntu `/bin/sh`) and of `bash` in posix mode, which
is what macOS ships as `/bin/sh`. The `2>/dev/null` makes the exit silent.

Observed 2026-09-01: the `/architect` Step 5 footprint block, run with `sh` in the toolkit
repo (which has no `.adlc/partials/` of its own), died at its first line and published
nothing; the identical block under `zsh` worked. The executor shell for skills on macOS is
zsh (LESSON-329), so for skills this is *latent* — but `partials/tests/run.sh` already
re-executes every harness under `/bin/sh` (REQ-609 BR-16), any consumer or CI job that
runs a fence under `sh` hits it, and a future executor change would turn every one of
the 55 call sites into a silent no-op at once. This is the LESSON-441 shape in reverse:
there, a *present* stale copy shadowed the canonical fix; here, an *absent* copy takes
the whole block down before the canonical copy is reached. Both come from the same
unexamined assumption that the first-level `.` failing is recoverable.

Reproduced 2026-09-02 with a sandbox (fake `$HOME` holding a canonical partial that
prints a marker; cwd with no `.adlc/partials/`):

| Form | `/bin/sh` (macOS, bash-posix) | `dash` | `bash` | `bash --posix` | `zsh` |
|---|---|---|---|---|---|
| `. A 2>/dev/null \|\| . B` (today) | **dies silently** | **dies silently** | ok (but see below) | **dies silently** | ok (but see below) |
| `command . A 2>/dev/null \|\| . B` | **dies silently** | ok | ok | — | ok |
| `[ -f A ] && . A \|\| . B` | ok, but sources **B as well** when A's last status is non-zero | same | same | — | same |
| `if [ -f A ]; then . A; else . B; fi` | ok | ok | ok | ok | ok |

So the `command` prefix is not a fix (macOS `/bin/sh` still exits), and the `&&`/`||`
chain is not a fix either: when the repo-local copy exists and its final command returns
non-zero, the canonical copy is sourced *on top of it*, inverting the repo-local-first
precedence that LESSON-441 depends on. The harness written for this REQ showed that **today's
`||` form has the same double-source defect** under bash and zsh: `.` returns the status of the
last command the sourced file ran, so a vendored copy whose final statement is non-zero also
triggers the canonical fallback on top of itself. Only the `if`/`else` form is correct under
every shell in the table.

**Blast radius.** The unguarded spelling is executable in 55 fenced call sites across
eight skills (`spec` 18, `analyze` 11, `wrapup` 10, `proceed` 8, `bugfix` 5, `architect`,
`manifest`, `status` 1 each), plus one fence each in `proceed/phases-6-8-ship.md` and
`agents/delegate-pre-pass.md`, once in `analyze/SKILL.md` prose that instructs the
agent to type the line, and **inside two partials**: a live two-level self-source in
`partials/emit-step-telemetry.sh`, and a three-level `. A || . B || . C` chain spread over
continuation lines in `partials/id-recheck.sh` — found not by any reader of the code but by
running the existing harnesses under `dash` once this REQ added it to `run.sh`. It is also the *documented* pattern in `partials/README.md`, in
`.adlc/context/conventions.md` "Bash in skills", in `.adlc/context/architecture.md`, in
the header comment of six partials and four companion `.md` files, and — load-bearing —
in `tools/lint-skills/check.py`, whose `CANONICAL_LITERALS` pins the *exact* old spelling
of the `delegate-gate.sh` and `delegate-tools-path.sh` source lines, backed by 16 lint
fixtures. Changing the fences without moving the lint in the same change makes the
canonical check fire on every delegating skill; changing the lint without the fences
leaves the pattern broken. They ship together.

**Why not a bootstrap partial.** A `partials/source-partial.sh` that defines
`adlc_source_partial <name>` cannot absorb this: the bootstrap itself has to be sourced
by every fence with the same repo-local-first two-level pattern, so every fence still
needs the guard — it would save nothing per call site while adding a third vendored file
to `/init` and `/template-drift`. The guard is applied at each call site, and the
structural guarantee that it *stays* applied is a lint check, not prose (LESSON-012).

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| SourceSite | file | string | a `*/SKILL.md`, `proceed/phases-*.md`, or `agents/*.md` under the scan root |
| SourceSite | line | number | absolute 1-based line inside a ` ```sh `/` ```bash `/` ```shell ` fence |
| SourceSite | partial | string | `<name>` in `partials/<name>.sh`; must resolve to an existing `partials/<name>.sh` |
| SourceSite | form | enum | `guarded` (the single canonical spelling, BR-3) \| `unguarded` (anything else that dot-sources a partials path) |
| Partial | repo_local_path | string | `.adlc/partials/<name>.sh` — may be absent (toolkit repo, pre-`/init` consumer) |
| Partial | canonical_path | string | `~/.claude/skills/partials/<name>.sh` — present on every symlink install |
| LintFinding | check | string | `unguarded-source`; reported as `<file>:<line>: …` so `/analyze` Step 1.9's parser reads it |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `fallback_sourced` | repo-local copy absent | canonical path sourced; execution continues past the source line under every shell in the table |
| `local_sourced` | repo-local copy present | repo-local sourced; canonical **not** sourced, regardless of the repo-local copy's final status |
| `source_failed_loud` | both copies absent, or the sourced copy has an error | the error reaches stderr naming the path; never swallowed by a redirect |
| `unguarded_source_found` | lint walk meets a `form=unguarded` site | `<file>:<line>` finding, non-zero exit from `check.sh` |

_Permissions: not applicable — no runtime actors. Section omitted deliberately._

## Business Rules

- [x] BR-1: Every sourceable-partial call site inside a fenced shell block MUST use a form under which an absent `.adlc/partials/<name>.sh` results in `~/.claude/skills/partials/<name>.sh` being sourced **and execution continuing past that line** under bash, zsh, dash, and bash-in-posix-mode (`/bin/sh` on macOS). Concretely: the repo-local copy is never dot-sourced without a `[ -f … ]` test proving it exists, because a failed `.` is a fatal special-built-in error under POSIX sh. The **final canonical arm is deliberately unguarded**: its absence means the toolkit is not installed, which is unrecoverable, so it fails loudly (fatal under `sh`, an error line under bash/zsh) rather than being tested and skipped — see BR-4 (informed by LESSON-329, LESSON-605).
- [x] BR-2: Exactly one copy is sourced. When the repo-local copy exists it is sourced and the canonical copy is NOT, even when the repo-local copy's final command returns non-zero — the `[ -f A ] && . A || . B` chain violates this and is therefore forbidden. Repo-local-first precedence is preserved unchanged (informed by LESSON-441).
- [x] BR-3: There is **one** canonical guarded spelling — `if [ -f .adlc/partials/<name>.sh ]; then . .adlc/partials/<name>.sh; else . ~/.claude/skills/partials/<name>.sh; fi` — on a single line, and the lint enforces that spelling, not "any guarded form". A family of accepted spellings is what rots a literal-presence guard (informed by LESSON-019 via REQ-436; REQ-425). The spelling contains no `$<digit>` (LESSON-335 arg-templating), no `[[`, no `local`, and stays correct under `set -e` and `set -u`.
- [x] BR-4: The guarded form suppresses **no** stderr. A syntax error inside a vendored copy, or a canonical copy missing on a machine without the toolkit, is reported on stderr naming the path. Today's `2>/dev/null` on the first arm is what made the 2026-09-01 death silent, and LESSON-441 requires that a crash be diagnosable against the copy actually sourced.
- [x] BR-5: `tools/lint-skills` gains an `unguarded-source` check: inside any ` ```sh `/` ```bash `/` ```shell ` fence, a statement-position `.` whose operand is a `partials/<name>.sh` path and which is not the BR-3 canonical spelling is a finding. In addition, the retired spelling (`.sh 2>/dev/null || . ~/.claude/skills/partials/`) is flagged **anywhere** in a walked file, prose included — the one prose occurrence in `analyze/SKILL.md` instructs the agent to type the line, so it is as executable as a fence. The check walks every file that carries such a source line: `*/SKILL.md`, `agents/*.md`, `proceed/phases-*.md`, and the partials themselves (`partials/*.sh` and a consumer's `.adlc/partials/*.sh`, every non-comment line, since a partial has no fences) — the last two families no lint check walks today and must be added without inflating the REQ-595 vacuous-scan count of `SKILL.md` files. Benign path (must NOT fire): the canonical spelling, and the executable-partial `!`-macro form `sh .adlc/partials/<name>.sh 2>/dev/null || sh ~/.claude/skills/partials/<name>.sh`, which runs `sh <file>` rather than `.` and so fails as an ordinary command (exit 127), never fatally (informed by LESSON-012, LESSON-440 via REQ-595 BR-4).
- [x] BR-6: `CANONICAL_LITERALS` in `check.py` is updated to the BR-3 spelling for the `delegate-gate.sh` and `delegate-tools-path.sh` source lines **in the same change** as the fences, and every lint fixture carrying the old spelling is updated so the suite stays green for the reason it should. A fixture that still carries the old spelling of the delegate-gate source line must fail the canonical check afterwards — proving the literal moved rather than being silently widened (informed by REQ-436 ADR-4, LESSON-019).
- [x] BR-7: A new harness `partials/tests/source-guard.test.sh` is added to `run.sh`'s harness list and runs under bash, zsh, and `/bin/sh` (and `dash` when installed — `run.sh`'s shell loop gains it with the same skip-with-notice posture as the others, because dash is the `/bin/sh` of Debian-family consumers). The harness does not hardcode the spelling under test: it extracts every distinct partial-sourcing line from the real fence-bearing files (BR-5's walk set) and executes each **verbatim** in a sandbox whose `$HOME` holds a marker-printing canonical partial per name, under the shell `run.sh` hands it via `ADLC_TEST_SHELL`. Cases: (a) repo-local absent → marker printed and a sentinel line *after* the source line printed (this case is **red under `/bin/sh` before the fences change** — the failing test is recorded, then made green); (b) repo-local present with a non-zero final status → repo-local marker printed, canonical marker NOT printed (BR-2); (c) both absent → stderr non-empty and naming the path (BR-4); (d) the `!`-macro executable form with the file absent → falls back, continues (BR-5 benign path). Extracting the lines from the corpus is what keeps the harness and the lint from disagreeing about what the fences actually say (informed by LESSON-329, REQ-609 BR-16).
- [x] BR-8: The pattern is retired from every place it is *documented*, not only where it executes: `.adlc/context/conventions.md` "Bash in skills" states the canonical spelling and the special-built-in reason; `partials/README.md`'s model-2 example, `.adlc/context/architecture.md`'s Partials paragraph, `tools/lint-skills/README.md`, and every partial header comment and companion `.md` example are updated. A grep for the retired spelling over the distribution surface (`*/SKILL.md`, `agents/`, `partials/`, `proceed/*.md`, `templates/`, `workflows/`, `README.md`, `.adlc/context/`, `tools/lint-skills/README.md`) returns zero hits. Historical records (`.adlc/specs/`, `.adlc/knowledge/`, `.adlc/bugs/`, `CHANGELOG.md`) are not rewritten.
- [x] BR-9: No new partial and no new skill directory. The guard lives at each call site; the guarantee lives in the lint (conventions: add partials sparingly; the bootstrap analysis in the Description).
- [x] BR-10: The change to partial header comments makes every consumer's vendored `.adlc/partials/*.sh` report `stale` in `/template-drift`. That is correct and expected; the CHANGELOG entry says so and names the re-sync as the follow-up, per-file and byte-for-byte (informed by LESSON-441, LESSON-465). The SKILL.md fences themselves are not vendored — they deploy to every session on a symlink install the moment the change lands.
- [x] BR-11: All shell introduced is BSD- and zsh-safe: no `\b` in `grep -E` (LESSON-013), no bare `$<digit>`, no `[0]` array indexing, no `status` variable, no unquoted word-splitting of a derived list (LESSON-335, LESSON-329), and any numeric token entering arithmetic is decimal-normalized (LESSON-396).
- [x] BR-12: A lint run that exits 0 having scanned zero files remains a failure (REQ-595 BR-5); the new check must not change the scanned count's meaning.

## Acceptance Criteria

- [x] AC-1: `sh partials/tests/run.sh` lists `source-guard.test.sh` and exits 0 under bash, zsh, and `/bin/sh` on the fixed tree; the PR records the harness's **red** `/bin/sh` result against the unfixed fences (case (a) failing, cases (b)–(d) as they stand).
- [x] AC-2: For every distinct partial-sourcing line extracted from the BR-5 walk set, case (a) prints the canonical marker and the post-source sentinel under `/bin/sh` with no `.adlc/partials/` present.
- [x] AC-3: Case (b) prints only the repo-local marker under all three shells; case (c) leaves a non-empty stderr naming the missing canonical path; case (d) continues past the `!`-macro form with the file absent.
- [x] AC-4: `bash tools/lint-skills/check.sh` on the repository is clean and reports a scanned count above zero. Against a fixture whose fence carries the retired spelling it reports `unguarded-source` with `<file>:<line>`; against a fixture whose prose carries it, it reports the finding; against fixtures carrying the canonical spelling and the `!`-macro executable form it reports nothing.
- [x] AC-5: `pytest tools/lint-skills/tests` passes; a fixture carrying the old spelling of the `delegate-gate.sh` source line fails the canonical check; a fixture in `proceed/phases-*.md` shape is walked by `unguarded-source` and is not counted as a `SKILL.md` for the vacuous-scan figure.
- [x] AC-6: `grep -rF '2>/dev/null || . ~/.claude/skills/partials/'` over the distribution surface named in BR-8 returns no matches.
- [x] AC-7: `.adlc/context/conventions.md` "Bash in skills" carries the canonical spelling, the special-built-in reason, and the two rejected forms with why (`command .` and the `&&`/`||` chain), so the next author does not re-derive them.
- [x] AC-8: The 2026-09-01 reproduction no longer reproduces: the `/architect` Step 5 footprint fence, extracted and run under `/bin/sh` from a checkout with no `.adlc/partials/`, executes past its source line.
- [x] AC-9: At least one single-fence skill (`/status` or `/manifest`) is executed under the real zsh executor after the change and behaves as before (informed by LESSON-329).
- [x] AC-10: `CHANGELOG.md` carries the entry with the BR-10 consumer note.

## External Dependencies

- None. `dash` is optional: `run.sh` skips it with a notice when absent.

## Assumptions

- The relevant POSIX-sh implementations are macOS `/bin/sh` (bash 3.2 in posix mode) and dash. The `if`/`else` form was verified under both on 2026-09-02, plus bash, `bash --posix`, and zsh; no other shell is claimed.
- `[ -f ]` (regular file exists) is the right existence test. An existing-but-unreadable repo-local copy then fails loudly at the `.` (BR-4), which is preferable to `[ -r ]` silently skipping to the canonical copy and hiding a permissions problem on the vendored file.
- The executor shell for skills stays zsh; this REQ is defence for `run.sh`, consumers, CI, and any future executor change, not a claim that skills fail today.
- The set of source-bearing files is `*/SKILL.md`, `agents/*.md`, `proceed/phases-*.md`, and `partials/*.sh` (plus a consumer's `.adlc/partials/*.sh`). If a fourth file family appears, the lint walk and the harness's extraction share one definition so they widen together.
- `~` is expanded by every shell in the table when it is the leading character of a `.` operand and of a `[ -f ]` operand; the canonical spelling relies on this exactly as the current one does.

## Open Questions

- [ ] Should the retired-spelling prose flag (BR-5, second sentence) be implemented as an entry in `sentinels.txt` (zero code, but sentinels walk only `SKILL.md` today) or inside the new check (walks all three file families)? Architecture decides; the requirement is only that all three families are covered.

## Out of Scope

- Rewriting the retired spelling in historical records (`.adlc/specs/`, `.adlc/knowledge/`, `.adlc/bugs/`, `CHANGELOG.md`).
- The executable-partial `!`-macro form (`sh … || sh …`) — it is not affected and is only *tested* here as the benign path.
- Re-syncing consumer repositories' vendored `.adlc/partials/` copies (a separate per-repo chore per LESSON-465, flagged by `/template-drift`).
- Changing the executor shell, or a general shell linter for fences (LESSON-329: lint cannot catch runtime shell semantics; this REQ adds one structural check for one known shape).
- Other `cmd 2>/dev/null || …` idioms in fences whose first command is an ordinary utility (`cat`, `git`, `gcloud`) — those fail as ordinary commands and are not special built-ins.

## Retrieved Context

- LESSON-605 (lesson, score 14): The octal-arithmetic trap is shell-divergent — zsh accepts what bash rejects, so dogfooding under one shell manufactures false evidence
- LESSON-441 (lesson, score 14): Repo-local-first sourcing means a canonical partial fix is not deployed until every vendored copy is re-synced
- LESSON-335 (lesson, score 14): Four zsh-executor/templating hazards in SKILL.md scripts: bare $<digit>, [0] arrays, unmatched globs, status= assignments
- LESSON-329 (lesson, score 14): Skill bash runs under the operator's shell (zsh) — dogfood by executing it, don't trust lint or an sh-only run
- LESSON-436 (lesson, score 11): zsh history-modifier parsing corrupts unbraced git refspecs
- LESSON-465 (lesson, score 10): A partially-synced repo looks healthy — vendored-surface drift must be verified per-file
- REQ-436 (spec, score 10): Extract analyze telemetry helper to a sourceable POSIX partial (fix cross-block + local declarations)
- LESSON-013 (lesson, score 10): BSD grep \b word-boundary in -E silently fails on macOS — use -wF instead
- REQ-603 (spec, score 9): Single-source the delegation authorization arms — the gate may veto, only Python may authorize
- REQ-595 (spec, score 9): BR→verification obligations: /architect emits the tests, not just the tasks
- LESSON-572 (lesson, score 9): A remediation is only real if its audience can execute it
- BUG-195 (bug, score 9): adlc_forge_pr_merge --delete-branch silently downgrades to a stderr suggestion
- REQ-522 (spec, score 9): De-brand the delegation surface and make skill telemetry single-fence-safe
- REQ-425 (spec, score 9): Pre-merge detection of corrupted shell constructs in SKILL.md files
- LESSON-396 (lesson, score 8): Zero-padded ids are octal to shell arithmetic — decimal-normalize portably

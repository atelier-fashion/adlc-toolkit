---
id: REQ-593
title: "Incident→REQ backlink: attribute a BUG to the REQ that shipped its cause"
status: draft
deployable: true
created: 2026-08-27
updated: 2026-08-27
component: "adlc/bugfix"
domain: "adlc"
stack: [markdown, bash, claude-skills]
concerns: [observability, correctness, maintainability]
tags: [backlink, traceability, incident, wrapup, cross-reference-rot, knowledge, attribution]
---

## Description

Today a BUG and the REQ that caused it are unrelated artifacts. `/bugfix` allocates a
BUG id, finds a root cause, ships a fix, and captures a LESSON — but nothing records
*which requirement introduced the defective behavior*. The knowledge loop closes into
hindsight (lessons) and never into attribution, so questions the corpus should be able
to answer cheaply — "which REQs have produced incidents?", "did REQ-483's ordering work
generate follow-on bugs?", "is this the third bug from the same REQ?" — require a human
to remember.

The linkage is already latent in the repo and merely unexploited. Conventions mandate a
`<type>(<scope>): <description> [TASK-xxx]` commit trailer for every pipeline-tracked
change, and each TASK file carries a `req:` frontmatter field. So `git blame` on the
lines identified during root-cause analysis yields a commit, the commit yields a
TASK/REQ trailer, and the TASK yields a REQ. This REQ makes that derivation an explicit,
guarded step of `/bugfix` and records the result on the bug artifact.

Scope note: this is *attribution*, not production telemetry. The toolkit has no log or
ticket ingestion surface and this REQ does not build one — incidents enter the system as
BUG artifacts, and BUG artifacts are what get attributed.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| Bug (frontmatter) | `introduced_by` | array of string | optional, additive; each element matches `^REQ-[0-9]{3,6}$`; empty array is a valid, meaningful "no attribution" |
| Bug (frontmatter) | `attribution` | string | optional; enum `derived` \| `manual` \| `none`; records how `introduced_by` was populated |
| Attribution candidate | `req` | string | `^REQ-[0-9]{3,6}$`; must resolve to an existing `.adlc/specs/<id>-*/` before it may be written |
| Attribution candidate | `evidence` | string | commit SHA + trailer literal the id was read from |
| Attribution candidate | `repo` | string | repo id from `.adlc/config.yml`; derivation is per-repo |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `attribution_proposed` | `/bugfix` completes root-cause analysis and has a file/line set | candidate list (`req`, `evidence`, `repo`) |
| `attribution_recorded` | candidate confirmed | `introduced_by`, `attribution: derived\|manual` |
| `attribution_declined` | no candidate survives validation | `attribution: none`, one stderr line stating why |

_Permissions: not applicable — no runtime actors, no roles. Section omitted deliberately._

## Business Rules

- [ ] BR-1: `bug-template.md` gains optional `introduced_by` (array) and `attribution` (enum) frontmatter fields. Purely additive — no existing field is renamed or reordered, and a bug without them stays valid (conventions: additive frontmatter changes only).
- [ ] BR-2: `/bugfix` derives candidates by running `git blame` over the file/line set already produced by root-cause analysis, then reading **both the subject and the body** of each blamed commit (`git log -1 --format='%s%n%b' <sha>` — blame's own `summary` field carries the subject only). Three attested forms are accepted, in precedence order: (1) a bracketed `[REQ-xxx]` or `[TASK-xxx]` anywhere in subject or body; (2) a bare subject prefix `REQ-xxx: …`; (3) a conventional-commit scope `<type>(REQ-xxx): …`. A `<type>(BUG-xxx): …` scope is **not** a REQ attribution — it identifies a prior fix, not the change that introduced the behavior — and yields no candidate from that commit. Measured per commit over this repo's 173-commit history at spec time: 72 commits carry provenance in one of the three forms, but only 37 carry a bracketed trailer **in the subject** — so a subject-only bracketed read finds 37 of 72 and silently loses 49% of available attributions (see Assumptions).
- [ ] BR-3: derivation is advisory. When more than one distinct REQ survives validation, `/bugfix` presents the candidates and does not choose; the operator selects **one or more**. Selecting several is legitimate when a defect genuinely emerges from the interaction of multiple merged REQs — this is why `introduced_by` is an array — but it is always an explicit human choice, never an automatic union of candidates. A detected-but-unresolvable attribution refuses rather than picking the closest guess (informed by LESSON-483).
- [ ] BR-4: the reverse index (REQ → its incidents) is **derived at read time** by scanning `.adlc/bugs/*.md` frontmatter. It is never written into the REQ spec. Storing the reverse edge would create exactly the cross-reference rot that a moved or renumbered artifact silently breaks (informed by LESSON-019, and the derive-don't-store posture of `/manifest` in REQ-482).
- [ ] BR-5: every id read out of a commit trailer is validated with the strict regex `^REQ-[0-9]{3,6}$` and an existence check before it is written to any artifact. The existence check resolves against the **primary** repo's `.adlc/specs/<id>-*/` — never the blamed repo's — because in cross-repo mode the spec directory exists only in the primary. Widening the regex is prohibited (informed by REQ-423, LESSON-008).
- [ ] BR-6: all shell is BSD- and zsh-safe: `grep -wF` never `\b` in `-E` (informed by LESSON-013), no bare `$<digit>`, no variable named `status`, no reliance on unquoted word-splitting (informed by LESSON-329, LESSON-335).
- [ ] BR-7: a bug with no derivable REQ — pre-dating the trailer convention, touching untracked files, or blaming to a commit with no trailer — produces `attribution: none` and continues. It does not halt `/bugfix` and never fabricates an id (benign-path rule, informed by LESSON-440).
- [ ] BR-8: derivation runs per-repo against that repo's own git history, keyed off the bug's `repo`/`touched_repos` frontmatter. A cross-repo bug produces at most one candidate set per touched repo (informed by REQ-484's per-repo attribution precedent).
- [ ] BR-9: `/status` gains a read-only line reporting bugs-with-attribution and the REQs they point at, derived per BR-4. No new skill directory is created (conventions: don't create skills casually).
- [ ] BR-10: TASK→REQ resolution is **scoped, never globbed**. A `TASK-xxx` id resolves only within the REQ identified by the same commit message (a bracketed `[REQ-xxx]`, a `REQ-xxx:` subject prefix, or a `(REQ-xxx)` scope), by reading `.adlc/specs/<that-req>-*/tasks/TASK-xxx*.md`. A bare `TASK-xxx` with no REQ context in the same commit is **not resolvable** and yields no candidate. TASK ids are per-REQ scoped, not global — `TASK-001.md`, `TASK-002.md`, and `TASK-003.md` each occur three times across different REQ directories — so a filesystem-wide glob would return several unrelated REQs and manufacture a false multi-candidate halt under BR-3.

## Acceptance Criteria

- [ ] A bug whose root cause blames to a commit carrying `[TASK-yyy]`, where `TASK-yyy`'s frontmatter says `req: REQ-xxx`, ends with `introduced_by: [REQ-xxx]` and `attribution: derived` in its frontmatter.
- [ ] A bug whose blame yields a commit with a direct `[REQ-xxx]` trailer (no task file) attributes identically.
- [ ] A bug whose blame yields a commit whose trailer is in the **body** and whose subject has none still attributes — the dominant real-world case, and the one a subject-only read misses.
- [ ] A bug whose blame yields a `REQ-526: …` subject-prefix commit attributes to REQ-526 with no bracketed trailer present anywhere.
- [ ] A bug whose blame yields a `fix(BUG-145): …` scope commit yields no candidate from that commit — a prior fix is not an introduction.
- [ ] A commit citing a bare `[TASK-001]` with no REQ context in the same message yields no candidate, and specifically does not halt with three candidates from the three `TASK-001.md` files on disk.
- [ ] A bug whose blame yields commits with no recognizable trailer ends with `attribution: none`, emits exactly one stderr line naming the reason, and `/bugfix` runs to completion.
- [ ] A trailer citing a REQ id with no matching `.adlc/specs/<id>-*/` directory is dropped, not written — verified by pointing a fixture commit at `REQ-999999`.
- [ ] Blame yielding two distinct valid REQ ids halts with both candidates presented and writes nothing until the operator selects one or more; selecting both writes a two-element `introduced_by`.
- [ ] Running the derivation on macOS `/usr/bin/grep` and under `zsh -c` produces the same result as under `sh -c` (dogfood requirement, informed by LESSON-329).
- [ ] Asking for REQ-xxx's incidents scans `.adlc/bugs/` and lists matching bugs; no `.adlc/specs/**` file is modified by that read.
- [ ] A cross-repo bug whose cause was blamed in a sibling repo still attributes: the id validates against the **primary** repo's specs directory and yields `attribution: derived`, not `none` (the BR-5/BR-8 interaction).
- [ ] A cross-repo bug touching two repos produces at most one candidate set per repo, each derived from that repo's own history.
- [ ] `/status` reports the bugs-with-attribution line, derived by scanning `.adlc/bugs/`; running it modifies no file.
- [ ] An existing bug file with neither new field parses and processes unchanged (backward compatibility).

## External Dependencies

- `git blame` (already assumed by the toolkit's git-native model)
- No new services, APIs, or libraries

## Assumptions

- Commit provenance is recorded in three forms, not one, and no single form dominates. Measured per commit at spec time over this repo's 173 commits: 37 carry a bracketed trailer in the subject, 37 in the body (59 in either), 20 use a `REQ-xxx:` subject prefix, 15 use a `<type>(REQ-xxx)` scope, and 19 use a `<type>(BUG-xxx)` scope that is deliberately not an attribution. 72 commits match at least one accepted form; the remaining 101 (merges, releases, un-tracked chores) carry no derivable provenance and are expected to yield `attribution: none`. BR-2's parser is sized to that measured distribution rather than to the convention as documented. Re-measure before assuming it holds in a consumer repo — a repo that squash-merges differently will have a different distribution.
- `git blame` on the root-cause file/line set is a sufficient proxy for "the change that introduced this behavior". Refactors and file moves will sometimes blame to the mover rather than the author of the defect; BR-3's refuse-don't-guess rule is what keeps that from becoming a false attribution.
- REQ ids allocated remotely (REQ-518) are stable and not renumbered after merge, so a stored forward edge stays valid.

## Open Questions

- [ ] Should `introduced_by` also be derivable in reverse for LESSONs (`LESSON-xxx` → REQ), or is the bug-only edge sufficient for now?
- [ ] Does a bug found *during* a REQ's own pipeline (caught pre-merge) count as attributed to that REQ, or is attribution reserved for post-merge escapes?
- [ ] Should `/manifest` surface attribution alongside its in-flight view, or does that belong only in `/status`?

## Out of Scope

- Ingesting production logs, APM data, crash reports, or support tickets. The toolkit has no runtime telemetry surface and this REQ does not create one.
- Any automatic reverse-edge write into REQ spec files (explicitly prohibited by BR-4).
- Renumbering, backfilling, or migrating attribution onto the 10 existing bugs. A follow-up may do this; it is not part of this REQ.
- Statistical or ML-based defect attribution. Derivation is deterministic blame-plus-trailer only.

## Retrieved Context

- LESSON-023 (lesson, score 11): When mirroring a hardened pattern to a sibling, port the rationale not just the mechanism
- REQ-441 (spec, score 9): Global cross-repo BUG-ID counter (mirror the global REQ counter)
- LESSON-020 (lesson, score 8): A shell function shared across SKILL.md steps must be a sourced partial
- REQ-436 (spec, score 8): Extract analyze telemetry helper to a sourceable POSIX partial
- BUG-193 (bug, score 7): Phase 8's terminal state write lives only on the cross-repo branch
- LESSON-402 (lesson, score 7): A status/degraded flag from `$(...)` must travel on stdout, not env
- LESSON-331 (lesson, score 7): Closed output schemas silently rot when a new code path adds fields
- REQ-423 (spec, score 7): /wrapup Step 4 robust JSONL discovery with sanitized path handling
- LESSON-553 (lesson, score 6): Post-work under one arm of a conditional is skipped by the other
- LESSON-483 (lesson, score 6): A detected miss must refuse, not fall back to the closest guess
- LESSON-441 (lesson, score 6): Repo-local-first sourcing means a canonical fix is not deployed until re-synced
- REQ-545 (spec, score 6): Wire the REQ id pre-push recheck into /proceed branch creation
- LESSON-335 (lesson, score 6): Four zsh-executor/templating hazards in SKILL.md scripts
- LESSON-329 (lesson, score 6): Skill bash runs under the operator's shell (zsh) — dogfood under it
- LESSON-330 (lesson, score 6): The Phase-5 review catches OMITTED requirements, not just bugs

---
id: REQ-594
title: "Spec intake: turn raw human input into a draft REQ plus an explicit gap list"
status: draft
deployable: true
created: 2026-08-27
updated: 2026-08-31
component: "adlc/spec"
domain: "adlc"
stack: [markdown, bash, claude-skills]
concerns: [correctness, developer-experience, retrieval]
tags: [intake, spec, requirements, gap-analysis, ambiguity, skill-md, provenance]
---

## Description

`/spec` assumes its input is already a coherent feature request. Its only concession to
ambiguity is item 3 of Step 1 (`spec/SKILL.md:34`): "If the feature request is vague or
ambiguous, ask clarifying questions before proceeding. Wait for answers." — an
unstructured, unbounded, easy-to-skip instruction with no artifact and no gate. (Note for
the implementer: this is a numbered list item under `### Step 1`, not a `### Step 1.3`
heading; the only sub-step headings in that skill are Step 1.5 and Step 1.6.) The upstream reality is messier: requirements arrive as meeting notes, a chat
transcript, a ticket dump, a voice-note transcription, or three paragraphs of stakeholder
prose. Today the operator does the compression from that into a feature request by hand,
before `/spec` ever runs, and whatever was lost or assumed in that compression is invisible.

This REQ adds an **intake step** to `/spec` that accepts unstructured input and produces
two things: a draft REQ, and an explicit, classified **gap list** naming what the source
material does not answer — checked section by section against the requirement template.
It converts "ask clarifying questions" from a prose suggestion into a structured artifact
with a gate, which is the same move LESSON-012 argues for generally: enforce structurally,
not by honor system.

The gap list is the point. A spec written from a transcript will always contain
assumptions; the failure mode is not making them, it is making them invisibly. ETHOS #1
says stop and clarify rather than guess — but only blocking gaps warrant stopping. The
rest become stated assumptions, which is what the template's Assumptions section is for.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| IntakeSource | `path` | string | file path; only the **basename** may be transmitted to a delegate (existing delegation privacy contract) |
| IntakeSource | `kind` | string | enum `transcript` \| `notes` \| `ticket` \| `prose` |
| Gap | `section` | string | the requirement-template section the gap belongs to (`System Model`, `Business Rules`, `Acceptance Criteria`, `External Dependencies`, `Out of Scope`) |
| Gap | `severity` | string | enum `blocking` \| `assumption` |
| Gap | `question` | string | the specific unanswered question, not a category label |
| Gap | `disposition` | string | enum `answered` \| `assumed` \| `open` |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `intake_started` | `/spec` receives unstructured input (BR-1 trigger conditions) | `IntakeSource` |
| `gaps_identified` | source material parsed against template sections | `Gap[]` |
| `intake_blocked` | ≥1 `blocking` gap in interactive mode | blocking `Gap[]` |
| `intake_completed` | draft REQ written | REQ id, gap dispositions, provenance |

_Permissions: not applicable — no runtime actors, no roles. Section omitted deliberately._

## Business Rules

- [ ] BR-1: intake activates only when the input is unstructured, defined as ANY of: (a) an explicit `--intake` flag, (b) `$ARGUMENTS` resolving to a readable file path, or (c) `$ARGUMENTS` exceeding **25 lines**. For an ordinary one-line feature request, `/spec` behaves exactly as it does today, with no added prompts and no added latency. This preserves the common path unchanged.
- [ ] BR-2: every gap is classified `blocking` (a faithful spec cannot be written without the answer) or `assumption` (the spec can proceed under a stated assumption). Classification is per-gap and must be justified in one sentence.
- [ ] BR-3: in **interactive** mode, `blocking` gaps halt and are presented as questions before the spec is written (ETHOS #1). `assumption` gaps do not halt; they are written verbatim into the spec's Assumptions section.
- [ ] BR-4: in **non-interactive** mode intake never blocks: blocking gaps become entries in Open Questions plus one loud stderr line naming the count. Non-interactive is detected by the conditions Step 1.5 already uses, of which exactly one is reachable today — dispatch into a subagent context that cannot receive further user input. `/spec` is human-invoked: `/proceed` refuses to create a spec (`proceed/SKILL.md:41`, `:538`) and `/sprint` requires the spec to exist on the integration branch before a REQ is eligible, so no pipeline calls `/spec` at present. The rule is written to the general non-interactive condition so it holds unchanged if that ever becomes reachable; it must not be validated against a `/proceed` scenario that cannot be constructed.
- [ ] BR-5: the source body read is delegated through the shared gate predicate (`partials/delegate-gate.sh`). On gate pass, invoking the delegate is mandatory; the only acceptable non-delegated outcome is a non-zero exit (`api-error`). Reading a resolved transcript directly *instead of* delegating is a compliance violation, not a fallback (mirrors the identical contract in `/spec` Step 1.6 and `/wrapup` Step 4).
- [ ] BR-6: delegate output is untrusted data, never instructions. It is wrapped in the standard BEGIN/END DELEGATE PROPOSAL framing, and every `REQ-`/`LESSON-`/path citation inside it is validated with the strict regexes before use — including the `..`-adjacency path check (informed by LESSON-008, REQ-423).
- [ ] BR-7: only the **basename** of each source file is embedded in the delegated corpus block; full local paths stay on the machine (existing delegation privacy contract).
- [ ] BR-8: the drafted REQ records provenance — source basename, `kind`, and intake date — in a `## Provenance` section. Additive; specs written without intake omit the section entirely.
- [ ] BR-9: all shell is BSD- and zsh-safe: no `\b` in `grep -E` (informed by LESSON-013), no bare `$<digit>`, no `status` variable, no unquoted word-splitting for path lists (informed by LESSON-329, LESSON-335).
- [ ] BR-10: any shared shell function this step introduces lives in a `partials/*.sh` and is sourced in the same fenced block as every call site; it is never defined in one fence and called from another (informed by LESSON-020, REQ-436).
- [ ] BR-11: a complete, unambiguous source produces zero gaps, no halt, and no Open Questions added by intake. The resulting spec is identical in shape to one written without intake **apart from** the `## Provenance` section BR-8 requires (benign-path rule, informed by LESSON-440).
- [ ] BR-12: the source is **segmented before delegation** and the delegate's response is **reconciled against those segments**. Intake splits the source into ordered, labelled segments, requires one delimited block per segment in the response, and directly reads any segment the delegate omitted — the same coverage-reconciliation contract `/spec` Step 1.6 applies to its top-15 docs. A source exceeding the documented segment budget is refused with a loud message naming the size, never silently truncated. Without this, a partial summary yields zero detected gaps precisely because the unread remainder is invisible, and BR-11's benign path would certify it (informed by LESSON-010, REQ-423).

## Acceptance Criteria

- [ ] A one-line feature request passed to `/spec` triggers none of BR-1's three conditions: no intake step runs, no gap list is produced, no `## Provenance` section appears in the output, and no intake stderr line is emitted.
- [ ] A meeting-transcript file passed to `/spec` produces a draft REQ plus a gap list with every entry classified `blocking` or `assumption` and attributed to a named template section.
- [ ] In interactive mode, a source missing an answer to "who is allowed to perform this action" yields a `blocking` gap on the Permissions/System Model section and halts before the spec file is written.
- [ ] Dispatched into a subagent that cannot receive user input, the same source writes the spec, puts the blocking gap in Open Questions, emits one stderr line stating the blocking-gap count, and does not wait for input. (Constructed by dispatching `/spec` via the Agent tool — the one non-interactive path that exists today.)
- [ ] `assumption`-severity gaps appear verbatim as entries in the written spec's Assumptions section — verified by grepping the output file for the gap text.
- [ ] With the delegate gate passing, telemetry records `mode=delegated`; with `ADLC_DISABLE_DELEGATE=1`, it records the disabled reason and the spec is still produced.
- [ ] A delegate response citing `REQ-999999` or a path containing `..` has that citation dropped from the draft — verified with a fixture response.
- [ ] The delegated corpus block contains only basenames; a full path from the source list appears nowhere in it.
- [ ] A delegate response that omits one segment causes that segment to be read directly, and the resulting gap list reflects its content — verified with a fixture response missing a middle segment.
- [ ] A source exceeding the segment budget is refused with a message naming the size; no spec is written from a partial read.
- [ ] Every fenced block introduced by this REQ passes `tools/lint-skills`, including the `cross-fence-fn` check.

## External Dependencies

- `adlc-read` and `extract-chat` (already shipped, already opt-in and gated). No new dependency; intake degrades to direct reading when the gate fails.

## Assumptions

- Unstructured sources arrive as text files on disk. Audio, video, and live meeting capture are not inputs to this REQ (see Out of Scope).
- The requirement template's section list is a sufficient checklist for gap detection. If the template gains sections later, the gap checker reads the template rather than a hardcoded list, so it follows automatically.
- The 25-line threshold in BR-1 is a heuristic. Misclassifying a long-but-clear request as needing intake is a tolerable failure — it produces zero gaps and proceeds (BR-11). Misclassifying a short-but-ambiguous one leaves the existing status quo in place, which is no worse than today.

## Open Questions

- [x] ~~Extension of `/spec` versus a separate `/intake` skill?~~ **Resolved 2026-08-27: extend `/spec`.** Conventions prohibit creating skill directories casually, and intake reuses `/spec`'s context loading, retrieval, and id allocation wholesale. Discoverability is addressed by documenting the flag in the skill catalog, not by a new directory.
- [ ] Should the gap list persist as its own artifact (`.adlc/specs/REQ-xxx-*/gaps.md`) or live only inside the spec's Assumptions and Open Questions sections?
- [ ] Should `/validate` gain a check that no `blocking` gap was silently dispositioned as `assumed`?
- [ ] The 25-line threshold in BR-1 is a chosen default, not a validated one. Should it be configurable in `.adlc/config.yml`, and is 25 the right number once real sources have been run through intake?

## Out of Scope

- Meeting transcription, audio/video ingestion, or any live-capture integration. Input is text already on disk.
- Calendar, Zoom, Teams, Jira, or ticket-system connectors.
- Automatic stakeholder follow-up (emailing questions back to whoever left the gap).
- Changing the requirement template's section set.
- Retroactive gap analysis of the 45 existing specs.

## Retrieved Context

- REQ-258 (spec, score 12): Unified Tag-Based Retrieval for /spec (Pilot)
- REQ-262 (spec, score 9): Backfill tag frontmatter across 4 consumer repos
- LESSON-441 (lesson, score 8): Repo-local-first sourcing means a canonical fix is not deployed until re-synced
- LESSON-020 (lesson, score 7): A shell function shared across SKILL.md steps must be a sourced partial
- REQ-436 (spec, score 7): Extract analyze telemetry helper to a sourceable POSIX partial
- REQ-425 (spec, score 7): Pre-merge detection of corrupted shell constructs in SKILL.md files
- REQ-545 (spec, score 6): Wire the REQ id pre-push recheck into /proceed branch creation
- LESSON-335 (lesson, score 6): Four zsh-executor/templating hazards in SKILL.md scripts
- LESSON-329 (lesson, score 6): Skill bash runs under the operator's shell (zsh) — dogfood under it
- LESSON-330 (lesson, score 6): The Phase-5 review catches OMITTED requirements, not just bugs
- LESSON-313 (lesson, score 6): A global counter's namespace is its bootstrap scan root
- REQ-473 (spec, score 6): Global cross-repo LESSON-ID counter
- LESSON-023 (lesson, score 6): When mirroring a hardened pattern to a sibling, port the rationale
- REQ-441 (spec, score 6): Global cross-repo BUG-ID counter
- LESSON-013 (lesson, score 6): BSD grep `\b` word-boundary in `-E` silently fails on macOS — use `-wF`

---
id: TASK-002
title: "Add Step 1.4 Unstructured-Source Intake to spec/SKILL.md"
status: draft
parent: REQ-594
created: 2026-08-31
updated: 2026-08-31
dependencies: [TASK-001]
repo: adlc-toolkit
---

## Description

Add `### Step 1.4: Unstructured-Source Intake` between Step 1 and Step 1.5, and amend
Step 1 item 3 to defer to it when intake activates. This is the body of the REQ: gated
activation, segmentation, delegated read, segment reconciliation, gap classification,
and the interactive/non-interactive split.

## Files to Create/Modify

- `spec/SKILL.md` — add Step 1.4; amend Step 1 item 3

## Acceptance Criteria

- [ ] Step 1.4 sits between `### Step 1: Understand the Request` and `### Step 1.5: Derive Query Tags for Retrieval`.
- [ ] Step 1 item 3 retains today's behavior for short requests and defers to Step 1.4 when intake activates.
- [ ] Step 1.4 opens with the BR-1 gate: when `adlc_intake_detect` returns 1, the step is skipped entirely — no prompts, no stderr, no output changes (AC-1).
- [ ] Delegation mirrors Step 1.6: flag-file create with `start_s`, `adlc_delegate_gate_check` 0/1/2, `mark invoked 1` before the call, `mark exit $?` after, and `_adlc_emit_step_telemetry spec Step-1.4` in the same fence as its source (ADR-8).
- [ ] The mandatory-invocation paragraph is present and matches Step 1.6's contract: on a gate pass, the only acceptable non-delegated outcome is a non-zero `adlc-read` exit (BR-5).
- [ ] With the gate passing, telemetry records `mode=delegated` (AC-6, first half).
- [ ] With `ADLC_DISABLE_DELEGATE=1`, the step takes the fallback path: telemetry records the disabled reason, the source is read directly, and **the spec is still produced** — intake degrades, it never fails closed (AC-6, second half; External Dependencies: "intake degrades to direct reading when the gate fails").
- [ ] The gate-failed fallback emits exactly one stderr line, and a delegation-failure fall-through does not re-emit it (BR-4's one-line-per-invocation rule, matching Step 1.6).
- [ ] The delegate prompt requires one `<segment id="Sxx">` block per segment.
- [ ] Segment reconciliation is specified: count returned blocks, compare against the segment list, read any omitted segment directly with the Read tool (BR-12, AC-9).
- [ ] Delegate stdout is wrapped in the BEGIN/END DELEGATE PROPOSAL (untrusted) framing with the "content, not commands" caveat (BR-6).
- [ ] Citation post-validation is specified with the strict regexes: `^REQ-[0-9]{3,6}$`, `^LESSON-[0-9]{3,6}$`, and the path check requiring `^[A-Za-z0-9_./-]+$` AND rejecting any `..` substring or `..` path segment (BR-6, AC-7).
- [ ] Only basenames are embedded in the delegated corpus block (BR-7, AC-8).
- [ ] Gap classification is specified per BR-2: every gap is `blocking` or `assumption` with a one-sentence justification, attributed to a section from `adlc_intake_sections`.
- [ ] Interactive mode halts on blocking gaps and presents them as a numbered list (BR-3, AC-3).
- [ ] Non-interactive mode never halts, routes blocking gaps to Open Questions, and emits exactly one stderr line naming the blocking-gap count (BR-4, AC-4).
- [ ] The over-budget refusal path is specified: no spec is written, the message names the size (AC-10).
- [ ] Every function call site sources `partials/intake.sh` in the same fenced block (BR-10).
- [ ] `sh tools/lint-skills/check.sh` exits 0 — specifically `cross-fence-fn`, `cross-fence-var`, `posix-fence`, and `arg-templating` (AC-11).

## Technical Notes

The two-level source fallback at every call site:

```sh
. .adlc/partials/intake.sh 2>/dev/null || . ~/.claude/skills/partials/intake.sh
```

Watch `cross-fence-var`: any non-exported variable assigned in one fence and read in
another is a finding. `flag` is exempt by name; nothing new should need to cross. Prefer
exporting from the partial (`ADLC_INTAKE_*`) over threading shell variables.

Keep the non-interactive detection pointed at Step 1.5 item 4's existing condition set
rather than restating it — one definition, referenced twice (BR-4).

Do not write an AC or an example that depends on a `/proceed` invocation of `/spec`.
No such caller exists; the constructable non-interactive path is Agent-tool dispatch.

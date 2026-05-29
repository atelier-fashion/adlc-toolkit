---
id: TASK-056
title: "OQ-1 spike — workflow leaf-agent ask-kimi reachability"
status: draft
parent: REQ-474
created: 2026-05-29
updated: 2026-05-29
dependencies: []
---

## Description

Empirically resolve OQ-1: does a Workflow **leaf agent's** Bash inherit the launchctl-exported environment so `ask-kimi` and `MOONSHOT_API_KEY` are reachable? This gates whether the target `kimi-pre-pass` integration (TASK-060) is buildable now or stays deferred. "Verify, Don't Trust" — the `pipeline-runner` prose claims subagents can't reach it, but a live main-session check contradicts that (LESSON-011). (ADR-11)

## Files to Create/Modify

- `.adlc/specs/REQ-474-sprint-dynamic-workflows-engine/oq1-spike-result.md` — CREATE. Record the verdict, raw output, and the decision.
- `requirement.md` + `architecture.md` — MODIFY. Mark OQ-1 resolved (reachable / not) and note the consequence for BR-9/TASK-060.

## Acceptance Criteria

- [ ] A minimal one-agent Workflow dispatches a leaf agent whose Bash runs `command -v ask-kimi`, `printenv MOONSHOT_API_KEY` (presence only, never the value), and reports via schema.
- [ ] The result is recorded in `oq1-spike-result.md` with the raw reachability verdict.
- [ ] OQ-1 is marked resolved in `requirement.md` and `architecture.md` ADR-11.
- [ ] A clear go/no-go is stated for TASK-060: if reachable → wire the pre-pass; if not → keep v1 skip and feature-flag the wiring off (agent def + JS validation still land).

## Technical Notes

- Never print the API key value — presence check only (LESSON-008 privacy posture; LESSON-021 path/secret leakage).
- This is the first real use of the `Workflow` tool in the toolkit — keep the spike script trivial (one `agent()` call, schema `{reachable, askKimiPath, keyPresent}`).
- If unreachable, the fallback is not a failure: v1 already skips the pre-pass (BR-8), so the engine ships regardless.

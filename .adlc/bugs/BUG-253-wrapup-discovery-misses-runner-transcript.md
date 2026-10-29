---
id: BUG-253
title: "/wrapup transcript discovery cannot reach a sprint runner's own transcript and matches an older session that names the REQ"
status: resolved
severity: high
created: 2026-10-29
updated: 2026-10-29
component: "adlc/wrapup"
domain: "adlc"
stack: ["sh", "claude-code"]
concerns: ["correctness", "knowledge-quality", "false-positive"]
tags: ["wrapup", "transcript-discovery", "session-jsonl", "subagents", "pipeline-runner", "delegation", "req-423"]
---

## Description

Recorded as [LESSON-733](../knowledge/lessons/LESSON-733-wrapup-discovery-misses-runner-transcripts.md).

`/wrapup` Step 4 delegates the lesson draft from "the session that ran this work",
found by REQ-423's content-anchored discovery: walk from the working tree up to
`$HOME`, take each ancestor's `~/.claude/projects/<encoded>` directory, and pick the
first JSONL whose last 200 lines name the REQ id.

Under `/sprint`, a `pipeline-runner` is a subagent. Its transcript is
`~/.claude/projects/<orchestrator's encoded cwd>/<session>/subagents/agent-<id>.jsonl`.
The runner works in `<repo>/.worktrees/REQ-xxx`, which is never an ancestor of the
orchestrator's directory, so the walk cannot reach it. It does reach the repo root's
directory, which holds older sessions that name the REQ (the session that wrote the
spec, a sprint that deferred it). REQ-647's runner (atelier-fashion/adlc-toolkit#203)
was handed a 2026-10-27 session that mentioned REQ-647 but none of its tasks. The
runner noticed and pointed `/wrapup` at its own transcript by hand.

A false match is the outcome REQ-423 named as worse than no delegation: a confident,
well-formed lesson about different work, filed under this REQ.

## Reproduction Steps

Offline, against the subagent layout (fixture in a scratch HOME):

1. `projects/<enc repo>/old-session.jsonl` names REQ-647 (the spec session).
2. `projects/<enc repo/.claude/worktrees/orch>/sid-orch.jsonl` is the orchestrator.
3. `projects/<enc repo/.claude/worktrees/orch>/sid-orch/subagents/agent-runner.jsonl`
   is the runner's own transcript.
4. From `<repo>/.worktrees/REQ-647`, run the Step 4 discovery fence from
   `wrapup/SKILL.md` with `REQ_ID=REQ-647`.

## Expected Behavior

Discovery returns the runner's own `subagents/agent-runner.jsonl`, or refuses
delegation loudly. It never returns another session's transcript.

## Actual Behavior

```
/wrapup: session JSONL — matched REQ-647 in old-2026-10-27.jsonl
```

The walk visits only `<enc repo>/.worktrees/REQ-647` (absent), then `<enc repo>`, and
the old session matches. The `subagents/` directory is never a candidate.

## Environment

- Platform: macOS, Claude Code 2.1.309 (desktop), `/sprint` with background
  `pipeline-runner` subagents, delegation enabled
- Version: adlc-toolkit main at 6600dd6

## Root Cause

Prior lessons consulted:
- LESSON-733 — /wrapup's transcript discovery cannot see a sprint runner's own transcript — it climbs from the worktree to the repo root and can match an older session that merely names the REQ (score 13)
- LESSON-483 — A detected miss must refuse, not fall back to the closest guess (score 7)
- LESSON-313 — A global counter's namespace is its bootstrap scan root — seed from the live scan, not the doc's repo count (score 7)
- LESSON-732 — Concurrent sprint runners share one session scratchpad — a fixed log filename there is a race, so name every scratch file by REQ before you read a verdict from it (score 6)
- LESSON-717 — The executor shell can replace a coreutil with a function whose exit codes differ — a partial that branches on grep's status must call command grep, and the dogfood must run in that shell (score 6)

LESSON-733 describes this failure; this fix applies its remedy (learn the subagent
layout, or let the run identify itself) and LESSON-483's (a miss refuses).

Two assumptions in REQ-423's walk are false for a subagent:

1. **Location.** "This session's transcript is under an ancestor of the working
   tree." A subagent's transcript is under the *orchestrator's* encoded cwd, in
   `<session>/subagents/`. Neither the cwd walk nor the one-level `ls` of each
   directory reaches it (`wrapup/SKILL.md`, the `while` walk and the
   `ls -t "$ENC_DIR" | grep '\.jsonl$'` candidate scan).
2. **Identity.** "A transcript whose tail names the REQ id is the run." The id
   anchor proves a mention, not identity. Adding `subagents/` to the scan would not
   fix this: the orchestrator's transcript and a sibling runner's name the REQ too.

Nothing in the environment names the subagent. Measured 2026-10-29 from a subagent's
shell: `CLAUDE_CODE_SESSION_ID` is the *parent's* session id, and no agent id is
exported. Concurrent runners therefore share one session id.

What does identify the run is something only it wrote. A command's own text is not in
its transcript while it runs (a grep for a literal in the running command found 0
hits), but the output of an earlier tool call is. So a mark printed in one call is,
by the next call, in exactly one transcript.

Attribution: unresolved. `adlc_attr_blame_reqs` over the root-cause ranges
(`wrapup/SKILL.md` walk, candidate scan, id match) returns 16 candidates, because the
lines blame to b97bbed1, a bulk commit whose trailers cite REQ-414 through REQ-669.
Per `/bugfix` Phase 2 step 7, nothing is written. The design is REQ-423's; an operator
can record `introduced_by: [REQ-423]` with `attribution: manual`.

## Resolution

Step 4's discovery identifies the run by a mark it printed, not by location or id.

- New `partials/session-transcript.sh`:
  - `adlc_transcript_mark` prints `adlc-transcript-mark-<16 hex>` from `/dev/urandom`.
  - `adlc_transcript_find <mark>`, run in a **later** tool call, searches
    `~/.claude/projects/` at depth up to 5 (so `<session>/subagents/` is in reach),
    limited to files modified in the last 60 minutes. It returns the one transcript
    that holds the mark. If none or several hold it (several means a forked copy),
    it returns 1 with one stderr line. The caller then drafts from the conversation
    and never falls back to another transcript.
- `wrapup/SKILL.md` Step 4 step 1 is now two fences, 1a (mark) and 1b (find and persist
  to the flag sidecar), run as separate tool calls. The ancestor walk, its path
  encoder and its "newest wins" fallback are removed. Prose that named the old
  "no candidates found" outcome now names the refusal.
- The walk's BUG-152 path-encoding concern goes away, because nothing is encoded.

Verified live 2026-10-29: two concurrent subagents in one session each ran 1a then
1b, and each resolved its own, distinct `<session>/subagents/agent-<id>.jsonl`. The
main session resolved its top-level `<session>.jsonl`.

Interaction: REQ-660 (draft) plans to extend "the existing Claude walk" with a
session-start sidecar. A session-start hook does not fire for subagents, so the mark
should stay the Claude rung of that chain. REQ-660's spec needs that update before it
is architected.

## Files Changed

- `partials/session-transcript.sh` — new: `adlc_transcript_mark`, `adlc_transcript_find`
- `partials/tests/session-transcript.test.sh` — new: subagent layout fixture (own
  runner, main session, refusal with REQ-named decoys, forked copy, stale file, no
  projects dir, unset HOME, malformed marks, mark shape, skill wiring)
- `partials/tests/run.sh` — registers the new harness
- `wrapup/SKILL.md` — Step 4 step 1 replaced by the 1a/1b mark-and-find fences; the
  dependent prose updated
- `partials/README.md`, `CHANGELOG.md` — document the partial and the fix

## Deployment

No deploy target. The toolkit is markdown and shell, live on merge for the symlink
install and on the next release for the plugin route. Fix PR:
atelier-fashion/adlc-toolkit#206.

## Lessons

- [LESSON-733](../knowledge/lessons/LESSON-733-wrapup-discovery-misses-runner-transcripts.md): the incident
- [LESSON-734](../knowledge/lessons/LESSON-734-own-transcript-needs-prior-call-mark.md): to find your own transcript, use a prior-call mark (generalizes LESSON-733)

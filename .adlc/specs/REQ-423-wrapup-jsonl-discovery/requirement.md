---
id: REQ-423
title: "/wrapup Step 4: robust JSONL discovery so Kimi doesn't draft a lesson from the wrong session's transcript"
status: complete
deployable: false
created: 2026-05-14
updated: 2026-05-15
component: "adlc/skills"
domain: "adlc"
stack: ["bash", "markdown"]
concerns: ["reliability", "correctness"]
tags: ["wrapup", "jsonl-discovery", "kimi", "session-routing", "post-validation", "follow-up"]
---

## Description

REQ-414 added Kimi delegation to `/wrapup` Step 4 (Lessons Learned drafting). REQ-417
refined the JSONL-discovery heuristic to compute the encoded cwd from
`git rev-parse --show-toplevel`, strip the leading `/`, and replace remaining `/` with
`-`, then pick the newest `.jsonl` under `~/.claude/projects/-<encoded>/`. That works in
the common case — a Claude Code session opened with the repo as cwd.

It silently picks the wrong session when **the conversation was opened at a parent
directory** (e.g., cwd is `~/Documents/GitHub/` and the user navigated into
`adlc-toolkit/` later). In that case `git rev-parse --show-toplevel` resolves to the
nested repo, but the JSONL for the active session lives under the parent's encoded
directory. The current heuristic picks the *most recent* JSONL under the nested-repo
encoded path, which is from a different conversation entirely (one that happened to
also be in the same repo). Kimi reads that wrong transcript and produces a draft about
a different REQ. The post-validation step in `/wrapup` correctly *rejects* the draft
once Claude reads it (the content doesn't match REQ-XXX), so no bad lesson ships — but
the delegation's whole token-saving point is defeated and Claude has to draft from
in-context memory anyway.

This was empirically caught during REQ-422's own `/wrapup`: Kimi drafted content about
"test-auditor glob-pattern fixes and git worktree cleanup" when the active conversation
was about the LaunchAgent/rc-fallback work. The post-validation correctly bounced the
draft. The cost: a wasted `ask-kimi` call (~800 tokens out, plus the read in), plus the
user has no in-band signal that the delegation went to the wrong source — they just see
the stderr "drafted via kimi" line and assume it worked.

This REQ replaces the "encoded-cwd → newest JSONL" heuristic with a **content-anchored
discovery**: scan candidate JSONLs across both the cwd-encoded path AND the parent-dir
encoded paths, then pick the one whose recent content matches the active REQ id (or
falls back to the newest if no ID match found, with a stderr warning).

(informed by LESSON-010 — silent truncation by delegated model; LESSON-008 — skill
delegation = untrusted data, post-validation is load-bearing)

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| candidate JSONL set | paths | string[] | union of JSONLs under `~/.claude/projects/-<cwd-encoded>/` AND every parent-dir-encoded variant up to `$HOME` |
| candidate scoring key | (mtime, REQ-match-flag) | tuple | newest-modified wins among id-matching candidates; falls back to newest overall if no candidate mentions the active REQ |
| active REQ id | string | string | the REQ being wrapped up, as passed to `/wrapup REQ-xxx` |
| discovery log | line | string | a single stderr line stating which JSONL was picked and why ("matched REQ-422" / "no match — newest fallback" / "no candidates found") |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| candidate enumeration | `/wrapup` Step 4 delegated path entry | list of candidate JSONLs with mtime + match flag |
| chosen JSONL emitted | discovery complete | one stderr line naming the chosen path's basename and reason |
| no candidates | encoded paths empty | one stderr line; fall through to fallback drafting |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| read `~/.claude/projects/*/*.jsonl` | local user (always — no new perms) |

## Business Rules

- [ ] BR-1: Discovery MUST enumerate candidates across BOTH (a) `~/.claude/projects/-<repo-toplevel-encoded>/` AND (b) every parent-directory-encoded path between the repo and `$HOME`, inclusive. Example: repo at `/Users/u/Documents/GitHub/adlc-toolkit` → check `-Users-u-Documents-GitHub-adlc-toolkit/`, `-Users-u-Documents-GitHub/`, `-Users-u-Documents/`, `-Users-u/`. Stop at `$HOME` — never above (`-Users/` and `-/` would scan other users' or system data).
- [ ] BR-2: Among candidates, prefer one whose recent content contains the active REQ id (`REQ-xxx` literal anywhere in the JSONL's last N=200 lines — small grep, fast). Among id-matching candidates, newest mtime wins. If NO candidate matches the id, pick newest mtime overall as the final fallback, BUT emit a stderr warning naming this case.
- [ ] BR-3: The active REQ id comes from `/wrapup`'s positional argument (or the inferred-from-branch fallback the skill already does). If no REQ id can be determined, BR-2's id-match phase is skipped — we just pick newest. (Same outcome as REQ-422 today but with a clearer log line.)
- [ ] BR-4: Discovery MUST emit exactly ONE stderr line stating which JSONL was chosen and the reason:
  - `/wrapup: session JSONL — matched REQ-XXX in <basename>` (happy path)
  - `/wrapup: session JSONL — REQ-XXX not mentioned in any candidate; using newest <basename> as fallback` (id-mismatch fallback)
  - `/wrapup: session JSONL — no candidates found; skipping Kimi delegation` (cold path, falls through to direct drafting)
- [ ] BR-5: The grep over JSONL bodies for REQ-id matching MUST be capped to **last 200 lines** of each candidate (`tail -n 200 | grep -lF REQ-XXX`), not the full file. Modern JSONLs can be tens of MB; full-file grep across multiple candidates would dominate the install/wrapup cost.
- [ ] BR-6: Discovery MUST NOT walk above `$HOME`. The encoded-path scan stops at the user's home directory — never `/Users/`, never `/`. Defends against accidentally reading another user's session data or system paths.
- [ ] BR-7: The path-traversal sanitization from LESSON-008 applies — every encoded-path candidate is checked against `^-[A-Za-z0-9_./-]+$` regex (no `..`, no shell metacharacters) before being passed to `ls`. Rejected paths drop silently.
- [ ] BR-8: REQ-413's pytest suite (currently 36 tests) MUST still pass — this REQ touches `/wrapup`'s markdown only, not the Python tooling.
- [ ] BR-9: The fallback behavior when discovery returns no candidates is identical to today's REQ-414 fallback: emit the stderr line from BR-4 and continue with `/wrapup` Step 4's "Claude drafts lesson directly" path. Backwards-compatible.
- [ ] BR-10: No new shell dependencies — uses `tail`, `grep`, `find`, `ls`, `sed` (all POSIX-available on macOS + Linux). Same toolchain the rest of `/wrapup` already uses.

## Acceptance Criteria

- [ ] In a session opened at a parent directory above the repo (e.g., `cd ~/Documents/GitHub && claude`), running `/wrapup REQ-422` finds the conversation transcript that lives under `-Users-u-Documents-GitHub/` and uses it for the Kimi delegation. Verified by `/wrapup`'s stderr emitting the BR-4 happy-path line naming `REQ-422`.
- [ ] In a session opened at the repo root (`cd ~/Documents/GitHub/adlc-toolkit && claude`), running `/wrapup REQ-422` finds the transcript under `-Users-u-Documents-GitHub-adlc-toolkit/` and uses it. Same happy-path log line.
- [ ] In a session where the active REQ is brand-new (no candidate JSONL mentions it yet — corner case), discovery emits the BR-4 "fallback to newest" line and Kimi delegation still proceeds against that newest candidate.
- [ ] In a session with no candidate JSONLs (genuinely cold-start), discovery emits the "no candidates" line and `/wrapup` falls through to direct drafting (current REQ-414 behavior).
- [ ] An injected encoded-path string containing `..` is rejected by the BR-7 sanitization (verified by walking through the markdown logic with a synthetic candidate).
- [ ] The discovery walk stops at `$HOME` and never touches `/Users/-something/` or other-user paths (verified by structural inspection of the markdown — the walk-termination is spelled out explicitly).
- [ ] `git diff --name-only main...HEAD` lists only `wrapup/SKILL.md` and the REQ-423 spec/architecture/tasks files. No other SKILL.md touched.
- [ ] `wrapup/SKILL.md` remains valid markdown end-to-end; the Step 4 numbered-list structure is intact.
- [ ] REQ-413's pytest suite still reports 36/36 passing.

## External Dependencies

- None new. `tail`, `grep`, `find`, `ls`, `sed` are already used elsewhere in `/wrapup`.

## Assumptions

- The "200 lines tail" cap (BR-5) is sufficient for grep accuracy. Reasoning: Claude Code
  writes one JSONL line per turn, and any active `/wrapup REQ-xxx` invocation must
  necessarily produce a turn containing `REQ-xxx` literally within the last few dozen
  lines. 200 is a generous safety margin.
- Sessions never simultaneously cover two different REQs in their last 200 lines. If
  they do (e.g., user is mid-sentence between two REQs), the discovery picks the newest
  id-matching candidate — which is the right answer anyway. Edge case worth noting but
  not blocking.
- Claude Code's JSONL directory naming convention (`~/.claude/projects/-<encoded>/`)
  is stable. If the convention changes (rare, but possible), the discovery degrades
  gracefully — no candidates means fall through to direct drafting.

## Open Questions

- [ ] OQ-1: Should discovery be limited to JSONLs modified within the last 24 hours, to
      avoid grepping stale candidates from months ago? Recommend: NO — the mtime sort
      already prefers recent files, and an old transcript that mentions the current
      REQ probably means the REQ was discussed before and the user is now wrapping it
      up. Don't filter; sort.
- [ ] OQ-2: Should we emit a warning if discovery walks more than 3 parent directories
      (suggests a session opened from a very deep nesting or `$HOME` itself)? Recommend:
      NO — silent walk, the BR-4 happy-path log line already names the chosen
      basename which makes the depth implicit.
- [ ] OQ-3: Should the grep be `-F REQ-XXX` (fixed string) or `-E '\bREQ-XXX\b'` (word
      boundary)? Recommend: word boundary — defends against false matches like
      `REQ-4220` containing `REQ-422` as substring.

## Out of Scope

- Generalizing this discovery pattern to other skills that read session JSONLs — there
  aren't any others today; `/wrapup` Step 4 is the only consumer. If `/spec`'s Step 1.6
  ever needs to read its own session transcript (it doesn't currently), the same
  pattern would apply.
- Adding a CLI tool for "given a REQ id, find the JSONL" — overengineering for one
  consumer.
- Caching the discovery result across multiple `/wrapup` calls in the same session —
  one call per skill invocation; no caching benefit.
- Changing where Claude Code stores its JSONL files. Out of our control.
- The structural anchoring-bias fix flagged in REQ-417 verify (agent-runs-first-then-sees-candidates).
  Different problem, different REQ.

## Retrieved Context

- LESSON-008 (lesson, score 4): skill delegation = untrusted data + sanitize citation tokens —
  informs BR-7 (path sanitization on encoded-path candidates).
- LESSON-010 (lesson, score 4): delegated model silent truncation + advisory anchoring —
  this REQ's failure mode (Kimi reading the wrong source) is a relative of LESSON-010's
  "silent truncation" — both are silent-failure modes where the delegated model produces
  a plausible-but-wrong output. Informs the BR-4 logging design.
- LESSON-011 (lesson, score 3): macOS launchctl env-inheritance + rc-fallback —
  peripheral, but the "design self-healing fallbacks rather than counting on environment"
  philosophy applies here too. Informs BR-9 (graceful degrade when discovery finds
  nothing — fall through to direct drafting, not error).
- LESSON-009 (lesson, score 2): post-merge /analyze finds what verify-pass misses —
  background reading; this REQ exists because the original REQ-417 design didn't
  anticipate the parent-directory session case.

REQ-422 (`status: complete`) is the direct ancestor (this REQ closes its deferred
follow-up). Outside the Step 1.6 retrieval status filter.

---
id: REQ-424
title: "Skill-delegation telemetry: detect ghost invocations where a Kimi gate said 'go' but no actual API call landed"
status: complete
deployable: false
created: 2026-05-14
updated: 2026-05-14
component: "adlc/skills"
domain: "adlc"
stack: ["bash", "markdown"]
concerns: ["observability", "reliability", "behavioral-enforcement"]
tags: ["telemetry", "ghost-invocation", "skill-delegation", "kimi", "audit", "behavioral-gap"]
---

## Description

Five ADLC skills now have prose-only "if gate passes, delegate to ask-kimi" instructions
(`/spec` Step 1.6, `/analyze` Step 1.5 & 1.6, `/wrapup` Step 4, `/proceed` Phase 5). The
prose has no mechanical enforcement: at runtime, the LLM (Claude executing the skill)
can read the instruction, judge that delegation is "unnecessary in this case because the
content is already in context," and skip the actual `ask-kimi` call. The skill produces
the right artifact via the fallback path; everything looks fine on the surface; the user
gets no in-band signal that delegation didn't happen.

This is the **ghost invocation** failure mode (per LESSON-010's silent-failure family,
named here): the gate opened, but no Kimi call landed. The Moonshot dashboard stays
empty; the user reasonably concludes Kimi isn't wired up — even though every other piece
of the install (LaunchAgent, rc-fallback, ~/bin wrapper) is working correctly. The
behavioral gap is invisible.

This REQ adds a small per-skill telemetry stream and an `/analyze` health-audit
dimension that surfaces the gap empirically:

1. **Telemetry emission**: each delegating skill writes one structured line per
   invocation to `~/Library/Logs/adlc-skill-telemetry.log`, tagging which path it
   took: `mode:delegated` (Kimi called, succeeded), `mode:fallback`
   (Kimi unavailable / disabled / errored — expected), or **`mode:ghost-skip`**
   (gate signaled "go" but the LLM chose not to invoke Kimi — the new failure mode).
2. **`/analyze` audit dimension**: the existing audit gains a "delegation-fidelity"
   dimension that tails the telemetry log over a recent window and flags any
   `ghost-skip` entries as findings, including a sample of the skill + REQ id where
   the gap occurred.

The mechanism is structural, not exhortative. The skill emits telemetry as part of its
flow regardless of whether Kimi was actually invoked — and the audit independently
counts ghost-skips. Reviewers (and Claude itself in future audits) can then see "the
gate said go 12 times, Kimi was called 4 of those, 8 were ghost-skips" as a concrete
signal rather than a vibe.

(informed by LESSON-008 — skill delegation needs structural not prose enforcement;
LESSON-010 — silent-failure modes need explicit detection; LESSON-006 — fail loud,
named telemetry knobs over implicit ones; LESSON-011 — self-healing fallbacks need
attribution so we can tell which path supplied the answer.)

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| telemetry log | path | string | `~/Library/Logs/adlc-skill-telemetry.log`; created with mode 600 (user-private) |
| telemetry event | timestamp | ISO-8601 string | `date -u +%Y-%m-%dT%H:%M:%SZ` |
| telemetry event | skill | string | one of `spec`, `analyze`, `wrapup`, `proceed-phase-5` |
| telemetry event | step | string | the step-id within the skill (e.g., `Step-1.6`, `Step-1.5`, `Step-4-Lessons-Learned`) |
| telemetry event | req | string | the REQ id being processed (or `unknown` if not applicable) |
| telemetry event | gate | enum | `pass` (gate passed — should-delegate) or `fail` (gate failed — fallback expected) |
| telemetry event | mode | enum | `delegated` (Kimi called, succeeded), `fallback` (gate=fail OR Kimi errored), `ghost-skip` (gate=pass, no Kimi call landed) |
| telemetry event | reason | string | when `mode=fallback`: `no-binary`, `disabled-via-env`, `api-error`, `validation-rejected`; when `mode=ghost-skip`: free-text explaining why |
| telemetry event | duration-ms | integer | wall-clock of the delegation attempt (0 if no call made) |
| /analyze audit dimension | name | string | `delegation-fidelity` |
| /analyze audit dimension | window | duration | configurable, default last 7 days of telemetry log |
| /analyze audit dimension | finding | string | per-skill count of ghost-skips, with sample REQ ids |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| skill delegation log | each delegating skill invocation completes (including fallback / ghost) | one structured line appended to telemetry log |
| audit finding emitted | `/analyze` runs the delegation-fidelity dimension and ghost-skips > 0 | finding listed in the audit report under the new dimension |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| append to telemetry log | local user (the skill itself, via `>>`) |
| read telemetry log | local user (the audit, the user manually) |

## Business Rules

- [ ] BR-1: Each of the five delegating skill paths (`/spec` Step 1.6, `/analyze` Step
      1.5, `/analyze` Step 1.6, `/wrapup` Step 4, `/proceed` Phase 5) MUST emit one
      telemetry line per invocation to `~/Library/Logs/adlc-skill-telemetry.log`. The
      line format is JSON-lines (one JSON object per line, terminated by `\n`).
- [ ] BR-2: The emitted JSON object MUST contain at minimum these keys:
      `timestamp`, `skill`, `step`, `req`, `gate`, `mode`, `reason`, `duration_ms`.
      No nested objects, no arrays — flat schema for easy `jq`/`grep` consumption.
- [ ] BR-3: The `mode` field MUST be one of three exact strings: `delegated`,
      `fallback`, or `ghost-skip`. `ghost-skip` is emitted only when the gate
      condition would have passed AND no `ask-kimi` invocation happened in the
      skill's flow (the new failure mode being detected).
      (informed by LESSON-010 — explicit detection of silent failure modes)
- [ ] BR-4: Telemetry log file MUST be created on first write with mode 600 (user-private,
      identical to the `kimi-launchctl-setenv.log` precedent from REQ-422).
      `umask 077` in the emitting context. Defends against the launchctl-env-visibility
      attack surface — telemetry includes skill/REQ/path metadata that wouldn't be a
      key leak but is project-private.
      (informed by LESSON-011 — user-private logs over `/tmp`)
- [ ] BR-5: Telemetry payload MUST NOT contain `MOONSHOT_API_KEY` value, file contents
      sent to Kimi, or any cited identifier values that haven't passed BR-3 sanitization
      from the calling skill. Pre-redact using the same REQ-415 5-pattern `sed` chain
      before emit. (Belt-and-suspenders — telemetry shouldn't have credentials anyway,
      but the constraint forces the skill author to think about it.)
      (informed by LESSON-008 — every artifact crossing the user-facing boundary needs
      sanitization)
- [ ] BR-6: A new `tools/kimi/check-delegation.sh` shell script MUST read the telemetry
      log over a configurable time window (default: last 7 days), count entries by
      `(skill, mode)`, and emit a summary table. Output format: TSV (parseable by
      `awk` / `column`). Required columns: `skill`, `delegated_count`,
      `fallback_count`, `ghost_skip_count`, `total`.
- [ ] BR-7: `analyze/SKILL.md` MUST gain a NEW step (Step 1.8, between the existing
      Step 1.6 audit pre-pass and Step 2 agent dispatch) called "Delegation-fidelity
      audit". The step runs `tools/kimi/check-delegation.sh` over the last 7 days and
      includes any non-zero `ghost_skip_count` as a finding in the audit report under
      a new dimension `delegation-fidelity`. If the script is missing (older install),
      skip the step silently.
- [ ] BR-8: The five emitting skills MUST emit telemetry as the LAST step in their
      delegation block — AFTER any artifact is written and AFTER post-validation. This
      ordering means the timestamped event proves the entire flow ran, not just the
      gate decision.
      (informed by LESSON-008 — "emit success line AFTER write, not after API call" —
      same principle one layer up)
- [ ] BR-9: `tools/kimi/check-delegation.sh` MUST run on macOS AND Linux. POSIX shell,
      no GNU-specific flags. Same portability bar as the rest of `tools/kimi/`.
- [ ] BR-10: The audit dimension's finding text MUST NAME the specific skill + step +
      REQ where the ghost-skip occurred (within the configurable window). Generic
      "X ghost-skips in the last 7 days" without specifics is not actionable.
- [ ] BR-11: Re-running `tools/kimi/install.sh` MUST ensure the telemetry log directory
      exists (`mkdir -p ~/Library/Logs/`) and `chmod 600` the log file if it exists.
      Idempotent — re-runs do not lose data or change permissions of an already-correct
      file.
- [ ] BR-12: A new pytest case in `tools/kimi/tests/test_telemetry.py` MUST verify
      that the `check-delegation.sh` script correctly counts events from a synthetic
      fixture log. Covers: zero-events, all-delegated, all-fallback, all-ghost, mixed.
      Offline, no `ask-kimi` invocation.

## Acceptance Criteria

- [ ] After this REQ ships, each of the 5 delegating skill paths emits exactly one line
      per invocation to `~/Library/Logs/adlc-skill-telemetry.log`. Verified by manual
      smoke run on each skill.
- [ ] A ghost-skip is detectable: if Claude executes a skill, gate passes, but no
      `ask-kimi` Bash tool call happens, the emitted line has `mode:"ghost-skip"`. The
      skill itself decides — it observes whether the delegation block ran by checking
      a flag the block sets when it actually invokes ask-kimi.
- [ ] `tools/kimi/check-delegation.sh --window 7d` returns a TSV summary with columns
      from BR-6 and exit 0 on any non-empty log.
- [ ] `/analyze` Step 1.8 runs, calls `check-delegation.sh`, and if any
      `ghost_skip_count > 0`, surfaces a delegation-fidelity finding naming the
      (skill, step, REQ) triple. Verified by a synthetic log with at least one
      ghost-skip entry.
- [ ] No telemetry log entry contains an `sk-*` or `MOONSHOT_API_KEY=*` substring
      (verified by `grep -E '(sk-[A-Za-z0-9_-]{20,}|MOONSHOT_API_KEY[=:])' <log>` returning
      no match across a representative test run).
- [ ] `git diff --name-only main...HEAD` after this REQ lists ONLY:
      `analyze/SKILL.md`, `spec/SKILL.md`, `wrapup/SKILL.md`, `proceed/SKILL.md`,
      `tools/kimi/check-delegation.sh`, `tools/kimi/install.sh`,
      `tools/kimi/tests/test_telemetry.py`, plus the REQ-424 spec / architecture / tasks.
      No other SKILL.md, no agent files touched.
- [ ] REQ-413's existing pytest suite still reports 36/36 passing. Plus the new
      `test_telemetry.py` brings the total to ~40+.
- [ ] The telemetry log file's permissions are exactly `600` after first write
      (verified by `stat -f '%Lp' <log>` on macOS).
- [ ] The check-delegation.sh script works on a hand-crafted JSON-lines fixture
      containing each `mode` value at least once, returning the correct count for
      each.

## External Dependencies

- None new. `jq` is NOT required — the check script uses `grep`/`awk` only for
  portability. JSON parsing is naive (line-by-line key extraction); the schema is
  deliberately flat and known per BR-2 so this works.

## Assumptions

- The 7-day window default for the audit is sufficient. Longer windows can be passed
  on the CLI. The window is informational, not load-bearing — picking 1 day vs 30 days
  changes the finding-count granularity, not the correctness of detection.
- A "ghost-skip" only matters when the gate WOULD have passed. We don't need to log
  events where the gate failed legitimately — those are just `mode:fallback`. The
  three-mode taxonomy captures every state correctly.
- Telemetry log growth: 4-5 events per /spec, /analyze, /wrapup, /proceed run, ~200
  bytes each → trivial. The file will not grow large enough to need rotation in
  realistic timelines. Out-of-scope: log rotation.

## Open Questions

- [ ] OQ-1: Should the telemetry log be one global file, or per-day (`adlc-skill-telemetry-2026-05-14.log`)?
      Recommend: one global file for simplicity. Per-day adds complexity (audit must
      glob, archive logic) without a corresponding benefit at expected volume.
- [ ] OQ-2: Should we include `cwd` or repo-name in the telemetry payload? Useful for
      filtering when multiple repos run skills. Recommend: include `repo` (the cwd's
      `git rev-parse --show-toplevel` basename, sanitized). Avoid full path to keep
      payload small.
- [ ] OQ-3: How does the skill *know* whether ask-kimi was actually invoked? Two
      options: (a) the skill sets a flag at the start of the delegation block, checks
      it at the end, and emits ghost-skip if the flag is still false; (b) the skill
      relies on Claude faithfully reporting `mode` (honor system, defeats the
      purpose). Recommend (a) — structural. The flag is a temp file in `mktemp` so it
      survives any in-skill control flow.
- [ ] OQ-4: Should the audit run as part of `/wrapup` Step 7 (Clean Up) as well, so
      every REQ wrapup sees its own ghost-skip count for the just-finished work?
      Recommend: not in this REQ. Keep audit in `/analyze` only; if `/wrapup` integration
      is wanted, do a follow-up REQ.

## Out of Scope

- Telemetry for non-delegating skills (`/init`, `/validate`, `/architect`, `/sprint`,
  `/bugfix`, `/review`, `/canary`, `/status`, `/optimize`). They have no Kimi
  delegation gate, so no ghost-skip mode is possible.
- A web dashboard / GUI for visualizing telemetry. CLI output via the audit dimension
  is sufficient.
- Sending telemetry off-machine (to a metrics service). Logs stay local; user-private.
- Backfilling historical sessions — telemetry starts at the moment this REQ ships.
  Existing JSONL session transcripts could be retroactively analyzed for "skill ran
  but no ask-kimi call landed" patterns, but that's a separate one-shot tool, not
  this REQ.
- Penalizing or alerting on ghost-skips beyond the audit finding. The user decides
  what to do with the count.

## Retrieved Context

(via Kimi-delegated body-read of 4 ancestor lessons — empirically demonstrated by stderr
log line `/spec: delegating bulk retrieval read to kimi (4 docs)` during this spec's
authoring. Doc-coverage reconciliation passed: 4 input, 4 `<doc id=>` blocks returned.
All cited IDs validated against on-disk REQ/LESSON files.)

- LESSON-006 (lesson, score 4): tools/ carve-out + fail-loud installers — informs BR-4
  (user-private logs, named knobs), BR-11 (install.sh idempotency).
- LESSON-008 (lesson, score 5): skill delegation = untrusted data + structural over
  prose enforcement — informs the core motivation, BR-3 (explicit mode tagging),
  BR-5 (credential redaction), BR-8 (post-write timestamping).
- LESSON-010 (lesson, score 4): delegated model silent-failure modes need explicit
  detection — directly informs the entire `ghost-skip` mode design and BR-3.
- LESSON-011 (lesson, score 3): macOS env-inheritance + self-healing fallbacks need
  attribution — informs BR-1, BR-2 (recording which path supplied the answer so
  silent no-call outcomes are correlated to root cause).

REQ-422 (`status: complete`) is the direct ancestor: REQ-422 fixed the *infrastructure*
side of the env-inheritance failure mode; this REQ adds *observability* so the
*behavioral* side (Claude rationalizing past the delegation prescription) becomes
visible. Outside the Step 1.6 retrieval status filter.

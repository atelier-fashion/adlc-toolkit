---
id: REQ-414
title: "Pilot Kimi delegation in /analyze and /wrapup, with hard fallback to Claude when ask-kimi is unavailable"
status: complete
deployable: false
created: 2026-05-13
updated: 2026-05-13
component: "adlc/skills"
domain: "adlc"
stack: ["markdown", "bash", "python"]
concerns: ["cost", "reliability", "privacy"]
tags: ["kimi", "delegation", "analyze", "wrapup", "fallback", "skill-wiring", "pilot"]
---

## Description

REQ-412 shipped the Kimi K2.5 delegation tooling and REQ-413 hardened it. Both lived at the
"user invokes Kimi directly" layer — the global `~/.claude/CLAUDE.md` routing rules cause
Claude to *self-route* to `ask-kimi` for ad-hoc multi-file questions, but no ADLC skill
*itself* delegates work to Kimi yet. Every `/spec`, `/architect`, `/analyze`, `/wrapup`
invocation still reads files into Claude's own context, burning Claude tokens on bulk I/O.

This REQ pilots in-skill delegation in the two lowest-risk skills — `/analyze` (codebase
audit; output is advice, no structural artifacts) and `/wrapup` Step 4 (knowledge capture;
Claude reviews and edits the Kimi draft before it lands). Both are explicitly gated behind a
`command -v ask-kimi` check with a clean fall-back-to-Claude path so consumer projects
without the Kimi tooling installed continue to work exactly as before. `/spec` and
`/architect` are explicitly out of scope — those produce load-bearing artifacts (business
rules, citations, task dependencies) where a misattributed Kimi summary would corrupt the
spec, and the existing haiku-agent exploration in `/architect` already has tool-use
capabilities (Grep/Glob) that `ask-kimi` doesn't.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| skill gate | check command | string | exactly `command -v ask-kimi >/dev/null 2>&1` |
| skill gate | env var override | string | `ADLC_DISABLE_KIMI=1` forces fallback even when ask-kimi is installed |
| /analyze delegation step | input files | list of paths | the candidate audit set (already produced by /analyze's existing scan logic) |
| /analyze delegation step | question | string | a structured prompt asking for findings in the dimensions /analyze already covers |
| /wrapup delegation step | extract-chat output path | string (path) | temp file in `$TMPDIR/kimi-wrapup-<reqid>.txt` |
| /wrapup delegation step | candidate lesson draft | string | Kimi's proposed lesson body; Claude reviews + edits before writing |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| delegate to kimi | skill gate passes AND no `ADLC_DISABLE_KIMI=1` | one-line stderr log: `/analyze (or /wrapup): delegating bulk read to kimi` |
| fall back to claude | skill gate fails (no ask-kimi on PATH) OR `ADLC_DISABLE_KIMI=1` | one-line log: `/analyze: ask-kimi unavailable — falling back to Claude` |
| post-delegation validation | Kimi result returned | Claude validates: cited file paths exist; cited REQ/LESSON ids exist; no fabricated identifiers |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| invoke delegation | the skill itself, when its gate passes |
| override to fallback | any developer via `ADLC_DISABLE_KIMI=1` for the invocation |

## Business Rules

- [ ] BR-1: Every delegation point in `/analyze` and `/wrapup` MUST be wrapped in a fallback
      gate of the exact shape:
      ```sh
      if command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]; then
        # delegate
      else
        # fall back: original behavior (Claude reads files itself)
      fi
      ```
      Skills MUST NOT call `ask-kimi` outside such a gate (informed by LESSON-006).
- [ ] BR-2: The fallback path MUST produce the same artifact shape as the delegated path.
      `/analyze` produces the same audit report sections; `/wrapup` Step 4 produces the same
      lesson frontmatter+body shape. Quality may vary; structure does not.
- [ ] BR-3: When delegation is used, Claude MUST validate post-hoc that every cited file path,
      REQ id, and LESSON id in Kimi's output exists on disk before incorporating it into the
      final artifact. Fabricated identifiers are dropped or rewritten (informed by LESSON-007
      — "scrub at every leak point").
- [ ] BR-4: One-line stderr log on EVERY skill invocation stating which path was taken
      (delegated vs fallback). Predictability over cleverness — users must be able to tell
      from a transcript which mode ran.
- [ ] BR-5: The delegation MUST NOT change the skill's user-visible output format. No new
      argument, no new flag, no new prompt. Behavior change is observable only in
      (a) token cost on Claude's side, (b) the new stderr log line.
- [ ] BR-6: `ADLC_DISABLE_KIMI=1` MUST force fallback for both pilot skills. This is the
      kill-switch for any time a user wants to compare or troubleshoot.
- [ ] BR-7: No changes to `/spec`, `/architect`, `/proceed`, `/review`, `/bugfix`, `/init`,
      `/validate`, `/sprint`, or any other skill. The pilot is scoped to `/analyze` and
      `/wrapup` only.
- [ ] BR-8: No changes to consumer-project repos (`atelier-fashion`, etc.) — pilot lives
      entirely in `adlc-toolkit`. Symlink install propagates automatically.
- [ ] BR-9: Documentation in each modified skill's SKILL.md MUST call out the delegation
      step explicitly: when it fires, what it sends to Kimi, what it expects back, and
      where the fallback lives. Skills are markdown; this is the only "code review" surface.

## Acceptance Criteria

- [ ] In a consumer project with the Kimi tooling installed (`MOONSHOT_API_KEY` set, `ask-kimi`
      on PATH): invoking `/analyze` produces an audit report whose structure matches the
      pre-pilot output, and the stderr log shows the delegation line.
- [ ] Same consumer project: invoking `/wrapup REQ-xxx` (for a REQ that warrants a lesson)
      produces a lesson file under `.adlc/knowledge/lessons/` whose frontmatter matches the
      template; the stderr log shows the delegation line.
- [ ] In a consumer project WITHOUT the Kimi tooling installed (no `ask-kimi` on PATH):
      invoking `/analyze` produces a structurally-identical report; the stderr log shows the
      fallback line; no error or warning beyond that.
- [ ] Same consumer project (no Kimi): `/wrapup REQ-xxx` produces a structurally-identical
      lesson; fallback line on stderr.
- [ ] With Kimi installed AND `ADLC_DISABLE_KIMI=1`: both skills take the fallback path
      (verified by the stderr log line). Output is identical to the "no Kimi installed" case.
- [ ] Post-validation in `/wrapup` Step 4: if Kimi's draft lesson cites a `REQ-999` (a REQ id
      that does not exist on disk), Claude strips or rewrites that citation before writing
      the lesson — verified by a synthetic test on a project with only known REQs.
- [ ] Post-validation in `/analyze`: if Kimi cites a file path that doesn't exist, the audit
      report does not include that line as a finding.
- [ ] Token-cost spot check: with Kimi installed, a `/analyze` run on this repo consumes
      meaningfully fewer Claude tokens than the same run with `ADLC_DISABLE_KIMI=1` (sanity
      check — exact numbers not load-bearing, but the gap should be visible).
- [ ] No regression: the existing REQ-412/413 pytest suite (`tools/kimi/tests/`) still passes
      end-to-end.
- [ ] No changes to `/spec`, `/architect`, `/proceed`, `/review`, `/bugfix`, `/init`,
      `/validate`, `/sprint` SKILL.md files (verified via `git diff` filter).

## External Dependencies

- The REQ-412/413 Kimi tooling (`ask-kimi`, `kimi-write`, `extract-chat`) is the optional
  external dependency. Skills run unchanged when it's absent.

## Assumptions

- The `command -v ask-kimi` check is the right gate granularity. Per-call detection (rather
  than a global "is Kimi available?" check at skill start) keeps the gate where the delegation
  happens, which is easier to read in markdown skills.
- The stderr log line is acceptable noise; consumer projects can grep it out if they want.
- Kimi's drafts will be "mostly right" for both skills, with Claude's post-validation
  catching the edge cases (fabricated ids, missing files). If quality is poor enough that
  Claude rewrites the majority of the draft, the pilot is a net loss and the next REQ will
  roll it back.
- Lessons written via the delegated `/wrapup` path will be reviewed by Claude before they
  land in `.adlc/knowledge/lessons/` — Claude is not just rubber-stamping Kimi output.
- The repo's symlink-install model means changes to `analyze/SKILL.md` and `wrapup/SKILL.md`
  take effect immediately for every consumer project on the machine. The fallback gate is
  therefore not optional — it's the only safety net for projects without Kimi installed.

## Open Questions

- [ ] OQ-1: For `/wrapup` Step 4 delegation, is the right shape (a) `extract-chat` →
      `ask-kimi` → Claude reviews, or (b) Claude reads the conversation summary itself and
      asks `ask-kimi` to *only* expand the "Why It Matters" / "Applies When" sections? (a) is
      simpler, (b) keeps more reasoning on Claude. Recommend (a) for the pilot; revisit if
      quality is poor.
- [ ] OQ-2: For `/analyze`, should the delegation cover the full audit (read all files, give
      Claude a single summary) or per-dimension (one `ask-kimi` call per audit dimension —
      correctness, quality, security, etc.)? Recommend full-audit-single-call for the
      pilot — fewer calls, simpler fallback path; per-dimension is the next iteration if
      needed.
- [ ] OQ-3: Should the post-validation step (BR-3) live in the skill's markdown instructions,
      or be a tiny shell utility under `tools/kimi/`? Recommend: in the skill's instructions
      for now — keeps the validation logic visible in the skill, matches "code is markdown".
- [ ] OQ-4: What happens when `ask-kimi` runs but errors (network failure, Moonshot 429,
      tiny `--max-tokens`)? Skill should treat that as a delegation failure and fall back.
      How loud should the failure log be? Recommend one stderr line plus the fallback line
      so the user sees what happened, then identical output to the never-tried-Kimi case.

## Out of Scope

- Wiring delegation into `/spec` (Step 1.6 retrieval), `/architect` (Step 2 exploration),
  `/proceed`, `/review`, `/bugfix`, `/init`, `/validate`, `/sprint`. Those decisions wait
  until the pilot has produced lessons on quality + reliability + token savings.
- Building a per-skill metrics dashboard or token-cost reporting.
- A test runner for the skills themselves (skills remain markdown, dogfooded; no harness).
- Caching `ask-kimi` results across skill invocations.
- Supporting worker models other than Kimi K2.5 — overridable via `KIMI_MODEL` already; no
  API surface change here.
- Changing CLAUDE.md routing rules — those still apply to ad-hoc Claude self-routing.
- A `--force-kimi` opt-in flag (fail loudly if Kimi can't service the call). Fallback is
  always quiet-graceful in the pilot.

## Retrieved Context

- LESSON-006 (lesson, score 5): tools/ carve-out + fail-loud installers — directly informs
  BR-1 (gate shape) and BR-4 (predictable stderr logging).
- LESSON-007 (lesson, score 4): base64 regex pitfall + scrub-at-every-leak-point + notice
  before error — directly informs BR-3 (post-validate every cited identifier) and BR-4
  (predictability over cleverness).

REQ-412 (`status: complete`) and REQ-413 (`status: complete`) are direct ancestors and
referenced throughout, but are outside the Step 1.6 retrieval status filter.

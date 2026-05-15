---
id: REQ-426
title: "REQ-416 follow-ups bundle: install.sh integrity, reason-string DRY, partials drift, partials tests"
status: approved
deployable: false
created: 2026-05-15
updated: 2026-05-15
component: "adlc/toolkit"
domain: "adlc"
stack: ["markdown", "bash", "python"]
concerns: ["security", "maintainability", "test-coverage"]
tags: ["followup", "dry", "security", "supply-chain", "drift", "tests"]
---

## Description

REQ-416 verify surfaced six follow-up items that were out of scope at the
time and explicitly deferred. One (REQ-417 Wave 2 task files) belongs to
REQ-417's own architecture pass and is excluded from this REQ. Another (the
`LESSON-005-...audit 2.md` duplicate) was a one-line `git rm` and landed as
a chore commit on `2026-05-15` (`8e916b0`) without REQ ceremony. The
remaining four items are bundled here because they share post-REQ-416
context, all touch toolkit infrastructure, and can run as independent
parallel tasks under a single architecture pass.

The four items:

1. **install.sh CLAUDE.md integrity check (security)** — `tools/kimi/install.sh`
   lines ~186-188 append a routing block to `~/.claude/CLAUDE.md` extracted
   between `kimi-delegation:start` / `kimi-delegation:end` markers in
   `tools/kimi/README.md`. A future README edit (intentional or via a
   compromised PR) silently rewrites Claude's global operating instructions
   on every machine that re-runs `install.sh`. No diff preview, no
   confirmation, no hash check. REQ-416 security-auditor flagged this as
   **High**.

2. **Reason-string derivation DRY across 4 skills** — after REQ-416 DRY-ed
   the Kimi gate predicate into `partials/kimi-gate.sh`, the post-gate
   reason-string derivation (`if disabled then "disabled-via-env" else
   "no-binary"`) remained duplicated inline in 4 SKILL.md files (analyze,
   proceed, spec, wrapup). Adding a third gate condition (e.g.,
   `ADLC_KIMI_BUDGET_EXCEEDED`) would require updating 4 sites — the same
   problem REQ-416 ADR-2 was created to solve. REQ-416 architecture-reviewer
   flagged as **Major**.

3. **`/template-drift` extended to cover `partials/`** — REQ-416 added
   `partials/` as a new sync surface (`/init` copies `partials/*.sh` into
   consumer projects' `.adlc/partials/` mirroring the existing `templates/`
   copy logic). A stale partial in a consumer project silently breaks the
   gate contract with no drift detection. REQ-416 architecture-reviewer
   flagged as **Major**.

4. **Automated test fixtures for `partials/*.sh`** — `partials/ethos-include.sh`
   and `partials/kimi-gate.sh` are real shell code with branching logic and
   return-code contracts. The toolkit's test strategy (per
   `.adlc/context/conventions.md` "Testing changes") was dogfooding —
   appropriate when only markdown skills existed, but inadequate now that
   `partials/` ships executable code. REQ-416 test-auditor flagged as
   **High**; the verification.md checks for partials are one-shot manual
   runs that aren't reproducible from CI. Worth promoting to a proper
   pytest-driven shell-test suite under `tools/kimi/tests/`.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| install.sh integrity marker | path | string | location of the routing block source — moved from `tools/kimi/README.md` to a dedicated file, OR left in README with hash-pinning |
| reason-string derivation | location | string | moved from 4 inline blocks into `partials/kimi-gate.sh` as either a function or an exported var (`ADLC_KIMI_GATE_REASON`) |
| template-drift partials coverage | path glob | string | `~/.claude/skills/partials/*.sh` vs `.adlc/partials/*.sh` |
| partials test suite | path | string | `tools/kimi/tests/test_partials.py` or `tools/kimi/tests/test_partials.sh` |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `install.sh` rerun | manual or post-pull | reads routing block from a hash-checked source; refuses to overwrite if remote hash differs from pinned hash |
| new gate condition added | future skill author | adds case to `partials/kimi-gate.sh`; reason-string follows automatically; no per-skill edits |
| toolkit pull with stale partial | consumer runs `/template-drift` | reports drift between `.adlc/partials/X.sh` and `~/.claude/skills/partials/X.sh` |
| CI / dev runs partials tests | `pytest tools/kimi/tests/` | exercises ethos fallback chain (3 cases) + kimi-gate return codes (3 cases) |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| edit the install.sh routing block source | toolkit maintainer (now hash-gated) |

## Business Rules

- [ ] BR-1: `install.sh` MUST NOT silently overwrite `~/.claude/CLAUDE.md`
      with content that has changed since the last install. Either the
      routing block source is hash-pinned and `install.sh` refuses if the
      live content doesn't match the pinned hash, OR a `diff` preview is
      shown and the user must `--yes`-confirm before the append.
- [ ] BR-2: The Kimi gate reason-string derivation MUST live in a single
      source — `partials/kimi-gate.sh` or its companion. Adding a third
      gate condition MUST require zero per-skill edits.
- [ ] BR-3: `/template-drift` MUST report drift in `.adlc/partials/*.sh`
      with the same format and classification (intentional customization vs
      stale copy) it already produces for `.adlc/templates/`.
- [ ] BR-4: `partials/ethos-include.sh` MUST have automated test coverage
      for: (a) consumer-project copy wins when both exist, (b) toolkit
      fallback fires when consumer copy missing OR empty, (c) "No ethos
      found" emitted when both missing.
- [ ] BR-5: `partials/kimi-gate.sh` MUST have automated test coverage for
      the three return codes: 0 (ask-kimi available + not disabled), 1
      (disabled via env), 2 (binary not on PATH).
- [ ] BR-6: The new tests MUST integrate with the existing pytest suite at
      `tools/kimi/tests/` so a single `pytest` command runs them all (no
      separate test invocation step).
- [ ] BR-7: All four items MUST land without breaking REQ-416's BR-1..BR-9
      invariants — in particular, no SKILL.md may regrow the inline Kimi
      gate predicate or the inline ethos macro.
- [ ] BR-8: Existing 46-test pytest suite MUST still pass after the
      additions.

## Acceptance Criteria

- [ ] `tools/kimi/install.sh` either (a) reads the routing block from a
      hash-pinned source and aborts on mismatch, or (b) shows a `diff` and
      requires `--yes` for the append. Documented in `tools/kimi/README.md`.
- [ ] `partials/kimi-gate.sh` exports or exposes the reason string; the 4
      delegating skills no longer inline-derive it. `grep -l 'reason="disabled-via-env"' */SKILL.md`
      returns empty (or contains only the `partials/` source).
- [ ] `/template-drift` invoked in a sandbox where `~/.claude/skills/partials/`
      and `.adlc/partials/` differ reports the difference using the same
      vocabulary it uses for templates.
- [ ] `tools/kimi/tests/test_partials.py` (or `.sh`) exists and exercises
      the 3+3 = 6 cases above. The full test suite is invocable as
      `pytest tools/kimi/tests/ -v` and passes.
- [ ] No SKILL.md regresses to inline gate predicate or inline ethos macro.

## External Dependencies

- None new. Uses existing `pytest` (already pinned in
  `tools/kimi/requirements.txt`) and existing POSIX shell.

## Assumptions

- The "hash-pinned source" approach for #1 is preferred over `--yes`
  confirmation because `install.sh` may run non-interactively (CI, scripted
  setup). Architecture will confirm.
- Reason-string DRY uses an exported shell variable
  (`ADLC_KIMI_GATE_REASON`) rather than a separate function call, so the
  per-skill call site remains a single `case` block.
- `/template-drift` extension reuses the templates/ comparison logic
  rather than duplicating it. Refactor target.
- Partials tests live inside `tools/kimi/tests/` rather than a new
  `partials/tests/` directory, so the existing pytest invocation picks
  them up automatically.

## Open Questions

- [ ] OQ-1 (item 1 approach): hash-pinned source file (`tools/kimi/claude-md-routing.txt`
      + `tools/kimi/claude-md-routing.txt.sha256`) vs `--yes` interactive
      confirmation vs both?
- [ ] OQ-2 (item 2 mechanism): export `ADLC_KIMI_GATE_REASON` from the
      function, or have callers invoke a second function
      `adlc_kimi_gate_reason`?
- [ ] OQ-3 (item 3 scope): does `/template-drift` need a per-file
      classification like "intentional customization" for partials, or
      should partial drift always be treated as stale (since partials are
      shared executable code, not customizable templates)?
- [ ] OQ-4 (item 4 framework): pytest with `subprocess.run` calling `sh`,
      or shell-native (bats / shunit2)? Pytest preferred because the
      existing suite is pytest; pulling in another framework is overhead.

## Out of Scope

- REQ-417 Wave 2 task files (they cite the deprecated inline gate). Owned
  by REQ-417's `/architect`.
- Adding `--require-hashes` to `tools/kimi/requirements.txt`. REQ-416
  out-of-scope; if this REQ adds a hash-pinning mechanism for #1, the
  pip-requirements case is a separate-but-similar follow-up.
- Migrating off mkdir-locks (REQ-416 OQ-4 already rejected this).
- Replacing dogfooding entirely. This REQ adds tests for `partials/` but
  doesn't touch the dogfood model for skill behavior.

## Retrieved Context

- REQ-416 (parent) — all four follow-ups originate in REQ-416 verify
  findings (B19eb2d commit message lists the deferrals).
- LESSON-014 — symlink-pre-check pattern; informs how `/template-drift`
  should treat partials whose drift could mask injected malicious code.
- LESSON-015 — subshell-exit-doesn't-propagate; informs how the new
  partials tests should assert on shell-script exit codes.
- LESSON-006 — `tools/` carve-out + fail-loud installers; informs
  BR-1's hash-check pattern.

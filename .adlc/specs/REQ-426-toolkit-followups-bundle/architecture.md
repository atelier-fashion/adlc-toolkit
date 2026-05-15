---
id: REQ-426
title: "Architecture — REQ-416 follow-ups bundle"
parent: REQ-426
created: 2026-05-15
updated: 2026-05-15
---

# Architecture — REQ-426

## Approach

Four orthogonal follow-ups grouped into one REQ for shared context. All
tasks run in parallel (Tier 1) — none depend on each other's outputs.
Verification runs as Tier 2.

```
Tier 1 (parallel):
  TASK-037  install.sh CLAUDE.md integrity check (item 1, security)
  TASK-038  reason-string DRY via ADLC_KIMI_GATE_REASON (item 2)
  TASK-039  /template-drift extended to cover partials/ (item 3)
  TASK-040  automated test fixtures for partials/*.sh (item 4)

Tier 2 (verification):
  TASK-041  end-to-end check (pytest expanded suite + drift dry-run)
```

## ADRs

### ADR-1 — install.sh integrity: hash-pinned source file (resolves OQ-1)

**Decision**: Extract the routing block out of `tools/kimi/README.md` into a
dedicated file `tools/kimi/claude-md-routing.txt`. Commit a SHA-256 pin in
`tools/kimi/claude-md-routing.txt.sha256`. `install.sh` recomputes the hash
on every run and refuses to write to `~/.claude/CLAUDE.md` if the live
file's hash doesn't match the pinned hash. The pin update is a one-line
edit gated by code review (visible in git history).

**Why this and not `--yes` interactive confirmation**:
- `install.sh` runs non-interactively in many flows (CI, fresh-machine
  bootstrap, sleep-cycle re-runs). Adding a TTY prompt breaks those.
- Hash-pinning makes "the routing block changed" visible at git review
  time, not at install time — earlier in the supply chain.
- An attacker who modifies the routing block would also need to modify the
  pin file in the same PR, which is exactly the gate we want a reviewer
  to see.

**Why not move routing block into a separate file but keep README markers**:
Two sources of truth invite drift. The file becomes canonical; the README
references it.

### ADR-2 — Reason-string DRY: export `ADLC_KIMI_GATE_REASON` (resolves OQ-2)

**Decision**: `partials/kimi-gate.sh`'s `adlc_kimi_gate_check` function
sets the **exported** shell variable `ADLC_KIMI_GATE_REASON` to one of
the canonical values: `"ok"`, `"disabled-via-env"`, `"no-binary"` (and
any future value when new gate conditions are added). Callers read the
variable in their `case $gate in ... esac` branches instead of
inline-deriving.

**Why export-var and not a second function call**:
- Single function call already returns the gate result (0/1/2). Asking
  callers to invoke a second function complicates the call site and
  invites the `$?`-clobber bug (LESSON-015's territory).
- Exported var pattern is canonical in shell — readers expect it.
- Lets future gate conditions add new values (`"budget-exceeded"`,
  `"rate-limited"`, etc.) without touching call sites that don't care
  about the reason.

### ADR-3 — `/template-drift` partials coverage: treat all drift as stale (resolves OQ-3)

**Decision**: Extend `/template-drift` to scan `~/.claude/skills/partials/`
vs `.adlc/partials/`. Unlike templates (which consumer projects may
intentionally customize), partials are shared executable code. **Any drift
in a partial is reported as `stale` with no "intentional customization"
classification**. This matches their security posture — a "customized"
malicious `kimi-gate.sh` shadowing the canonical one is exactly the threat
ADR-1 from REQ-416 was concerned about, and `/template-drift` is the right
detection surface.

**Why not allow customization classification for partials**:
- Templates customize *content* (project-specific spec sections). Partials
  customize *executable code* — much higher blast radius.
- Customizable partials would require a "trusted customization" registry
  (hash allowlist) which is out of scope.

### ADR-4 — Partials tests: pytest + subprocess.run (resolves OQ-4)

**Decision**: Add `tools/kimi/tests/test_partials.py` using `subprocess.run`
to invoke the shell partials in controlled sandboxes (via `tmp_path`
fixtures). Reuses the existing pytest framework, conftest, and CI
invocation. No new test framework dependency.

Test coverage:
- `test_ethos_consumer_precedence` — sandbox with `.adlc/ETHOS.md` present
  and non-empty → that content wins
- `test_ethos_toolkit_fallback` — sandbox without `.adlc/ETHOS.md` →
  `~/.claude/skills/ETHOS.md` content emitted
- `test_ethos_empty_consumer_falls_back` — sandbox with empty
  `.adlc/ETHOS.md` → toolkit fallback fires (REQ-416 H1 regression test)
- `test_ethos_no_source` — sandbox with both ETHOS sources mocked absent
  via PATH manipulation or HOME redirection → "No ethos found"
- `test_kimi_gate_available` — `ask-kimi` on PATH, no `ADLC_DISABLE_KIMI`
  → return code 0, `ADLC_KIMI_GATE_REASON=ok`
- `test_kimi_gate_disabled` — `ADLC_DISABLE_KIMI=1` → return code 1,
  reason `disabled-via-env`
- `test_kimi_gate_unavailable` — `ask-kimi` not on PATH → return code 2,
  reason `no-binary`

Why not bats/shunit2: introducing a second test framework triples the
maintenance surface (install paths, CI invocation, fixture style) without
proportional benefit. Existing pytest suite handles subprocess-based shell
testing fine.

## Data Model / API Changes

None — toolkit has no DB or API.

## File Layout (new)

```
adlc-toolkit/
├── partials/
│   └── kimi-gate.sh                         # MODIFIED — exports ADLC_KIMI_GATE_REASON
├── tools/kimi/
│   ├── README.md                            # MODIFIED — references new routing file
│   ├── claude-md-routing.txt                # NEW — canonical routing block
│   ├── claude-md-routing.txt.sha256         # NEW — pinned SHA-256
│   ├── install.sh                           # MODIFIED — hash-check before append
│   └── tests/
│       └── test_partials.py                 # NEW — 7 partials tests
└── template-drift/SKILL.md                  # MODIFIED — partials/ coverage
```

## Out of Scope (architecture-flagged)

- Migrating `tools/kimi/requirements.txt` to `--require-hashes`. Same
  supply-chain pattern, different surface. Separate REQ.
- Promoting the dogfood test model to fully automated for ALL skills
  (just markdown skills, not the partials/ executable code). Separate REQ
  if ever pursued.
- Extending `/template-drift` to detect injection at install time (the
  current scope is install-time-or-later; this REQ doesn't add a pre-pull
  trigger).

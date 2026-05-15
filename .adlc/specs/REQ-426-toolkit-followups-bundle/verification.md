---
req: REQ-426
verified: 2026-05-15
verifier: TASK-041
verdict: PASS
---

# REQ-426 — End-to-end verification

Runs after TASK-037 (hash-pin claude-md-routing), TASK-038 (DRY gate
reason-string via ADLC_KIMI_GATE_REASON), TASK-039 (template-drift covers
partials/), TASK-040 (pytest fixtures for partials/*.sh) all committed
(`92ce436`, `6e40d9b`, `cb7e80c`, `bf05956`).

## Check 1 — pytest suite full (53/53 passing)

Command:

```
~/.claude/kimi-venv/bin/pytest tools/kimi/tests/ -v
```

Result: **PASS — 53 passed in 7.04s**.

Breakdown:

- `test_cli_warn.py` — 8 passed
- `test_common.py` — 16 passed
- `test_extract_chat.py` — 12 passed
- `test_partials.py` — 7 passed (new in TASK-040: 4 ethos-include + 3
  kimi-gate-check)
- `test_telemetry.py` — 10 passed

Matches the expected count (46 pre-existing + 7 new = 53). No skips, no
xfails, no warnings of note.

## Check 2 — install.sh tampering test (hash-mismatch refusal)

Setup: copied `tools/kimi/` into a standalone scratch repo at
`/tmp/req426-repo.aX4OXB`, initialized as a fresh git repo so install.sh's
`git rev-parse --git-common-dir`-based REPO_ROOT resolution targets the
scratch tree (and not the canonical adlc-toolkit checkout, which currently
lacks `claude-md-routing.txt.sha256` on `main`). Used a sandbox
`HOME=/tmp/req426-home-tamper.vAPcoZ` so the real `~/.claude/CLAUDE.md`
was never touched.

Tamper: appended a single `X` byte to the scratch repo's
`tools/kimi/claude-md-routing.txt`.

- Pinned hash:   `5f42f9e4b31336720b5ee9042746b5228c82a84478b715e87b9df94b4b32cce5`
- Tampered hash: `c6ed44ce57799069e2ad7bcf9f753670ef366f39c6a6b48820b4d3fe5439aab4`

Ran `HOME=$SANDBOX MOONSHOT_API_KEY="" sh $SANDBOX_REPO/tools/kimi/install.sh`.

Result: **PASS**.

- Exit code: `1` (non-zero, as required).
- Stderr contained:

  ```
  ERROR: claude-md-routing.txt hash mismatch — refusing to modify ~/.claude/CLAUDE.md
    Pinned:   5f42f9e4b31336720b5ee9042746b5228c82a84478b715e87b9df94b4b32cce5
    Computed: c6ed44ce57799069e2ad7bcf9f753670ef366f39c6a6b48820b4d3fe5439aab4
    If this change is intentional, update tools/kimi/claude-md-routing.txt.sha256 in the same commit.
  ```

  Both pinned and computed digests are surfaced verbatim, per ADR-1.

- Sandbox `$HOME/.claude/CLAUDE.md`: **absent** after the failed run.
  The hash gate fires before any append, so CLAUDE.md is never created.

Side-effect cleanup: install.sh got past the venv/wrapper/LaunchAgent
setup before exiting (those run before the hash check on line ~200); the
sandbox LaunchAgent was booted out via `launchctl bootout gui/$(id -u)`
to avoid leaking it into the real launchctl session.

After the run, restored the scratch repo's routing file from its initial
commit so the happy-path check below could reuse it.

## Check 3 — install.sh happy-path (idempotent marker-guarded append)

Setup: same scratch repo at `/tmp/req426-repo.aX4OXB` (routing file
restored to its pinned hash), new sandbox
`HOME=/tmp/req426-home-happy.zHDVC6`.

First run: `HOME=$SANDBOX MOONSHOT_API_KEY="" sh $SANDBOX_REPO/tools/kimi/install.sh`.

- Exit code: `0`.
- `$SANDBOX/.claude/CLAUDE.md` created: 63 lines.
- `grep -c 'kimi-delegation:start' ...`: **1** marker.
- `grep -c 'kimi-delegation:end' ...`: **1** marker.

Second run (idempotency): re-ran the identical command against the same
sandbox.

- Exit code: `0`.
- `$SANDBOX/.claude/CLAUDE.md` line count: **63** (unchanged).
- Marker count: **1** (no duplicate append).

Result: **PASS**. The marker guard at install.sh:211
(`grep -q 'kimi-delegation:start' "$CLAUDE_MD"`) correctly short-circuits
the append on the second invocation. Sandbox LaunchAgent booted out
post-test.

## Check 4 — BR-2: no inline reason-string derivation

Command:

```
grep -l 'reason="disabled-via-env"' */SKILL.md
```

Result: **PASS** — empty output (exit 1 from grep, no files matched).
All skills route the gate reason string through
`ADLC_KIMI_GATE_REASON` per the TASK-038 refactor; no skill carries the
hand-rolled `reason="disabled-via-env"` literal anymore.

## Check 5 — /template-drift partials coverage (markdown audit)

Inspected `template-drift/SKILL.md` directly (the skill is prompt-driven,
so the verification is a content audit, not a runtime invocation).

- Step 3 ("Detect Partial Drift", line 47) exists and is dedicated to
  scanning `.adlc/partials/*.sh` vs `~/.claude/skills/partials/*.sh`.
- The three-way classification vocabulary `synced` / `stale` / `missing`
  is defined (lines 58–60) and matches Step 2's template vocabulary so
  the final report can use a unified summary.
- The "Rationale — why no intentional customization classification for
  partials" paragraph (lines 51–53) is present and articulates the
  threat-model argument: partials are shared executable code, consumer-
  side modification would shadow gate logic / strip the ETHOS preamble,
  so every partial drift is reported as `stale` and surfaced loudly.
- Reverse-direction check ("any `*.sh` in `.adlc/partials/` that does
  NOT exist in `~/.claude/skills/partials/`" — line 62) is also covered.
- The reconciliation step (line 146) explicitly says "every `stale` or
  `missing` partial (no customization escape hatch for partials — see
  Step 3 rationale)", confirming the report drives a remediation
  prompt.

Result: **PASS**.

## Check 6 — BR-7: REQ-416 invariants preserved

Three grep checks plus the line-count gate on `proceed/SKILL.md`:

| Check | Command | Result |
|---|---|---|
| 6a — no inline ethos macro | `grep -l "cat .adlc/ETHOS.md" */SKILL.md` | empty — **PASS** |
| 6b — no inline gate predicate | `grep -l 'command -v ask-kimi.*ADLC_DISABLE_KIMI' */SKILL.md` | empty — **PASS** |
| 6c — proceed/SKILL.md size | `wc -l proceed/SKILL.md` | **480** lines (≤ 480) — **PASS** |

Result: **PASS** on all three. No skill has regressed to inline ethos
injection or inline gate predicate; the `/proceed` skill is exactly at
the 480-line ceiling.

## Environmental notes / soft prerequisites

- `tools/kimi/install.sh` resolves `REPO_ROOT` via
  `git rev-parse --git-common-dir`, which always points at the canonical
  adlc-toolkit checkout — not the worktree this REQ lives in. Since
  TASK-037's `claude-md-routing.txt.sha256` is not on `main` yet,
  running install.sh straight from the worktree triggers a "canonical
  routing files missing" error. The verification used a standalone
  scratch repo at `/tmp/req426-repo.aX4OXB` to exercise install.sh end-
  to-end; this is the intended consumer experience post-merge.
- `MOONSHOT_API_KEY` was deliberately unset for both install.sh runs so
  `launchctl setenv` would be skipped — this prevents the sandbox runs
  from leaking a key into the real launchctl session.
- The sandbox LaunchAgents written by install.sh into
  `$SANDBOX/Library/LaunchAgents/` were booted out after each run; no
  leakage into the real GUI session.
- The pre-existing pip-version warning ("You are using pip version
  21.2.4; however, version 26.0.1 is available.") on the sandbox venv is
  cosmetic and unrelated to this verification.

## Overall verdict

**PASS** — all six checks green. REQ-426 is ready to ship.

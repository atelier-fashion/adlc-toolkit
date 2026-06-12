---
id: TASK-003
title: "doctor checks: symlinks, path, gh, git, delegate-gate, counters, launchctl, template"
status: draft
parent: REQ-519
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-002]
repo: adlc-toolkit
---

## Description

Implement every check in the registry (BR-4) in `tools/adlc/checks.py`, each
returning `(Result, detail, remediation)` with a copy-pasteable remediation on
fail (BR-5). The `delegate-gate` check reuses REQ-515's
`partials/delegate-gate.sh` and `_common.parse_delegate_config` rather than
reinventing config resolution (per launch-prompt directive + ADR-4).

## Files to Create/Modify

- `tools/adlc/checks.py` — one function per check id, plus assembly of the
  `REGISTRY` list consumed by `doctor.py`:
  - `skills-symlink`, `agents-symlink`: `~/.claude/skills` / `agents` is a
    symlink resolving into a git checkout. fail → `ln -sfn <root> ~/.claude/...`.
  - `toolkit-clean`: clone on a branch (not detached) and not unexpectedly
    dirty. fail → `git -C <root> status`.
  - `path-shims`: `adlc` resolves on PATH (`shutil.which`) and `adlc --version`
    exec's. fail → `./install.sh --repair` + restart shell.
  - `gh-present`: `gh` on PATH. fail → per-OS install line.
  - `gh-auth`: `gh auth status` exits 0. SKIP if `gh` absent (chain on
    gh-present). fail → `gh auth login`.
  - `git-identity`: `git config user.name`/`user.email` both set. fail → exact
    `git config --global` lines.
  - `delegate-gate`: source `partials/delegate-gate.sh`, read rc + reason
    (ADR-4 table): rc 0→PASS; rc 1→SKIP(reason); rc 2 → SKIP if not opted-in,
    FAIL if config `enabled: true` (misconfigured). Config read via
    `_common.parse_delegate_config` through a subprocess probe so `adlc` keeps
    no hard import dependency on the kimi module.
  - `counters`: each `~/.claude/.global-next-{req,bug,lesson}` present & numeric;
    `.lock.d` not stale. SKIP a counter that legitimately doesn't exist yet
    (first run). fail → exact `printf`/`rmdir` remediation.
  - `launchctl`: macOS-only (`applies_to` os==Darwin). PASS if kimi setenv agent
    loaded when delegation opted-in; SKIP on Linux and when delegation not
    opted-in.
  - `template-version`: pointer to `/template-drift` when project `.adlc/`
    scaffold drifted. SKIP when run outside a consumer project.
  - `claude-code` (report-only): never FAIL the verdict (always PASS or SKIP).

## Acceptance Criteria

- [ ] Every check returns a copy-pasteable remediation on FAIL — no "see docs"
      (BR-5).
- [ ] `delegate-gate` maps the gate's 0/1/2 + reason exactly per ADR-4; it
      reuses `partials/delegate-gate.sh` and `_common.parse_delegate_config`,
      does NOT re-derive config precedence.
- [ ] Breaking each dependency (unlink skills symlink, unset gh auth, corrupt a
      counter to non-numeric, leave a stale lock dir) makes that check FAIL, and
      the printed remediation, run verbatim, returns it to PASS (AC-5).
- [ ] macOS-only `launchctl` is SKIP (not FAIL) on Linux (BR-6, AC-2).
- [ ] `claude-code` is report-only and never contributes a FAIL.

## Technical Notes

- Stdlib + `subprocess` for `gh`/`git`/sourcing the partial. Resolve the partial
  with the two-level fallback: prefer `<repo_root>/partials/delegate-gate.sh`,
  fall back to `~/.claude/skills/partials/delegate-gate.sh` (architecture.md
  Partials pattern).
- Sourcing a shell partial from Python: run
  `bash -c '. <partial>; adlc_delegate_gate_check; echo "$?:$ADLC_DELEGATE_GATE_REASON"'`
  and parse rc + reason from stdout (the function's own rc is captured before
  the echo so capture it into a var first). Keep BSD/zsh-safe (BR-7) — invoke
  with `bash`, not the login shell.
- Stale lock detection for counters: a `.lock.d` directory older than a sane
  threshold (or simply present with no live holder) — mirror the staleness
  notion from the global-counter lock pattern (architecture.md). Remediation:
  `rmdir ~/.claude/.global-next-req.lock.d`.
- `_common.parse_delegate_config` probe: `tools/kimi/` may be absent on a
  skills-only checkout — handle ImportError/missing-file by treating config as
  "delegation not opted-in" (→ SKIP), never a traceback (BR-2 spirit).
- Counter staleness threshold and "live holder" semantics: prefer a simple,
  documented rule (e.g. lock dir present > N minutes with no pid file) and state
  it in the remediation text so the user knows why it flagged.

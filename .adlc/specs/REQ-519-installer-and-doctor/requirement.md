---
id: REQ-519
title: "One-Command Installer and `adlc doctor` Health Check"
status: complete
deployable: false
created: 2026-06-11
updated: 2026-06-11
component: "adlc/toolkit"
domain: "adlc"
stack: ["bash", "python", "markdown"]
concerns: ["onboarding", "portability", "dx"]
tags: ["install", "doctor", "symlink", "path", "bootstrap", "preflight"]
---

## Description

Installing the toolkit today is undocumented machine surgery distributed across
several manual steps: clone the repo, symlink `~/.claude/skills` and
`~/.claude/agents`, run `tools/kimi/install.sh` (venv + shims + PATH export in
`~/.zshrc` + launchctl plist), seed permission allowlists, and trust that the
counters bootstrap correctly. The shims even embed the installing user's
absolute home path. A new adopter at another company reconstructs this from
lessons and folklore — which is exactly the reconfiguration burden driving the
portability initiative (REQ-515/516/518).

This REQ ships two entry points:

1. **`install.sh`** at the repo root — one idempotent command that performs the
   full setup: symlinks, optional delegation-tool install (default off per
   REQ-515 BR-11), PATH wiring, config scaffold, and a final doctor run.
2. **`adlc doctor`** — a read-only diagnostic that checks every known
   environmental dependency end-to-end and reports pass/fail per check with the
   exact remediation command. Doctor is also the pre-flight primitive other
   skills can call (generalizing the probe-before-dispatch lesson). (informed by LESSON-356)

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| Check | id | string | stable slug, e.g. `skills-symlink`, `gh-auth`, `delegate-gate`, `counters`, `path-shims` |
| Check | result | enum | pass / fail / skip (with reason, e.g. "delegation not enabled") |
| Check | remediation | string | required on fail — the literal command or file edit to fix it |
| InstallRun | mode | enum | fresh / repair / dry-run |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| doctor report | `adlc doctor` (manual or skill pre-flight) | ordered check results, overall verdict, machine profile (OS, shell) |
| install summary | `install.sh` completes | actions taken vs skipped-already-done; ends with embedded doctor report |

## Business Rules

- [ ] BR-1: `install.sh` is idempotent and repair-capable: a second run on a healthy machine changes nothing and says so; a run on a broken machine fixes only what is broken. Idempotency gates on file/symlink content, not process state. (informed by LESSON-006)
- [ ] BR-2: Every mutation of user files (`~/.zshrc`, settings, config scaffold) is fail-loud and atomic: backup, temp-write, rename; malformed existing content produces an actionable message, never a traceback or a silent overwrite. (informed by LESSON-006)
- [ ] BR-3: Generated shims and config contain no hardcoded user-specific absolute paths beyond what is derived at install time from the actual clone location; reinstalling after moving the clone regenerates them correctly (`install.sh --repair`).
- [ ] BR-4: `adlc doctor` is strictly read-only and exits non-zero iff any non-skip check fails. Checks cover, at minimum: skills/agents symlinks resolve to a git checkout; toolkit clone is on a branch and not unexpectedly dirty; PATH shims resolve and execute; delegation gate state (enabled/disabled/misconfigured per REQ-515 config); `gh` present and authenticated; git identity set; counters present, numeric, and lock-dir not stale; project-level `.adlc/` scaffold version vs toolkit templates (staleness pointer to `/template-drift`).
- [ ] BR-5: Every failed check prints its remediation as a copy-pasteable command or exact file edit — no "see documentation." Validation rules are written as concrete example lists of what passes/fails, not prose-only descriptions. (informed by LESSON-009)
- [ ] BR-6: Doctor detects the machine profile honestly: real login shell (not `$SHELL` assumptions), OS family; macOS-only steps (launchctl) are skipped-with-notice on Linux and vice versa — skip, never fail, on inapplicable checks. (informed by LESSON-009)
- [ ] BR-7: All shell is BSD- and zsh-safe and dogfooded under `zsh -c` and `bash -c` on macOS and `bash` on Linux; lint-skills conventions apply to any fenced blocks added to skills. (informed by LESSON-013, LESSON-329, LESSON-335)
- [ ] BR-8: Skill pre-flights converge on doctor: `/sprint`'s and `/proceed`'s existing environment probes (e.g. gcloud auth, gh auth) are reimplemented as or delegated to doctor checks with a `--checks` filter, rather than maintaining parallel probe code. Sibling skills are audited so probe logic is not left duplicated. (informed by LESSON-356, LESSON-020, LESSON-023)
- [ ] BR-9: `install.sh` never enables delegation by default; it offers the delegation install as an explicit opt-in step that requires the REQ-515 config (`enabled: true`) and prints the data-governance notice.
- [ ] BR-10: README installation section is rewritten to exactly two commands (clone + `./install.sh`), with everything else discoverable via `adlc doctor`.
- [ ] BR-11: `adlc` ships as an umbrella CLI under `tools/adlc/` (decided 2026-06-11): `doctor` is its first subcommand, and it is the designated home for subsequent user-facing commands (`adlc renumber` from REQ-518, the REQ-516 tier render). `install.sh` puts `adlc` on PATH via the same shim mechanism as the other tools (no hardcoded absolute paths, BR-3). Subcommand dispatch is data-driven so later REQs add commands without touching dispatch logic.

## Acceptance Criteria

- [ ] On a clean macOS user account (no `~/.claude` customization), `git clone` + `./install.sh` yields: working skills/agents symlinks, `adlc doctor` all-pass (delegation checks = skip/disabled), and a usable `/init` in a fresh consumer repo.
- [ ] Same flow on Ubuntu (container is acceptable) passes with launchctl checks reported as skipped, not failed.
- [ ] Second consecutive `install.sh` run reports zero actions taken.
- [ ] Moving the clone to a new path and running `install.sh --repair` regenerates symlinks and shims; doctor passes; no stale absolute paths from the old location remain (grep-verified).
- [ ] Breaking each doctor-checked dependency one at a time (unlink skills symlink, unset gh auth, corrupt a counter to non-numeric, leave a stale lock dir) produces a failing doctor with a remediation that, when executed verbatim, returns doctor to pass.
- [ ] `adlc doctor --checks gh-auth,delegate-gate` runs only those checks (the skill pre-flight contract, BR-8).
- [ ] Dry-run mode (`install.sh --dry-run`) prints the action plan and changes nothing (verified by before/after filesystem diff).

## External Dependencies

- None new: git, gh (checked, not required to install), python3 for the existing venv path when delegation is opted into.

## Assumptions

- The symlink install model remains canonical (no copy-based install mode in this REQ).
- REQ-515's config file location is settled before doctor's `delegate-gate` check is implemented; if REQ-519 lands first, that check ships as `skip: delegation config not yet specified`.
- Windows is out of scope; WSL counts as Linux.

## Open Questions

- [ ] Should `install.sh` offer to write the permission-allowlist baseline into project `.claude/settings.json` (the LESSON-001-style allowlists), or is that strictly `/init`'s job? Proposed: doctor *checks* and reports, `/init` writes.
- [ ] Doctor check for Claude Code itself (version, model availability)? Proposed: report-only, never fail on it.

## Out of Scope

- Per-company pipeline policy (branch gates, merge modes, deploy adapters) — separate follow-up REQ.
- ETHOS.md/template customization-vs-staleness handling — separate follow-up REQ (extends `/template-drift`).
- A copy-based (non-symlink) install mode or version pinning at the install layer.
- Windows-native support.

## Retrieved Context

- LESSON-006 (lesson, score 7): tools dir carve-out and fail-loud installers
- LESSON-013 (lesson, score 6): BSD grep word-boundary silent failure
- LESSON-335 (lesson, score 5): zsh-executor and arg-templating hazards
- LESSON-329 (lesson, score 5): dogfood skills under executor shell
- LESSON-019 (lesson, score 5): presence guards rot when indirection moves
- LESSON-020 (lesson, score 5): cross-block shell state and guard rot
- LESSON-313 (lesson, score 4): global counter scope is its scan root
- LESSON-023 (lesson, score 4): mirror the rationale not just mechanism
- LESSON-014 (lesson, score 4): lock symlink TOCTOU
- LESSON-012 (lesson, score 4): structural telemetry beats prose enforcement
- LESSON-008 (lesson, score 4): skill delegation untrusted data and citation sanitization
- LESSON-009 (lesson, score 4): hotfix verify finds what original verify missed
- LESSON-356 (lesson, score 3): probe gcloud auth before dispatching GCP REQs
- LESSON-330 (lesson, score 3): review catches omitted requirements
- LESSON-010 (lesson, score 3): delegated-model silent truncation and advisory anchoring

---
id: REQ-415
title: "Kimi hotfix bundle: path-traversal regex, broader credential redaction, install.sh shell detection + launchctl, gitignore pipeline-state, Prerequisites blocks, stale tags"
status: approved
deployable: false
created: 2026-05-13
updated: 2026-05-13
component: "tools/kimi"
domain: "adlc"
stack: ["python", "bash", "markdown"]
concerns: ["security", "privacy", "developer-experience"]
tags: ["kimi", "hotfix", "path-traversal", "credential-redaction", "install-sh", "launchctl", "prerequisites", "gitignore"]
---

## Description

REQ-414 shipped the first ADLC-skill Kimi delegation pilot. A `/analyze` audit on the resulting
codebase surfaced one Critical regression, three High-severity findings, and a few smaller
hygiene items that share a root: small mistakes in REQ-412..414 that didn't show up until the
toolkit was being used in real consumer-side conditions (bash login shells, GUI-launched
Claude Code, real lessons getting written). This REQ bundles those small-but-load-bearing
fixes into a single hotfix REQ so they ship together and don't drag.

Eight discrete items:

1. **Path-traversal regex bypass (Critical)** — the BR-3 file-path validator in `analyze/SKILL.md`
   and `wrapup/SKILL.md` uses `^[A-Za-z0-9_./-]+$`. Because `.` is in the class, that regex
   matches `../../etc/passwd`. The validator then proceeds to `test -f` against the attacker-
   controlled path. Fix: reject any citation whose path contains a `..` segment.
2. **Incomplete credential redaction (High)** — the `sed` pass in `wrapup/SKILL.md` only
   matches `sk-…` and `MOONSHOT_API_KEY=…`. AWS access keys (`AKIA…`), GitHub PATs (`ghp_…`),
   high-entropy `Bearer …` headers, and `*_API_KEY=`/`*_TOKEN=` patterns slip through. Expand
   the redaction patterns.
3. **`install.sh` only writes to `~/.zshrc` (High)** — on macOS with a `bash` login shell,
   PATH and the key reminder go nowhere; user has no Kimi tooling unless they manually edit
   `~/.bash_profile`. Detect `$SHELL` (or `getent passwd $USER` shell field) and write to the
   correct rc file. ALSO run `launchctl setenv MOONSHOT_API_KEY` (when present) so
   GUI-launched Claude Code inherits the var.
4. **3 stranded `pipeline-state.json` files (High tech-debt)** — `pipeline-state.json` got
   committed by accident in REQ-412 and never gitignored. Three of them now live on `main`
   in stale `completed:true + merged:false` states. Gitignore the pattern and remove the
   tracked copies.
5. **4 skills missing `## Prerequisites` block (Major convention violation)** — `/analyze`,
   `/optimize`, `/status`, `/wrapup`. Add a one-paragraph Prerequisites section consistent
   with the convention.
6. **Stale `Co-Authored-By: Claude Opus 4.6` tag in `/wrapup`** — should reference the
   current model (Opus 4.7) or be made model-agnostic.
7. **Stray `LESSON-005-sibling-skill-anti-pattern-audit 2.md`** — Finder-created duplicate
   of LESSON-005 that has been in untracked status since the start. Delete it (or commit it
   if it's actually different — it's not).
8. **Documentation of the macOS GUI env-inheritance gotcha** — add a brief "Troubleshooting"
   subsection in `tools/kimi/README.md` explaining that env vars exported in `~/.zshrc` are
   not visible to GUI-launched Claude Code unless `launchctl setenv` is also run, and pointing
   at the new `install.sh` behavior.

This REQ is **deployable: false**. The "deploy" is the user re-running `bash tools/kimi/install.sh`
locally after merge (idempotent, picks up the new behaviors).

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| BR-3 file-path validator | regex+rejection | string | rejects `..` segments AND any chars outside `[A-Za-z0-9_./-]` |
| credential redaction patterns | set of regexes | string[] | covers `sk-…`, `MOONSHOT_API_KEY=…`, `AKIA[A-Z0-9]{16}`, `ghp_[A-Za-z0-9]{36,}`, `Bearer [A-Za-z0-9._-]{20,}`, `[A-Z_]+_(API_KEY|TOKEN)[[:space:]]*[=:][[:space:]]*[^[:space:]]+` |
| install.sh shell detection | shell id | string | one of `zsh`, `bash`, `unknown`; chooses `~/.zshrc`, `~/.bash_profile`, or prints manual instructions |
| install.sh launchctl step | command | string | `launchctl setenv MOONSHOT_API_KEY "$MOONSHOT_API_KEY"` when key is set in the install shell; skip silently when unset |
| .gitignore entry | pattern | string | exactly `.adlc/specs/*/pipeline-state.json` |
| Prerequisites block | content | markdown | one short paragraph + the standard "run /init first" failure mode |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| install.sh detects bash shell | login shell of invoking user is bash | wrappers + key reminder written to `~/.bash_profile` instead of `~/.zshrc` |
| install.sh detects key is set | `MOONSHOT_API_KEY` is in install shell's env | `launchctl setenv MOONSHOT_API_KEY "$MOONSHOT_API_KEY"` runs |
| pipeline-state.json change in any REQ | git operation | file is now gitignored — does not show in `git status` |
| path-traversal citation in Kimi output | Kimi proposes citation containing `..` | rejected at validation, dropped from artifact, drop noted in skill log |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| run install.sh | local developer |
| run `launchctl setenv` | install.sh on behalf of the local developer |
| edit `~/.bash_profile` / `~/.zshrc` | install.sh (marker-guarded, idempotent) |

## Business Rules

- [ ] BR-1: BR-3 file-path validators in `analyze/SKILL.md` and `wrapup/SKILL.md` MUST reject
      any path containing a `..` segment, in addition to the existing character-class regex.
- [ ] BR-2: The credential-redaction `sed` pass in the wrapup delegated path MUST cover at
      minimum: `sk-[A-Za-z0-9_-]{20,}`, `AKIA[A-Z0-9]{16}`, `ghp_[A-Za-z0-9]{36,}`,
      `Bearer [A-Za-z0-9._-]{20,}`, and `[A-Z_]+_(API_KEY|TOKEN)[[:space:]]*[=:][[:space:]]*[^[:space:]]+`.
- [ ] BR-3: `install.sh` MUST detect the user's login shell and write the PATH entry +
      `MOONSHOT_API_KEY` reminder into the correct rc file (`~/.zshrc` for zsh,
      `~/.bash_profile` for bash). Unknown shells get a printed instruction with no rc edit.
- [ ] BR-4: `install.sh` MUST run `launchctl setenv MOONSHOT_API_KEY "$MOONSHOT_API_KEY"`
      (macOS only) when the var is present in the install shell. This is the only reliable way
      to make the key visible to GUI-launched processes. If `launchctl` is not present (e.g.
      Linux), skip silently.
- [ ] BR-5: `.gitignore` MUST list `.adlc/specs/*/pipeline-state.json` and the three already-
      tracked stale files MUST be removed from the repo (via `git rm`). A re-run of any REQ
      pipeline must not re-introduce them as tracked files.
- [ ] BR-6: Each of `/analyze`, `/optimize`, `/status`, `/wrapup` SKILL.md MUST contain a
      `## Prerequisites` section consistent with the other skills' Prerequisites blocks (verify
      `.adlc/context/project-overview.md` exists; instruct user to run `/init` if missing).
- [ ] BR-7: The stale `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>` line in
      `wrapup/SKILL.md` MUST be updated to `Claude Opus 4.7` (or made model-agnostic, e.g.
      `Co-Authored-By: Claude <noreply@anthropic.com>`).
- [ ] BR-8: The stray `LESSON-005-sibling-skill-anti-pattern-audit 2.md` MUST be deleted
      from the working tree (it has been untracked since first commit and serves no purpose).
- [ ] BR-9: `tools/kimi/README.md` MUST gain a short "Troubleshooting" subsection covering
      the GUI vs terminal launch env-inheritance gotcha, naming `launchctl setenv` and the
      `~/.bash_profile` path for bash users.
- [ ] BR-10: Re-running `install.sh` after this REQ MUST remain idempotent — no duplicate
      PATH entries, no duplicate `launchctl setenv` (it's naturally idempotent), no duplicate
      CLAUDE.md routing block.
- [ ] BR-11: REQ-414's existing pytest suite (29 tests in `tools/kimi/tests/`) MUST still pass
      after this REQ's changes — regression check.

## Acceptance Criteria

- [ ] `git grep -nE '\^.*\.\..*[^\\][^\\]/.*\$|\^[A-Za-z0-9_./-]\+\$' analyze/SKILL.md wrapup/SKILL.md`
      shows the path-validator now has an explicit `..`-rejection alongside the character-class
      regex, AND a synthetic Kimi-output containing `../../etc/passwd` would be rejected
      (verified by walking through the markdown logic).
- [ ] The wrapup delegated path's `sed` pass contains at least 5 distinct redaction patterns
      covering the BR-2 list (verified by `grep -F '[REDACTED]' wrapup/SKILL.md` finding the
      consolidated sed call and counting patterns).
- [ ] On a macOS machine with `chsh -s /bin/bash`-style bash login, running `bash install.sh`
      results in a `~/.bash_profile` entry for `~/bin` PATH (verified by `grep -F 'adlc-toolkit
      kimi install.sh' ~/.bash_profile`) and NO duplicate entry in `~/.zshrc` (and vice versa
      for zsh).
- [ ] After `install.sh` runs on macOS with `MOONSHOT_API_KEY` set, `launchctl getenv
      MOONSHOT_API_KEY` returns the key value (proving GUI-launched apps will inherit it).
- [ ] `git ls-files .adlc/specs/ | grep pipeline-state.json` returns empty (no tracked
      pipeline-state files remain on main).
- [ ] `.gitignore` contains the line `.adlc/specs/*/pipeline-state.json`.
- [ ] `grep -l '^## Prerequisites' analyze/SKILL.md optimize/SKILL.md status/SKILL.md wrapup/SKILL.md`
      lists all 4 files.
- [ ] `grep -F 'Claude Opus 4.6' wrapup/SKILL.md` returns empty; `grep -E 'Claude Opus 4\.[78]|Claude <noreply' wrapup/SKILL.md` returns at least one match.
- [ ] `ls '.adlc/knowledge/lessons/LESSON-005-sibling-skill-anti-pattern-audit 2.md' 2>&1`
      reports "No such file" after this REQ.
- [ ] `tools/kimi/README.md` has a `### Troubleshooting` (or similar) subsection mentioning
      `launchctl setenv` and the bash/`~/.bash_profile` path.
- [ ] Re-running `install.sh` twice on the same machine: ~/.zshrc OR ~/.bash_profile (whichever
      applies) has exactly one PATH-marker line; `launchctl setenv` invocation reports no error
      on the second run.
- [ ] `~/.claude/kimi-venv/bin/python3 -m pytest tools/kimi/tests/ -q` reports 29/29 passing
      (or higher if any new tests were added).

## External Dependencies

- `launchctl` (macOS only, always present on macOS). The behavior is skipped on Linux where
  `launchctl` does not exist.
- No new Python packages.

## Assumptions

- The user's login shell is one of `zsh` or `bash`. Other shells (fish, csh, nu) print a
  manual-instruction message — supporting them is out of scope.
- `launchctl setenv` until-reboot is sufficient for this REQ. Permanent across-reboot
  persistence (via a `LaunchAgent` plist) is a follow-up if needed; most consumer-facing usage
  doesn't reboot often enough to make it worth it.
- The 3 stale `pipeline-state.json` files on main are not load-bearing — no skill reads them
  from main. They were `.adlc/specs/*/pipeline-state.json` from REQ-412/413/414 which all
  completed successfully; removing them is a no-op for runtime.

## Open Questions

- [ ] OQ-1: Should the credential redaction `sed` be moved from inline-in-skill to a tiny
      helper script under `tools/kimi/` (callable as `kimi-redact < in > out`)? Recommend yes
      eventually for testability, but not in this REQ — inline is simpler and the patterns
      need to be eyeball-reviewed anyway.
- [ ] OQ-2: Should `install.sh` also write a launchd plist for persistence across reboots?
      Recommend no for this REQ; until-reboot is acceptable; revisit if user feedback says
      otherwise.
- [ ] OQ-3: Should "Prerequisites" content for `/optimize` and `/status` be identical to the
      existing pattern in `/spec`/`/architect`, or a tailored version? Recommend a tailored
      one-paragraph version per skill that names which `.adlc/context/*` files it actually
      reads.
- [ ] OQ-4: Should the stale Co-Authored-By line be updated to current model or made
      model-agnostic (`Claude <noreply@anthropic.com>`)? Recommend model-agnostic — the model
      name will drift again.

## Out of Scope

- The larger REQ-416 refactor items (DRY Kimi gate / ethos macro, `/proceed` size reduction,
  lock symlink TOCTOU full review, `requirements.txt` pinning). Those belong in REQ-416 and
  deserve a proper `/architect` pass.
- Adding a new skill, agent, or template.
- Changing `MOONSHOT_API_KEY` storage to macOS Keychain.
- Building a CI test runner for the skill markdown.
- Auto-rotating the key on a schedule.

## Retrieved Context

- LESSON-006: tools/ carve-out + fail-loud installers — informs BR-3, BR-4, BR-10.
- LESSON-007: scrub-at-every-leak-point — informs BR-1, BR-2.
- LESSON-008: skill delegation = untrusted data, citation sanitization — informs BR-1
  (the regex hardening is a direct follow-up to LESSON-008's "sanitize citation tokens with
  a strict regex BEFORE any shell expansion").

REQ-412, REQ-413, REQ-414 (all `status: complete`) are direct ancestors and are referenced
throughout; outside the Step 1.6 retrieval status filter.

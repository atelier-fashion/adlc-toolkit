---
id: TASK-136
title: "install.sh: ADLC_HOME, Claude Code's mount always, the skills-only view, the ~/.agents/skills mount, and the shim's run-time home"
status: complete
parent: REQ-654
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-134]
repo: adlc-toolkit
---

## Description

`install.sh` resolves `ADLC_HOME` before any mutation, keeps Claude Code's mount, installs
`<adlc_home>/skills|agents` under an override, builds the skills view (ADR-4) and the
`~/.agents/skills` mount (ADR-5), and stamps a shim that resolves the venv through
`ADLC_HOME` at run time (ADR-3). `--dry-run` and `--repair` cover all of it.

## Files to Create/Modify

- `install.sh` — `ADLC_HOME_DIR` from `partials/adlc-home.sh`; `ensure_skills_view`; `ensure_agents_mount`; shim and `report_venv_pyyaml` via the home; config under the home; help text
- `tools/adlc/tests/test_install_home.py` — new: full-installer runs in a sandbox clone and `HOME` (AC-1, AC-2, AC-4, AC-5, AC-9)
- `tools/adlc/tests/test_install_shim.py` — shim cases under an overridden and an invalid home; no `.bak` of the generated shim
- `tools/adlc/tests/test_config_scaffold_parity.py` — the slice's globals gain `ADLC_HOME_DIR`

## Acceptance Criteria

- [ ] Default home: the first run on a healthy pre-REQ install acts only on the view, the mount and the shim; the second run reports zero actions; pre-existing paths are byte-identical
- [ ] `ADLC_HOME=/x`: skills, agents, config and view under `/x`, plus `~/.claude/skills` → clone
- [ ] `~/.agents/skills/` lists exactly the clone's skill directories; adding and removing a skill adds and removes one link
- [ ] A pre-existing real `~/.agents/skills/` with `mine/` and a decoy `spec/` gets every other skill linked, `spec` reported skipped, `mine/` untouched; `--dry-run` prints the same plan and changes nothing
- [ ] Moving the clone and running `--repair` repoints every link; no file or link under the sandbox `~/.claude`, `~/.agents` or `~/bin` names the old path
- [ ] An invalid `ADLC_HOME` exits before the first mutation, naming the variable

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/adlc/tests/test_install_home.py::test_default_home_is_byte_identical` | yes |
| BR-3 | test-case | `tools/adlc/tests/test_install_home.py::test_override_home_keeps_claude_mount` | yes |
| BR-4 | test-case | `tools/adlc/tests/test_install_home.py::test_view_tracks_added_and_removed_skill` | yes |
| BR-5 | test-case | `tools/adlc/tests/test_install_home.py::test_existing_real_dir_keeps_user_entries` | yes |
| BR-6 | test-case | `tools/adlc/tests/test_install_home.py::test_override_home_keeps_claude_mount` | yes |
| BR-10 | test-case | `tools/adlc/tests/test_install_home.py::test_repair_after_clone_move` | yes |
| AC-1 | test-case | `tools/adlc/tests/test_install_home.py::test_default_home_is_byte_identical` | yes |
| AC-2 | test-case | `tools/adlc/tests/test_install_home.py::test_override_home_keeps_claude_mount` | yes |
| AC-4 | test-case | `tools/adlc/tests/test_install_home.py::test_view_tracks_added_and_removed_skill` | yes |
| AC-5 | test-case | `tools/adlc/tests/test_install_home.py::test_existing_real_dir_keeps_user_entries` | yes |
| AC-9 | test-case | `tools/adlc/tests/test_install_home.py::test_repair_after_clone_move` | no |

## Technical Notes

- The sandbox clone is a `git init` copy of the files `install.sh` and the doctor read, with
  **no remote**, so the closing doctor's `reservations` check SKIPs and never pushes (the
  reason `test_install_shim.py` slices instead of running the installer).
- Bash 3.2: no `declare -A`, no `mapfile`, no `${var,,}`. Name lists travel as
  newline-separated text compared with `grep -qxF`.
- `ensure_symlink` keeps its refusal for a non-symlink at a Claude Code mount path.
- The view path and the mount are classified before the first mutation (LESSON-017).

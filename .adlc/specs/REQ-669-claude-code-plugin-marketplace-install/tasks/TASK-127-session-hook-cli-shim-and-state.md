---
id: TASK-127
title: "Plugin SessionStart hook (pointer file, config scaffold, PATH) and the scripts/adlc CLI shim"
status: complete
parent: REQ-669
created: 2026-10-28
updated: 2026-10-28
dependencies: [TASK-123]
---

## Description

Apply architecture ADR-4. The plugin ships `hooks/hooks.json`, which registers `scripts/session-start.sh` on SessionStart. The script does three idempotent things, each of which exits 0:

1. It validates `CLAUDE_PLUGIN_ROOT`, then atomically writes `~/.claude/adlc/plugin-root`.
2. It writes `~/.claude/adlc/config.yml` only when absent, byte-identical to `install.sh`'s scaffold, so delegation stays off.
3. When `CLAUDE_ENV_FILE` is set, it appends `<root>/scripts` to PATH once.

`scripts/adlc` is the POSIX shim that makes `adlc doctor` runnable with no `install.sh`. There is no top-level `bin/` (BR-20). TASK-120's hook rows decide two things. If plugin hooks get no `CLAUDE_ENV_FILE`, step 3 is dropped and the BR-20 second arm is recorded. If hooks do not run at all, this task ships only the shim, and the pointer arm is retired in TASK-122's line.

## Files to Create/Modify

- `hooks/hooks.json` — new. A SessionStart entry whose command is `sh "${CLAUDE_PLUGIN_ROOT}/scripts/session-start.sh"`.
- `scripts/session-start.sh` — new. POSIX sh, stdlib-free (no python). Every path exits 0, with at most one `adlc:` stderr line.
- `scripts/adlc` — new, mode 755. POSIX shim. It resolves its own directory with `cd "$(dirname "$0")/.." && pwd -P`, then runs `exec python3 "<root>/tools/adlc/adlc.py" "$@"`. It exits 127 with a one-line message when `python3` is absent.
- `partials/tests/session-start.test.sh` — new harness.
- `partials/tests/run.sh` — register it.
- `tools/adlc/tests/test_config_scaffold_parity.py` — new. It asserts that the scaffold bytes in `scripts/session-start.sh` equal those `install.sh`'s `ensure_config` writes, extracting both from the files rather than from a copy.

## Acceptance Criteria

- [x] `session-start.test.sh` runs in a sandbox `HOME` and covers each of these:
  - a valid root writes the pointer;
  - a second run makes no write, by mtime;
  - a root that is relative, lacks `plugin.json`, or names a different plugin writes nothing and still exits 0;
  - an existing `config.yml` is left byte-identical (the benign path);
  - an absent one is created with `enabled: false`;
  - with `CLAUDE_ENV_FILE` set, exactly one PATH line is appended across two runs, and it appends after `$PATH`, not before;
  - with it unset, no file is created;
  - a read-only `~/.claude` makes every step fail soft with exit 0.
- [x] The harness passes under bash, zsh, sh and dash.
- [x] `scripts/adlc doctor` runs from a cache-shaped copy with no `~/bin/adlc` and no venv.
- [x] `test_config_scaffold_parity.py` passes, and fails if either copy changes alone.
- [x] TASK-121's `plugin-manifest` check still passes, with no top-level `bin/`.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-6 | test-case | `partials/tests/session-start.test.sh::case_config_absent_scaffolded_disabled` | no |
| BR-6 | test-case | `partials/tests/session-start.test.sh::case_existing_config_untouched` | yes |
| BR-7 | test-case | `partials/tests/session-start.test.sh::case_env_file_path_appended_once` | no |
| BR-7 | test-case | `tools/adlc/tests/test_config_scaffold_parity.py::test_scaffold_bytes_match_install_sh` | no |
| BR-17 | test-case | `partials/tests/run.sh` under bash, zsh, sh and dash: `session-start.test.sh` | no |
| BR-20 | test-case | `partials/tests/session-start.test.sh::case_invalid_root_rejected_no_write` | yes |
| AC-5 | test-case | `partials/tests/run.sh` under bash, zsh, sh and dash: `session-start.test.sh` | no |

## Technical Notes

- Validate before any write, reading each input once (LESSON-017). Write through a temp file in the same directory, then `mv`.
- The pointer content is one absolute path and a newline. Reject any value containing a newline or `..`.
- The PATH line carries a marker comment (`# adlc-plugin-path`) so the idempotence check is a `command grep -F` of the marker, not a regex on a path (LESSON-717).
- The README text (TASK-130) must disclose what the hook writes. The directory's security scan looks for undisclosed behavior.

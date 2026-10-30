---
id: TASK-204
title: "The session-record partial"
status: complete
parent: REQ-660
created: 2026-10-30
updated: 2026-10-30
dependencies: []
repo: adlc-toolkit
---

## Description

Replace the stub with the full contract under the same name, keeping the command body `adlc_session_record` unchanged (BR-5, BR-6, BR-7, BR-8, ADR-4, ADR-7).

## Files to Create/Modify

- `partials/session-record.sh` — thin sh function around one embedded Python program
- `partials/tests/hooks.test.sh` — revised body, generated ids, field args, path containment, resume, pruning, timing
- `tools/adlc/tests/test_session_record_table.py` — TABLE equals hook_payload
- `templates/hooks.yml` — comment only: no longer a stub
- `harness/claude/README.md` — describe the sidecar if it names the stub

## Acceptance Criteria

- [ ] Sidecar lines in order: harness, session_id, transcript_path, cwd, started_at; mode 600
- [ ] No `.adlc/` writes nothing; empty, non-JSON and id-less payloads exit 0, print nothing, and write at most a generated-id sidecar
- [ ] An unsafe session id (`../../etc`, `a/b`, `.gitignore`, `.`) is replaced by a generated id
- [ ] `transcript_path` outside `$HOME`, with `..`, or with a control character is recorded empty
- [ ] A re-fire keeps `started_at`; a 31-day-old sidecar is pruned and a newer one kept; `.gitignore` is never pruned
- [ ] `--harness X --field item=key` reads only named items; an invalid harness records `unknown`
- [ ] `adlc harness render --check` still passes: the command text is unchanged

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-5 | test-case | `partials/tests/hooks.test.sh::case_session_record_inert` | yes |
| BR-6 | test-case | `tools/adlc/tests/test_session_record_table.py::test_claude_row_equals_hook_payload` | yes |
| BR-7 | test-case | `partials/tests/hooks.test.sh::case_session_record_prunes` | yes |
| BR-8 | test-case | `tools/adlc/tests/test_session_record_table.py::test_rendered_command_names_the_partial` | no |
| AC-1 | test-case | `partials/tests/hooks.test.sh::case_session_record_writes` | yes |
| AC-2 | test-case | `partials/tests/hooks.test.sh::case_session_record_inert` | yes |
| AC-10 | test-case | `partials/tests/hooks.test.sh::case_session_record_harness_arg` | no |
| AC-13 | test-case | `partials/tests/hooks.test.sh::case_session_record_prunes` | yes |

## Technical Notes

Run as `command python3 -I -c "$_adlc_sr_prog" "$@" >/dev/null 2>&1 || true`, program in a single-quoted sh variable, so no single quote inside it. Guard in sh first: `[ -d .adlc ] || return 0`, `[ -L .adlc ] && return 0`, `command -v python3 >/dev/null 2>&1 || return 0`. Read stdin with `select` under a 2-second deadline and a 1 MiB cap. id regex `^[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}$`; else `"gen-" + os.urandom(8).hex()`. Detection: a row matches when `payload[row["transcript_path"]]` is a string containing `row["marker"]` and `payload[row["session_id"]]` is a string. `TABLE = {"claude": {"session_id": "session_id", "cwd": "cwd", "transcript_path": "transcript_path", "marker": "/.claude/projects/"}}` on one line. Unknown payloads read the claude keys. Write to `.tmp-<pid>` with `O_CREAT|O_EXCL|O_NOFOLLOW`, `fchmod` 0600, then `os.replace`. Refuse a symlinked `.adlc/.session`. Containment: `realpath(v)` under `realpath($HOME) + "/"`. Keep the in-directory `.gitignore` of `*` (ADR-7). Top-level `try/except BaseException: pass`. The file must stay `*.sh`, sourceable and silent, for plugin-sandbox `guard_partials`.

## Dependencies

None.

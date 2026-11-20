---
id: TASK-272
title: "`--arg-file` is opened from a handle on the working directory, with no check-then-open window"
status: draft
parent: REQ-719
repo: adlc-toolkit
created: 2026-11-20
updated: 2026-11-20
dependencies: []
---

## Description

Rewrite `fence_run.read_arg_file` as architecture ADR-4 describes. Its signature and its `Refusal` behaviour stay, so `parse_values` still turns every failure into exit 65.

## Files to Create/Modify

- `tools/adlc/fence_run.py` — `read_arg_file` only, plus the module-level seam it calls between component opens. Leave `run()` alone: TASK-273 owns it.
- `tools/adlc/tests/test_fence_arg_file.py` — new.
- `tools/adlc/tests/test_fence_run.py` — only `test_arg_file_bounds`, if an expectation in it changes.

## Acceptance Criteria

- [ ] Refused, with nothing bound: a symlink as the last component (also one that points inside the working directory), a symlink as a directory component, a `..` segment, an absolute path outside the working directory, a directory, a file over 1 MiB, bytes that are not UTF-8, an empty path, a NUL.
- [ ] A FIFO at the path is refused, and the call returns within two seconds.
- [ ] A plain file is read under a relative path, under an absolute path in the working directory's given spelling, and under one in its real spelling (a test whose working directory is reached through a symlinked parent).
- [ ] Through `fence-run run … --arg-file`, each refusal above is exit 65 with one `fence_run_bad_value:` line.
- [ ] Swap test: with the seam replaced by a function that renames a directory component away and puts a symlink to an outside directory in its place, the read is refused and no byte of the outside file is returned.
- [ ] No path is resolved and then opened: the function calls neither `os.path.realpath` on the file's path nor `open` on a path string for the file.
- [ ] `python3 -m pytest tools/adlc/tests/test_fence_arg_file.py tools/adlc/tests/test_fence_run.py` passes.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-15 | test-case | `tools/adlc/tests/test_fence_arg_file.py::test_req719_a_swapped_directory_leaks_nothing` | no |
| BR-16 | test-case | `tools/adlc/tests/test_fence_arg_file.py::test_req719_refused_paths_bind_nothing` | no |
| BR-16 | test-case | `tools/adlc/tests/test_fence_arg_file.py::test_req719_a_plain_file_is_read_under_each_spelling` | yes |
| AC-12 | test-case | `tools/adlc/tests/test_fence_arg_file.py::test_req719_a_fifo_is_refused_without_blocking` | no |
| AC-12 | test-case | `tools/adlc/tests/test_fence_arg_file.py::test_req719_a_plain_file_is_read_under_each_spelling` | yes |

## Technical Notes

- Standard library only, Python 3.9. `os.open(name, flags, dir_fd=fd)`, `os.fstat`, `stat.S_ISREG`, `os.read`. Close every descriptor on every path (`try/finally`).
- A symlink met with `O_NOFOLLOW` is `ELOOP` on macOS and may be `ENOTDIR` or `EMLINK` elsewhere: treat any `OSError` from a component open as a refusal, and name the component in the message.
- `realpath(cwd)` is used only to recognise the real spelling of the working directory as a text prefix (LESSON-844). The file's own path is cut to a relative one by text.
- Drop empty and `.` components after the split.
- Keep the message text of today's refusals where a test pins it (`test_arg_file_bounds` only checks the exception type).

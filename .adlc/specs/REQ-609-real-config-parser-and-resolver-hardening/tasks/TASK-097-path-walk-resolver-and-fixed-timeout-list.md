---
id: TASK-097
title: "The gate resolves adlc-read by walking $PATH and picks timeout from a fixed absolute list; proven under sh, bash, zsh"
status: complete
parent: REQ-609
created: 2026-09-01
updated: 2026-09-01
dependencies: []
---

## Description

Replace `_adlc_resolve_read_bin` in `partials/delegate-gate.sh` with a `$PATH` walk that never calls `command -v` (REQ BR-11, architecture ADR-3): iterate on `:` with parameter expansion, skip entries not beginning with `/`, take the first `dir/adlc-read` that is a regular executable file, then `$HOME/bin/adlc-read` only when `$HOME` begins with `/`. The result is always an absolute path or empty. Choose the `timeout` wrapper from a fixed absolute candidate list. Invoke both through `command`. Extend the shell harness with hijack, relative-entry, planted-`timeout`, and non-absolute-`HOME` sections, and make `run.sh` drive `/bin/sh` as well as `bash` and `zsh`.

## Files to Create/Modify

- `partials/delegate-gate.sh` — new `_adlc_resolve_read_bin`; new `_adlc_resolve_timeout`; both call sites use `command`; header comment no longer says "the bare name, when it is on PATH"
- `partials/tests/delegate-gate.test.sh` — new sections (i) walk resolves a real file on an absolute entry, (j) function + alias + hash-table entry named `adlc-read` under each shell → `2 no-binary` and the planted binary's marker file is never written, (k) relative and empty `$PATH` entries are skipped, (l) a planted `timeout` on `$PATH` is not invoked, (m) `HOME` without a leading `/` is ignored, (n) a zsh function named with the absolute path does not intercept
- `partials/tests/run.sh` — add `sh` to the shell loop (skip with notice if `/bin/sh` is absent, as zsh is today)
- `tools/delegate/tests/test_partials.py` — `test_delegate_gate_path_wins_over_home_bin` expects the absolute PATH hit, not the bare name (found at implementation: it pinned the contract BR-11 replaces)

## Acceptance Criteria

- [ ] `sh partials/tests/run.sh` passes under `bash`, `zsh`, and `/bin/sh`
- [ ] `grep -n 'command -v' partials/delegate-gate.sh` matches nothing
- [ ] With a shell function, an alias, and a hash-table entry (`hash -p`) each named `adlc-read` pointing at a planted binary, and no real `adlc-read` on an absolute `$PATH` entry, the gate returns `2` with reason `no-binary` in all three shells and the planted binary writes no marker
- [ ] With `PATH=relative/bin:/abs/bin` and `adlc-read` only under `relative/bin`, the resolver returns empty
- [ ] A `timeout` planted on `$PATH` is never executed (marker file absent); when a candidate from the fixed list exists it is the one used
- [ ] Sections (a)–(h) from REQ-603 still pass unchanged; the frozen fixture under `partials/tests/fixtures/` is not modified
- [ ] The new resolver is mutation-proven in a scratch copy: restoring `command -v`, dropping the `/*` case, and dropping the `-f` test each fail a section

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-11 | test-case | `partials/tests/delegate-gate.test.sh::(i) path-walk resolves real file` | yes |
| BR-11 | test-case | `partials/tests/delegate-gate.test.sh::(j) function alias hash cannot satisfy resolution` | yes |
| BR-11 | test-case | `partials/tests/delegate-gate.test.sh::(k) relative and empty PATH entries skipped` | yes |
| BR-11 | test-case | `partials/tests/delegate-gate.test.sh::(l) planted timeout never invoked` | yes |
| BR-11 | test-case | `partials/tests/delegate-gate.test.sh::(m) non-absolute HOME ignored` | yes |
| BR-16 | test-case | `partials/tests/run.sh (bash, zsh, sh)` | yes |
| AC-6 | test-case | `partials/tests/delegate-gate.test.sh::(j) function alias hash cannot satisfy resolution` | yes |
| AC-7 | test-case | `partials/tests/delegate-gate.test.sh::(l) planted timeout never invoked` | yes |
| AC-14 | test-case | `partials/tests/run.sh (bash, zsh, sh)` | yes |
| BR-11 | test-case | `tools/delegate/tests/test_partials.py::test_delegate_gate_path_wins_over_home_bin` | yes |

## Implementation notes (recorded at completion)

- Under `/bin/sh` (bash 3.2 in POSIX mode) the hijack that cannot be installed is the hyphenated function name, not `hash -p` as this task predicted; section (j) installs function + alias + hash where the shell allows and prints the installed set per shell.
- `_adlc_resolve_timeout` sets `$_timeout` rather than echoing, so the authorize path gains no second fork; the candidate list is one line so the harness can assert every entry is absolute.
- The harness's inner runs use the shell named by `run.sh` (`ADLC_TEST_SHELL`) so the walk is exercised under all three, not always `/bin/sh`.
- `test_partials.py::test_delegate_gate_path_wins_over_home_bin` needed two distinct directories to tell the arms apart (the helper's PATH stub lived under `$HOME/bin`).

## Technical Notes

- **Walk.**
  ```sh
  _adlc_resolve_read_bin() {
    _rest="${PATH:-}:"
    while [ -n "$_rest" ]; do
      _dir="${_rest%%:*}"; _rest="${_rest#*:}"
      case "$_dir" in /*) ;; *) continue ;; esac
      if [ -f "$_dir/adlc-read" ] && [ -x "$_dir/adlc-read" ]; then printf '%s\n' "$_dir/adlc-read"; return 0; fi
    done
    case "${HOME:-}" in /*) if [ -f "$HOME/bin/adlc-read" ] && [ -x "$HOME/bin/adlc-read" ]; then printf '%s\n' "$HOME/bin/adlc-read"; return 0; fi ;; esac
    printf '\n'; return 1
  }
  ```
  No arrays, no `IFS` change, no word-splitting (LESSON-329), no globs (LESSON-335). `unset _rest _dir` afterwards, as the gate does for its other locals.
- **Timeout.** `for _t in /usr/bin/timeout /opt/homebrew/bin/timeout /usr/local/bin/timeout /opt/homebrew/bin/gtimeout /usr/local/bin/gtimeout; do [ -f "$_t" ] && [ -x "$_t" ] && { ...; break; }; done`. A `for` over a literal list is safe in zsh.
- **Invocation.** `command "$_timeout" 10 "$ADLC_READ_BIN" --print-gate` and `command "$ADLC_READ_BIN" --print-gate`. Section (n) defines `function /abs/path/adlc-read` in zsh (zsh permits it) and asserts the real file is what ran.
- **Hijack section.** Build a sandbox with `$SANDBOX/planted/adlc-read` (writes `$SANDBOX/marker` and prints `1 ok`), then under each shell: `adlc-read() { "$SANDBOX/planted/adlc-read" "$@"; }`, `alias adlc-read=...` (with `shopt -s expand_aliases` in bash), `hash -p "$SANDBOX/planted/adlc-read" adlc-read`; `PATH="$SANDBOX/empty"`; source the gate; assert rc 2, reason `no-binary`, marker absent. Run each shell as `bash -c`, `zsh -c`, `/bin/sh -c` with the body in a heredoc file so quoting is identical.
- BSD `grep -E` has no `\b` (LESSON-013); the harness's assertions use fixed strings.
- **Do not touch `partials/tests/fixtures/`** — it is the parity baseline.

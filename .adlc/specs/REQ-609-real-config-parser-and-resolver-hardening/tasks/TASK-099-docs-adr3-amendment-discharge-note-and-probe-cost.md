---
id: TASK-099
title: "Docs to the new contract, REQ-515 ADR-3 amended, REQ-603 BR-14 discharged, probe cost measured"
status: complete
parent: REQ-609
created: 2026-09-01
updated: 2026-09-02
dependencies: [TASK-095, TASK-096, TASK-098]
---

## Description

Bring every document this REQ owns to the landed behaviour (REQ BR-14, BR-15), and pin the claims with a small pytest so they cannot drift back. Amend REQ-515 ADR-3 in that spec's architecture with the Description's reasoning; write the discharge note into REQ-603's BR-14 and into this REQ's architecture; update `tools/delegate/README.md`, `partials/delegate-gate.md`, `CHANGELOG.md`, `.adlc/context/architecture.md`, `.adlc/context/conventions.md`; measure the probe's cost before and after and record it in this REQ's Assumptions (AC-12). If `tools/delegate/claude-md-routing.txt` changes, regenerate its `.sha256` and verify pinned == computed.

## Files to Create/Modify

- `tools/delegate/README.md` — the `delegate:` schema (four keys, `enabled` bool only, unknown keys refuse), the 64 KiB cap, relative `$PATH` entries rejected, `--version`'s rc-file read, the PyYAML floor and the `dependency-missing` behaviour
- `partials/delegate-gate.md` — resolver contract: absolute path or empty, never a bare name; the fixed `timeout` list; the call-site refusal shape (skills exit non-zero; the pre-pass agent degrades — see TASK-098's notes); line ~131 still says `"${ADLC_READ_BIN:-adlc-read}"` and must go
- `CHANGELOG.md` — REQ-609 entry naming the behaviour changes and the parity divergences registered in TASK-095
- `.adlc/context/architecture.md` — the paragraph proposed in this REQ's architecture
- `.adlc/context/conventions.md` — delegation pattern without the bare-name fallback; mention `read-bin-fallback`
- `.adlc/specs/REQ-515-provider-agnostic-delegation/architecture.md` — ADR-3 amendment block dated 2026-09-01 citing REQ-609
- `.adlc/specs/REQ-603-single-source-delegation-opt-in-predicate/requirement.md` — BR-14 discharge note (one sentence, keep the history)
- `.adlc/specs/REQ-609-real-config-parser-and-resolver-hardening/requirement.md` — Assumptions: the measured probe cost before/after (median of 20 runs of `adlc-read --print-gate`)
- `tools/delegate/tests/test_unparseable_config_reports_shipped_defaults.py` or wherever `test_unparseable_config_reports_shipped_defaults` lives — drop the "fail-SOFT is deliberate" header, keep the test with its new expectation
- `tools/delegate/tests/test_req609_docs.py` — new: the doc-contract cases under Verification
- `tools/lint-skills/tests/test_read_bin_fences.py` — delete the `AC8_TASK_099_RESIDUALS` waiver entry for `partials/delegate-gate.md:131` once that paragraph is rewritten (the test asserts exact equality and will go red until you do)
- `tools/delegate/claude-md-routing.txt` + `.sha256` — only if the routing text changes

## Acceptance Criteria

- [ ] `grep -rn "bare name" partials/delegate-gate.sh partials/delegate-gate.md` matches only lines saying it is rejected
- [ ] REQ-515's architecture carries an `ADR-3 amendment (REQ-609)` block; REQ-603 BR-14 says "discharged by REQ-609" with the PR reference once known
- [ ] This REQ's Assumptions record the probe cost before and after, with the command used
- [ ] `install.sh`'s routing hash check passes (pinned == computed) after any routing-text change
- [ ] `python3 -m pytest tools -q` and `sh partials/tests/run.sh` green; `tools/lint-skills/check.sh` scans from outside `.worktrees`

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-14 | test-case | `tools/delegate/tests/test_req609_docs.py::test_req515_adr3_amended` | no |
| BR-14 | test-case | `tools/delegate/tests/test_req609_docs.py::test_req603_br14_discharged` | no |
| BR-15 | test-case | `tools/delegate/tests/test_req609_docs.py::test_bare_name_only_rejected` | yes |
| BR-15 | test-case | `tools/delegate/tests/test_req609_docs.py::test_readme_names_cap_relative_path_and_version_rc_read` | no |
| BR-15 | test-case | `tools/delegate/tests/test_req609_docs.py::test_shipped_defaults_header_no_longer_says_fail_soft` | no |
| BR-1 | test-case | `tools/delegate/tests/test_req609_docs.py::test_assumptions_record_probe_cost` | no |
| BR-7 | test-case | `tools/delegate/tests/test_req609_docs.py::test_readme_keys_match_schema_constant` | yes |
| AC-10 | test-case | `tools/delegate/tests/test_req609_docs.py::test_req515_adr3_amended` | no |
| AC-11 | test-case | `tools/delegate/tests/test_req609_docs.py::test_bare_name_only_rejected` | yes |
| AC-12 | test-case | `tools/delegate/tests/test_req609_docs.py::test_assumptions_record_probe_cost` | no |

## Implementation notes (recorded at completion)

- **The ADR-3 amendment is dated 2026-09-02**, not the 2026-09-01 the Files list guessed — the task landed the following day and a dated block that lies about its date is exactly the drift the block exists to prevent.
- **The probe cost is `+4.3 ms`, not "roughly thirty".** `--print-gate` went from a 21.2 ms median (min 20.6) on `main` `e70a1f1` to 25.5 ms (min 25.0) on this branch; `--help` is unchanged at 21.6 → 19.5 ms (the sign is noise, and it never reaches the loader — BR-1). Measured with `time.perf_counter()` around `subprocess.run`, 20 runs each, **through `~/.claude/delegate-venv/bin/python3` directly**: `~/bin/adlc-read` `exec`s the primary checkout, which is still on `main`, so the wrapper would have measured the *before* code twice. The after figure includes the import **and** the strict parse of the reference machine's real config.
- **`tools/delegate/claude-md-routing.txt` was NOT changed** — nothing in it is made wrong by this REQ (it names the opt-in *enablers* and the precedence order, both unchanged) — so the `.sha256` was not regenerated. Verified pinned == computed by install.sh's own method (trailing newlines collapsed to one).
- **BR-15's "`--version`'s rc-file read" is documented as measured, not as written.** `--version` does *not* read the rc file: `_read_key_from_rc` is reached only from `resolve_key`, which is on the real call's path and therefore on `--print-gate`'s. The README documents the read, its 256 KiB cap and its descriptor-based open under the resolver, and names the asymmetry it creates — `--print-gate` can report `0 disabled-via-config` on a machine where `--version` prints `enabled: true`, verified by hand on a temp `HOME`.
- **`test_unparseable_config_reports_shipped_defaults` already passed** under the new loader; only the framing was wrong. It gained one assertion (`enabled: false`) so the docstring's fail-closed claim is asserted rather than asserted-about.
- Two positive controls back the exclusion tests (LESSON-602): `test_bare_name_checker_flags_the_retired_sentence` plants the sentence the doc used to carry, and `test_schema_table_parser_notices_a_missing_key` plants a table missing a key. `test_probe_cost_parser_needs_both_numbers` is the third.
- The `AC8_TASK_099_RESIDUALS` waiver is now `set()`; its comment and the assertion's guidance were rewritten too, since a waiver that is empty but still tells the reader to "delete the matching entry" is the guard rot LESSON-019 names.

## Technical Notes

- `test_readme_keys_match_schema_constant` imports `DELEGATE_KEYS` from `_machine_config` and parses the README's schema table — the LESSON-331 structural pin that keeps the closed schema and its documentation equal.
- The "bare name" grep test reads both files and asserts every matching line also contains `reject` or `never` (case-insensitive, fixed strings — no `\b`, LESSON-013).
- Probe cost: `for i in $(seq 20); do /usr/bin/time -p adlc-read --print-gate; done` on `main` before and on the branch after, in the same shell; record medians in milliseconds and the machine. Under REQ-603's 104-second median delegated step, tens of milliseconds is noise; say so with the numbers.
- The ADR-3 amendment keeps the original text and appends a dated block; do not rewrite history.
- Regenerate the hash with `shasum -a 256 tools/delegate/claude-md-routing.txt | awk '{print $1}' > tools/delegate/claude-md-routing.txt.sha256` only if the text changed, then assert pinned == computed.

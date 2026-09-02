---
id: TASK-094
title: "One config loader by descriptor, PyYAML behind a strict schema, adapters in _common"
status: complete
parent: REQ-609
created: 2026-09-01
updated: 2026-09-02
dependencies: []
---

## Description

Create `tools/delegate/_machine_config.py` — the single loader for `~/.claude/adlc/config.yml` — and make `_common.parse_delegate_config` a thin adapter over it. The loader opens by descriptor (`O_RDONLY | O_NONBLOCK`), decides the kind on `fstat`, reads under the 64 KiB cap, decodes strictly, parses with `yaml.safe_load` through a duplicate-key-refusing `SafeLoader` subclass, and returns a `ConfigOutcome(kind, document, reason, path)` with `kind ∈ {absent, parsed, malformed}` that never raises (architecture ADR-1). The adapter validates the `delegate` section against the strict schema and keeps the `{}` / `{_MALFORMED: True, ...}` return convention so `delegation_enabled()` and `resolve_gate_verdict()` are untouched. The rc-file key reader reuses the same descriptor-based open helper (BR-5). `require_delegation_enabled` gains the malformed branch that names the path and the condition (BR-13). PyYAML is pinned in `requirements.txt` and imported lazily inside the loader (BR-1, BR-9).

Tests first, in a scratch copy for mutations (never in the shared worktree while agents read it).

## Files to Create/Modify

- `tools/delegate/_machine_config.py` — new: `_open_regular(path)`, `_read_capped(fd)`, `_StrictLoader` (duplicate-key refusal with the second mark's line), `load_machine_config(path=None) -> ConfigOutcome`, `validate_delegate_section(document)`, `DELEGATE_KEYS` constant, `CONFIG_CAP_BYTES = 65536`, `dependency_missing_line()` for the one stderr line
- `tools/delegate/_common.py` — `parse_delegate_config` becomes the adapter (keeps signature, `_MALFORMED`, adds `_MALFORMED_REASON`, `_MALFORMED_PATH`); `_read_key_from_rc` opens through `_open_regular`; `require_delegation_enabled` malformed branch; no other cascade change
- `tools/delegate/requirements.txt` — add `pyyaml>=6.0` (pin the tested version with `==` per the existing style, and note the floor in the README task)
- `tools/delegate/tests/config_corpus.py` — new: the seeded corpus, one named entry per shape in REQ AC-1, each with the outcome the System Model specifies; importable by TASK-095 and by the shell tests
- `tools/delegate/tests/test_machine_config.py` — new: the tests listed under Verification
- `tools/delegate/tests/test_print_gate.py` — rewrite (do not delete) the assertions that encode the pre-existing fail-opens: absent config still reads `{}`; a directory, `/dev/null`, a comment-headed block now resolve as the System Model says
- `tools/delegate/tests/test_common.py` — rc-reader cases for the descriptor-based open
- `tools/delegate/tests/_child_env.py` — new (found at implementation): a child interpreter with a redirected `HOME` loses a user-site PyYAML (the system `python3` case), so tests that spawn the CLIs put a symlink to the parent's `yaml` package on the child's `PYTHONPATH`; the venv wrapper is unaffected in production
- `tools/delegate/tests/test_resolve_provider.py`, `tools/delegate/tests/test_version.py` — child env through the helper; the fake-checkout copy list gains `_machine_config.py`
- `tools/delegate/tests/test_pre_req_gate_parity.py` — minimal: child env through the helper, and the two "both grant" known-limitation rows flipped to REQ-609's outcomes; TASK-095 registers them as named divergences

## Acceptance Criteria

- [ ] `load_machine_config` returns exactly one of the three kinds for every corpus entry and never raises; `python3 -m pytest tools/delegate -q` green
- [ ] A repeated key anywhere in the document is `malformed` with reason `duplicate-key` and a line number; distinct keys parse
- [ ] A null document (empty, comments only) is `parsed` with `document == {}`; a list or scalar top level is `malformed`
- [ ] Directory, fifo, `/dev/null`, dangling symlink, unreadable parent, NUL in path, undecodable bytes, over-cap file are each `malformed`; ENOENT with `lexists` false is `absent`
- [ ] `validate_delegate_section` refuses a non-mapping, a non-bool `enabled` (including the string `"false"`), non-string `model`/`base_url`/`api_key_env`, any unknown key, any nested mapping or sequence; accepts a well-formed section; absent section → `{}`
- [ ] With a poisoned `yaml` module on `PYTHONPATH` that raises `ImportError`, `--print-gate` prints `0 disabled-via-config` and stderr names PyYAML once; `--help` exits 0 without importing it
- [ ] `require_delegation_enabled` on a malformed config names the path and the reason and does not mention `ADLC_DELEGATE_ENABLED`
- [ ] A fifo at the config path and at an rc-file path returns `malformed` / skipped in under one second (thread + flag, not a timeout exception — `TimeoutError` is an `OSError` and would be swallowed)
- [ ] Every new branch is mutation-proven in a scratch copy: swapping the `lexists` check, dropping the cap, removing the duplicate-key override, and accepting `str` for `enabled` each fail at least one test; the mutation list goes in the commit body

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `tools/delegate/tests/test_machine_config.py::test_help_does_not_import_yaml` | yes |
| BR-1 | test-case | `tools/delegate/tests/test_machine_config.py::test_requirements_pin_pyyaml` | no |
| BR-2 | test-case | `tools/delegate/tests/test_machine_config.py::test_duplicate_key_is_malformed_with_line` | yes |
| BR-3 | test-case | `tools/delegate/tests/test_machine_config.py::test_outcome_is_three_state_and_never_raises` | yes |
| BR-3 | test-case | `tools/delegate/tests/test_machine_config.py::test_null_document_is_parsed_empty` | yes |
| BR-4 | test-case | `tools/delegate/tests/test_machine_config.py::test_non_regular_file_is_malformed` | yes |
| BR-5 | test-case | `tools/delegate/tests/test_machine_config.py::test_fifo_returns_malformed_within_one_second` | yes |
| BR-5 | test-case | `tools/delegate/tests/test_common.py::test_rc_reader_opens_by_descriptor_and_skips_fifo` | yes |
| BR-6 | test-case | `tools/delegate/tests/test_machine_config.py::test_absent_section_is_unconfigured` | yes |
| BR-7 | test-case | `tools/delegate/tests/test_machine_config.py::test_schema_refuses` | yes |
| BR-9 | test-case | `tools/delegate/tests/test_machine_config.py::test_missing_pyyaml_refuses_and_names_package` | yes |
| BR-13 | test-case | `tools/delegate/tests/test_machine_config.py::test_refusal_names_path_and_condition` | yes |
| AC-1 | test-case | `tools/delegate/tests/test_machine_config.py::test_seeded_corpus_three_surfaces` | yes |
| AC-3 | test-case | `tools/delegate/tests/test_machine_config.py::test_missing_pyyaml_refuses_and_names_package` | yes |
| AC-4 | test-case | `tools/delegate/tests/test_machine_config.py::test_duplicate_key_is_malformed_with_line` | yes |
| AC-9 | test-case | `tools/delegate/tests/test_machine_config.py::test_refusal_names_path_and_condition` | yes |
| AC-12 | test-case | `tools/delegate/tests/test_machine_config.py::test_help_does_not_import_yaml` | yes |
| AC-13 | test-case | `tools/delegate/tests/test_machine_config.py::test_fifo_returns_malformed_within_one_second` | yes |

## Implementation notes (recorded at completion)

- The implementing agent stalled during its mutation re-runs (whole-suite runs under CPU contention exceeded the tool's time limit); the orchestrator verified its work, applied the helper to the parity test it was not allowed to edit, re-ran the four required mutations against the targeted test files in a scratch copy, and committed. Mutation results are in the commit body.
- PyYAML is pinned `pyyaml==6.0.3` (the tested version); the README task records the `>=6.0` floor.
- The rc-file reader keeps `errors="replace"`; its cap is 256 KiB (`RC_CAP_BYTES`), separate from the 64 KiB config cap.

## Technical Notes

- **Open, then decide.** `fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)`; `st = os.fstat(fd)`; `stat.S_ISREG(st.st_mode)` or close and return `malformed/not-regular-file`. `os.open` on a directory succeeds on macOS and Linux — the `fstat` is what rejects it. A fifo with no writer opens immediately under `O_NONBLOCK`. Wrap the fd in `os.fdopen(fd, "rb")` and read `CAP + 1` bytes; more than `CAP` is `over-cap`.
- **Absent vs dangling.** On `FileNotFoundError`/`NotADirectoryError`: `absent` iff `not os.path.lexists(path)`; else `malformed/dangling-symlink`. `PermissionError` on the parent is `unreadable`. `ValueError` (embedded NUL) is `malformed`.
- **Decode.** `data.decode("utf-8")` strict; strip one leading `﻿`. `UnicodeDecodeError` → `undecodable`.
- **Loader.** Subclass `yaml.SafeLoader`; in `construct_mapping(node, deep=False)` call `self.flatten_mapping(node)`, then walk `node.value`, `self.construct_object(key_node, deep=True)`, keep a `seen` set, and on a repeat raise `yaml.constructor.ConstructorError("while constructing a mapping", node.start_mark, f"found duplicate key {key!r}", key_node.start_mark)`. Map `yaml.YAMLError` → `yaml-error`, the duplicate case → `duplicate-key` (check `isinstance` and the message, or raise your own subclass).
- **Reason strings carry no file content.** Key names in the duplicate message are allowed (they are the operator's own keys, needed to fix the file); values never are.
- **Lazy import.** `import yaml` inside `load_machine_config`, after the file has been read, so a config-less `--version` and `--help` never pay for it. `ImportError` → `malformed/dependency-missing` + `sys.stderr.write("adlc: PyYAML is not importable in <sys.executable>; run install.sh --with-delegation\n")` once per process (module-level flag).
- **Schema.** `DELEGATE_KEYS = frozenset({"enabled", "model", "base_url", "api_key_env"})`. `isinstance(v, bool)` for `enabled` — note `bool` is a subclass of `int`, so check `bool` first and refuse `int`. PyYAML 1.1 booleans (`yes`/`no`/`on`/`off`) arrive as `bool` and are accepted per the REQ's assumption. `api_key_env` keeps the existing name-shape regex and the key-shaped-value refusal already in `_common`.
- **Adapter.** `parse_delegate_config(path=None)`: outcome `absent` → `{}`; `parsed` → `validate_delegate_section(doc)` (schema error → `{_MALFORMED: True, _MALFORMED_REASON: "schema: ...", _MALFORMED_PATH: path}`); `malformed` → the same shape with the loader's reason. Existing consumers only test `cfg.get(_MALFORMED) is True`.
- **Poisoned module test.** Write `tmp_path/yaml/__init__.py` containing `raise ImportError("poisoned")` and run the CLI with `PYTHONPATH=tmp_path`; for the laziness test make it `raise RuntimeError` so an accidental import fails loudly rather than being caught as ImportError.
- **Fifo test.** `os.mkfifo`; run the reader in a `threading.Thread`; `join(1.0)`; assert the thread finished and the result is `malformed`. Do not use `signal.alarm`.
- **Mutation testing only in a scratch copy**: `cp -R tools partials VERSION <scratch>/` and run pytest there.

---
id: TASK-040
title: "Automated test fixtures for partials/*.sh"
status: complete
parent: REQ-426
created: 2026-05-15
updated: 2026-05-15
dependencies: []
---

## Description

Resolve REQ-426 BR-4, BR-5, BR-6 (ADR-4). Add a pytest test module that
exercises both partials via `subprocess.run`, replacing the one-shot
manual verification checks from REQ-416's verification.md with a
reproducible regression harness.

**Note on parallelism with TASK-038**: TASK-038 adds the
`ADLC_KIMI_GATE_REASON` export. This task's `test_kimi_gate_*` tests
assert on that variable, so this task is logically downstream of
TASK-038. But the test file can be drafted in parallel and the assertions
written against the TASK-038 contract — they merge cleanly because
TASK-038 only changes `partials/kimi-gate.sh` and TASK-040 only adds a
new test file. If TASK-040 runs first by chance, its tests fail until
TASK-038 lands; that's the desired ordering anyway.

## Files to Create/Modify

- `tools/kimi/tests/test_partials.py` — NEW. Pytest module with 7 tests:

  ```python
  # ethos-include.sh tests
  def test_ethos_consumer_precedence(tmp_path):
      # write .adlc/ETHOS.md with "LOCAL ETHOS", run partial, assert stdout==that
  def test_ethos_toolkit_fallback(tmp_path):
      # no .adlc/ETHOS.md, but ~/.claude/skills/ETHOS.md present (use HOME=mocked)
      # assert stdout matches the toolkit ETHOS
  def test_ethos_empty_consumer_falls_back(tmp_path):
      # touch .adlc/ETHOS.md (empty file), assert toolkit fallback fires
  def test_ethos_no_source(tmp_path):
      # both sources absent (HOME points at empty dir), assert "No ethos found"

  # kimi-gate.sh tests
  def test_kimi_gate_available(tmp_path):
      # ask-kimi on PATH, no ADLC_DISABLE_KIMI → return 0, REASON=ok
  def test_kimi_gate_disabled(tmp_path):
      # ADLC_DISABLE_KIMI=1 → return 1, REASON=disabled-via-env
  def test_kimi_gate_unavailable(tmp_path):
      # ask-kimi NOT on PATH → return 2, REASON=no-binary
  ```

  Use `subprocess.run(['sh', '-c', ...], env=..., cwd=..., capture_output=True, text=True)`.
  Locate the partials via a `PARTIALS_DIR` fixture that resolves from the
  repo root using `git rev-parse --show-toplevel`.

- `tools/kimi/tests/conftest.py` — MODIFIED if it exists, else NEW. Add
  `partials_dir` fixture returning the absolute path to `partials/` for
  tests to source. If the existing conftest has shared fixtures, append;
  do not replace.

## Acceptance Criteria

- [ ] `tools/kimi/tests/test_partials.py` exists with the 7 tests above.
- [ ] Running `pytest tools/kimi/tests/ -v` includes the partials tests
      in its output. They all pass against the post-TASK-038 partials
      behavior (export of `ADLC_KIMI_GATE_REASON`).
- [ ] Test fixtures use `tmp_path` for sandbox isolation — no test leaks
      files into the working tree or `~/`.
- [ ] The `test_ethos_empty_consumer_falls_back` case is the explicit
      regression test for REQ-416 verify finding H1.
- [ ] Total pytest suite count grows from 46 to 53 (= 46 + 7).
- [ ] Tests are deterministic — no `sleep`-based polling, no real
      `ask-kimi` invocation (mock or restrict PATH).

## Technical Notes

- For `test_kimi_gate_unavailable`, set `env={'PATH': '/usr/bin'}` to
  exclude `~/bin` where `ask-kimi` lives. Alternatively, use a `tmp_path`
  PATH with only `/bin` and `/usr/bin`.
- For `test_kimi_gate_available`, the test environment must have
  `ask-kimi` on PATH. Skip the test with `pytest.skip` if not present —
  the test asserts return code 0, which requires `ask-kimi` to exist.
  Document this as a soft prerequisite in the test docstring.
- Subprocess invocation idiom for sourceable partial:
  ```python
  r = subprocess.run(
      ['sh', '-c', f'. {partials_dir}/kimi-gate.sh; adlc_kimi_gate_check; '
                   'echo "RC=$?"; echo "REASON=$ADLC_KIMI_GATE_REASON"'],
      env={...}, capture_output=True, text=True
  )
  assert 'RC=0' in r.stdout
  assert 'REASON=ok' in r.stdout
  ```
- Use the existing pytest fixtures (`tmp_path`) and idioms. Do not pull
  in `pytest-subprocess` or another plugin.

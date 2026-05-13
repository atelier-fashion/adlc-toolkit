---
id: REQ-413
title: "Kimi tools hardening: offline test suite, base64 filter, exfiltration notice"
status: draft
deployable: false
created: 2026-05-13
updated: 2026-05-13
component: "tools/kimi"
domain: "developer-experience"
stack: ["python", "pytest"]
concerns: ["testing", "security", "privacy"]
tags: ["kimi", "tests", "base64", "exfiltration", "extract-chat", "pack-corpus", "follow-up"]
---

## Description

REQ-412 shipped the Kimi K2.5 delegation tooling (`tools/kimi/`) and is live and verified
end-to-end. Three optional follow-ups were deliberately deferred from REQ-412 and noted in
its PR / ship summary. This REQ delivers them:

1. **Offline pytest smoke suite** under `tools/kimi/tests/` covering the key-free, deterministic
   logic — `extract-chat` JSONL parsing (`_iter_turns`, `_extract_text_from_content`,
   `_looks_binary`) and `kimi-write._strip_fences`. These are exactly the regression-prone
   functions where a 30-line fixture catches drift without any live dependency.
2. **`extract-chat` base64 filter** — also drop content blocks whose string body is a long
   base64 run that lacks the `data:` URI prefix. The current filter only catches `type == "image"`
   blocks and `data:`-prefixed strings; some Claude Code transcript shapes embed raw base64.
3. **In-band data-exfiltration notice in `ask-kimi` / `kimi-write`** — print a one-line stderr
   notice when the tool sends file contents to Moonshot, with a `--no-warn` suppression flag and
   a `KIMI_NO_WARN=1` env override for repeated use. Also: change `_common.pack_corpus` to
   transmit `basename(path)` (or a caller-supplied label) instead of the full filesystem path,
   so home-directory structure and project names don't leak as request metadata.

This REQ continues to follow the `tools/` carve-out established in REQ-412 (executable code in
an otherwise markdown-only repo is permitted under `tools/<name>/` with its own README — see
LESSON-006). It adds a `tools/kimi/tests/` subdirectory which is the first formal test surface
in this repo; conventions and the tools/ carve-out note may need a small amendment to
acknowledge that (informed by LESSON-006).

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| pytest test module | path | string (path) | under `tools/kimi/tests/`, filenames `test_*.py` |
| test fixture | content | string / dict | inline literals or small files in `tools/kimi/tests/fixtures/` |
| ask-kimi flag | `--no-warn` | bool | suppresses the exfiltration notice for this invocation |
| ask-kimi env | `KIMI_NO_WARN` | string ("1"/unset) | global suppression for repeated use |
| kimi-write flag | `--no-warn` | bool | same as ask-kimi |
| pack_corpus input | label per path | string | defaults to `os.path.basename(path)`; tests assert no leak of the full path string |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| pytest run | `pytest tools/kimi/tests/` from a venv with pytest installed | green/red summary |
| exfiltration notice emit | `ask-kimi`/`kimi-write` invoked without suppression | one-line stderr message naming Moonshot as destination |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| run the test suite | any developer (no key required) |
| suppress the notice | the invoking user (per-call `--no-warn` or via `KIMI_NO_WARN`) |

## Business Rules

- [ ] BR-1: All new tests MUST be runnable offline — no live `MOONSHOT_API_KEY`, no network. Live-API
      tests remain manual per REQ-412.
- [ ] BR-2: The test suite MUST cover at minimum: a malformed JSONL line is skipped without crashing;
      `tool_use` / `tool_result` / `type:image` / `data:`-prefixed blocks are excluded from output;
      a raw long base64 string (no `data:` prefix) is excluded; `_strip_fences` correctly handles
      no-fence, plain `` ``` `` fences, language-tagged fences, and a closing fence with a trailing
      language tag.
- [ ] BR-3: The base64 filter MUST classify a content string as binary when it is ≥ a documented
      length threshold AND consists entirely of base64-alphabet characters (`A–Z a–z 0–9 + / =`),
      with a minimum length chosen high enough that prose is not false-positively filtered
      (e.g., ≥ 512 chars). The threshold MUST be a named constant in the module, not a magic
      number scattered through the code (informed by LESSON-006 — fail loud, named knobs).
- [ ] BR-4: The exfiltration notice MUST go to stderr, MUST name Moonshot as the destination, MUST
      NOT print the contents being sent, MUST NOT print the API key, and MUST be suppressible via
      `--no-warn` or `KIMI_NO_WARN=1`. The notice MUST NOT be emitted by `extract-chat` (no API
      call). (informed by LESSON-006)
- [ ] BR-5: `pack_corpus` MUST embed only `os.path.basename(path)` (or a caller-supplied label) in the
      `<file path='…'>` tag sent to Moonshot — never the full filesystem path. Internal Python
      tracebacks and `SystemExit` messages may still use the full path for actionability.
- [ ] BR-6: Pytest MUST be installed into the existing `~/.claude/kimi-venv` by `install.sh` so the
      suite can run without a separate venv. `install.sh` MUST remain idempotent (no duplicate pip
      installs on re-run — `pip install --upgrade` is the existing pattern; reuse it).
- [ ] BR-7: No changes to public CLI interfaces other than the additive `--no-warn` flag. Existing
      `ask-kimi` / `kimi-write` invocations from REQ-412 MUST continue to work unchanged.
- [ ] BR-8: The full test suite MUST execute in under 5 seconds on a stock developer machine — these
      are pure-Python deterministic tests.

## Acceptance Criteria

- [ ] `pytest tools/kimi/tests/ -q` (using `~/.claude/kimi-venv/bin/python3 -m pytest`) reports all
      tests passing with at least 8 distinct test cases across `extract-chat` and `_strip_fences`.
- [ ] A test case asserts that a raw base64 string (≥ threshold length, no `data:` prefix) is
      excluded from `extract-chat` output.
- [ ] A test case asserts that a malformed JSONL line in the middle of a transcript is skipped and
      surrounding valid lines still emit.
- [ ] A test case asserts that `_strip_fences` handles all four cases (no-fence, plain fences,
      language-tagged open, language-tagged close).
- [ ] A test case asserts that `pack_corpus` produces a `<file path='…'>` block whose `path`
      attribute is exactly the basename — full path absent from the corpus string.
- [ ] Running `ask-kimi` against any non-empty `--paths` prints a one-line stderr notice naming
      Moonshot; running with `--no-warn` (or `KIMI_NO_WARN=1`) does not. Same for `kimi-write`.
- [ ] `extract-chat` does NOT emit the exfiltration notice (it makes no API call).
- [ ] Re-running `install.sh` after this REQ does not duplicate pip installs or PATH/CLAUDE.md/
      settings.json entries — idempotency preserved.
- [ ] All REQ-412 acceptance criteria continue to pass (regression check on the live API path: one
      `ask-kimi` smoke run still returns a coherent summary).

## External Dependencies

- **pytest** — added to `~/.claude/kimi-venv` by `install.sh`. No specific minimum version required;
  current pytest releases are fine.

## Assumptions

- The base64 detection threshold (proposed ≥ 512 chars, base64 alphabet only) is tight enough to
  avoid false positives on normal prose / code. To be validated by an explicit test case using a
  500-char-of-letters non-base64 string vs. a 600-char real base64 string.
- Stderr is the right channel for the exfiltration notice (doesn't pollute the stdout pipeline
  that feeds `ask-kimi`'s output back into Claude).
- The `tools/` carve-out (REQ-412 ADR-1) extends naturally to `tools/<name>/tests/`. The
  `conventions.md` note may need a small amendment to confirm tests under `tools/` are permitted
  (the "code is markdown, no test runner" rule is already carved out for `tools/`).
- Users who pipe `extract-chat` into `ask-kimi` are content with the basename-only path in the
  corpus tag (downstream prompts already pass paths via the question text when ordering matters).

## Open Questions

- [ ] OQ-1: Exact base64 threshold length and minimum prose-safety case — confirm 512 chars is the
      right floor, or whether to raise/lower based on real transcript samples.
- [ ] OQ-2: Should `--no-warn` also be honored for piped (`!sys.stderr.isatty()`) invocations
      automatically, or is explicit opt-in (flag/env) the right default? Recommend explicit opt-in.
- [ ] OQ-3: Should the suite include a tiny `conftest.py` smoke fixture that points to a synthetic
      JSONL file in `tools/kimi/tests/fixtures/`, or inline literals only? Recommend inline.
- [ ] OQ-4: Should the basename change in `pack_corpus` be configurable (e.g., `--full-paths` flag
      on `ask-kimi`) for power users who want absolute paths in the corpus tag? Recommend no —
      keep the privacy default sticky.

## Out of Scope

- Wiring delegation into ADLC skills (`/spec` Step 1.6 retrieval, `/architect` context-reading,
  `/analyze`, `/wrapup` Step 4 knowledge capture) — that is a larger separate REQ (the
  "ADLC-skill-wiring follow-up" referenced in the REQ-412 ship summary). Touching those skills
  is a fundamentally different change surface from the hardening here.
- Switching to a different worker model (Kimi K2.6, K2-thinking, DeepSeek, Gemini Flash) — already
  overridable via `KIMI_MODEL` / `--model`; no API change needed.
- Adding a `kimi-write --dry-run` or `--diff` mode.
- A `tools/kimi/tests/` CI runner — this repo has no CI; tests run on demand. A future REQ could
  wire pytest into a lightweight GitHub Action if/when the repo adopts CI.
- Replacing the `~/bin` wrapper approach with an entry-point install.
- Changing the wire format of the corpus block beyond the path-attribute basename change.

## Retrieved Context

- LESSON-006 (lesson, score 4): Executable code in a markdown-only repo needs a documented
  tools/ carve-out; installers that mutate user config must fail loud and write atomically.

REQ-412 (`status: complete`) is the direct parent of this REQ and is referenced throughout, but is
outside the Step 1.6 retrieval status filter (`approved` / `in-progress` / `deployed` only). No
other tagged documents matched this area.

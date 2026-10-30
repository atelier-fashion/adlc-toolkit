---
id: TASK-203
title: "extract-chat --format and the record-type filter"
status: complete
parent: REQ-660
created: 2026-10-30
updated: 2026-10-30
dependencies: ['TASK-202']
repo: adlc-toolkit
---

## Description

Add `--format`, refuse unproven formats, and drop harness-internal records by `type` (BR-10, ADR-5, ADR-6).

## Files to Create/Modify

- `tools/delegate/extract-chat` — `--format` with choices, default claude; `_PARSERS`; record-type filter
- `tools/delegate/tests/test_extract_chat.py` — golden, negative, refusal and record-type tests
- `tools/delegate/README.md` — document `--format`

## Acceptance Criteria

- [ ] Omitting `--format` is byte-identical on the fixture, and every pre-existing test passes
- [ ] `--format bogus` exits non-zero naming the accepted values
- [ ] Each of codex, copilot, gemini, cursor exits non-zero, prints one stderr line and creates no `-o` file
- [ ] A record with `type: api-request-blob` and a user-role `message` produces no output; a record with no `type` still parses

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-10 | test-case | `tools/delegate/tests/test_extract_chat.py::test_unproven_formats_refuse` | yes |
| BR-12 | test-case | `tools/delegate/tests/test_extract_chat.py::test_claude_golden_explicit_format` | no |
| AC-7 | test-case | `tools/delegate/tests/test_extract_chat.py::test_format_bogus_names_values` | no |
| AC-8 | test-case | `tools/delegate/tests/test_extract_chat.py::test_claude_output_has_no_tool_markers` | no |

## Technical Notes

Add `--format` to both `_VERSION_VALUE_FLAGS` and `_KNOWN_FLAGS`; `test_version.py` holds the second equal to the parser. Refuse before opening the input. Parser table: `_PARSERS = {"claude": _iter_turns}`; `FORMATS` is the five names. Filter at the top of the record loop: `rtype = record.get("type"); if rtype is not None and rtype not in ("user", "assistant"): continue`.

## Dependencies

TASK-202

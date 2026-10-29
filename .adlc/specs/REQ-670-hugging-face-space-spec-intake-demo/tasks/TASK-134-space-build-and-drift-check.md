---
id: TASK-134
title: "Space build step: generate toolkit-data.js from the toolkit, with a --check drift gate"
status: draft
parent: REQ-670
created: 2026-10-29
updated: 2026-10-29
dependencies: []
repo: adlc-toolkit
---

## Description

Add the markers that delimit `/spec` intake's gap rules, and a zero-dependency Node
build script that reads every toolkit-owned input the Space needs and writes them
into one generated file. `--check` regenerates in memory and fails on any drift
(architecture ADR-3).

## Files to Create/Modify

- `spec/SKILL.md` — wrap Step 1.4 items 4–5 (the gap rules: specific question, the blocking/assumption table, the one-sentence justification) and the non-interactive disposition paragraph in `<!-- intake-gap-rules -->` / `<!-- /intake-gap-rules -->` markers, indented to sit inside the list. No wording change.
- `space/build.mjs` — reads `templates/requirement-template.md`, the marked block of `spec/SKILL.md`, `partials/intake.sh` (segment lines, max segments, redaction regex, section exclusions), the two `claude plugin` install lines in `README.md`, and `VERSION`; writes `space/toolkit-data.js`. `--check` exits 1 naming each differing field; a missing marker, constant or install line exits 2 with the reason.
- `space/toolkit-data.js` — generated output, committed. Header comment says it is generated and how to regenerate.
- `space/tests/build.test.js` — node:test cases.

## Acceptance Criteria

- [ ] `node space/build.mjs` writes `space/toolkit-data.js`; running it again changes nothing.
- [ ] `node space/build.mjs --check` exits 0 on the committed tree.
- [ ] In a temp copy of the inputs, appending a line to the template makes `--check` exit 1 and name `template` (AC-5); the same for the gap rules and the redaction regex.
- [ ] The POSIX regex translates to a JS RegExp; a surviving `[[:` class is a build error.
- [ ] Budget constants come out as 200 lines per segment and 40 segments (8000 lines).
- [ ] Gap-check sections equal the template's `## ` headings minus the exclusions read from `adlc_intake_sections`.
- [ ] A missing marker pair in `spec/SKILL.md` exits 2 rather than emitting an empty rule block.
- [ ] `tools/lint-skills/check.sh` still passes after the marker edit.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `space/tests/build.test.js::check fails when the template changes` | yes |
| BR-4 | test-case | `space/tests/build.test.js::budget constants come from intake.sh` | no |
| BR-7 | test-case | `space/tests/build.test.js::redaction regex translated from intake.sh` | no |
| BR-11 | test-case | `space/tests/build.test.js::install commands come from README` | no |
| AC-5 | test-case | `space/tests/build.test.js::check fails when the template changes` | yes |

## Technical Notes

- Toolkit root = parent of `space/` (`new URL('..', import.meta.url)`), with an optional `--root <dir>` for tests that run against a temp copy. Never read `$ADLC_TOOLKIT_ROOT`: the build runs from a checkout.
- Output format: `(function (g) { var d = {...}; if (typeof module !== 'undefined' && module.exports) module.exports = d; else g.ADLC_TOOLKIT = d; })(this);` with `JSON.stringify(data, null, 2)` so the diff is readable and deterministic.
- Fields: `version`, `template`, `templateSections`, `gapSections`, `gapRules`, `segmentLines`, `maxSegments`, `redactPattern` (JS source string), `redactFlags` (`g`), `installCommands`.
- The benign path in the `--check` test is the unchanged tree passing.

---
id: TASK-136
title: "Space page: disclosure, model id, key input, sample run, rendering, download, card"
status: draft
parent: REQ-670
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-135]
repo: adlc-toolkit
---

## Description

The static page, its DOM layer, configuration, the synthetic SampleRun and the
Hugging Face Space card (architecture ADR-1, ADR-2, ADR-7, ADR-8, ADR-11).

## Files to Create/Modify

- `space/index.html` — CSP meta tag; BR-12 disclosure and the model id element above the key input; key input (`type=password`, `autocomplete=off`); paste textarea and `.txt`/`.md` upload; result area; download button; next-step block; scripts loaded from files only.
- `space/style.css` — page styles.
- `space/app.js` — DOM wiring; loads `config.json`; renders with `textContent` only; with no key shows the sample and makes no call; builds the `requirement.md` download from the displayed result; fills the next-step block from `ADLC_TOOLKIT.installCommands` plus `/adlc:spec --intake <file>`.
- `space/config.json` — `{ "model": "claude-sonnet-5-5", "max_tokens": 16000 }`.
- `space/sample.js` — a synthetic meeting transcript and its output (every template section, at least one blocking and one assumption gap).
- `space/README.md` — Space card: YAML front matter (`sdk: static`, `app_file: index.html`), what it does, the key and privacy statement, links to the repo and the plugin install; no dataset link (REQ-671 not live).
- `space/tests/page.test.js` — node:test structural and behavioral cases.

## Acceptance Criteria

- [ ] The disclosure and the model id element come before the key input in `index.html` (AC-9).
- [ ] `index.html` has no inline script and a CSP whose `connect-src` is exactly `'self' https://api.anthropic.com`.
- [ ] `app.js` and `intake.js` contain no `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `localStorage`, `sessionStorage`, `indexedDB`, `document.cookie`, `console` or `eval` (BR-1, BR-6, BR-8).
- [ ] With no key, the app's run path returns the sample and calls no fetch (AC-2), proven by driving the exported run handler with a fetch spy.
- [ ] The download text equals the displayed `requirement_md` (AC-10), and the next-step block holds both REQ-669 install commands.
- [ ] The sample output contains every template section and gaps with severity and justification.
- [ ] `config.json`'s model is what the page shows; changing only `config.json` changes it (BR-9).
- [ ] The card links the repo and the plugin install, and carries no dataset link (BR-13).

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `space/tests/page.test.js::no storage, console or HTML sinks` | no |
| BR-2 | test-case | `space/tests/page.test.js::no key shows the sample and makes no call` | yes |
| BR-6 | test-case | `space/tests/page.test.js::CSP limits connect-src` | no |
| BR-8 | test-case | `space/tests/page.test.js::no storage, console or HTML sinks` | no |
| BR-9 | test-case | `space/tests/page.test.js::model id comes from config.json` | no |
| BR-11 | test-case | `space/tests/page.test.js::download matches display and next step has install commands` | no |
| BR-12 | test-case | `space/tests/page.test.js::disclosure and model id precede the key input` | no |
| BR-13 | test-case | `space/tests/page.test.js::card links only live targets` | no |
| AC-2 | test-case | `space/tests/page.test.js::no key shows the sample and makes no call` | yes |
| AC-9 | test-case | `space/tests/page.test.js::disclosure and model id precede the key input` | no |
| AC-10 | test-case | `space/tests/page.test.js::download matches display and next step has install commands` | no |

## Technical Notes

- `app.js` exports its non-DOM decisions (`decideRun({ apiKey, source })`, `downloadText(result)`, `nextStepText(toolkit)`) under `module.exports` when loaded by Node, so they are tested without a DOM.
- Read uploads with `File.text()`, normalize CRLF to LF, then treat as pasted text (LESSON-606).
- The key is read from the input at click time and passed straight to `runIntake`; it is not kept in a module variable.
- Download: `Blob` + `URL.createObjectURL`, filename `requirement.md`, revoke the URL after the click.

---
id: ASSUME-007
title: "A browser calling the Anthropic Messages API directly can read the status and body of an error response, so the Space can classify errors"
status: validated
req: REQ-670
created: 2026-10-29
resolved: 2026-10-29
---

## Assumption

When a page calls `https://api.anthropic.com/v1/messages` from the browser with the
`anthropic-dangerous-direct-browser-access: true` header, error responses (401, 429,
529) carry CORS headers too. The page's `fetch` therefore sees the real HTTP status and
JSON error body, not an opaque network failure.

## Context

REQ-670's Space (architecture ADR-1) sends the visitor's key from the browser, never
through a server. BR-10 asks for errors in five classes. The classifier in
`space/intake.js` matches on the status and `error.type`. If error responses lacked
CORS headers, the browser would report every failure as a network error, every class
would collapse to `unclassified`, and AC-8 would hold in tests but not live. The
fallback would still be honest, because `unclassified` asserts nothing (LESSON-581).

## Resolution

Validated 2026-10-29, during REQ-670 Phase 4. The test served `space/` from a local
static server and ran it in a real browser with an obviously fake key and a synthetic
two-line source. The page showed `Invalid API key: HTTP 401 — invalid x-api-key`. The
browser read the 401 status and the `authentication_error` body. The 429 and 529 paths
were not exercised live. They are covered by mocked tests, and should be rechecked at
the first deploy (RELEASING.md, Space step 4).

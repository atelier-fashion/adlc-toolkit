---
id: LESSON-471
title: "A new print surface turns latent guard gaps into live disclosures — validate the resolved value, allowlist over blocklist"
component: "adlc/delegation"
domain: "adlc"
stack: ["python", "argparse"]
concerns: ["security", "validation", "observability"]
tags: ["print-surface", "allowlist", "post-cascade-validation", "argv-scanning", "version-flag"]
req: REQ-553
created: 2026-08-03
updated: 2026-08-03
---

## What Happened

Adding `--version` to the delegation CLIs created a new stdout surface printing `api_key_env`, `base_url`, and `model`. The verify pass immediately found two High-severity disclosures that had been latent for as long as those values stayed in-process: the key-shape blocklist (`sk-`, `AKIA…`) failed open for vendor tokens like `gsk_…`/`hf_…`, and the guard validated only the config-file tier — the highest-precedence `ADLC_DELEGATE_API_KEY_ENV` override was printed completely unvalidated. `ADLC_DELEGATE_API_KEY_ENV=gsk_live_SECRET` put the credential on stdout, in output the spec explicitly markets for pasting into bug reports.

## Why It Happened

The pre-existing guard validated an *input* (the config field) rather than the *post-cascade resolved value*, so precedence rules routed around it; and its blocklist required enumerating every bad token shape, which fails open for unknown vendors. Both gaps were harmless while nothing printed — "validation exists somewhere" and "validation covers the value that escapes" are different claims, and only a new output surface makes the difference observable.

## The Fix

- **Validate resolved values, not inputs**: the guard moved to after the whole precedence cascade, so the final `api_key_env` is checked regardless of source.
- **Allowlist over blocklist**: `^[A-Z][A-Z0-9_]*\Z` (UPPER_SNAKE name shape) fails closed for every unknown key shape; the blocklist (extended with the AWS access-key-ID family) remains as defense in depth only.
- **Sanitize everything interpolated into contract output**: printed values are whitespace-collapsed and control-char-stripped so argv/env values cannot forge extra `key: value` lines.
- **Pre-parse argv scans need provable completeness**: `wants_version` runs before argparse, so argparse's `allow_abbrev` default let `--sp "--version"` hijack the invocation into a silent exit-0 no-op. Fix: `allow_abbrev=False`, a per-CLI `_KNOWN_FLAGS` set, and a drift test asserting the set equals the parser's real option strings.

## Takeaways

- Any new output surface is a security surface — before printing a previously internal value, audit whether its guards cover the *resolved* value that will actually escape.
- Allowlists fail closed; blocklists require knowing every bad pattern. When the legal domain is small (env-var names), allowlist it.
- A probe that runs before the parser must mirror the parser completely — and the mirror must be enforced by a drift test, not prose (LESSON-012 class).
- Verify-then-re-verify pays: the re-audit of the first fix round found the abbreviation bypass and fail-open redaction that the first round introduced or missed.

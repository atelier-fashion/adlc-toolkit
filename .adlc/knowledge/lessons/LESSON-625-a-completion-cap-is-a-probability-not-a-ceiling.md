---
id: LESSON-625
title: "A completion cap on a reasoning model is a probability, not a ceiling — read finish_reason, never infer completeness from the content that came back"
component: "adlc/delegate"
domain: "delegation"
stack: ["python", "openai-sdk"]
concerns: ["correctness", "observability", "data-loss"]
tags: ["max-tokens", "finish-reason", "reasoning-tokens", "silent-truncation", "model-repin", "default-expiry", "adlc-read", "adlc-write"]
req: BUG-213
created: 2026-09-03
updated: 2026-09-03
---

## What Happened

`adlc-read` returned `empty completion — increase --max-tokens` on a changelog summary,
and an identical retry returned a partial list with nothing to say it was partial. The
two facts were the same defect seen from two sides. `complete()` raised only when the
returned content was *empty*; it never read `finish_reason`. A run that hit
`max_tokens` with content already emitted was therefore returned as a whole answer. On
the `adlc-write` path that partial file was written to `--target` under `wrote:`, and
under `--force` it replaced a good one — a 188-line pytest module ending in a bare
`assert` was one such output.

Both CLIs' defaults (8192 and 16384, set independently under REQ-515 and REQ-412) were
correct for a model whose whole budget was output. BUG-208 re-pinned the default to
`kimi-k2.6`, a reasoning model on which `max_tokens` covers reasoning **and** output —
and most of it goes to reasoning before the first output token. The re-pin's acceptance
criterion was a live round-trip, which passes on a short question. Neither number was
revisited, and nothing would have told anyone to.

Then the measurement that reframed the fix: three runs of an **identical** request —
same reference, same spec, same model — drew 14706, 12591, and 7880 reasoning tokens.
The uncapped run was the cheapest. There was no ceiling to measure and set a cap above.

## Lesson

1. **`finish_reason` is the completeness contract. Content is not.** A non-empty result
   proves the model emitted *something*; only `finish_reason` says whether it was
   allowed to finish. Check it on every completion, and treat `length` as a failure
   whether or not content came with it — the case with content is the dangerous one,
   because it is the one nothing downstream can detect. Discard the partial output;
   never return it, never persist it. Name the real reason in the message rather than
   asserting the one you expect (LESSON-581's fall-through class): `stop` with nothing in
   it is not a budget problem, and sending the operator to `--max-tokens` for it wastes
   their time.

2. **A completion cap on a reasoning model is a probability, not a ceiling.** The cost
   of an identical request varies widely between runs — ~2x here — so no fixed number
   clears every draw; a higher cap only lowers how *often* you truncate. Set the default
   from measurement with real headroom, from one constant shared by every consumer, and
   let the `finish_reason` check be the thing that makes the number safe rather than the
   number itself.

3. **A numeric default is a claim about the model generation it was set under.** When
   the model is re-pinned, every default whose meaning the model defines — token
   budgets above all — expires silently unless something re-derives it. Put that
   re-derivation in the re-pin's acceptance criteria: a live round-trip on a short
   question proves the endpoint answers, not that the budget still means what it did.

## Why It Matters

The failure mode is not a crash; it is a plausible, well-formed, incomplete answer that
the caller relays or writes to disk as whole. Every skill that delegates inherits it
(`/spec` Step 1.6, `/wrapup` Step 4, `/analyze`, `/architect`, `/proceed` Phase 5), and on
the write path it is data loss with a success message. LESSON-010 named this class at
the prompt level (a word budget that silently drops trailing documents) and prescribed
coverage reconciliation; this is the same class one layer down, in the shared API
helper, where the provider *tells you* it truncated and the helper did not listen.

## Applies When

- Calling any chat-completion API with a `max_tokens`, especially on a reasoning model or
  one that reports `reasoning_tokens` in `usage`.
- Writing a helper that returns model output to callers who will treat it as complete —
  and above all one whose output is persisted to disk.
- Re-pinning a default model: audit every default whose meaning the model defines.
- Diagnosing "empty completion" or "the answer just stopped" from a delegated call: read
  `finish_reason` and `usage.completion_tokens_details.reasoning_tokens` before touching
  the cap.

---
id: BUG-213
title: "The delegate CLIs' max-tokens defaults truncate silently — adlc-read returns a partial answer, adlc-write persists a partial file — and complete() reports a cause it never checked"
status: resolved
severity: high
created: 2026-09-03
updated: 2026-09-03
component: "adlc/delegate"
domain: "delegation"
stack: ["python", "openai-sdk"]
concerns: ["correctness", "observability", "developer-experience"]
tags: ["delegation", "max-tokens", "reasoning-tokens", "silent-truncation", "finish-reason", "adlc-read", "adlc-write", "force-overwrite", "data-loss", "kimi-k2.6", "error-message-accuracy"]
introduced_by: ["REQ-412", "REQ-515"]
attribution: derived
---

<!--
attribution: derived. `git log -L` on the two defective sites:
  - tools/delegate/_common.py:1042-1044 (the empty-content check and its message)
    → cccf701 "feat(kimi): Kimi K2.5 delegation tooling [REQ-412]" (#34)
  - tools/delegate/adlc-read:59 (`--max-tokens` default 8192)
    → 7246e06 "REQ-515: Provider-Agnostic Delegation Layer" (#80)
Both REQ ids validated against .adlc/specs/ (REQ-593 BR-2). Two candidates,
both retained: the defect genuinely emerges from their interaction — REQ-412's
missing finish_reason check is what makes REQ-515's low default silent rather
than loud.
-->

## Description

`adlc-read` defaults `--max-tokens` to **8192** ([`adlc-read:59`](../../tools/delegate/adlc-read))
and `adlc-write` to **16384** ([`adlc-write:56`](../../tools/delegate/adlc-write)). **Both are
exceeded by realistic use of the CLI they belong to** — measured below — and the two numbers
were set independently, so they had already drifted apart once.

On this endpoint `max_tokens` budgets **reasoning and content together**, and `kimi-k2.6`
spends 2.3k–9.1k tokens reasoning *before emitting a single content token*. At 8192 the
reasoning alone can consume nearly the whole budget, so what comes back is either empty or a
partial answer — and which one you get is not stable across identical requests.

Two distinct defects, and the second is the serious one:

**1. A truncated read is returned as a successful one.**
[`_common.complete()`](../../tools/delegate/_common.py) raises only when content is *empty*:

```python
content = resp.choices[0].message.content
if not content or not content.strip():
    raise SystemExit("empty completion — increase --max-tokens")
return content
```

`finish_reason` is present on the response and never read. A run that stops at the cap with
6112 characters already emitted returns those characters to the caller as a complete answer.
That is the outcome that actually causes harm: not a visible failure, but a plausible,
well-formatted, *incomplete* result that the caller has no way to distinguish from a whole
one. Every skill routing through `adlc-read` inherits this — `/spec` Step 1.6, `/wrapup`
Step 4, `/analyze`, `/architect`, `/proceed` Phase 5.

**On the `adlc-write` path it is worse, because the output is persisted.** `adlc-write`
calls the same `complete()`, runs `_strip_fences` on whatever comes back, writes it to
`--target`, and prints `wrote: <target>`. A generation that hit the cap mid-statement is
written to disk as a file, under a success line. And the `--force` path — the one the
documented workflow uses to regenerate — opens the existing target with `"w"` *after*
`complete()` returns, so a good file is replaced by a truncated one with no signal that
anything went wrong. Measured 2026-09-03: a test-module generation at the 16384 default
stopped with `finish_reason='length'` after 188 lines, the last of which was a bare
`assert` with nothing after it. `complete()` returned it; `adlc-write` would have written
it.

This is LESSON-010's class (silent truncation of a delegated read, with advisory anchoring)
reappearing one layer down, in the shared helper rather than a call site. It also sits
against the project's own precedent: REQ-594's intake step **refuses** over an 8000-line
budget rather than truncating, on exactly the reasoning that "a silently truncated read
reports zero gaps precisely because the unread remainder is invisible."

**2. The error message asserts a cause it never verified.**
`"empty completion — increase --max-tokens"` is a guess. Because `complete()` never inspects
`finish_reason`, it prints that identical line for a length cutoff, a content-filter stop, a
tool-call-only response, or a model that legitimately returned whitespace with
`finish_reason='stop'`. It happened to be correct in the observed case, which is the least
useful way for a diagnostic to be right. LESSON-581 verbatim: a fall-through default is a
claim about every input it has not distinguished.

## Reproduction Steps

Corpus: the `[Unreleased]` section of `CHANGELOG.md`, 795 lines, ~13.8k prompt tokens.
Model `kimi-k2.6` on the shipped default endpoint. Measured 2026-09-03 by calling
`chat.completions.create` directly and printing `finish_reason` and `usage`:

| `--max-tokens` | question | `finish_reason` | completion | of which reasoning | content | outcome |
|---|---|---|---|---|---|---|
| 8192 | brief summary | `stop` | 3568 | 2276 | 5128 ch | complete |
| 8192 | exhaustive, "be complete" | **`length`** | 8192 | 6885 | 6112 ch | **truncated, returned as success** |
| 16384 | exhaustive, "be complete" | `stop` | 11532 | 9107 | 10910 ch | complete |
| 20000 | moderate | `stop` | 7990 | 6768 | 4942 ch | complete; value accepted by the endpoint |

`adlc-write` path — a reference file plus a generation spec, the shape the documented
workflow uses (`--spec ... --context <reference> --target <file>`):

| `--max-tokens` | task | `finish_reason` | completion | of which reasoning | content | outcome |
|---|---|---|---|---|---|---|
| 16384 | sh test harness from a 550-line reference | `stop` | 15570 | 13544 | 212 lines | complete — **95% of budget** |
| 16384 | pytest module from a 517-line reference | **`length`** | 16384 | 14706 | 188 lines, ends in a bare `assert` | **truncated; would be written to disk** |
| 20000 | same pytest module | `stop` | 14169 | 12591 | 181 lines | complete |
| 32768 | same pytest module | `stop` | 9017 | 7880 | 143 lines | complete — uncapped, and used *less* than at 20000 |

Code generation reasons **harder** than reading does — against 6.9k–9.1k for the exhaustive
read — and, more importantly, its cost is **not a function of the task**. The three pytest
runs are the same reference, same spec, same model: reasoning drew **14706, 12591, and
7880** tokens — a **~2x spread on an identical request**. The uncapped run was the cheapest.
So there is no "ceiling" to measure and set a cap above; the reasoning cost is a wide random
draw, and any fixed cap will eventually meet a draw that exceeds it. That is the strongest
argument in this bug for item 2 below: a cap can only shift how *often* the write path
truncates, never whether it *can*.

To reproduce the user-visible failure through the CLI:

```sh
sed -n '33,827p' CHANGELOG.md > /tmp/unreleased.md
adlc-read --paths /tmp/unreleased.md --question "List EVERY distinct entry under each heading (Added / Changed / Fixed / Removed). For each give the artifact id, title, and a 1-2 sentence description. Do not merge entries. Be complete — the full list, not highlights."
```

Observed 2026-09-03: one invocation exited with `empty completion — increase --max-tokens`;
an identical retry returned a partial list with no indication it was partial. The
nondeterminism is the reasoning budget landing either side of the cap.

For the write path, the same thing with a file on disk at the end of it:

```sh
adlc-write --spec "<an exhaustive test-module spec>" --context tools/delegate/tests/test_resolve_provider.py --target /tmp/out.py
tail -1 /tmp/out.py     # a bare `assert`, no expression — and `wrote: /tmp/out.py` was printed
```

## Expected Behavior

1. A delegated read of an ordinary-sized corpus completes rather than hitting the cap.
2. A response that *did* hit the cap is a hard failure, whether or not content was emitted.
   A truncated answer is never returned as a successful one.
3. The failure message names the reason the API actually reported.

## Actual Behavior

1. `adlc-read`'s 8192 is exceeded by reasoning alone on an exhaustive question over a
   ~14k-token corpus; `adlc-write`'s 16384 is exceeded by a test-module generation from a
   500-line reference, and sits at 95% on one that completes.
2. A `finish_reason='length'` response with non-empty content is returned to the caller as a
   complete answer — and on the write path, written to `--target`, replacing the prior file
   under `--force`.
3. Every empty-content failure is attributed to `--max-tokens`, regardless of cause.

## Environment

- Platform: macOS (darwin 25.6.0)
- Version: adlc-toolkit 5.0.0, `kimi-k2.6` (the BUG-208 re-pinned default),
  `~/.claude/delegate-venv`
- Note: the reasoning-token accounting that drives this arrived with the model generation,
  not with the toolkit. The 8192 default predates reasoning models — see Root Cause.

## Root Cause

(filled during investigation — hypothesis below)

REQ-515 set `--max-tokens 8192` for `adlc-read` when the delegate was a non-reasoning
completion model, where the entire budget went to content and 8192 was generous for a
summary. The BUG-208 re-pin to `kimi-k2.6` changed what the budget *pays for* — reasoning
now consumes most of it — without revisiting the number, because the re-pin's acceptance
criterion was a live round-trip, which succeeds on a short question. Nothing in the re-pin
was wrong; the default's assumption simply expired underneath it.

`adlc-write`'s 16384 is the same expiry one step later: set higher because generated code
runs longer than a summary, and correct for a model whose whole budget was output. It was
never revisited either.

REQ-412's `complete()` checked empty content because that was the only observable failure a
non-reasoning model produced. `finish_reason` was never consulted because, at the time, an
answer that came back non-empty was an answer that came back whole.

## Proposed Direction

1. **Raise both defaults to 20000, in the same change.** For `adlc-read` the measured worst
   case is 11532 completion tokens, so 20000 is ~1.7x headroom and verified accepted by the
   endpoint; 16384 is the minimum the data supports and 20000 the chosen margin. For
   `adlc-write` the heaviest completed run used 14169 at 20000 and the truncated run had
   already spent 14706 on reasoning alone at 16384 — so 20000 clears the measured cases, but
   with thinner margin (~30% on the heaviest completed run, less on a worse reasoning draw)
   than the read path enjoys. That is recorded here deliberately: 20000 is *sufficient on the
   evidence*, not *generous*, for the write path, and the two defaults should be set from one
   constant so they cannot drift apart a second time. Given the ~2x reasoning variance on
   identical requests, 20000 clears every draw observed (worst 14706 + ~2.3k content) — it
   does not clear every draw *possible*, and no fixed number does.
2. **Read `finish_reason` in `complete()`.** Raise on `'length'` whether or not content is
   empty, and say so — a truncated answer must fail loudly. For a non-`length` finish with
   empty content, name the reason the API returned instead of asserting `--max-tokens`.
3. **Do not paper over it with a retry.** Silently re-issuing at a higher cap would restore
   the same property this bug is about: the caller cannot tell a whole answer from a patched-up
   one. Fail, name the cap, let the caller raise it.

Item 1 fixes today's failure; item 2 closes the class. Item 2 is the one worth having — a
floor is a number that expires, as this bug demonstrates twice over (both defaults, set at
different times, expired the same way), and the next model generation will shift the
reasoning/content ratio again. On the write path item 2 is also what makes item 1's thin
margin acceptable: with a loud failure on `length`, a worse-than-measured reasoning draw
costs a retry at a higher cap, not a truncated file on disk.

**Severity: `high`.** The read path alone would be `medium` — delegate output is advisory at
most call sites (`agents/delegate-pre-pass.md` treats it as untrusted stdout never acted on
directly), with a primary-model reader between it and any decision. The write path is what
sets the severity: a truncated file is *persisted* under a `wrote:` success line, and under
`--force` it *replaces* a good one. BUG-208 — a silent fallback that lost the cheap tier
and no data — is filed `high`; this loses data.

## Resolution

Both halves of the Proposed Direction, as one change:

1. **One default, 20000, in `_common.DEFAULT_MAX_TOKENS`**, read by both CLIs' parsers.
   The constant's comment carries the measurements and the reason the number is not the
   fix. The two defaults had been set independently and had drifted once; a parser
   default that is the *same object* as the constant is pinned by test so it cannot
   happen silently again.

2. **`complete()` reads `finish_reason`.** A `length` finish raises `SystemExit` whether
   or not content was emitted — the partial output is **discarded, not printed and not
   returned**, so the write path cannot persist it. The message names the cap, how many
   characters were emitted before the cutoff (so the operator knows it was partial rather
   than empty), and the provider's `reasoning_tokens` when reported. An empty result with
   any *other* finish names that reason and says explicitly that raising `--max-tokens`
   will not help — the old message asserted the opposite for every cause.

Deliberately **not** done: an automatic retry at a higher cap. That would restore the
property this bug is about — the caller could not tell a whole answer from a patched-up
one. Fail, name the cap, let the caller raise it.

`tools/delegate/tests/test_complete.py` pins fourteen cases. The one that matters is
`test_length_with_content_raises` — the regression that produced the 188-line file ending
in a bare `assert`.

## Deployment

- Merged: [#160](https://github.com/atelier-fashion/adlc-toolkit/pull/160), squash `9f54afb`,
  2026-09-03. Verified `state=MERGED`, `branch_deleted=1`.
- Staging / production: n/a — this repo has no Cloud Run or iOS deploy targets; the toolkit
  is symlink-installed, so the fix is live in every session that starts after the merge.
  Delegation installs pick up the new defaults on the next `adlc-read`/`adlc-write` call.

## Files Changed

- `tools/delegate/_common.py` — `DEFAULT_MAX_TOKENS`; `complete()` reads `finish_reason`,
  discards on `length`, names the real reason otherwise; `_reasoning_tokens` helper
- `tools/delegate/adlc-read` — `--max-tokens` default from the shared constant, help text
- `tools/delegate/adlc-write` — same
- `tools/delegate/tests/test_complete.py` — new; every finish_reason case, the shared
  default, and both CLIs' parser defaults being the same object
- `tools/delegate/README.md` — "Output budget (`--max-tokens`)" section
- `CHANGELOG.md` — Fixed entry

## Related

- **BUG-208** — re-pinned the default model to `kimi-k2.6`, which is what changed the
  reasoning/content split under the unchanged 8192 default.
- **LESSON-010** — delegated-model silent truncation and advisory anchoring. This is the same
  class in the shared helper rather than a call site.
- **LESSON-581** — a classifier's fall-through default is a claim about every input it has not
  distinguished. Applies verbatim to the error message.

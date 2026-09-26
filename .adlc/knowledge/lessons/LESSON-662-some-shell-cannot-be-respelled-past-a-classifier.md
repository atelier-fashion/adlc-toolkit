---
id: LESSON-662
title: "Some shell cannot be respelled past a provenance classifier — the skill text has to route around it"
component: "adlc/delegation"
domain: "adlc"
stack: ["markdown", "sh"]
concerns: ["privacy", "portability"]
tags: ["teton-code", "shell-provenance", "session-pinned", "adlc-read", "harness-agnostic", "lint-skills", "bug-228"]
req: BUG-228
created: 2026-09-26
updated: 2026-09-26
---

## What happened

BUG-218 and BUG-220 fixed Teton Code pins by **respelling**: the preamble lines
were rewritten into the classifier's grammar (`test`/`cat`/`echo`, in-root
paths, no quotes or `$`). BUG-228 looked like the same class, since the pin
reason again named a quoted string. The obvious next move was the same one:
fold the gate, telemetry and `adlc-read` into one vendored in-root script with
plain args.

Reading `shell_provenance.rs` first showed that move would have pinned too.
A program named by path is `Unknown` on purpose (REQ-619 H2), `adlc-read` is
not a recognised verb, and the child environment is allowlisted, so a script
cannot even detect which harness it is in. The classifier's refusal here is
**correct**. `adlc-read` reads files and sends them to a third party, which is
exactly the reach it exists to catch.

## Lesson

Before writing a fix for a host classifier's refusal, ask whether the command
*should* pass. If it reads arbitrary files or leaves the machine, no spelling
will pass it, and trying is a search for a false negative in someone else's
security boundary. The fix then belongs in the only layer the model reads, the
skill text: a conditional that skips the step and takes its fallback. That
layer is prose, so enforce it structurally (`lint-skills` `harness-skip`), not
by honor system (LESSON-012).

## How to apply

- Read the classifier's allowlist tables and fallthrough before choosing a
  fix; don't infer the grammar from the one reason string an event carried.
- If you add a new step that runs `adlc-read`/`adlc-write` or any by-path
  helper, put the `**Provenance-classifying harness (BUG-228):**` line above
  its gate. The lint check will fail the build if you forget.
- Expect a skipped step to write no telemetry record on such a harness. The
  sidecar is itself a by-path program, so an absent record there is not a
  ghost-skip.

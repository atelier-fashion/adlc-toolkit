---
id: ASSUME-032
title: "Codex runs a command no allow names inside its sandbox, rather than not at all"
status: validated
req: REQ-707
created: 2026-11-16
resolved: 2026-11-16
---

## Assumption

Under `codex exec --sandbox workspace-write`, a command that no `prefix_rule` allow names still runs, inside the sandbox. Writes under the working copy, `/tmp` and `$TMPDIR` succeed, and writes anywhere else fail. A command an allow names runs outside the sandbox.

## Context

REQ-707's 2026-11-16 amendment moved `runner-redirect`'s target into the working copy. A refused redirect line can then still create its target, so the control's effect had to be something only an admitted command can produce: the runner's own output, carried through the redirect. The fake harness's `sandboxed-refusal` flag models this assumption.

## Resolution

Validated on codex-cli 0.166.0 in the BUG-279 live runs. In the probe's `runner-baseline` launch the stub had no allow, and it ran: its write to the sentinel outside the workspace failed with `Operation not permitted`, and its `command_execution` record shows `exit_code: 0`. The `runner-positive` launch ran the same stub under an allow and wrote that sentinel. Whether codex's model will now submit the in-workspace redirect line is a separate assumption (REQ-707, Assumptions), still unresolved until the next live run.

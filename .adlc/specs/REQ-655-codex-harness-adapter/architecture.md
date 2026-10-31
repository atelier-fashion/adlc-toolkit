# REQ-655 — Architecture

## Approach

Everything Codex-specific is data in `harness/codex.yml`, plus format renderers in the
framework. The work is the Codex column of REQ-657's table: one adapter at schema 3, four
new formats (`starlark-prefix-rule`, `codex-hooks-json`, `codex-config-toml`, `toml-role`),
one stdlib TOML scanner, and the framework gaps a third adapter reaches first (LESSON-756).
Nothing here branches on a harness name. Lessons applied: LESSON-755 and LESSON-757 (decide
a hook capability from the installed binary, and never render what the consumer ignores),
LESSON-716 (a validator for a format another reader consumes fails closed), LESSON-718 (the
lane check is untouched), LESSON-006 (lint and render share one code path), LESSON-582 and
LESSON-395 (shell portability; the doctor stays stdlib), LESSON-663 and LESSON-619 (the
allowlist is a convenience, never the control).

## Data model changes (adapter schema 3)

`KNOWN_SCHEMA_VERSIONS` gains 3. Everything below is refused under an older version, so
`harness/copilot.yml` and `harness/cursor.yml` stay at 2 unedited, and `harness/claude.yml`
stays at 1 with the one added line BR-13 allows.

| Field | Purpose |
|---|---|
| `paths.config` (surface `config`) | `project`, `user`, `mode: rendered`, `write_mode: merge`, `owned_keys`, plus `values` (what the owned keys hold), `refuse` (values that fail the render) and `user_owned: {table, key}` |
| `sandbox_can_reach_common_gitdir` | required at schema 3 and above |
| `capabilities.unmatched_shapes` | the deny-form shapes a deny-tier rule cannot see; each is a fidelity finding `shape.<name>` |
| `capabilities.unmatched_default` | `sandbox`: an unmatched command is not "will prompt", so the summary says what the README measured and the fence needs no remedy |
| `capabilities.deny_under_allow.<shape>.by_hand` | `strictest-wins` / `allow-wins` / `unverified`, the by-hand half of the restoration path |
| `doctor_rows[].requires` | `delegation`: the row SKIPs with the reason when the delegation CLIs are absent |
| `doctor_rows[].target.legacy_marker` | a `marker-present` row also accepts this marker |

## Service layer

- `tools/adlc/toml_merge.py` (new): the scanner of BR-5. `scan()` classifies top-level keys
  and tables and raises `TomlConstructError` naming the construct; `merge_owned()` adds owned
  keys above the first header, reports conflicts, refuses postures and re-classifies its own
  output; `union_list()` adds one path under the owned table.
- `tools/adlc/harness_render.py`: the four formats; `same_position()` and `restores()` (below);
  the shape findings; `user`-scope plans for the delegation rules and the routing block;
  format-aware `drift()`; `config` in parity and goldens; TOML agent copies.
- `tools/adlc/harness_cli.py`: `install --writable-root`, `install --only-if-detected`,
  `render --check` agent copy drift, the posture message, and the stanza remedy.
- `tools/adlc/harness_doctor.py` and `tools/adlc/checks.py`: a shipped adapter reading
  `unverified` fails, rows SKIP on `requires`, and each non-fact row is its own check.
- `tools/delegate/install.sh`: one call, through the guard, and no path.

## Key decisions

**ADR-1: restoration keeps three conditions at schema 3.** A `pass` record alone restored an
allow before. BR-3 says that is wrong for a token prefix: `git push origin --force` matches
`["git", "push"]`, as `codex execpolicy check` shows. So at schema 3 an omitted allow returns
only when the record is a valid pass, `by_hand` reads `strictest-wins` for a `confirm`
mechanism (the probe measures `forbidden`), and `same_position()` holds: every token the deny
adds after the allow's spelling is a fixed word, not a flag (`-`) or refspec (`+`). The list
form of `never_restore` is enforced in the lint too, where it was render-only, so a hand-added
`allow ["git", "push"]` fails whatever the records say. Schema 1 and 2 keep their behaviour:
Claude's grandfathered record and the REQ-656 fixtures do not move.

**ADR-2: `session-compact` is `unsupported`, not `PostCompact`.** The spec's first draft
mapped it to `PostCompact` if Codex had it. It has it, and the event cannot add context: its
output schema has no `additionalContext` and refuses extra keys. A rendered hook there would
parse and do nothing, which is LESSON-757. A manual compaction fires no `SessionStart` either
(recorded). So `compact_rehook: no`, and the README states the loss.

**ADR-3: `hook_output` is absent; plain stdout is the recorded contract.** The framework's
`json:<key>` writes a top-level key, which Codex refuses. Its JSON channel is
`hookSpecificOutput.additionalContext`, reachable only by a new partial form. Plain stdout
reaches the session and a subagent on recorded runs, so the simplest thing is also measured.

**ADR-4: `subagent_start_hook` stays `no`.** A reviewed hook reaches a subagent, but review is
per hook and per absolute path, so a linked worktree starts unreviewed. The ETHOS read line
costs one sentence and needs no review. Flipping would make ETHOS in subagents depend on a
step that does not survive `/proceed`'s own worktrees.

**ADR-5: nothing writes `hooks.state`.** The toolkit could compute the hash. It would then be
approving its own hooks, the one thing the gate exists to prevent. `/init` prints the step.

**ADR-6: delegation rules and routing are gated on one predicate.** `delegation_installed()`
(the same PATH-then-`~/bin` walk as `partials/delegate-gate.sh`) gates the user-level writes
and the two doctor rows, so a direct `adlc harness install --harness codex` on a machine
without delegation writes no routing that would name absent commands. `install.sh` calls after
the CLIs are linked, so the predicate holds there. The three command names are toolkit facts,
so they live in `harness_render`, not the adapter.

**ADR-7: a quoted header is classified, not refused, unless it spells the owned table.** The
trust step itself writes `[projects."<path>"]`, so refusing every quoted header would refuse
every user file that could reach this code. Only `["sandbox_workspace_write"]` and
`[ sandbox_workspace_write ]`, the spellings that hide the owned table from a literal match,
fail closed (LESSON-716).

**ADR-8: `sandbox_can_reach_common_gitdir: true` follows BR-10's rule, and says what it means.**
The row is `pass`, so the value is `true`. The evidence shows an allowed `git commit` reaches
the common git dir and a sandboxed command does not (`index.lock` blocked). The adapter comment
and the spec say so, because REQ-662 chooses a working-copy strategy from this field.

**ADR-9: the restraint sentence follows the spec and fires on Edit and Write.** It moves to the
spec's wording, keeps "unless your instructions say to" because `delegate-pre-pass` writes a
temp file, and `agent_tool_restriction: none` now tests the tools line instead of its presence:
an agent that may write gets no restraint.

**ADR-10: the gate is recorded through a pty and the engine's own evaluator.** BR-10's by-hand
cases run in the real TUI in a throwaway repo against a throwaway bare remote, trust added to
the user config and restored with `cmp`, because `-c` does not load a project layer. `codex
execpolicy check` is recorded beside them, since it reads the rules with no model session.

## Task graph

TASK-210 (schema, TOML) -> TASK-211 (renderers, adapter, goldens) -> TASK-212 (install, doctor,
delegate installer) -> TASK-213 (gate) -> TASK-214 (skills, docs, loss table). TASK-215 (probe
scrubber) has no dependencies.

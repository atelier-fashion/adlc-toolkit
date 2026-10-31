# Architecture — REQ-658: Antigravity CLI adapter

Evidence: `.adlc/research/antigravity-compatibility.md`, from `agy` 1.4.12. Every fact
below is one of that note's rows. Where this document says "recorded", the note names the
session or command. The task list orders the BR-2 and BR-3 work, then the note, before any
adapter task (BR-1), so the choices here are checked against the finished note before
TASK-219 writes the adapter.

## Approach

`agy` has its own formats on every surface, so the plugin route that looked likely on
paper delivers nothing here. The adapter renders into `agy`'s own paths, from data, through
REQ-657's framework. Five things in the framework change, all additive, and all invisible
to the four adapters that ship: a `skills` surface that renders a file, two schema 4 hook
fields, two format flags for agent files, one capability for a fence no rule can match, and
one doctor rule for a harness with nothing rendered.

| Surface | Where | Route | How |
|---|---|---|---|
| skills | `$HOME/.gemini/config/skills.json` | render | one user-level file whose `entries` names the skills view |
| agents | `$HOME/.gemini/config/agents/<name>.md` | render | user-level copies; `tools:` a YAML list |
| hooks | `.agents/hooks.json` | render | project layer, named-hook map |
| permissions | none | printed | a JSON block, for `settings.json` or `agy --settings` |
| instructions | `AGENTS.md` | render | the canonical file; `agy` reads it as an always-on rule |

## Decisions

### ADR-1: render on every surface, and no manifest

**Decision.** No `.antigravity-plugin/plugin.json`, no call to `agy plugin` anywhere.

**Why.** BR-4 prefers the plugin route where it delivers a surface with no new renderer,
and it delivers none. `agy plugin install` on the Claude Code manifest loaded zero skills
(they sit at the root, and it scans `skills/`), zero agents (a comma `tools:` line and
`model: opus` both fail its loader) and no hooks (Claude Code's `hooks.json` shape fails to
parse). A native manifest with `"skills": ["./"]` does load the seventeen skills, as
`adlc:..:review`, a name nobody can type by accident. AC-4's condition cannot be met
either: `agy plugin validate --strict` fails on nine skills over 24,000 bytes, and on
`AGENTS.md`, `hooks/hooks.json` and `workflows/`, none of which can move.

### ADR-2: skills reach `agy` through a user-level `skills.json`

**Decision.** `paths.skills` is `rendered`, one file, whose `entries` names the skills view
(`<ADLC_HOME>/adlc/skills-view`), or ToolkitRoot when no view exists, as on the plugin
route. Detect reports `mounted` when an entry reaches this toolkit.

**Why.** A recorded run loaded a skill through `~/.gemini/config/skills.json`, and through
an entry that was a directory of symlinks, which is what the view is. Skills keep bare
names, so `/proceed` means what it means elsewhere. `agy` documents no read of
`~/.agents/skills`, and the one test of it is a write this run may not make, so the mount
stays `unverified` and nothing depends on it. An `entries` scan is one level deep, so
ToolkitRoot is safe as the fallback: only `<name>/SKILL.md` matches.

The file's write mode is `create`. A user with a `skills.json` of their own keeps it, and
the render says what to add. That is a smaller promise than a merge, and ADR-3 says why.

### ADR-3: permissions are printed, so `merge_json` does not change

**Decision.** `paths.permissions` is `printed`. BR-7 reads not applicable.

**Why.** Four candidate paths in a repository were read by nothing, so
`committable_allowlist: no`, and the rule set belongs to the user's `settings.json`. A
printed block needs no merge into a file the toolkit does not own, and the same block works
as `agy --settings <file>`, which REQ-662 can use. Writing it would need BR-7's whole
framework change for a convenience. A thin adapter that tells the truth is the stated
acceptable result, and a user's settings cannot be lost by a render that does not touch
them. `settings.json` refuses unknown keys, so the block carries no comment.

### ADR-4: schema 4 adds fields around the canonical hook command

**Decision.** `hook_cwd` adds one line before the command, and `hook_output_envelope` wraps
the command's output. Both are optional and refused below schema 4.

```
cd .. || exit 0
<the canonical command> --harness antigravity --field … --context-key systemMessage | { IFS= read -r adlc_line && printf '<envelope>\n' "$adlc_line"; }
```

**Why.** Two recorded facts. A hook runs in the directory holding `hooks.json`, so every
relative path in the canonical command misses from `.agents/`. And context reaches the
model only as `{"injectSteps":[{"systemMessage":{"systemMessage":…}}]}`, while plain
stdout fails to unmarshal and is dropped. Wrapping in the rendered command, not in
`partials/ethos-inject.sh`, means a project with an older vendored partial still works:
`--context-key` has been there since REQ-656, and an unknown flag in a stale copy would
fail silently. An empty ETHOS prints nothing, `read` fails, and the hook prints nothing.

### ADR-5: formats are named for their shape

**Decision.** `named-hooks-json`, `action-rules-json`, `yaml-tools-agent-md` and
`skills-entries-json`.

**Why.** BR-5's grep must find no harness name in `tools/adlc` outside the two tables. A
format is a shape, and the next harness with the same shape can use it.

### ADR-6: agent files carry a marker, and a file without one is refused

**Decision.** Format flags `agent_tools_list` (a YAML list) and `agent_header` (a generated
line in the body). With `agent_header`, `render_copies` reads every target first and writes
nothing if any existing file lacks the line.

**Why.** `$HOME/.gemini/config/agents/` is the user's directory too, and a `reflector.md`
of theirs must not be overwritten. All-or-nothing, because half a render is the worse
failure. The other copy formats keep what they do today.

### ADR-7: a headless refusal counts as the ask being reached

**Decision.** `Profile.refusal_stderr` is a regex. A launch whose stderr matches sets
`Obs.denied`, and the deciders treat that as they treat the nonce: the model got as far as
the command and was refused.

**Why.** This is REQ-664's open follow-up, and on this harness it is not optional. An
auto-denied tool ends the run with exit 0 and an empty response, so no refused launch can
ever return the nonce, and every variant would read `ask-not-reached`.

The same fact means a launch must allow the look-around a model does first, or it dies
before the command under test. `Profile.prep_allow` carries those read-only commands, and a
test holds them apart from everything a probe tests. The first full run lacked it, which is
why the note reads some `fail`s as artifacts.

### ADR-8: the probe needs no user file

**Decision.** Rules reach each launch through `agy --settings <file>`, written under the run
directory. `allow_form="launch-flags"`, `trust="none"`, and `dry-run` reports no user file.

**Why.** `--settings` is session-only and never saved, and a recorded run showed the rules
in force. Hooks and skills are project-local, and they loaded with no trust record.

### ADR-9: `subagent_start_hook` stays `no`

**Decision.** `hook_events.subagent-start: unsupported`, `subagent_start_hook: "no"`, and
rendered agents keep the ETHOS read line.

**Why.** A recorded run shows `SessionStart` fires for a subagent's own conversation, and
the context reached it. But agent copies are user-level and the hook is project-level, so a
project without the hook file has an agent with no ETHOS. The read line costs little, and
the agent then has it either way. There is no `SubagentStart` event to map, and mapping
this event to `SessionStart` would register the hook twice.

### ADR-10: "nothing rendered" SKIPs, from schema 4

**Decision.** `harness_doctor.skip_reason(adapter, toolkit)` returns a reason when the
binary is absent, or, at schema 4 and later, when no user-level file of the adapter exists.
`render_currency` and `_row_check` both use it.

**Why.** `agy` is installed on machines that never asked for this adapter. An unrendered
harness must not read FAIL (BR-12). Older adapters keep their behaviour, which REQ-655 and
REQ-656 tests pin. A deleted file still FAILs: one user-level file remaining counts as
rendered.

### ADR-11: `fence_unmatchable` decides, whatever `accepted_fidelity` says

**Decision.** A schema 4 capability. With it, no fence rule renders and no remedy prints,
and `fence_broad_spelling` is not required. `accepted_fidelity` must still list the omission.

**Why.** `fence-vs-allowlist` failed in all three variants, because a compound line is judged
part by part. A rendered `command(if [ -f .adlc/partials/)` would be inert config that reads
as coverage (LESSON-757), and the stock remedy would tell a user that a widening works when
it was measured not to. Keying this on `accepted_fidelity` alone left a gap: removing that key
silently rendered the rule, which the test for it caught.

### ADR-12: `apply_plans` says `kept` when it keeps a differing file

**Decision.** A create-mode file that differs from its render now reads `kept`, and for
`skills` the render prints the entry to add.

**Why.** ADR-2 promises this, and the branch was unreachable: `target == existing` always
held first, so a kept file read `unchanged`, which was false. This changes one word of
output for every adapter, and no byte on disk.

## Merge surface

None (ADR-3). `merge_json` is unchanged and AC-7 is not applicable.

## Task graph

```
TASK-216 detect, doctor ─┐
TASK-217 probe profile ──┼─> TASK-218 live run and note ─> TASK-219 schema 4, adapter
                                                                │
                                         TASK-220 install, doctor ┤
                                                                └─> TASK-221 docs, loss table
```

## What this does not do

No transcript parsing (REQ-660), no `exec` keys beyond the `flags: unverified` Codex also
carries (REQ-662), no edit to any `SKILL.md`, no edit to `harness/claude.yml`,
`copilot.yml`, `cursor.yml` or `codex.yml`, and no change to the skills that exceed the
cap: ADR-1's measurement is stated as a loss, not worked around.

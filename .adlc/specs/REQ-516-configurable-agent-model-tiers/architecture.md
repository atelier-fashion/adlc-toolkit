# Architecture — REQ-516: Configurable Agent Model Tiers

## Overview

Make the `model:` frontmatter of every `agents/*.md` a **rendered output** of a
declarative tier system instead of a hand-edited literal. Each agent declares a
stable `tier:` class; a config section maps class → model alias (with optional
per-agent overrides); a render script stamps the resolved `model:` into each
file. With no config, the shipped defaults reproduce today's exact 18 assignments
(BR-3) — zero behavior change.

The render logic ships as a subcommand of the existing umbrella `adlc` CLI
(REQ-519) — `adlc agents render` — registered **additively** in the data-driven
`SUBCOMMANDS` table (no dispatch-logic edit, per REQ-519 BR-11). This is the
coordination boundary with the concurrently-running REQ-518, which also appends
to `SUBCOMMANDS`: both REQs touch only the table literal, not the dispatch code,
so the only possible merge conflict is two adjacent dict entries — trivially
resolvable.

## Surface inventory (what changes)

| File | Change | Why |
|---|---|---|
| `agents/*.md` (×18) | Add `tier:` frontmatter field + a one-line header comment marking `model:` as derived | BR-1 |
| `tools/adlc/agents_render.py` (new) | Render + drift-check engine (pure stdlib) | BR-2, BR-4, BR-7; the "same code path" for BR-5 |
| `tools/adlc/adlc.py` | Append one `SUBCOMMANDS` entry + one lazy handler `_cmd_agents` | additive registration (REQ-519 BR-11) |
| `tools/adlc/tests/test_agents_render.py` (new) | pytest coverage mirroring `test_dispatch.py`/`test_checks.py` | every AC |
| `tools/lint-skills/check.py` | Add one check `check_agent_model_drift` that calls `agents_render.check_drift(root)` | BR-5 (drift surfaced by lint-skills) |
| `tools/lint-skills/tests/` | One test for the new drift check | BR-5 verification |
| `tools/adlc/README.md` | Document `adlc agents render [--check]`, the `agents:` config block, and the alias set | discoverability |

**Not changed**: agent prompts, tool restrictions, which agents exist (out of
scope). `/template-drift` SKILL.md is **not** modified — see ADR-4.

## Tier-class assignments (the shipped default — BR-3 source of truth)

Derived from today's committed `model:` values (captured at implementation time
from the 18 agents on `origin/main` @ REQ-519). The resolved-decision mapping
(spec Open Questions): `delegate-pre-pass`→`explorer`, `pipeline-runner`→
`orchestrator`. Reviewer/scanner/explorer/implementer/orchestrator are the five
classes.

| Agent | tier | shipped model |
|---|---|---|
| adversary | reviewer | opus |
| correctness-reviewer | reviewer | opus |
| reflector | reviewer | opus |
| security-auditor | reviewer | opus |
| architecture-reviewer | reviewer | sonnet |
| quality-reviewer | reviewer | sonnet |
| code-quality-auditor | reviewer | sonnet |
| test-auditor | reviewer | sonnet |
| api-cost-scanner | scanner | sonnet |
| db-perf-scanner | scanner | sonnet |
| latency-scanner | scanner | sonnet |
| architecture-mapper | explorer | haiku |
| convention-auditor | explorer | haiku |
| delegate-pre-pass | explorer | haiku |
| feature-tracer | explorer | haiku |
| integration-explorer | explorer | haiku |
| task-implementer | implementer | opus |
| pipeline-runner | orchestrator | opus |

**Crucial design point (ADR-1):** a single class is NOT a single model in the
shipped defaults. `reviewer` covers both opus (adversary, correctness-reviewer,
reflector, security-auditor) and sonnet (architecture-reviewer, quality-reviewer,
code-quality-auditor, test-auditor). A naive "class → one model" default map
would silently flip 4 sonnet reviewers to opus (or vice-versa), violating BR-3.

The shipped default is therefore **the per-agent map itself**, not a
class→model collapse. The class system exists for the *adopter's* config (so they
can say `reviewer: sonnet` and move all 8), but the zero-config render reproduces
each agent's individually-shipped value. This is exactly the spec's resolved
decision: "the shipped default policy is today's explicit per-agent assignments,
NOT the drop-`model:` variant."

## Resolution algorithm (BR-2)

For each agent, resolve `model` by precedence (first hit wins):

1. **per-agent override** — config `agents.overrides.<agent-name>`
2. **class mapping** — config `agents.classes.<tier>` (the agent's declared `tier:`)
3. **shipped default** — the per-agent value from the table above (the
   `_SHIPPED_DEFAULTS` dict baked into `agents_render.py`)

A resolved value of `inherit` means: remove the `model:` line entirely (agent
inherits the session model). Any other resolved value is written as `model: <value>`.

`_SHIPPED_DEFAULTS` is the authority for both the per-agent fallback AND the
`tier:` value each agent file must declare; the render asserts the file's `tier:`
matches the table (a guard against an agent file drifting its tier).

## Config format (BR-3, REQ-515 alignment)

Lives in the `agents:` top-level section of `~/.claude/adlc/config.yml` (the same
file REQ-515 uses for `delegate:`). Minimal flat reader, mirroring
`tools/kimi/_common.py:parse_delegate_config` — NO PyYAML dependency (REQ-515
ADR-3). Two nested maps:

```yaml
agents:
  classes:
    reviewer: sonnet        # move all reviewer-class agents to sonnet
    scanner: haiku
    # explorer/implementer/orchestrator omitted -> shipped defaults
  overrides:
    correctness-reviewer: opus   # beats the class mapping above
    pipeline-runner: inherit     # drop model: line for this one agent
```

Absent file, absent `agents:` section, or empty maps ⇒ shipped defaults (BR-3).
The reader tolerates one level of nesting (`classes:`/`overrides:` under
`agents:`), parsing `key: value` scalars two indents deep. It reads ONLY these
two sub-maps and ignores everything else (including REQ-515's sibling
`delegate:` block), so the two REQs coexist in one file.

## Alias validation (BR-7)

Allowed alias set: `{opus, sonnet, haiku, inherit}`. Escape hatch: any value
matching a full-model-id shape (`^[a-z0-9][a-z0-9.\-]*$` containing a digit and a
`-`, e.g. `claude-opus-4-8`, conservatively `claude-*`/`*-4-*`) is accepted and
passed through verbatim. Anything else (`gpt5`, `Sonnet`, empty) → **fail loud**,
exit non-zero, message naming the bad key, the bad value, and the allowed set.
No silent fall-through to a default (LESSON-009). Validation runs over every
config value (classes + overrides) BEFORE any file is written, so an invalid
config never half-renders.

## Atomicity & idempotence (BR-4)

Per file: read full text → compute new text by rewriting ONLY the `model:` line
(or inserting/removing it) within the frontmatter block → if unchanged, skip
(no write, no mtime churn) → else write to a temp file in the same directory and
`os.replace()` (atomic rename). Never reflow other frontmatter keys or body
content. The frontmatter is located as the text between the first `---` line and
the next `---` line; the `model:` line is matched by `^model:` at line start
within that block only. Second run produces an empty diff (idempotent).

For `inherit` (remove the line): drop the single `model:` line and its newline,
leaving the rest byte-identical. For alias→present when currently absent
(re-adding after inherit): insert `model: <value>` immediately after the `tier:`
line (deterministic position).

## Header comment (BR-1)

Each agent gains a single HTML comment line inside the body, right after the
closing `---` of frontmatter (NOT inside frontmatter, where Claude Code's YAML
parser would choke):

```
<!-- model: is rendered by `adlc agents render` from tier: + ~/.claude/adlc/config.yml; do not hand-edit. -->
```

The render is idempotent w.r.t. this comment (inserts only if absent).

## Drift check (BR-5) — ADR-4

`agents_render.check_drift(root)` returns the list of agents whose on-disk
`model:` differs from what the current config would render. `adlc agents render
--check` runs it read-only (exit non-zero if any drift; print the offenders).

**Host: `lint-skills`, not `/template-drift`** (ADR-4 rationale below). A new
`check_agent_model_drift(root)` in `tools/lint-skills/check.py` imports
`agents_render` and emits a `Finding` per drifted agent — surfacing it through
the linter that already scans the toolkit checkout's own `agents/`. This is the
"same code path" the spec requires (LESSON-006 carve-out: drift and render share
one implementation, no divergent re-derivation).

## ADRs

**ADR-1 — Shipped default is the per-agent map, not a class→model collapse.**
Because the existing assignments split classes across models (4 opus + 4 sonnet
reviewers), collapsing to one-model-per-class would change behavior, violating
BR-3. The `_SHIPPED_DEFAULTS` per-agent table is the zero-config authority; the
class map is purely the adopter's override lever. (Trade-off: the default table
is verbose, but it is the only encoding that satisfies BR-3 exactly.)

**ADR-2 — No PyYAML; flat reader mirrors `_common.py`.** REQ-515 ADR-3 already
established a dependency-light flat config reader for three scalar fields. We
extend the same approach to the two-level `agents:` map rather than introducing
PyYAML, keeping `adlc` pure-stdlib (REQ-519 ADR-1) so `adlc agents render` runs
on a machine that never opted into delegation.

**ADR-3 — Render engine in its own module, registered additively.** The logic
lives in `tools/adlc/agents_render.py`; `adlc.py` gains only a `SUBCOMMANDS`
entry + a 2-line lazy handler. This (a) keeps the CLI dispatch untouched (REQ-519
BR-11 / minimizes the REQ-518 merge surface — both REQs only append a dict
entry), and (b) lets `lint-skills` import the drift function directly without
pulling in CLI argparse machinery.

**ADR-4 — Drift surfaced via `lint-skills`, not `/template-drift`.**
`/template-drift` compares a *consumer project's* `.adlc/templates|partials`
copies against the toolkit; consumer projects have no `agents/` dir (agents are
symlinked, not copied). Agent `model:` drift is a **toolkit-internal** condition
(the checkout's own `agents/*.md` vs its own config render), so the structurally
correct host is `lint-skills`, which already lints the toolkit checkout. The spec
explicitly allows this: "`/template-drift` (or `lint-skills`)". We mirror the
template-drift *rationale* (staleness detection, LESSON-023) via the same
`Finding`/report mechanism, not its consumer-copy mechanism.

**ADR-5 — `adlc agents render` subcommand grouping.** The subcommand is
`agents` with a required action arg (`render`), leaving room for future
`adlc agents <other>` actions without another top-level command. `--check` is a
flag on `render` (dry-run drift report). This matches `doctor`'s
single-handler-takes-remaining-argv contract in `adlc.py`.

## BSD/zsh safety (BR-6)

The render engine is **Python**, not shell, so most BSD/sed/grep hazards do not
apply. The only shell is the `lint-skills` invocation (already Python) and any
test harness. Tests dogfood the CLI via `subprocess` under the default shell. No
`grep -E \b`, no bare `$<digit>`, no `[0]` index, no `status=` var anywhere in
new shell. (The Python implementation sidesteps the entire shell-portability
class — a deliberate choice given BR-6's litany of shell footguns.)

## Test strategy

`tools/adlc/tests/test_agents_render.py` (pytest, offline, `tmp_path`-driven —
mirrors `test_checks.py`). Each AC maps to a test:

1. `scanner: haiku` renders only scanner agents; others byte-identical.
2. Fresh checkout, no config → render is a no-op (every agent already at its
   shipped default; empty diff) AND resolved value == committed value for all 18.
3. Class `inherit` removes `model:`; re-render to an alias restores it.
4. Render twice → second run writes nothing (idempotent).
5. Drift: hand-edit a `model:`, `check_drift` flags it; re-render clears it.
6. Invalid alias (`scanner: gpt5`) → fail loud, message names key+value+allowed.
7. Linux parity: pure-Python + `os.replace` is OS-agnostic; tests run identically
   on macOS/Linux CI (no shell-ism to diverge).

Plus `test_dispatch`-style: `adlc agents render` dispatches; the new
`SUBCOMMANDS` entry is data-driven; `--check` exit codes.

## Task graph

```
TASK-001 (tier: frontmatter + header comment on 18 agents)
TASK-002 (agents_render.py: config reader, resolver, validator, renderer, check_drift)
TASK-003 (register adlc agents render in adlc.py — additive SUBCOMMANDS entry)
TASK-004 (lint-skills drift check importing agents_render)
TASK-005 (README + tests for render & drift)

Dependencies:
  TASK-002 depends on TASK-001 (needs the tier values to validate against)
  TASK-003 depends on TASK-002 (handler imports the module)
  TASK-004 depends on TASK-002 (imports check_drift)
  TASK-005 depends on TASK-002, TASK-003 (tests exercise the CLI + engine)
```

Single repo (`adlc-toolkit`), so every task is `repo: adlc-toolkit`.

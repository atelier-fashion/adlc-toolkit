# REQ-656 — Architecture: Copilot CLI and Cursor adapters

Exploration ran inline (pipeline-runner subagent mode; `.adlc/agents/` is absent in
this repo, which `/init` (`/adlc:init` on the plugin install) vendors, so the
`feature-tracer`, `architecture-mapper` and `integration-explorer` checklists were
read from `$ADLC_TOOLKIT_ROOT/agents/`). The harness facts below were checked against
the vendor pages plan §7 cites on 2026-10-30. Neither CLI was on the machine, so
every one of them is what a page says, not what a binary does.

## Approach

Two data files, their goldens, and the framework gaps a first non-Claude adapter
exposes. REQ-657 shipped against one adapter and a fixture, so several paths it
built had never run with a real second harness: a `printed` surface, a `via:` agents
surface, a hard deny under a shared base, a second file on one surface, a report-only
fact. Each gap is closed in the framework as data plus one code path. No code in
`tools/adlc` compares a harness name.

```
templates/permissions.yml ─┬─ copilot (token-prefix, {user: deny}) ─► printed line + fidelity report
                           └─ cursor  (command-base, {project: deny}) ─► .cursor/cli.json
                                                                       └► .cursor/permissions.json (also:)
templates/hooks.yml ───────── copilot (flat hooks, hook_output) ──────► .github/hooks/adlc.json
agents/*.md ───────────────── copilot (.agent.md, tool_map) ──────────► $HOME/.copilot/agents/
                              cursor  (via:claude) ───────────────────► nothing; one line says why
```

## Key decisions

**ADR-1 — Copilot's granularity is `token-prefix`.** REQ-657 BR-9 and AC-16 define
`subcommand` as a two-token cap. Under it `gh pr view` collapses to `gh pr`, which
wraps `gh pr merge`, and every deny collapses too, so `--deny-tool` for
`git push --force` would deny all of `git push`. `token-prefix` is the same matcher
with no cap, and it is the only value that yields AC-6's omission list. The README
keeps the plan's word, "subcommand prefix", and names the mapping. Keeping
`subcommand` with an opt-out field would add schema to say what `token-prefix`
already says.

**ADR-2 — Allows spell `shell(<argv>:*)`, denies always spell `shell(<argv>:*)`.**
`:*` is the one documented prefix form. Whether a bare `shell(git push)` takes
trailing arguments is undocumented. A `match: exact` allow stays bare, at worst
as wide as `:*`. A deny is always `:*`, because a deny that misses
`--force origin main` is the worse failure, and any form neither spelling catches
still prompts, since BR-6 omits the routine prefix. `renders_exact` is true for the
format, and the format chooses the suffix per rule kind.

**ADR-3 — `schema_version: 2`, four optional fields.** `paths.<surface>.also` (a
further file on a surface, with its own format), `hook_output` (hook id →
`json:<key>`), `fidelity_notes` (sentences the report prints), `doctor_rows[].fact`
(ADR-7). The loader refuses each under version 1, so `harness/claude.yml` stays at 1,
byte for byte (BR-14). No field is required of every adapter.

**ADR-4 — A deny's clash check reads the routine candidates, not the survivors.**
REQ-657 computed the clash after the shared-base omission, so on `command-base` every
`git` allow was gone by the time `Shell(git)` was tested as a deny, and the render
would deny all of git. Any routine candidate now counts. `claude` and `fake-prefix`
render the same, because a longer deny spelling never matches a shorter allow.

**ADR-5 — `hook_output` wraps ETHOS as JSON on Copilot.** The Copilot page says plain
stdout is not injected and context arrives as `{"additionalContext": "…"}`. The
adapter maps `ethos-inject: json:additionalContext`, the render appends
`--context-key additionalContext` to that hook alone, and `adlc_ethos_inject` emits
the object, in POSIX sh, escaping backslash, quote and tab, joining lines with `\n`
and dropping other control bytes so the JSON always parses. With no key it prints the
file as before, so the `claude` render is unchanged. `session-record` gets no extra
argument, because REQ-660 owns that partial.

**ADR-6 — `.cursor/permissions.json` is rendered as what it is.** Its documented keys
are `terminalAllowlist`, `mcpAllowlist` and `autoRun`, and unknown keys are ignored,
so a copy of `cli.json` would be an inert file that reads as enforced. `also:` adds
the file with its own `cursor-terminal-allowlist` format: the same allow bases, no
deny. A fidelity note says the deny tier has no IDE form. No deny-tier command goes
into `autoRun.block_instructions`, which the docs call steering rather than
enforcement, and BR-2 allows a deny tier only under a real deny.

**ADR-7 — Facts are `doctor_rows` with a `fact`.** A shipped row FAILs
`render-currency:<name>` when false, which is wrong for a statement like "Cursor reads
this path too". A row with `fact` is skipped by the render-currency loop and reported
under `harness:<name>`, which never fails. The two `harness:` rows stay report-only
and `grep 'def check_harness_copilot'` stays empty.

**ADR-8 — Copy agents' golden is a frontmatter manifest.** `render-parity` compares
`harness/copilot/rendered/agents.json`: each agent's file name and mapped `tools:`.
A full-text golden would make every body edit to `agents/*.md` touch `harness/**`,
which `lane_check` blocks, so a lite REQ that fixes a checklist typo would escalate. A
`tools:` change does escalate, and should: it is a widening of what an agent may do.
Bodies are covered by `render-currency:copilot` on any machine with the binary.

**ADR-9 — Render scopes stay honest.** `adlc harness render` at `project` scope writes
project files only and prints the command that writes the user-level copies. At
`--scope user`, and through `install`, it writes them. `/init` therefore never writes
under `$HOME`. `AGENTS.md` is still written by a Cursor render (BR-7), so AC-9's "only
the two permission files" reads as "no agent and no hook file".

**ADR-10 — `drift --opted-in`.** `/template-drift` must report Copilot's and Cursor's
files without reporting them `missing` in every project that never asked for them
(BR-14). `--opted-in` adds each shipped adapter with at least one project-layer file
on disk to whatever `--harness` names. Step 3g runs
`adlc harness drift --harness claude --opted-in`.

**ADR-11 — `harness-loss-table`, a lint.** The README's tables sit in
`<!-- harness-loss: <name> -->` blocks. The check derives each expected fact from the
adapter and a fresh render (granularity, committed allowlist, deny mechanism, the
omitted bases) and fails on a missing row, a contradicted fact or a missing residual
statement, so the table cannot outlive the adapter (LESSON-012, LESSON-019).

**ADR-12 — Two closures of BR-2 in the render.** A routine candidate whose accepted
verdict is `inexpressible` is withheld, generalising REQ-657 ADR-7 past the fence, so
`gcloud.read` on Cursor never becomes `Shell(gcloud)`. A routine spelling whose first
token is in BR-2's set is omitted and fails `evaluate_rules` by hand. Neither touches
the `claude` render.

**ADR-13 — `subagent_start_hook: "no"` on both.** Not one row of evidence shows the
hook reaching a subagent, and the cost of `no` is one repeated read, while the cost of
a wrong `yes` is agents with no ETHOS at all (Reconciliation). Copilot still renders
`subagentStart`; the flag only decides whether the ETHOS-first line stays.

**ADR-14 — Report summary.** `fidelity_summary` turns the findings into what the
operator acts on: what will prompt, what has no hard deny, what was widened, then the
adapter's `fidelity_notes`. It skips the fence, which has its own remedy, so `claude`
prints exactly what it printed before (BR-14).

## Affected files

New: `harness/copilot.yml`, `harness/cursor.yml`, `harness/copilot/{README.md,rendered/}`,
`harness/cursor/{README.md,rendered/}`, `tools/adlc/tests/test_harness_adapters.py`,
`tools/lint-skills/tests/test_harness_loss_table.py`.
Modified: `tools/adlc/{harness_adapter,harness_render,harness_cli,harness_doctor,agents_render,checks}.py`,
`tools/lint-skills/check.py`, `partials/ethos-inject.sh`, `partials/tests/hooks.test.sh`,
`tools/adlc/tests/test_lane_check.py`, `init/SKILL.md`, `template-drift/SKILL.md`,
`harness/claude/README.md`, `README.md`, `tools/adlc/README.md`, `tools/lint-skills/README.md`,
`.adlc/context/architecture.md`, `.adlc/context/conventions.md`,
`.adlc/research/multi-harness-plan.md`, `CHANGELOG.md`.

## Lessons applied

LESSON-716 (model the reader: Copilot's hook reader, Cursor's IDE file), LESSON-751
(re-measure before building), LESSON-755 (read the delivery contract, not the event
list), LESSON-619 (never cite the allowlist as the gate), LESSON-012 (the README lint),
LESSON-582 (POSIX in the partial), LESSON-718 (no gate path added).

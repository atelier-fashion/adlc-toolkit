# REQ-666 Architecture — Skill text portability

## Approach

The spec was written on 2026-10-27, before REQ-669 (plugin route, ToolkitRoot,
`dispatch-fallback`, `toolkit-path`, `builtin-collision`) and REQ-654 (`ADLC_HOME`,
`adlc-home`) landed. Both of those REQs name this one as the reconciler
(REQ-669 BR-18, ADR-9; REQ-654 architecture "Lint"), so this design applies the
spec to the tree as it now stands rather than to the tree it describes. Where
that changes a stated detail, the table or ADR below says so and why.

Nothing a skill does on Claude Code changes beyond the two effects BR-15 allows
(the context reads become one shell call; a failing context command no longer
aborts the invocation). Every change is text, lint, tests and documentation,
plus two data edits: `lane_check.py`'s default blocked paths and the settings
template's allow list.

## Reconciliation with the landed tree

| Spec says | Tree now has | Decision |
|---|---|---|
| ETHOS line `… run /init to vendor .adlc/ETHOS.md` | REQ-669's dual-spelled line `… run /init, or /adlc:init on the plugin install, to vendor .adlc/ETHOS.md` | `ethos-line` pins **today's** line (BR-2 says "byte-identical to today's"). The check reads it from conventions.md "Ethos injection pattern", the one copy. |
| "REQ-610 guarded fence spelling, with its literal `~/.claude/skills/partials/<name>.sh` fallback" | REQ-669 retired that operand; fences use the root line plus `"$ADLC_TOOLKIT_ROOT/partials/<name>.sh"` | The exception is the REQ-669 root line (`TOOLKIT_ROOT_LINE`) and the ADR-2 token, exactly as `toolkit-path` excepts them. |
| `dispatch-has-fallback`, a new check | `dispatch-fallback` (REQ-669 ADR-6) already requires one canonical sentence per dispatching step | ADR-4: the existing check is renamed `dispatch-has-fallback` and widened; one check, one canonical block. |
| `no-harness-path` "subsumes REQ-654 BR-13's narrower check" | `toolkit-path` (REQ-669) and `adlc-home` (REQ-654) both exist | ADR-5: `no-harness-path` absorbs `toolkit-path` whole (REQ-669 BR-18 asked for exactly this). `adlc-home` stays as the code-side machine-state check; ADR-5 gives the reasoning. |
| `/sprint`'s two `~/.claude/agents/pipeline-runner.md` references | REQ-669 rewrote them to `$ADLC_TOOLKIT_ROOT/agents/pipeline-runner.md` | Rewritten to `.adlc/agents/pipeline-runner.md`, with the ToolkitRoot copy as the named fallback (BR-3, BR-4). |
| "about 70" `~/.claude` mentions in skill prose | REQ-654 and REQ-669 already rewrote all but a handful | The remaining lines are rewritten; the agents' rendered `model:` header is a whole-line HTML comment and is excepted as a comment line. |
| REQ-648 "(draft)", to be amended before it is architected | REQ-648 shipped: `harness-skip` requires the BUG-228 line above every `emit-run-outcome.sh` fence | BR-6 therefore **reverses REQ-648 BR-3 in part** (the skip line above the run-outcome fences); the CHANGELOG names it. |

## ADR-1: Input prose replaces `$ARGUMENTS` (BR-1)

Every `Target: $ARGUMENTS`-style line becomes a sentence: the argument is
whatever follows the skill name in the invocation (on Claude Code it can also
arrive as an `ARGUMENTS:` line appended after the skill text), and what the skill
does when there is none. Prose that referred to "`$ARGUMENTS`" says "the argument".

Three fences consumed the value and now carry an angle-bracket placeholder:

- `/spec` Step 1.4's two fences: `adlc_intake_detect '<request>'`.
- `/manifest`'s self-id fence: `self_args='<req-ids>'`, with `MANIFEST_SELF` and
  the branch name as fallbacks in the precedence the old
  `${ARGUMENTS:-${MANIFEST_SELF:-}}` expressed. A placeholder left unsubstituted
  holds no REQ id and falls through, so that failure mode is today's behaviour.
- `/sprint`'s `Workflow` call already took a model-normalised list; only its prose changes.

The substitution rule is stated **once**, in conventions.md "Bash in skills"
("Substituting a value into a fence"): replace the placeholder and its quotes
with the value single-quoted, every `'` in it written `'\''`; or, where the fence
reads stdin, a quoted-delimiter here-doc. Each fence's prose points at that
rule. A double-quoted substitution would expand backticks and `$`; an unescaped
apostrophe ends the quote early and turns the probe into a syntax error that
silently skips the intake gate.

`--lite`/`--full` (`/spec`), `--workflow` (`/sprint`), `--full` (`/proceed`) and
`--close-out` (`/wrapup`) were always read by the model, so they keep working.

`tools/lint-skills/tests/test_skill_text_portability.py` extracts `/spec`'s gate
fence, substitutes a request holding a backtick, `$HOME`, `$(id)` and an
apostrophe with the rule's spelling, and runs it under bash, zsh, `/bin/sh` and
dash: it must print `intake_gate=1` (AC-2). AC-1's two greps are asserted there too.

## ADR-2: One run-and-read context block per skill (BR-2, OQ-3)

OQ-3 resolved as proposed: the `## Context` heading stays where the `!` lines
were; its body is one instruction sentence and one `sh` fence whose first line
is the marker comment `# adlc-context`. No step number, so nothing collides with
`/proceed`'s Step 0.

Each read is two lines, a label and the command with its notice:

```sh
echo '--- Architecture (.adlc/context/architecture.md)'
cat .adlc/context/architecture.md 2>/dev/null || echo 'No architecture context found'
```

Every command ends in `|| echo '<notice>'` (today's notice text), so a missing
file or a non-git directory prints the notice and the fence exits 0. The fences
read nothing under ToolkitRoot and carry no root line, except `/template-drift`,
whose toolkit-listing fence is merged into its context fence (one fence per
skill) and keeps the root line. Fence rules hold: POSIX, no `local`, no bare
`$<digit>`, no `[0]`, no `status=`.

The prose mention of a backticked bang line in `/template-drift` is respelled
("a preamble line"), so that `grep -n '!\`' */SKILL.md` finds only the ETHOS
line (AC-3).

Permissions (BR-15): the commands are `echo`, `cat`, `grep`, `ls`, `test`,
`find`, `pwd`, `which`, `git branch|status|log|worktree|rev-parse|for-each-ref|diff-tree`
and, in `/canary`, `gcloud config get-value` and `gcloud run services list`.
`templates/claude-settings-template.json` gains `Bash(cat:*)`, `Bash(grep:*)`,
`Bash(git rev-parse:*)`, `Bash(git for-each-ref:*)`, `Bash(git diff-tree:*)`,
`Bash(gcloud config get-value:*)` and `Bash(gcloud run services list:*)`; the
CHANGELOG lists each.

The ETHOS line stays byte-identical in every skill (plan M6). A new `ethos-line`
check reads the line from conventions.md "Ethos injection pattern" (the one copy)
and requires it exactly once in every `*/SKILL.md`: a missing line, an altered
one (a line that starts like it but differs) and a duplicate are each a finding.
A missing or unreadable conventions copy is itself a finding, so deleting it
cannot disarm the check.

BR-16's execution test (`test_skill_text_portability.py`): every skill's
`# adlc-context` fence is extracted and run under bash, zsh, `/bin/sh` and dash,
in this repo and in a bare consumer (a temp git repo with no `.adlc/templates/`);
each run must exit 0, and in the consumer each absent file's notice must appear.

## ADR-3: Teton retirement (BR-5)

Removed in one change:

- lint: `check_harness_skip`, `check_provenance_safe_fence`, the
  `missing-harness-line` rule in `check_lesson_check_order`, the `HARNESS_SKIP_*`
  and `PROVENANCE_SAFE_*` constants, their wiring in `run()`, their fixtures and
  tests, and their README items;
- skill text: every `**Provenance-classifying harness (BUG-228):**` and
  `(BUG-230):` paragraph (SKILL.md files, `proceed/` companions,
  `agents/pipeline-runner.md`), `/analyze`'s "Shell on a provenance-classifying
  harness" rule and its Step 1.8/1.9/1.10 skips, every `# provenance-safe`
  marker (the git spellings under them stay), and the Teton Grep alternatives in
  `/review` and `/spec`;
- docs: the "Provenance-classifying harnesses" sections of
  `partials/delegate-gate.md` and `partials/lesson-check.md`, the Teton lines of
  `partials/README.md`, and conventions.md's preamble-grammar (BUG-220) and
  delegating-step (BUG-228) paragraphs.

Kept: the read-only rule for inline audits (now in the dispatch paragraph,
ADR-4), `/analyze` Step 2a's git spellings, and the `adlc-read` timeout
guidance, which moves under `### What a call site does with it` in
`partials/delegate-gate.md` and into conventions.md's Delegation pattern.

AC-5's expected residue is the repo-name set BR-5 lists, plus
`tools/dataset/denylist.json` and `tools/dataset/detectors.py`, which REQ-671
added after the spec: both name the `teton-code` repository as a scrub target,
a repo name, not a harness. Lessons and bugs under `.adlc/` are not edited.

## ADR-4: One dispatch paragraph, one check (BR-3, BR-4, BR-12, OQ-5)

The canonical block in conventions.md "Agent dispatch patterns" (between the
existing `<!-- dispatch-fallback-sentence -->` markers, kept so no reader moves)
becomes the portable paragraph: the spec's leading sentence, then REQ-669's
name-form guidance, then BR-4's absent-directory rule, then the read-only rule.
Every dispatching step carries it, copied whole.

A second block, `<!-- dispatch-requires-subagents -->`, holds `/sprint`'s
explicit-stop line: the step needs a harness that can run subagents, and stops
and says so otherwise; it carries the same name-form guidance.

`dispatch-fallback` is renamed `dispatch-has-fallback` and widened:

| Mention | Owed in the same step |
|---|---|
| a toolkit agent named as dispatched (REQ-669's three shapes) | the canonical paragraph, or the explicit-stop block |
| any other instruction to dispatch: "using the Agent tool", or `launch`/`dispatch`/`spawn` … `agents` naming no toolkit agent ("Launch Explore agents", "launch 3 agents using the Agent tool") | the leading clause "If this harness can run subagents", or the explicit-stop block |

Negations, fenced lines and cross-references stay non-mentions, as today.
`/bugfix`'s Explore dispatch has no checklist file, so it carries the leading
clause with "trace the bug yourself with your harness's search and read tools"
as its inline arm (BR-3).

OQ-5 resolved with a reasoned alternative to the proposal: no third form. The
canonical inline arm ("run each checklist inline from `.adlc/agents/<name>.md`")
already describes `/proceed` Phase 4's sequential behaviour, because the
`task-implementer` file is the implementation checklist that an in-context run
follows. One block keeps the check a single comparison.

`/analyze`'s condensed inline checklist is dropped (BR-3); its no-agent path is
the paragraph, plus the kept read-only rule.

## ADR-5: `no-harness-path` absorbs `toolkit-path` (BR-13)

The `toolkit-path` machinery (surfaces, walk, arming, file and tree exceptions,
`_scan_surfaces` shared with `builtin-collision`) is kept and renamed; the check
id becomes `no-harness-path`. Spellings widen:

- **Markdown families** (`*/SKILL.md`, `proceed/phase*.md`, `agents/*.md`,
  `partials/*.md`): any home path of the five harnesses: `~/.claude`,
  `$HOME/.claude` in every brace form, and the same for `.codex`, `.copilot`,
  `.gemini` and `.cursor`.
- **Code families** (`partials/*.sh`, `tools/**`, `workflows/*.js`, `presets/*`,
  `templates/*`): `toolkit-path`'s `.claude/skills` and `.claude/agents`
  spellings plus the four other harness homes. A general `~/.claude` in code
  stays `adlc-home`'s.

Exceptions, one list (`TOOLKIT_PATH_EXCEPTIONS` lifted whole, plus): one more
default-expansion token, `${ADLC_HOME:-$HOME/.claude}` (REQ-654's machine-state
default); a line carrying an `adlc-home:` marker of a valid kind (in Markdown as
an HTML comment, `<!-- adlc-home: claude-code -->`); a whole-line HTML
comment in Markdown (the rendered agent `model:` header); and
`tools/adlc/harness_probe.py`, whose §6 probes edit those harnesses' user files
by design, as the doctor inspects the symlink install by design.

**Why `adlc-home` is not folded in (the reasoned alternative to "subsumes").**
`adlc-home` judges machine-state literals in *code*, with a docstring rule and a
marker vocabulary specific to code; `no-harness-path` judges harness paths in
*text*, and toolkit or foreign-harness paths in code. After this change the two
partition the space: a general `~/.claude` in code is only `adlc-home`'s,
everything else only `no-harness-path`'s, and the marker is one mechanism both
honour. Folding them would rewrite REQ-654's suite for no change in what is
caught; the spec's aim, one exception list per kind of path, holds.

The remaining prose literals are rewritten to `${ADLC_HOME:-$HOME/.claude}/…`
(machine state), or keep the literal with the marker naming its kind (Claude
Code's projects directory, `claude-code`; the compatibility aliases, `alias`).
So that each line is reported once, `adlc-home` leaves a code line holding a
toolkit path (`.claude/skills`, `.claude/agents`) to `no-harness-path`.

## ADR-6: Agents vendored into `.adlc/agents/` (BR-8, BR-9)

`/init` Step 6 copies `"$ADLC_TOOLKIT_ROOT/agents"/*.md` into `.adlc/agents/`
(all of them, by glob, overwriting: canonical wins), and its
`<!-- sync-surfaces: init -->` block gains `agents`. ToolkitRoot is the source on
both routes, which satisfies REQ-669 BR-9 ("keeps `$ADLC_TOOLKIT_ROOT/agents/` as
the second source"). No harness is configured to discover agents there.

`/template-drift` gains Step 3f, `agents`, in partials posture (`synced`,
`stale`, `missing`, `missing upstream`, no customization classification), and
its sync-surfaces block lists it. `SYNC_SURFACES` and `INIT_COPIED_SURFACES`
gain `agents`. A copy that differs only in the rendered `model:` line reports
`stale` (BR-9).

AC-8 is tested by extracting `/init`'s agents copy and `/template-drift`'s
Step 3f fence and running them in a temp consumer: synced, then stale after an
edit, then every agent missing after the directory is deleted.

## ADR-7: `description-budget` and `skills-ref` (BR-7, BR-11, OQ-1, OQ-2)

OQ-1 resolved as proposed: `DESCRIPTION_BUDGET = 512` Unicode code points
(`len(str)`, never bytes). The check parses the `description:` value (quoted or
bare), reports each skill over the budget, and prints the sum to stderr.
`adversary` (535) and `template-drift` (1105, grown since the spec) are trimmed,
keeping every "Use when" phrase a user types.

OQ-2: the validator is not installed on this machine, and an unattended run does
not download one, so the question cannot be answered by running it. Decision:
`argument-hint` stays a top-level key, because Claude Code reads it there and
moving it under `metadata:` would remove the hint on Claude Code (a BR-15
behaviour change). The `skills-ref` check therefore validates a copy of each
skill directory, staged under the system temp directory, whose frontmatter
omits the keys in `SKILLS_REF_HARNESS_KEYS` (`argument-hint`); the directory
name is preserved, so a `name:` mismatch still fails (AC-10). With `skills-ref`
not on PATH the check prints one SKIP line naming `pip install skills-ref` and
adds no finding. The installed-path run is a manual verification item, recorded
in the PR (the spec's resolved OQ-6).

## ADR-8: Lane-check defaults (BR-10)

`DEFAULT_BLOCKED_PATHS` gains `.adlc/agents/**`, `.github/agents/**` and
`.github/hooks/**` in the "pipeline and agent config" group. The pinning list
gains `.github/agents/x.md`, `.github/hooks/adlc.json` and
`.adlc/agents/reflector.md`, and a new parametrised test asserts, for each of the
eight BR-10 globs, that the glob is in the tuple and that an example path under
it produces `("blocked-path", path)`. `partials/lane-check.md`'s defaults list
names the same paths.

## Files

| Area | Files |
|---|---|
| Skills | every `*/SKILL.md`; `proceed/phase-4-implementation.md`, `proceed/phases-lite.md`, `proceed/phases-1-3-validation.md`, `proceed/phases-6-8-ship.md` |
| Agents | `agents/pipeline-runner.md` |
| Lint | `tools/lint-skills/check.py`, `tools/lint-skills/README.md`, `tools/lint-skills/tests/**` |
| Lane | `tools/adlc/lane_check.py`, `tools/adlc/tests/test_lane_check.py`, `partials/lane-check.md` |
| Partials docs | `partials/README.md`, `partials/delegate-gate.md`, `partials/lesson-check.md`, `partials/forge.md` |
| Templates | `templates/claude-settings-template.json` |
| Docs | `.adlc/context/architecture.md`, `.adlc/context/conventions.md`, `README.md`, `CHANGELOG.md` |

## Task graph

```
TASK-179 retire the Teton surface
   └─ TASK-180 one dispatch paragraph, dispatch-has-fallback
TASK-181 argument prose
TASK-182 context blocks + ethos-line
TASK-183 description-budget + skills-ref
TASK-184 no-harness-path
TASK-185 agents vendoring + lane defaults
TASK-186 docs, README, CHANGELOG   (after every other task)
```

## Risks

- A widened `dispatch-has-fallback` can fire on prose that is not an
  instruction. Mitigation: REQ-669's must-not-fire cases stay pinned, and the
  check runs clean on the finished tree with a non-vacuity assertion.
- The context fence adds one shell call per skill invocation on Claude Code; a
  consumer whose `.claude/settings.json` predates this REQ prompts for `cat` and
  `grep` until it takes the template's additions. The CHANGELOG says so.
- AC-14's end-to-end Claude Code runs and AC-10's installed-validator run are
  manual; the PR lists them as open verification items.

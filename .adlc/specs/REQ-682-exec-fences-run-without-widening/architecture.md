# Architecture — REQ-682: skill fences run under `/sprint --exec` without widening

## Evidence first

The spec left three questions open and said the design must not rest on them until they were run. They were run on 2026-11-09 against the installed `claude` 2.1.316, in throwaway directories under the session scratchpad. Every launch passed BUG-260's isolation flags (`--setting-sources "" --settings <file> --strict-mcp-config`). The verdicts below come from files that did or did not appear, and from each refusal message in the launch's stream-json record (LESSON-768). No verdict rests on model prose. `~/.claude.json` had 319 project entries before the probes and 319 after.

| # | Allow rule(s) | Command | Result | Refusal text (abridged) |
|---|---|---|---|---|
| 1 | `touch p-plain:*` | `touch p-plain` | ran | — |
| 2 | same | `touch p-plain; touch p-compound` | refused | the second statement is checked on its own |
| 3 | same | `… && touch p-and`, or a newline | refused | same |
| 4 | same | `X=1 touch p-plain-envprefix` | refused | an env-prefixed command is not admitted by the bare rule |
| 5 | same | `touch p-plain-sub-$(echo x)` | refused | "A nested command … can't be checked before it runs" |
| 6 | same | `touch 'p-plain-q;touch p-quoted'` | refused, one statement | a `;` inside quotes does not split; matching reads the raw, quoted text |
| 7 | same | `touch p-plain-redir > f` | refused | "Output redirection … needs approval" |
| 8 | same | `if [ -d . ]; then touch p-plain-if; fi` | refused | the inner statement is checked |
| 9 | `. <tk>/:*` | `. <tk>/ok.sh` | refused | "'.' evaluates arguments as shell code", **even with a matching allow** |
| 10 | same | `. <tk>/../evil.sh`, `. <tk>/fn.sh && pfn` | refused | same |
| 11 | `<tk>/runner:*` | `<tk>/runner a` | ran | — |
| 12 | same | `<tk>/runner-evil` | refused | the prefix stops at a word boundary |
| 13 | same | `Y=1 <tk>/runner env` | refused | env prefix |
| 14 | `ADLC_TOOLKIT_ROOT=:*`, `PROBE_ENV=:*` | `ADLC_TOOLKIT_ROOT=x touch …`, `PROBE_ENV=1 touch …` | refused | the env prefix is stripped and `touch` is judged on its own |
| 15 | allow `PROBE_ENV=:*`, deny `touch p-denied:*` | `PROBE_ENV=1 touch p-denied` | refused **by the deny** | a deny sees through an env prefix |
| 16 | `cp:*`, `touch:*`, `mkdir:*` | each, aimed outside the working directory | refused | "The path is outside the working directories" beats the allow |
| 17 | `sed:*` | `sed -i … <out>/../work/a` | refused | "Path contains '..' traversal" |
| 18 | `Write` (bare) | Write tool, a file outside the working directory | **written** | — |
| 19 | (init record) | skills and agents loaded under `--setting-sources ""` | **no toolkit skill or agent** | `skills` lists only Claude's built-ins, and `agents` lists only `claude`, `Explore`, `general-purpose`, `Plan` and two others |

What this settles:

- **Compound commands are checked per statement** (rows 2, 3, 8). The spec's first assumption holds.
- **No allow can admit sourcing** (rows 9–10). A narrow-allow route is impossible, not merely risky.
- **An absolute-path prefix rule is a usable boundary** (rows 11–13). It admits that one executable with trailing arguments, and refuses a sibling name, an env prefix, `$(…)` and a compound tail.
- **The two fence allows the exec tier carries today are inert** (rows 9 and 14). `Bash(if [ -f .adlc/partials/:*)` and `Bash(ADLC_TOOLKIT_ROOT=:*)` admit nothing a fence needs, and nothing else.
- **Toolkit skills do not load under BUG-260's isolation** (row 19). The pipeline prompt says to "invoke the `/validate` skill", along with `/architect`, `/reflect` and `/review`. Under `--exec` that instruction cannot work today, whatever happens to fences. The spec's skill assumption is false.
- **A bare `Write` allow writes outside the working copy** (row 18). The exec tier passed bare `Write` and `Edit`, so an exec model could overwrite `<ToolkitRoot>/partials/forge.sh`, which `/sprint approve` then sources with the operator's credentials. This was a shipped hole in REQ-659, of the same class as BUG-260. **BUG-265 fixes it.** The file tools become path-scoped rules for each repo's working copy (plus the close-out's `--add-dir`), with read-only access to ToolkitRoot, and live rows `file-scope-write` and `file-scope-read` prove it. REQ-682 is implemented on a main that holds that fix (ADR-9).

## Approach

Fences run through **one toolkit-owned executable**, `<ToolkitRoot>/tools/adlc/fence-run`. It is admitted by a single absolute-path prefix allow, and it runs only fence text it reads from its own toolkit tree. The model never sources anything. It names a fence by id and supplies placeholder values, which the runner binds as data. The same runner prints the toolkit's skills to the model, with every fence rewritten into a runner call (`fence-run show`), because the skills are not otherwise loaded under isolation.

```
claude -p (exec model)
  └─ Bash: <ToolkitRoot>/tools/adlc/fence-run run validate/SKILL.md#2:3f9a01c2 --arg spec='…'
             │  admitted by Bash(<ToolkitRoot>/tools/adlc/fence-run:*), nothing else
             ▼
        fence-run (stdlib Python, root from its own realpath)
          1. recompute the census from <ToolkitRoot> text; the id must be route=runner, sha must match
          2. transform: root line → literal root; canonical sourcing → toolkit arm only;
             placeholders → "$ADLC_ARG_<name>", each value checked against its pattern
          3. env: inherited env + ADLC_ARG_* + ADLC_FENCE_TOOLKIT_ONLY=1 + ADLC_TOOLKIT_ROOT=<root>
          4. /bin/sh -c '<preload closure by absolute path>; <transformed fence>'
```

The census is computed from toolkit text alone, so there is no manifest file the model could edit, and no environment variable the runner trusts for its integrity. The only things the runner trusts are its own real path and the files under it, which is REQ-659 BR-23a's rule.

### New modules (`tools/adlc/`, stdlib only, Python 3.9)

| Module | Role |
|---|---|
| `fence_census.py` | Extracts every shell fence from the exec file set, assigns ids and routes, holds the placeholder table and the engine and excised tables. Pure: text in, records out. |
| `exec_matcher.py` | Claude's exec-scope matching as the probes measured it. Splits a command into statements, refuses `.`/`source`, `$(…)`, backticks, redirection other than to `/dev/null`, and an env prefix, then runs REQ-657's prefix matcher per statement. Used by the census for `direct` routes and by the policy tests. |
| `fence_run.py` + `fence-run` | The entry point. `run <id> [--arg n=v]… [--arg-file n=path]…` and `show <file>`. The executable is a shell shim (no `python3` first token, `harness_adapter.py:78`) that runs the ONE interpreter (REQ-609) on `fence_run.py`. |

### Who owns which file

| File | Written by | Read by |
|---|---|---|
| `harness/claude/exec-fence-census.json` | `fence_census.py --write` (committed golden) | `test_fence_census.py`, which holds it equal to a fresh census, so a fence whose route changes shows in review |
| the census at run time | recomputed by `fence-run` on every call | `fence-run` only |
| `<runDir>/settings.json` | the orchestrator (unchanged path) | `claude` |

## Decisions

### ADR-1: a content-addressed fence runner, not a narrow allow and not engine pre-runs alone

**Decision.** One executable, admitted by `Bash(<ToolkitRoot>/tools/adlc/fence-run:*)`, runs every fence the model needs that is not `direct`.

**Why.**

- **Narrow allow is ruled out by evidence.** Rows 9–10 show sourcing is refused even with a matching allow. Per-function allows would need sourcing in the same command.
- **Engine pre-runs cannot cover the pipeline.** Most fences take values the model produces mid-run: a lesson set's components, a PR body, a validation target. The engine-run route is kept for the fences whose inputs exist before launch (ADR-6).
- **The runner's boundary is measured.** Rows 11–13 show the allow admits that one path and its arguments, and nothing else. A compound tail is still checked per statement (rows 2–3), so `fence-run …; git push origin HEAD:main` is refused at the push.

### ADR-2: fence identity is `<toolkit-relative path>#<ordinal>:<sha8>`, recomputed on every call

- **Ordinal:** the 1-based index among the shell fences (`sh`, `bash` or `shell` info string) in that file.
- **sha8:** the first 8 hex digits of the SHA-256 of the fence's original text. A skill edited between `show` and `run` fails with a mismatch, instead of running a different fence under the old id.
- **Path:** validated through `toolkit_root.toolkit_file()`, which refuses absolute paths and `..`, and must be in the closed exec file set (ADR-5).
- **Where trust comes from:** `fence-run` recomputes the census from its own tree on each call. A fence whose route is not `runner` is refused with `opaque_entry_refused`, naming its route. That covers `excised` (it does a one-way move), `engine` (the orchestrator did it) and `direct` (run it as written).

Because nothing is cached, there is no state for the model to change. The runner's refusals depend only on toolkit text and the runner's own real path, which satisfies BR-5's last sentence.

### ADR-3: values are data, bound by name and checked by pattern

- **Placeholder shapes.** The runner rewrites a placeholder only in three token shapes: `"<name>"`, `'<name>'` and a bare `<name>` delimited by blanks. Each becomes `"$ADLC_ARG_<name>"`. A placeholder in any other position, for example inside a longer quoted string, makes the fence **unroutable**. The census reports it, and BR-8 stops the build.
- **The placeholder table.** `fence_census.PLACEHOLDERS` maps each name to a full-match pattern. Examples: `id` → `^(REQ|BUG|TASK|LESSON)-[0-9]{3,6}$`; `bug` → `^\.adlc/bugs/BUG-[0-9]{3,6}-[a-z0-9-]+\.md$`; `component` → `^[A-Za-z0-9_./-]+$` with no `..`; `flag` → a `skill-flag.sh` path under `$TMPDIR`.
  - The table is closed. A placeholder name it does not list makes the fence unroutable.
  - A value that fails its pattern is refused before anything runs.
  - A value is never spliced into code. It reaches the fence as an environment variable, expanded once, inside double quotes.
- **Repeated flags.** A `--flag "<name>"` pair whose prose says "one per …" may be bound several times. The runner expands the pair once per value. That is the only list form the runner supports.
- **Long values.** `--arg-file name=<path>` reads a value from a file the model wrote, such as a PR body. The path must resolve, after `realpath`, to a regular file under the working directory, and is capped at 1 MiB. `show` tells the model to use `--arg-file` for any value that holds a quote or a newline. A quoted newline is the one argument shape the probes did not measure.

### ADR-4: toolkit-only partial resolution — preload first, gate the arms preload cannot reach

The fence's own sourcing line is rewritten to the toolkit arm, but partials source other partials through their own working-copy arms. The examples are `lessons.sh:32-33` (`forge.sh`), `forge.sh:69` (`adlc-home.sh`), `id-alloc.sh:90`, `id-recheck.sh:101,162`, `delegate-tools-path.sh:28-33` and `emit-step-telemetry.sh:64-69`. `forge.sh:224-227` also runs the working copy's `tools/adlc/forge_config.py` before the toolkit's.

The runner does two things:

1. **It preloads by absolute path,** the way `exec_safety.partial()` already does (`exec_safety.py:413-436`). It sources `adlc-home.sh`, then `forge.sh`, then the fence's partials, in the dependency order the census records. Every nested arm whose guard is `command -v <fn>` then skips.
2. **It sets `ADLC_FENCE_TOOLKIT_ONLY=1` in the fence's environment,** set by the runner itself after it builds that environment. The arms that preload cannot reach test this flag and take the toolkit path: the `forge_config.py` resolver, `delegate-tools-path.sh`'s cwd-relative `tools/delegate`, `emit-step-telemetry.sh`'s repo-local arm, and any `id-*` arm without a function guard.

With the flag unset, every one of those arms behaves exactly as it does today, so interactive use is unchanged (BR-10). The `unguarded-source` lint learns this one gated variant of the canonical spelling. Its rule otherwise stays byte for byte.

A decoy test proves the closure is complete. It plants a sentinel-writing copy at every working-copy arm (`.adlc/partials/*.sh`, `tools/delegate/*`, `tools/adlc/forge_config.py`, `.adlc/tools/adlc/forge_config.py`), runs every `runner` fence, and asserts that no sentinel is written. Coverage is not argued from a list.

### ADR-5: skills reach the model through `fence-run show`, from a closed set

- **The set.** `fence_census.EXEC_FILES` is a closed tuple: the pipeline sources `exec_prompt.py` already inlines, plus the skills the delivered text sends the model to. Those are `validate/SKILL.md` (Phases 1 and 3), `architect/SKILL.md` (Phase 2), `manifest/SKILL.md` (Phase 0's advisory), `review/SKILL.md` (Phase 5's superseded lookup), `spec/SKILL.md` (cited for the LessonSet scoring rule) and the close-out sections of `wrapup/SKILL.md`. The set also takes each `references/*.md` those skills name, and the agent files the text dispatches: the six Phase-5 agents, `task-implementer`, `lite-reviewer` and `test-auditor`. `/reflect` is not in the set, because no `proceed/` file names it.
- **Agents run inline.** The exec prompt drops the "SUBAGENT MODE" line (`exec_prompt.py:277-279`), so the model dispatches agents by name. Toolkit agents do not load under isolation either (row 19). Dispatched by name, an agent fails, or runs as a generic agent without its checklist, which is the silent failure the dispatch paragraph warns about. The notes therefore tell the model that toolkit agents are not loaded, and to run each agent's checklist inline from `fence-run show agents/<name>.md`, as the existing dispatch-fallback paragraph already allows. This also takes the open question of whether an `Agent`-tool subagent inherits the parent's allow and deny out of the pipeline's path. It stays a live row (`subagent-scope`), because the `Agent` tool remains allowed.
- **The build check.** The prompt build extracts every `/<skill>` the delivered text tells the model to invoke, and every `agents/<name>.md` it names. A name missing from `EXEC_FILES` fails the build (BR-8). The set cannot silently lag the text (LESSON-712).
- **What `show` prints.** `show <file>` prints the file with each fence replaced by its route's form:
  - a `runner` fence becomes a runner call with `--arg name='<name>'` stubs;
  - a `direct` fence prints unchanged;
  - an `engine` or `excised` fence becomes one plain line saying who does it and why.

  `show` refuses any file outside the set.
- **The prompt notes.** The unattended block's notes (`_EXEC_NOTES`) say that toolkit skills and agents are not loaded in this session. Wherever the text says to invoke `/x` or follow `agents/x.md`, the model runs `fence-run show …` and follows the output.
- **The `Skill` tool.** It stays in `allow_tools`. Under isolation it can only load Claude's built-ins (row 19), and dropping it would change nothing measurable.

### ADR-6: four routes, three of them closed tables

| Route | How a fence gets it | What the model sees |
|---|---|---|
| `direct` | every statement is admitted, as written, by `exec_matcher` over the ExecPolicy. Example: `ls -t .adlc/knowledge/lessons` | the fence, unchanged |
| `runner` | it passes ADR-3's transforms, ADR-7's reach audit, and has every placeholder in the table | a `fence-run run <id>` call |
| `engine` | its id is in `fence_census.ENGINE`, a table keyed by `id` with a reason. Examples: the Phase-0 `git -C <repo-path> fetch`, `worktree list` and `worktree add` fences, which `sprint_exec.py`'s prepare step already does | one line: "the orchestrator already did this: <reason>" |
| `excised` | its id is in `fence_census.EXCISED`, or its text holds a BR-24 empty-allowlist token (`adlc_forge_pr_merge`, `gh pr merge`, …) or a deny-tier spelling the static scan finds | one line: "this does not run under --exec: <reason>" |

A fence that fits none of these is **unrouted**. `exec_prompt` raises `ExecPromptRefused`, a subclass of `PromptRefused`, naming the fence id and the first statement `exec_matcher` refuses. `sprint_exec.py` records that as `exec_prompt_refused` at the three prompt call sites (`:483`, `:1036`, `:1448`). No model is launched.

The committed golden `harness/claude/exec-fence-census.json` lists every id with its route and its placeholders. It turns "a new fence was added to `/review`" into a reviewable diff, rather than something discovered on a live run.

### ADR-7: reach is audited by two checks — a static closure scan and a stubbed run with hostile values

`test_exec_reach.py` runs in CI.

- **The static check.** It builds a function index over `partials/*.sh` (name → body, file:line), takes the transitive call closure of every `runner` fence, and scans it. It looks for every deny-tier spelling (`templates/permissions.yml` deny, plus `harness/claude.yml` `engine_deny`, plus the BR-24 tokens) and for every construct that runs data as code (`eval`, `sh -c "$…"`, `. "$var"` with a non-literal operand).
  - A call to a name that is neither in the index nor in a closed table of external commands fails, so a new function starts refused (BR-4, LESSON-781).
  - A hit fails, naming the fence, the function and the line.
- **The dynamic check.** For every `runner` fence × every placeholder × every BR-6 hostile value, it runs `fence-run` with `ADLC_FORGE_MOCK=1` and recording stubs for `git`, `gh`, `az` and `curl` first on `PATH`. It then matches every recorded argv against the deny tier with `exec_matcher`'s deny side.
- **Declared reach.** The reach records sit beside the census in the golden. Each is the observed external commands per fence, so a change in reach is a diff too.
- **One declared reach is not a branch move.** That is the id-reservation push, `git push origin <oid>:refs/adlc/ids/<kind>/<n>` from `id-alloc.sh:397`. The amended BR-2 excludes it from the deny tier: it is a non-force push of a new ref under `refs/adlc/ids/`, and it moves no branch. Only the close-out allocates ids.
  - The reach record for each allocation fence names that push.
  - The audit checks every recorded push. Each must be non-force, its destination must match `^refs/adlc/ids/(req|bug|lesson|assume|task)/[0-9]{3,6}$`, and its source must be an object id, never a branch.
  - A recorded push to any other destination fails the audit.
  - With that, the close-out's two allocation fences (`wrapup/SKILL.md` Step 4, `adlc_alloc_id`) are `runner`.

  The close-out's transcript-discovery fences, which its rule 4 says to skip, are `excised` with that reason. Its other fences take the pipeline's route.

### ADR-8: the policy change in `harness/claude.yml`, and why `fence_broad_spelling` retires through `fence_unmatchable`

- **Two allows are removed** from the exec tier: `allow_extra: [ADLC_TOOLKIT_ROOT=]` and the exec render of `fence.partial-source` (`if [ -f .adlc/partials/`). Both are inert (rows 9, 14), and reporting `widened` for an entry that matches nothing is what BR-7 forbids.
- **One allow is added** through a new key, `exec.fence_runner: tools/adlc/fence-run`. `tiers()` spells it as `Bash(<root>/tools/adlc/fence-run:*)`, with `<root>` from `toolkit_root()`. It is resolved once, like `{branch}`.
  - `vet_extra` accepts it only if the resolved path is absolute, matches `^[A-Za-z0-9_./-]+$`, exists as a regular file under the root, and does not leave the root after `realpath`.
  - A root that fails the check refuses the launch. A space in the path is refused rather than quoted, because a quoted path does not match a prefix rule (row 6).
- **`fence_broad_spelling`.** The loader requires the key unless `capabilities.fence_unmatchable: "yes"` (schema 4, `harness_adapter.py:769-779`). Claude now has evidence for that flag (row 9), so `claude.yml` sets it and drops the key.
  - **Constraint:** the project-scope verdict for `fence.partial-source` must stay `inexpressible`, and `test_harness_lints.py:30`'s counts must hold (AC-7).
  - If setting the flag moves the project render, the flag is applied to exec scope only, and the key stays for project scope.
  - Copilot and Codex keep their keys. Their exec adapters are REQ-662's.
- **The opener ban grows.** `harness_adapter.py:72-78` and `vet_extra` refuse `.`, `source` and `[` as first tokens. `Bash(. :*)` and `Bash(source:*)` pass today.

### ADR-9: one prerequisite fix and two spec amendments, all settled 2026-11-09

- **The prerequisite: BUG-265.** Bare `Write` and `Edit` in `exec.allow_tools` wrote anywhere (row 18). While they stayed bare, neither BR-3's "no path the exec model can write" nor REQ-659 BR-23's trust in the toolkit install could hold. BUG-265 replaces them with `exec.file_rules`, scoped per root.
  - It changes `ExecAdapter.tiers()` to `tiers(branch, config_extra, write_roots, read_roots)`, and TASK-248 builds on that signature.
  - Implementation starts from a main that holds BUG-265. This branch is rebased onto it before TASK-243 starts.
- **Amendment A (applied to BR-2 and BR-4).** BR-2 and BR-4 hold for what this REQ adds: the runner, its fences, and every route. The declared-residual list gets no longer.
  - **Why.** The tier already admits code-running commands: `awk` (`system()`), `sed` (`e`), `find -exec`, `npx`, `npm run`, and the REQ's own test runner. These are REQ-657 BR-18's declared residuals. As first written, BR-2 made each one an OpaqueEntry with unbounded reach, which no route could satisfy.
  - **What does not change.** Rule B still makes them tolerable. The approval ledger, the pinned merge and the scoped child credentials are the gate.
- **Amendment B (applied to BR-2).** The id-reservation push is named as non-deny reach (ADR-7), so the close-out can allocate lesson ids under exec.

## Sequence: a `runner` fence mid-run

1. The model meets a fence in `fence-run show validate/SKILL.md`. It shows as `fence-run run validate/SKILL.md#2:3f9a01c2 --arg spec='<spec>'`.
2. The model substitutes the value and calls Bash. Claude checks one statement against the runner allow, and it is admitted.
3. `fence-run` recomputes the census and checks the id, the route and the sha. It validates `spec` against its pattern, transforms the fence and builds the environment.
4. It runs `/bin/sh -c '. <root>/partials/adlc-home.sh; . <root>/partials/forge.sh; …; <fence>'`, with the fence's stdout, stderr and exit code passed through.
5. On a refusal, it exits 3 with one stderr line: `opaque_entry_refused: <id>: <reason>`. Refusal stays loud (BR-9). The model reports it, and the run ends `blocked` or `denied` as the pipeline's gate protocol says.

## Testing

| Layer | File | Covers |
|---|---|---|
| matcher | `tools/adlc/tests/test_exec_matcher.py` | rows 1–15 as fixtures, each probe command with its verdict (rows 16–18 are Claude's path checks, which a command matcher does not model; BUG-265's live rows pin them), so the model of Claude's matching is pinned to what was measured; the `.`, `source` and `[` opener ban |
| census | `tools/adlc/tests/test_fence_census.py` | every fence routed; golden equality; covers the pipeline, close-out and every invoked skill or agent; an injected unrouted fence raises `ExecPromptRefused`; the unmodified tree raises nothing |
| runner | `tools/adlc/tests/test_fence_run.py` | id, sha and route checks; transforms; hostile values; `--arg-file` bounds; refusals; the delegation environment |
| reach | `tools/adlc/tests/test_exec_reach.py` | the static closure scan and the stubbed dynamic run; fixtures that add `gh pr merge` or `git push --force` to an admitted function fail |
| decoys | `partials/tests/fence-toolkit-only.test.sh` | ADR-4's sentinel decoys at every working-copy arm; with the flag unset, interactive arms unchanged |
| engine | `test_exec_prompt.py`, `test_exec_adapter.py`, `test_exec_launch.py`, `test_harness_framework.py` | rewritten prompts, the new tier, `exec_prompt_refused`, retired keys |
| live | `tools/adlc/tests/e2e/claude-exec-live.sh` | AC-1's rows, through the engine's own argv and isolation flags, plus `subagent-scope`: a built-in `general-purpose` subagent asked to run a command the parent's tiers deny is refused, with no sentinel |

The fixtures that exist today are `exec_helpers.Sandbox`, the fake harness, `ADLC_FORGE_MOCK` with its store, and the per-test `gh` and `az` shims in `partials/tests/forge.test.sh`. There is no shared recording stub for `git`, `gh`, `az` and `curl`, so TASK-246 adds one (`tools/adlc/tests/recording_stubs.py`) for the reach and hostile-value tests. The `install` fixture in `test_exec_prompt.py:31-41` copies only `proceed/`, `wrapup/` and `sprint/SKILL.md`. The census tests need a copy that holds every `EXEC_FILES` entry, plus `partials/` and `agents/`.

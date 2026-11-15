---
id: BUG-269
title: "The exec engine's `git -C * push --force` denies were inert on claude: a glob rule that ends in `:*` matches nothing"
status: open
severity: medium
created: 2026-11-10
updated: 2026-11-10
component: "adlc/tools/adlc/exec-adapter"
domain: "adlc"
stack: ["python", "yaml"]
concerns: ["security", "correctness"]
tags: ["exec-engine", "allowlist", "deny", "wildcard", "git-c", "matcher-model", "live-run", "claude-code"]
introduced_by: ["REQ-659", "REQ-682"]
attribution: derived
---

## Description

The claude adapter's `exec.engine_deny` lists `git -C * push --force` and `git -C * push -f` (`harness/claude.yml`, REQ-659 BR-8). `ExecAdapter.spell()` rendered each as `Bash(git -C * push --force:*)`. Claude Code 2.1.316 never matches a rule that holds a `*` and also ends in `:*`, so both denies were inert.

The matcher model had the same blind spot. `tools/adlc/exec_matcher.py` is the toolkit's model of how claude judges a command at exec scope. It modelled that rule as matching, and before judging a deny it stripped `git -C <path>`, which Claude does not do. So `admits()` and `policy_problems()` called a policy sound when Claude would run the command. `fence_census` and the reach tests use those two calls. A `git -C` allow would have let `git -C <wc> reset --hard` and the other git denies run, and the model would have refused them.

**No committed rule set is exposed today.** Neither the project allowlist (`harness/claude/rendered/settings.json`) nor the `/sprint --exec` tiers (`ExecAdapter.tiers()`) holds an allow that matches a `git -C …` command. Claude matches an allow against the raw text, so `Bash(git push:*)` and `Bash(git status:*)` do not admit `git -C <dir> push --force`. Such a command therefore prompts in a project session and is refused headless. The finding that started this is REQ-664's `ask-tier-deny/wrapped-allow` failing on 2.1.316 (PR #263). That probe allows `Bash(git -C:*)` itself, so it measures a placement neither rule set uses.

## Reproduction Steps

All runs on 2026-11-10, against the installed `claude` 2.1.316, logged in, in a throwaway repo under the session scratchpad that pushes to a throwaway local bare remote. Every launch used the engine's isolation flags: `claude -p --output-format json --setting-sources "" --settings <file> --strict-mcp-config`. Each prompt asked for one command, run once as written. The verdict is whether the ref appeared on the bare remote, together with the result's `permission_denials`. `~/.claude.json` held 323 project entries before and after.

| Row | Allow | Deny (or ask) | Command | Result |
|---|---|---|---|---|
| l0 | `git push:*` | `git push --force:*` | `git push --force origin HEAD:refs/heads/l0` | refused (control) |
| l1 | `git push:*` | — | `git -C <repo> push --force origin …` | refused: no allow matches the `-C` form |
| l2 | `git push:*` | `git push --force:*` | `git -C <repo> push --force origin …` | refused |
| l3 | `git push:*` | ask `git push --force:*` | `git -C <repo> push --force origin …` | refused (the project placement) |
| l5 | `git status:*`, `git push` | — | `git -C <repo> push --force origin …` | refused (the exec placement) |
| l6 | `git -C:*` | — | `git -C <repo> push --force origin …` | **ran** (control) |
| l4 | `git -C:*` | `git -C * push --force:*` | `git -C <repo> push --force origin …` | **ran**: the deny is inert |
| w4 | `git -C:*` | `git -C * push --force:*` | `git -C . push --force origin …` | **ran** |
| w6 | `git -C:*` | `git -C * push:*` | `git -C <repo> push --force origin …` | **ran** |
| w1 | `git -C:*` | `git -C * push --force *` | `git -C <repo> push --force origin …` | refused |
| x1 | `git -C:*` | `git -C * push --force *` | `git -C . push --force` (bare) | **ran**: ` *` needs an argument |
| w2 | `git -C:*` | `git -C *` | `git -C <repo> push --force origin …` | refused |
| w3 | `git -C:*` | `git -C:*` | `git -C <repo> push --force origin …` | refused |
| w5 | `git push:*` | `git push origin +*` | `git push origin +HEAD:refs/heads/w5` | refused |
| y1 | `git -C:*` | `git -C * push --force*` | `git -C . push --force` (bare) | refused |
| y2 | `git -C:*` | `git -C * push --force*` | `git -C . push --force origin …` | refused |
| y3 | `git -C:*` | `git -C * push --force`, `git -C * push --force *` | `git -C . push --force` (bare) | refused |
| y4 | `git -C:*` | `git -C * push --force*` | `git -C . push origin …` | ran (the glob is not too wide) |

## Expected Behavior

The engine's `git -C` force-push denies refuse `git -C <path> push --force` and `-f`, bare or with arguments. The matcher model refuses a command only where Claude was measured to refuse it.

## Actual Behavior

The rendered `Bash(git -C * push --force:*)` and `Bash(git -C * push -f:*)` matched nothing. The model treated them as matching, and treated every deny as seeing through `git -C <path>`.

## Environment

- Platform: macOS (Darwin 27.2.0)
- Version: claude 2.1.316; toolkit main at `2cecd6c`

## Root Cause

Prior lessons consulted:
- LESSON-844 — A tool rule with no path in it admits every path: scope a harness's file tools by root, and spell each root the way the model will write it (score 6)
- LESSON-796 — An engine's allowlist is not the harness's policy: the harness merges every settings source it reads, so narrowing the engine's flags alone narrows nothing (score 6)
- LESSON-782 — Do not commit a test that says a file is unchanged against origin/main: it passes on main and fails the next REQ that may edit it (score 3)
- LESSON-854 — A harness's trust gate can drop a project's allows while still loading its hooks: pass rules a launch needs through the harness's session flag, and keep in the project file only the placement under test (score 2)
- LESSON-845 — A reach audit of code the permission check cannot see must follow every executable a fence runs through a variable; a stubbed run is what finds the one the static reading missed (score 1)

None of these describes this failure. The nearest is LESSON-716, cited in `exec_matcher`'s docstring: the model never says yes on a guess. Here the model guessed the other way: it said a rule refused a command, and no run had ever measured that.

`ExecAdapter.spell()` (`tools/adlc/exec_adapter.py:111`) treats a spelling specially only when it ends in `*`. Every other spelling gets the adapter's `shell_rule`, `Bash(%s:*)`. A spelling with a `*` in the middle therefore comes out with both an inner glob and the `:*` prefix suffix. Claude 2.1.316 reads such a rule as matching nothing (rows l4, w4, w6). The same pattern without `:*` works, whether as `X *` (w1), `X*` (y1, y2) or a trailing `+*` (w5). Nothing measured the spelling when REQ-659 added the denies. The only test of it was `test_exec_matcher.py::test_wildcard_rule_text`, which checks the toolkit's own regex.

`exec_matcher.Rule` compiled an inner `*` to `.*` whether or not the rule ended in `:*`. `_deny_views()` added a `git -C <path>`-stripped view of every statement, and `explain()` and `admits()` judged denies against it. That view is right for `deny_hits()`, an audit meant to find a deny-tier move in any spelling. It is wrong for admission: REQ-664's `wrapped-allow` on 2.1.316 shows that a plain-spelling deny does not stop the `-C` form.

The bug was latent because no allow in either tier matches `git -C`. Every `git -C` call already fell through to Claude's default, which prompts in a project session and refuses in a headless one. The engine denies are defence in depth for an allow that does not exist yet. The model's job is to warn when one is added, and both defects made it fail at that job.

`git blame` on the root-cause lines names two REQs. REQ-659 shipped the engine denies and `spell()`; REQ-682 shipped the matcher model. The operator chose both: the defect needed both REQs, the inert spelling and the model that called it working.

## Resolution

- `ExecAdapter.spell(argv, exact, deny)` gives a deny that holds an inner `*` a trailing `*` of its own instead of `:*`: `Bash(git -C * push --force*)`. That glued form matches the bare command and any arguments (y1, y2), and leaves a non-force `-C` push alone (y4). `X *` was rejected: it misses the bare command (x1). An allow keeps its old spelling. A glob allow is inert on claude today, and the glued form would also admit `--forcefoo`, so only a deny changes.
- `exec_matcher.Rule` marks a prefix rule with an inner `*` as `inert` and matches nothing with it. A non-prefix rule's `*` is a glob over any characters.
- `exec_matcher._deny_views(text, git_c=False)`: admission (`explain`, `admits`, so `policy_problems`) judges a deny against the statement as written and with its env prefixes stripped (row 15), never with `git -C <path>` stripped. `deny_hits` still asks for the `git -C` view.
- `claude-exec-manual.md` records the live rows. The `harness/claude.yml` comment says how the glob denies are spelled.

### Question 2: should claude emit `git -C *` deny spellings at project scope?

No. `capabilities.git_c_spelling` lists the `git -C` **allow** prefixes a harness renders. copilot, codex and antigravity carry `[[git, -C]]`. The render then tests each deny's `git-c` form against that allow, and omits the allow unless `deny_under_allow.git-c` reads `pass` from REQ-664's `wrapped-allow` (the README "Consumer mapping"; REQ-655, REQ-656, REQ-662). claude's `git_c_spelling: []` renders no `git -C` allow, so every `git -C` call already prompts, and a `git -C` ask would change nothing. The 2.1.316 `wrapped-allow: fail` is the reason `[]` must stay. The engine's own `git -C` denies remain as exec-scope defence in depth, and now work.

## Files Changed

- `tools/adlc/exec_adapter.py` — `spell()` takes `deny` and spells a glob deny without `:*`; `tiers()` passes `deny=True`
- `tools/adlc/exec_matcher.py` — inert glob-plus-`:*` rules; no `git -C` view in admission; docstring rows
- `tools/adlc/tests/test_exec_adapter.py` — `test_deny_superset` pins the glob spelling and that no deny holds both an inner `*` and `:*`; new `test_glob_spelling_is_deny_only`
- `tools/adlc/tests/test_exec_matcher.py` — `test_wildcard_rule_text` pins rows l4, w1, w6, x1, y1, y2, y4; new `test_a_deny_does_not_see_through_git_c`; `Bash(git -C:*)` added to the widened-allow fixture
- `harness/claude.yml` — comment on the glob engine denies
- `.adlc/research/harness-probes/claude-exec-manual.md` — the live rows

## Regression Test

Regression tests: off for this project (`.adlc/config.yml` does not exist). The four new or changed tests failed against the unfixed source: `test_wildcard_rule_text`, `test_a_deny_does_not_see_through_git_c`, `test_deny_superset` and `test_glob_spelling_is_deny_only`, with 78 other tests passing. With the fix, all of them pass. The full suite (`pytest tools/adlc/tests`, throwaway `HOME` and `ADLC_HOME`) ran 1891 passed, 2 skipped and 1 failed: `test_exec_approve.py::test_rebase_mismatch_pushes_nothing`, which refused with "REQ-902 is blocked" during the 19-minute run. That test touches neither the matcher nor `spell()`, and it passes when run alone.

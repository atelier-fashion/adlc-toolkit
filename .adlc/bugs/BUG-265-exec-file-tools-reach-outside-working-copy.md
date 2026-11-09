---
id: BUG-265
title: "`/sprint --exec` gave the model bare `Write`, `Edit` and `Read`: it could overwrite the toolkit the orchestrator later runs"
status: resolved
severity: high
created: 2026-11-09
updated: 2026-11-09
component: "adlc/tools/adlc/exec-adapter"
domain: "adlc"
stack: ["python", "yaml"]
concerns: ["security", "correctness"]
tags: ["exec-engine", "allowlist", "file-tools", "path-scope", "write", "read", "toolkit-trust", "approve-gate", "live-run"]
introduced_by: ["REQ-659"]
attribution: derived
---

## Description

The claude adapter's exec block (`harness/claude.yml:99`) put the file tools in the allow tier as bare names: `Read, Write, Edit, Glob, Grep`. A bare tool name in Claude Code's allow list admits that tool on any path, so the exec model's `Write` and `Edit` reached outside its working copy.

That defeats the trust the orchestrator places in the toolkit (REQ-659 BR-23: the orchestrator never runs code a harness could write). On the symlink install, ToolkitRoot is the primary clone behind `~/.claude/skills`. An exec model could overwrite `<ToolkitRoot>/partials/forge.sh`, and `/sprint approve` then sources that file with the operator's own credentials. The same reach covers `~/bin/adlc`, a shell rc file, or `~/.ssh/authorized_keys`. A bare `Read` lets the model read `~/.ssh` and put it in a PR body.

The shell is not affected. Claude refuses `cp`, `touch`, `mkdir`, `cat`, `grep`, `head`, `find` and `ls` outside the working directories even when an allow rule matches. Only the file tools needed their own scope.

## Reproduction Steps

All runs on 2026-11-09, against the installed `claude` 2.1.316, in throwaway directories under the session scratchpad. Each launch used the engine's isolation flags: `claude -p --setting-sources "" --settings <file> --strict-mcp-config --output-format stream-json --verbose`.

1. Use a settings file whose allow list holds the bare `Write` (as the exec tier does), and set cwd to a working directory `work/`.
2. Ask the model to `Write` `outside/t-write`. **The file is written**, outside the working directory.
3. In the same launch, `cp`, `touch` and `mkdir` aimed at `outside/` with matching allows are refused: "The path is outside the working directories for this session".

## Expected Behavior

The exec model's file tools write only inside the run's working directories, and read only those directories plus the toolkit tree it is told to read.

## Actual Behavior

`Write` and `Edit` write anywhere the operator's user can write. `Read` reads anywhere the operator's user can read.

## Environment

- Platform: macOS (Darwin 27.2.0)
- Version: claude 2.1.316; toolkit main at `7250000`

## Root Cause

Prior lessons consulted:
- LESSON-796 — An engine's allowlist is not the harness's policy: the harness merges every settings source it reads, so narrowing the engine's flags alone narrows nothing (score 14)
- LESSON-756 — A framework proven on one adapter has only proven that adapter's branches — audit what the second one reaches first, because those paths have never run (score 9)
- LESSON-777 — Test a per-path grant against the key the harness actually reads: Claude keys a linked worktree's trust at the main repo root (score 8)
- LESSON-779 — A rule that withholds an allow can withhold a step the pipeline cannot run without: compare the render with the calls the pipeline makes (score 8)
- LESSON-769 — A project default carried into a user-level render widens to every project: re-ask what each key means at the scope it lands in (score 8)

`ExecAdapter.tiers()` (`tools/adlc/exec_adapter.py:139-143`) starts the allow tier with `allow_tools` verbatim from the adapter. `harness/claude.yml:99` lists the file tools there as bare names. Bare names carry no path, so the rule admits every path. The tier was written as if `--allowedTools Write` meant "write in the working copy", the way Bash writes are confined, but the path check that confines Bash does not confine a file tool that an allow admits by name.

This is the BUG-260 class (LESSON-796), one layer over. That bug was about which settings sources the harness merges. This one is about what a single rule admits: a rule with no path in it admits every path.

The fix has to keep two pipeline steps working (LESSON-779):

- **The close-out** writes the primary repo's `pipeline-state.json` through its `--add-dir` (`wrapup/SKILL.md`, close-out rule 3; `sprint_exec.py:1459`).
- **A cross-repo run** writes every repo's working copy, not only the primary's.

Both must be write roots.

**Validated with live probes** (claude 2.1.316, the engine's isolation flags, the dogfood layout with the working copy at `<tk>/.worktrees/REQ-x`). The allow list was `Edit(//<wc>/**)` plus `Read(//<tk>/**)`, with no bare file tool. The table reads one probe row per line:

| Action | Result |
|---|---|
| `Write`, `Edit` inside the working copy | allowed |
| `Write` to `outside/` | refused: "Claude requested permissions to write" |
| `Edit` of `<tk>/partials/f.sh` | refused; the file was unchanged |
| `Write` through `<wc>/../` | refused |
| `Write` through a symlink out of the working copy | refused |
| `Read` of `<wc>` and `<tk>` | allowed |
| `Read` of `secret/key.txt` | refused |
| Control: the same `Write` inside the working copy, with no `Edit` rule | refused, so the scoped rule is what admits it |
| `cat`, `grep`, `head`, `find`, `ls` on `secret/`, with matching Bash allows | refused by Claude's own path check |
| `cat` of `<tk>/partials/readme.txt` | allowed: the `Read` rule extends shell reads too |

`Glob` and `Grep` are not tools in 2.1.316, so their names in `allow_tools` were inert.

## Resolution

No exec launch admits a file tool by name any more. Each one is a path-scoped rule.

- **The adapter.** `harness/claude.yml`'s `allow_tools` keeps only the tools that touch no file (`Agent`, `Skill`, `TodoWrite`). A new `file_rules` block holds the file tools as rules with a `{root}`: `Edit(/{root}/**)` plus `Read(/{root}/**)` per write root, and `Read(/{root}/**)` per read root.
- **The loader.** It refuses a bare file tool in `allow_tools`, and a file rule with no `{root}`, so no adapter can bring the bare form back.
- **The tiers.** `ExecAdapter.tiers()` takes `write_roots` and `read_roots`. It refuses a root that is not a plain absolute path (a glob, a space, `..`, `.`, an empty segment, a trailing `/`), because a root becomes a gitignore-style pattern. It emits each root under both its given and its real spelling, because Claude matches a rule against the path as written: a live row's write to `/var/...` was refused by a rule on `/private/var/...`.
- **The launches.** The pipeline launch passes every repo's working copy as a write root. The close-out passes its own working copy and its `--add-dir` (the primary repo's spec dir, where close-out rule 3 writes `pipeline-state.json`). Both pass ToolkitRoot as the read root.

**Verified.**

- `claude-exec-live.sh`'s new `file-scope-write` and `file-scope-read` rows pass on claude 2.1.316 through the engine's own argv. The only recorded denial in the write row is the write outside the working copy.
- The eight existing rows are unchanged: seven pass, and `fence` still fails, which is REQ-682.
- `~/.claude.json` held 319 project entries before and after.

**Regression tests.** They were written before the fix. Against the unfixed tree they failed on `assert 'Read' not in ['Read', 'Write', 'Edit', 'Glob', 'Grep', 'Agent', ...]` (the launch) and `assert [] == ['Edit(//…close-out/**)']` (the close-out). With the fix they pass. This project's regression-test mode is `off`, so no `regression_tests` field is recorded.

## Files Changed

- `harness/claude.yml` — `allow_tools` loses the file tools; new `file_rules`.
- `tools/adlc/harness_adapter.py` — `EXEC_FILE_TOOLS`; refuses a bare file tool and a root-less file rule; `file_rules` in `_EXEC_KEYS`.
- `tools/adlc/exec_adapter.py` — `_ROOT_RE`, `file_rules()`, `tiers(write_roots, read_roots)`.
- `tools/adlc/sprint_exec.py` — the pipeline and close-out launches pass their roots.
- `tools/adlc/tests/test_exec_adapter.py` — scoped rules, the loader refusal, unsafe roots, the two-spelling rule; `test_deny_superset` no longer pins bare `Read`/`Edit`.
- `tools/adlc/tests/test_exec_launch.py` — `test_launch_scopes_file_tools`.
- `tools/adlc/tests/test_exec_approve.py` — `test_close_out_scopes_file_tools`.
- `tools/adlc/tests/e2e/claude-exec-live.sh` — roots in the engine argv, a real-path `$T`, and the `file-scope-write` and `file-scope-read` rows.
- `tools/adlc/README.md`, `README.md`, `.adlc/research/harness-probes/claude-exec-manual.md` — the scope, the rows and the probe findings.
- `CHANGELOG.md` — the Fixed entry.
- `.adlc/knowledge/lessons/LESSON-844-a-tool-rule-with-no-path-admits-every-path.md` — the lesson.

## Deployment

n/a: the toolkit is not deployed. It is live on each machine through its install, so the fix takes
effect on the next `/sprint --exec` launch after `main` is pulled.

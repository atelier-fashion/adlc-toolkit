# Architecture — REQ-707: a `runner-prefix` variant for `fence-vs-allowlist`

## Where it lands

Everything goes into the two files REQ-664 built. No new module is added.

| File | Change |
|---|---|
| `tools/adlc/harness_probe.py` | the thirteen runner launches in `_VARIANTS["fence-vs-allowlist"]`; `_prepare_runner`; the runner branch of `_observe`; `decide_runner_prefix`; the runner branch of `_decide_probe` |
| `tools/adlc/tests/fake_harness/fake_harness_impl.py` | the `per-statement`, `split-ask` and `first-statement-only` flags; `asked_commands` learns the witness-then-fence prompt |
| `tools/adlc/tests/test_harness_probe_unit.py` | `decide_runner_prefix` over hand-built `Obs` maps; stub content; allow sets |
| `tools/adlc/tests/test_harness_probe_e2e.py` | the fake scenarios of AC-2 to AC-8, on all six profiles |
| `tools/adlc/README.md`, `README.md`, `CHANGELOG.md` | BR-11 |

## Decisions

### ADR-1: thirteen launch variants, one decided sub-result, outside the disjunction

`_VARIANTS["fence-vs-allowlist"]["*"]` becomes the three existing variants followed by
`RUNNER_LAUNCHES`. Those are the thirteen names in REQ-707 BR-3, in table order, with
`runner-baseline` before the refusal controls. The run order of a probe's launches is the
tuple's order, so `runner-positive` and `runner-baseline` run before any control. A
reader of a half-finished run sees them first.

`_decide_probe` gains a `fence-vs-allowlist` branch:

1. The three existing variants are decided exactly as today, with `decide_plain` on the
   `effect` sentinel. Their disjunction is the probe-level `status` (REQ-707 BR-1).
2. The thirteen runner launches go to `decide_runner_prefix(observed)`. It returns
   `(Verdict, subs)` the way `decide_ask_tier_deny` does.
3. `sub_results` is the union: the three variants, the thirteen launch sub-results, and the
   decided `runner-prefix`.

**Why not a separate probe id.** REQ-662 BR-11 and AC-24 were amended to read
`fence-vs-allowlist`'s `runner-prefix` variant, and REQ-664's coverage map ties §6.11 to
that one id. A new probe id would need a second amendment to REQ-662 and a second §6.11
entry, for no gain.

**Why outside the disjunction.** The probe-level `status` answers REQ-664's question:
does a partial-sourcing fence match an allow? On `claude` it is `fail`, and the runner
route exists because of that. Folding `runner-prefix` in would flip it to `pass` and
make the old answer unreadable.

### ADR-2: the stubs sit outside the repository, as ToolkitRoot sits outside the working copy

- `RunnerStub` is `<run_dir>/tk/fence-run`, and `TailStub` is `<run_dir>/tk/fence-run-x`.
- Both are outside `repo/` and `wt/`, matching where `<ToolkitRoot>/tools/adlc/fence-run`
  sits relative to an exec working copy. A harness that refuses to run an executable
  outside its workspace then reads `fail` on `runner-positive`. That reading is true of
  the real runner too.
- `_prepare_runner` writes both stubs fresh before each launch, mode `0755`, through the
  existing `_write_text(..., executable=True)`. `_reset` removes `<run_dir>/tk/` and every
  runner sentinel, so a stub from one launch never serves the next (REQ-664 BR-16).
- Each stub writes `"$0"`, then its arguments one per line, then `X=${X-unset}`, to a
  sentinel under the repo's `.probe/` (`_sent(repo)`). The `X` line is how
  `runner-env-prefix` tells a harness that ran the prefixed command from a model that
  dropped the prefix. `fence-run` exits 1 when its first argument is `fail`, which
  `runner-or` needs, because `a || b` runs `b` only when `a` fails. This mirrors how the existing sentinels are named, so
  the stale-state check already covers them. Each stub's body names only its own
  sentinel path, as a literal, and reads no environment variable.
- `runner-redirect`'s target is a third path under `.probe/`, the "redirect sentinel". It
  is distinct from both stub sentinels, so a redirect that wrote it is told apart from a
  stub that ran.
- The paths are checked against `_SAFE_PATH` in `_prepare_runner` before the first launch,
  and a failure raises `ProbeError`, as an unquotable temp root does today.

### ADR-3: prompts follow `ask-tier-deny`'s two-command shape

Every runner launch asks for two things:

> Run `touch <witness>` on its own, then run `<asked>` as a separate command, then reply
> with the nonce reversed and nothing else. The nonce is <n>.

`runner-newline` cannot put its command in backticks, so its prompt is:

> Run `touch <witness>` on its own, then run this fenced block exactly as written, as one
> command, then reply …

followed by a `sh` fence of two lines.

The witness allow is `Rule("touch <witness>", exact=True)`, added to the routine set.
`touch` is already routine, so the exact rule only matters on a harness whose profile
renders no routine set. The witness answers the one question BR-4 needs: did the model
act at all?

### ADR-4: one per-launch rule, then the variant rule

Each launch is decided by `decide_variant` (REQ-664's three-way rule plus the witness),
read as follows:

| `decide_variant` | the launch was |
|---|---|
| `fail` (effect present) | admitted |
| `pass` (effect absent, witness present, ask reached) | refused |
| `unknown` | unknown, with that reason |

For `runner-positive` and `runner-baseline`, the effect is the runner sentinel. For the
controls, it is the sentinel BR-3's table names. `runner-env-prefix`'s effect is a runner
sentinel holding `X=1`.

A refusal control that `decide_variant` reads as refused is then held to REQ-707 BR-4's
`ask-split` rule, in `read_runner_launch(obs, asked)`. It stays refused only if:

- the runner sentinel is absent; or
- `asked` appears in `obs.evidence`'s captured output or session record, either raw or as
  `json.dumps(asked)[1:-1]` (the JSON-escaped form a tool record carries).

Otherwise the control is `unknown` with the reason `ask-split`. This is the one decision
input that reads the harness's own record. It only ever downgrades a refusal to
`unknown`; it never upgrades anything to `pass`. A record format the check cannot see
into fails toward `unknown`, which is the safe side for a hard gate (LESSON-716).

`decide_runner_prefix` then applies REQ-707 BR-5 in order: positive, baseline, refusal
half. The launch sub-results are recorded with the words `admitted`, `refused` or
`unknown` in their `reason`, and their status is the verdict their row produces for the
gate (an admitted control reads `fail`). So a reader of `sub_results` never has to invert
a status in their head.

`evidence` on `runner-prefix` carries `boundary`, `admitted` and `refused` (the
Verdict row of the System Model).

### ADR-5: what ran is recorded, not inferred

`_observe`'s runner branch adds three things to the launch's evidence:

- the contents of each stub sentinel that exists (its argv, scrubbed with `scrub`);
- which of the runner, tail and redirect sentinels exist;
- whether the witness exists.

The harness's own tool record is already in `stdout_tail` and `stderr_tail` via
`_launch_evidence`. Together these answer BR-6's question. The runner sentinel's argv
shows whether the stub received `probe` or the whole compound line, and the tail
sentinel's `$0` shows how the tail was invoked. No transcript parser is added.

### ADR-6: the fake's `per-statement` flag is its own small matcher, plus two model-habit flags

`fake_harness_impl.verdict()` keeps its current body. Under the new `per-statement` flag
it first refuses a command line holding any of:

- `$(`
- a backtick
- an output redirection other than `>/dev/null` or `2>/dev/null`
- a leading `NAME=` assignment

It then splits the line on `;`, `&&`, `||`, `|`, `&` and newlines, outside quotes, with a
character scan of about thirty lines. It returns `run` only if every statement is matched
by an allow under the existing `matches()`, with no deny. Otherwise it returns `refused`.

- `matches()` already enforces a word boundary (`cmd.startswith(text + " ")`), so
  `runner-sibling` is refused in both modes.
- Without the flag, `run_command` still splits on `&&` only, so plain `perform` refuses
  `runner-and` and admits the other compound shapes. AC-3 pins exactly that set.

Two more flags play the model habits that BR-4's `ask-split` rule guards against:

- `split-ask` runs only the text before the first `;`, `&`, `|`, `>` or newline, with any
  leading `NAME=` dropped and `$(…)` and backtick spans removed. It is a model tidying the
  command, and it writes no tool record of the full line.
- `first-statement-only` records the whole asked line in its tool record, then runs only
  its first statement. It is a harness that refuses the tail but runs the head.
- The fake imports nothing from `exec_matcher` (REQ-707 BR-8, AC-8). A test asserts it
  by reading the module's import lines.

`asked_commands` learns one more prompt shape: backticked commands followed by a fenced
block. It yields the backticked commands and then the whole fence as one asked command,
whose match text is the whole fence (not its first line), so that `per-statement` judges
both lines. The existing "Run this fenced block exactly as written" shape is unchanged.

### ADR-7: the thirteen launches stay separate

The spec's second Open Question asked whether `runner-semicolon` and `runner-and` should
fold into one launch to save quota. They stay separate. Each control already shares one
`TailStub`, so a folded launch could not say which separator carried the tail. And on a
harness where the first refusal ends the run (LESSON-767), the first separator's refusal
would hide the second. Thirteen launches is the cost of a hard gate. BR-12's pre-launch count
shows it before any launch.

The first Open Question, whether to add `.` and `source` launches, is answered no.
REQ-662 BR-3 bans those openers on every harness, so no gate reads them.

## Testing

| Layer | Covers |
|---|---|
| unit | `decide_runner_prefix` over hand-built `Obs` maps: every row of BR-5, including `runner-baseline` `unknown`, a single admitted control, and a control `unknown` with none admitted; `read_runner_launch`'s `ask-split` rule (runner present without the asked line on record, raw and JSON-escaped forms, the `X=unset` case); stub bodies; the allow set of each launch holding exactly one rule that names the stub; `_SAFE_PATH` refusal |
| e2e (fake) | AC-2 (`perform` + `per-statement`, six profiles); AC-3 (`perform`); AC-4 (`split-ask`, `first-statement-only`); AC-5 (`runs-all`, a withheld runner allow, `refuse`, `no-witness`, `refuse-silent`); AC-7 (probe-level status unchanged, `merge_only` tests unchanged); AC-8 (fresh state, cleanup, the user's `fence-run` untouched, no `exec_matcher` import) |
| lint | `bash tools/lint-skills/check.sh`; `sh partials/tests/run.sh` under four shells (no partial changes, run for AC-9) |

REQ-664's existing AC-7 test (`test_harness_probe_e2e.py:270`) asserts the three
variant names. It is updated to assert the three plus `runner-prefix` and the thirteen
launch names, and its fixed launch counts grow by thirteen. Each such change is named in the PR.

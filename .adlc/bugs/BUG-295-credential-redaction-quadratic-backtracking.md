---
id: BUG-295
title: "Three arms of the credential chains backtrack quadratically, or worse, on one long line: in Python and in the Space's JavaScript, not in macOS sed or grep"
status: open
severity: medium
created: 2026-11-23
updated: 2026-11-23
component: "adlc/tools/adlc/credential-redact"
domain: "adlc"
stack: ["python", "shell", "javascript", "regex"]
concerns: ["performance", "security", "availability"]
tags: ["redaction", "credential-regex", "backtracking", "quadratic", "redos", "posix-ere", "regex-portability", "scaling-test"]
introduced_by: []
attribution: none
---

## Description

The toolkit carries two credential chains, each a POSIX ERE written for `sed -E` or `grep -E`:

- the five-arm intake chain (`adlc_intake_redact` in `partials/intake.sh`), copied into `tools/adlc/credential_redact.py` (`INTAKE_PATTERN`), `tools/adlc/harness_probe.py`, `tools/delegate/emit-telemetry.sh`, the `/proceed`, `/wrapup` and `agents/delegate-pre-pass.md` fences, and, through `space/build.mjs`, `space/toolkit-data.js`;
- the wide chain (`_alc_cred` in `partials/lesson-check.sh`), copied into `credential_redact.py` (`WIDE_PATTERN`).

`tools/adlc/tests/test_credential_redact.py` holds the Python copies equal to the shell text. Three arms of those chains have a repeat that can start at any character of a long run. An engine that backtracks re-reads the run from every start, so the cost grows with the square of the line's length, and with its cube where two such repeats sit either side of a keyword:

| Arm | Chain | The repeat |
|---|---|---|
| `[A-Z_]+_(API_KEY\|TOKEN)…` | intake | the name before `_API_KEY` or `_TOKEN` |
| `[A-Za-z_]*(secret\|password\|passwd\|api_key\|token)[A-Za-z_]*…=…` | wide | the identifier on each side of the keyword |
| `eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.` | wide | the JWT header |

REQ-672's security re-audit met the first two on 2026-11-23 and worked around them in `tools/launch/recording_check.py` by reading each line in 2,000-character windows. The patterns were left as they were.

## Reproduction Steps

1. `python3 -c 'import sys,time; sys.path.insert(0,"tools/adlc"); import credential_redact as cr; s="token"*2000; t=time.time(); cr.WIDE_PATTERN.sub("x", s); print(time.time()-t)'` from the repo root, on `main` at `da5b465`. It does not return in a minute.
2. The same with `cr.INTAKE_PATTERN` and `s="AB_"*13334` (40,000 characters): 4.2 s. With 10,000 characters: 0.27 s.
3. In Node: `require('./space/intake.js').redact('AB_'.repeat(26667), require('./space/toolkit-data.js'))` takes 2.4 s; a quarter of that line takes 0.16 s.

## Expected Behavior

Four times the line costs about four times the CPU, in every engine a copy of the chains runs in.

## Actual Behavior

Measured on `main` at `da5b465`, one line per input, `subn` over the whole chain. Seconds at 5,000, 20,000 and 80,000 characters; `>20` means stopped at 20 seconds. Linear is ×4 from one column to the next.

Python 3.9.6, `re`:

| Chain | Line | 5,000 | 20,000 | 80,000 | 20k / 5k |
|---|---|---|---|---|---|
| `INTAKE_PATTERN` | `Ab_` repeated (letters and underscores) | 0.000 | 0.000 | 0.001 | linear |
| `INTAKE_PATTERN` | `AB_` repeated (capitals and underscores) | 0.065 | 1.065 | 17.048 | ×16.4 |
| `INTAKE_PATTERN` | `token` repeated | 0.000 | 0.000 | 0.001 | linear |
| `INTAKE_PATTERN` | `_TOKEN` repeated | 0.087 | 1.365 | >20 | ×15.8 |
| `INTAKE_PATTERN` | `A` × n, then `_API_KEY` | 0.024 | 0.399 | 6.361 | ×16.3 |
| `WIDE_PATTERN` | `Ab_` repeated | 0.346 | 5.631 | >20 | ×16.3 |
| `WIDE_PATTERN` | `AB_` repeated | 0.354 | 5.625 | >20 | ×15.9 |
| `WIDE_PATTERN` | `token` repeated | >20 | >20 | >20 | did not finish |
| `WIDE_PATTERN` | `_TOKEN` repeated | >20 | >20 | >20 | did not finish |
| `WIDE_PATTERN` | `A` × n, then `_API_KEY` | 0.401 | 6.288 | >20 | ×15.7 |
| `WIDE_PATTERN` | `eyJ` repeated | 0.297 | 4.733 | >20 | ×16.0 |
| `WIDE_PATTERN` | letters, `token`, then blanks | 0.110 | 1.760 | >20 | ×15.9 |

Each arm was then compiled and timed alone, on the same lines and on `://a:b:b:…`. Three of the nineteen arms are superlinear, and no other:

| Arm | Line | 5,000 | 20,000 | 80,000 |
|---|---|---|---|---|
| intake, assignment | `AB_` repeated | 0.060 | 0.982 | >8 |
| wide, assignment | `Ab_` repeated | 0.330 | 5.070 | >8 |
| wide, assignment | `token` repeated | >8 | >8 | >8 |
| wide, JWT | `eyJ` repeated | 0.007 | 0.117 | 1.852 |

Node v26.7.0 (V8), `space/intake.js` `redact` with the generated intake chain:

| Line | 5,000 | 20,000 | 80,000 |
|---|---|---|---|
| `AB_` repeated | 0.012 | 0.156 | 2.405 |
| `_TOKEN` repeated | 0.017 | 0.237 | 3.811 |
| `A` × n, then `_API_KEY` | 0.017 | 0.164 | 2.419 |
| `Ab_` repeated, `token` repeated | 0.001 | 0.002 | 0.006 |

macOS `/bin/sh`, `/usr/bin/sed -E` through the real `adlc_intake_redact`, and `LC_ALL=C grep -nE` with the real `_alc_cred`, as `_alc_scan` runs it: linear on all nine lines. Wall time, process start included: `sed` 0.007 to 0.008 s at 5,000 characters and 0.009 to 0.014 s at 80,000; `grep` 0.006 to 0.007 s and 0.022 to 0.040 s. At 100,000 and 400,000 characters `sed` used 0.008 and 0.027 s of CPU on `AB_` repeated, and `grep` 0.041 and 0.140 s on `token` repeated. macOS `sed` and `grep` do not backtrack on these expressions.

So the engines are: Python `re` superlinear on three arms; V8 superlinear on the one of them it runs; macOS `sed` and `grep` linear on all. GNU `sed` and `grep` were not measured: no Linux machine or container was available.

Who runs the superlinear copies:

- `tools/dataset` scrubs every line of every exported artifact with both chains, and its residue pass searches with both.
- `tools/launch/recording_check.py` searches a recording with both, in windows. `tools/launch/adoption_snapshot.py` and `quickstart_e2e.py` redact short text with both.
- `tools/delegate/run_outcome.py` redacts each free-text field with the intake chain.
- `tools/adlc/harness_probe.py` redacts transcripts with its own copy of the intake chain.
- The Space redacts whatever a visitor pastes, in the visitor's browser, on the main thread.

None of these reads text an attacker gains by slowing, and ordinary prose never has a 5,000-character run of letters. A minified file, a base64 line without digits, or a pasted blob does.

## Environment

- macOS 27.2.1 (Darwin 27.2.0), arm64. Python 3.9.6. Node v26.7.0. `/usr/bin/sed` and `/usr/bin/grep` as shipped.
- Toolkit `main` at `da5b465`.

## Root Cause

Prior lessons consulted:
- LESSON-735 — A sed regex ported to JavaScript must keep sed's matching rules, not just its syntax: one line at a time, and the longest match across alternatives
- LESSON-873 — A probe effect built from two side effects can be met by two separate commands: tie it to the admitted command's own output, and never read a refusal from a step the shell runs before the command
- LESSON-744 — Credential redaction chains match inside ordinary identifiers — validate identifier fields by format instead of redacting them
- LESSON-716 — A validator for a format another reader consumes must parse the way that reader does — enumerate last-wins keys, key spellings and continuations, and fail closed on anything it cannot see
- LESSON-619 — A harness that executes lines extracted from markdown is an execution surface — gate on a token allowlist, and never cite the lint as the control

LESSON-735 is this failure's neighbour, and its remedy is half of this one. It says a regex moved from `sed` to another engine must keep `sed`'s matching rules as well as its syntax, and names two: one line at a time, and the longest alternative. This bug is a third thing that does not travel with the syntax: cost. `sed` and `grep` on macOS read a line once whatever the expression. `re` and V8 try each start in turn and, at each, each way a repeat can give characters back. LESSON-744 describes what the chains match inside ordinary identifiers; the fix keeps that set as it is, and the table of real shapes includes its `task-` slug. The other three are about other surfaces.

The mechanism, for `[A-Z_]+_(API_KEY|TOKEN)` on a line of n capitals and underscores:

1. At start 0, `[A-Z_]+` takes the whole run, n characters.
2. `_(API_KEY|TOKEN)` does not follow, so the repeat gives back one character at a time and tries again: n steps.
3. No match at start 0. The engine moves to start 1 and does the same over n − 1 characters.

That is n²/2 steps. The wide chain's assignment arm has the same repeat in front of its keyword and another behind it. On `tokentoken…` every start finds a keyword at each of n/5 places, and from each the trailing repeat runs to the end of the line and gives it back: n³ over a constant. The JWT arm starts only at `eyJ`, so it needs a line dense in `eyJ` to show, and then each start reads to the end of the run looking for the dot.

An unbounded repeat alone is not the fault: `sk-[A-Za-z0-9_-]{20,}` has one and is linear, because it fails only when fewer than twenty characters follow. The three arms share two properties: the repeat can begin at any character of a run, and what must follow it is usually absent.

The chains were written for `sed` (REQ-415, REQ-646) and are linear there. The cost arrived with each port to a backtracking engine, and no port was timed: the pins compare text and output on short lines.

Attribution: `git blame` on the root-cause lines returns one REQ per copy, six in all, so none is written (the `/bugfix` rule for two or more candidates): REQ-671 (`tools/adlc/credential_redact.py` 28 to 48), REQ-594 (`partials/intake.sh` 366), REQ-646 (`partials/lesson-check.sh` 524), REQ-664 (`tools/adlc/harness_probe.py` 111 to 126), REQ-424 (`tools/delegate/emit-telemetry.sh` 56) and REQ-670 (`space/toolkit-data.js` 46). The copies that backtrack came from REQ-671, REQ-664 and REQ-670.

## Resolution

Each of the three repeats is bounded, in the shell source and in every copy a test holds equal to it: `partials/intake.sh`, `partials/lesson-check.sh`, `tools/adlc/credential_redact.py`, `tools/adlc/harness_probe.py` and the generated `space/toolkit-data.js`.

| Arm | Before | After |
|---|---|---|
| intake, assignment | `[A-Z_]+_(API_KEY\|TOKEN)` | `[A-Z_]{1,64}_(API_KEY\|TOKEN)` |
| wide, assignment | `[A-Za-z_]*(…)[A-Za-z_]*` | `[A-Za-z_]{0,64}(…)[A-Za-z_]{0,64}` |
| wide, JWT | `eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.` | `eyJ[A-Za-z0-9_-]{1,255}\.eyJ[A-Za-z0-9_-]+\.` or `[A-Za-z0-9_-]{255}\.eyJ[A-Za-z0-9_-]+\.` |

With a bound of k, a start costs at most k steps, so a line costs k times its length.

Why a bound and not an anchor for the two assignment arms. ERE has no lookbehind, so "the name starts at a word boundary" can only be written as `(^|[^A-Z_])` in front, and that character becomes part of the match: `export GITHUB_TOKEN=x` would redact to `export[REDACTED]`, and every differential test against the real `sed` would change. A bound changes nothing for a name of 64 characters or fewer, and real names are far shorter: `AWS_CONTAINER_AUTHORIZATION_TOKEN` is 33 characters and `ACTIONS_ID_TOKEN_REQUEST_TOKEN` is 30.

Why the JWT arm has two forms. A header is usually under 150 characters, but a header that carries a key or a certificate chain runs to thousands, and POSIX guarantees a repeat count only up to 255 (macOS `grep` refuses `{1,256}`: "maximum repetition exceeds 255"). So the first form reads a header of up to 255 characters, exactly as before. The second reads a longer one by its end: exactly 255 header characters, then `.eyJ`, the payload and its dot. An exact count gives nothing back, so a start reads 255 characters and stops, wherever in a run it is. The second segment keeps its `+`: once a header and `.eyJ` have matched, at most 86 starts share one segment.

The second form was first written as `(^|[^A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{255,}\.…`, a long header anchored to the start of a word. An independent review of the diff showed what that missed: a long-header JWT straight after a letter, which is where it sits after a terminal colour code (`\x1b[32m`) or inside a JSON string after `\n`. It also took the character in front of the header into the match. The exact count replaced it before anything was committed.

What the bounds change, each pinned by `test_bug_295_what_the_bounds_change`:

- A name longer than 64 characters keeps its head and loses its value: 70 capitals, `_TOKEN=` and a value redact to six capitals and `[REDACTED]`.
- An assignment whose keyword is followed by more than 64 identifier characters before the `=` is no longer read by the wide chain. An identifier of 71 characters or more with its keyword at the front is not a shape seen in real input.
- A JWT whose header is longer than 255 characters is still found, wherever it sits. In a substitution the match now starts 255 characters before the header's dot, so the head of such a header stays in the text. The payload is replaced as before, and the signature was never part of the match.
- The second JWT form does not ask for `eyJ` at its start, so 255 header characters followed by `.eyJ`, a payload and a dot match with no `eyJ` in front. The old arm needed one somewhere in the run.

`tools/launch/recording_check.py`'s windowed scan is removed: the fix makes it unnecessary. It was also hiding credentials. A shape longer than a window is whole in none of them, and `test_a_credential_longer_than_2000_characters_is_found` shows a JWT with a 3,000-character payload returning no hit before this change. The check now reads each line whole, one line at a time, as the chains' shell originals do.

After the fix, same machine, same lines. Seconds at 5,000, 20,000 and 80,000 characters:

| Engine | Chain | Line | 5,000 | 20,000 | 80,000 |
|---|---|---|---|---|---|
| Python `re` | `INTAKE_PATTERN` | `AB_` repeated | 0.002 | 0.008 | 0.030 |
| Python `re` | `INTAKE_PATTERN` | `_TOKEN` repeated | 0.002 | 0.009 | 0.034 |
| Python `re` | `INTAKE_PATTERN` | `A` × n, then `_API_KEY` | 0.001 | 0.003 | 0.011 |
| Python `re` | `WIDE_PATTERN` | `Ab_` repeated | 0.011 | 0.043 | 0.172 |
| Python `re` | `WIDE_PATTERN` | `token` repeated | 0.047 | 0.190 | 0.769 |
| Python `re` | `WIDE_PATTERN` | `_TOKEN` repeated | 0.041 | 0.166 | 0.664 |
| Python `re` | `WIDE_PATTERN` | `A` × n, then `_API_KEY` | 0.012 | 0.047 | 0.187 |
| Python `re` | `WIDE_PATTERN` | `eyJ` repeated | 0.010 | 0.040 | 0.161 |
| Python `re` | `WIDE_PATTERN` | letters, `token`, then blanks | 0.006 | 0.026 | 0.104 |
| Node (V8) | intake, `space/intake.js` | `AB_` repeated | 0.002 | 0.004 | 0.015 |
| Node (V8) | intake, `space/intake.js` | `_TOKEN` repeated | 0.002 | 0.005 | 0.017 |
| macOS `sed -E` | intake, `adlc_intake_redact` | `AB_` repeated | 0.012 | 0.029 | 0.095 |
| macOS `grep -nE` | wide, `_alc_cred` | `token` repeated | 0.087 | 0.440 | 1.317 |
| macOS `grep -nE` | wide, `_alc_cred` | `eyJ` repeated | 0.153 | 0.359 | 1.418 |

The Python and Node rows are ×4 from one column to the next. The `sed` and `grep` rows are wall time with process start in them, and are ×5.1 at most. The worst line for Python, `token` repeated, costs about 10 µs a character.

The bound is not free in `sed` and `grep`. They were linear before and are linear now, but a counted repeat is more states for them to carry, so the lines above cost more than they did: `sed` 0.011 s before and 0.095 s after at 80,000 capitals, `grep` 0.040 s before and 1.317 s after at 80,000 characters of `token`. On ordinary prose the difference is smaller: at 400,000 characters `sed` used 0.018 s of CPU before and 0.021 s after, `grep` 0.127 s and 0.263 s. `grep` runs the wide chain over a lesson's frontmatter only, a few short lines.

Weighed and not done:

- **The copies only `sed` runs.** `tools/delegate/emit-telemetry.sh` and the `/proceed`, `/wrapup` and `agents/delegate-pre-pass.md` fences carry the five-arm chain too, and keep `[A-Z_]+`. They measured linear, so they do not have this defect, and bounding them would cost `sed` the constant above for nothing. `test_delegation_tools_untouched` also holds `emit-telemetry.sh` byte-identical to `origin/main` on any branch, and the two skill fences are exec fences whose ids are in `harness/*/exec-fence-census.json`. So `partials/intake.sh` and those four now differ on a name longer than 64 characters: intake leaves the name's head, the others take the whole name. `test_redaction_parity_with_emit_telemetry_sed_chain` still passes. GNU `sed` was not measured; if it backtracks, those four want the same bound.
- **`tools/dataset`'s own patterns.** `detectors.JWT_RE`, `detectors.EXTRA_CREDENTIAL` and three of `residue._EXTRA_CREDENTIAL` measure superlinear too (`EXTRA_CREDENTIAL` did not finish 5,000 characters of `token` repeated in 6 s). They are not copies of the shell chains and nothing pins them to one, so they are left for a bug of their own. Until then the dataset scrub is still superlinear on such a line.
- **`harness_probe.redact` on a line of many matches.** It searches every arm again from each match, so a line of nothing but short assignments costs ×12 for ×4 the input: 0.001 s at 5,000 characters and 0.012 s at 20,000. A different cause, and small.
- **Vendored copies.** A project that ran `/init` has its own `.adlc/partials/intake.sh` and `lesson-check.sh`, and keeps the unbounded regex until it is re-synced. Those copies run only in `sed` and `grep`.
- **A possessive repeat or lookbehind in the Python copy alone.** Either would be linear with no bound. Python 3.9 has no possessive repeat, and both would break the rule that the Python text is the shell text.

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`).

Failing-first tests were still written, before any of the fix. Each scaling test compares two line lengths and asserts a ratio, never a time: ×4 the input may cost at most ×8 the CPU (linear is 4, quadratic 16). The Python ones time each chain in a child with a 45-second limit, because the unfixed chains did not finish some lines at all.

Without the fix (`main` at `da5b465` plus the tests), under a throwaway `HOME` and `ADLC_HOME`:

- `python3 -m pytest tools/adlc/tests/test_credential_redact.py -q`: 18 failed, 13 passed. First failing assertion: `BUG-295: INTAKE_PATTERN on capitals and underscores took 0.2664 s at 10000 characters and 4.2469 s at 40000: x15.9 for x4 the input`. Ten of the fourteen scaling cases then written did not finish in 45 s, among them `WIDE_PATTERN did not finish the word token, repeated at 10000 and 40000 characters in 45 s`.
- `python3 -m pytest tools/adlc/tests/test_harness_probe_pins.py -q -k bug_295`: 4 failed. `BUG-295: redact took 0.2623 s at 10,000 characters and 4.2620 s at 40,000`.
- `node --test --test-name-pattern='BUG-295' space/tests/intake.test.js`: both fail. `capitals and underscores: 44132 µs at 10,000 characters, 641669 µs at 40,000`.
- `/bin/sh partials/tests/intake.test.sh`, on an export of `HEAD` with the new test file: 1 fails, 131 pass. `BUG-295 redact: a 70-character name keeps six characters and loses its value (expected 'AAAAAA[REDACTED] tail', got '[REDACTED] tail')`.
- `python3 -m pytest tools/launch/tests/test_recording_check.py -q -k credential`: `test_a_credential_longer_than_2000_characters_is_found` fails, `assert None == 0`: the windowed scan returns no hit for a JWT with a 3,000-character payload.

With the fix, all of them pass.

The whole-chain run cannot show the JWT bound alone, because the unbounded assignment arm fails every `WIDE_PATTERN` case first. So each bound was also taken out alone, with the other two in place:

- only the JWT arm unbounded: `WIDE_PATTERN: eyJ, repeated` fails, `0.0454 s at 10000 characters and 0.5255 s at 40000: x11.6`; the other 15 cases pass;
- only the repeat after the assignment keyword unbounded: four `WIDE_PATTERN` cases do not finish in 45 s (`the word token, repeated`, `_TOKEN, repeated`, `every keyword, repeated`, `token= then blanks`); six pass;
- only the repeat before the keyword unbounded: not run to the end. It is the reported shape, and the unfixed run covers it.

Tests that pass before and after, and pin the fix from the other side:

- `test_bug_295_match_set_unchanged_on_real_shapes`: 74 real-shaped lines (assignments, prose that only names a variable, kebab and snake identifiers including LESSON-744's `task-` slug, every key shape, JWTs bare, quoted, assigned, glued to a word and after a terminal colour code, long lines of prose, JSON and base64). For each chain, the bounded chain and the chain with the three old arms put back give the same output, the same count and the same spans on every line. Before the fix it fails by design, on `no bounded arm in …`.
- `test_bug_295_match_set_unchanged_on_random_lines_inside_the_bounds`: 4,000 seeded random lines for each chain, built from the chains' own literals and what sits near them, with no identifier run over 64 characters and no header run over 255. Same output and count from the bounded and the unbounded chain on every line. A larger run of the same generator, once, by hand: 119,764 lines, 12,952 replacements, no difference.
- `test_bug_295_lesson_744_false_positive_class_is_unchanged`: `task-ordering-race-in-fixture` still redacts to `ta[REDACTED]`; the snake form and `task-short` are still left alone.
- `test_bug_295_shell_chains_agree_on_real_shapes`: the same table through the real `grep -nE` with `_alc_cred` (the same lines hit as `WIDE_PATTERN`) and the real `adlc_intake_redact` (the same output as `INTAKE_PATTERN`, line for line).
- `test_bug_295_shell_chains_are_linear_in_line_length`: the same ratio for `sed` and `grep`, by the CPU time of the child, at 50,000 and 200,000 characters. On macOS it passes before the fix too; it is there for an engine that does backtrack.
- Five cases in `partials/tests/lesson-check.test.sh`: a 61-character name before the keyword, a 60-character one after it, a JWT with a 300-character header, a JWT glued to a word, and a long-header JWT glued to a word are each rejected.

The wider runs, with the fix, each under a throwaway `HOME` and `ADLC_HOME` built with `env -i`:

- `python3 -m pytest tools -q`: 5924 passed, 7 skipped, rc 0, in 44 min 33 s.
- `sh partials/tests/run.sh`: rc 0, 9997 cases pass, 0 fail, under bash, zsh, `/bin/sh` and dash.
- `node --test 'space/tests/*.test.js'`: 54 pass, 0 fail.
- `node space/build.mjs --check`: rc 0.
- `sh tools/lint-skills/check.sh`: rc 0.

Those five ran on this change rebased onto `main` at `5d52616`. This report's own text was finished after them; `tools/dataset` and the lint, which read `.adlc/bugs`, were run again on the final commit.

An earlier full run of the Python suite, before the rebase, ended 5922 passed, 2 failed: `test_exec_approve.py::test_req719_an_offline_abort_releases_the_hold_queued_behind_it` and `test_exec_launch.py::test_plan`, both `the harness did not exit`. The machine went to sleep and woke several times during that run (`pmset -g log`), and those tests wait on a child process against the clock. The two files passed alone straight after, 225 of 225, and the whole suite passed on the next run with the machine held awake. Neither test reads a credential chain.

What was not measured:

- **Linux.** Every run was on macOS. GNU `sed`, GNU `grep`, and Python and Node builds other than the two above were not timed.
- **Real traffic.** No real intake source, recording or dataset export was run through the chains: the table of real shapes is written by hand, from the shapes the existing tests and LESSON-744 name.
- **The Space in a browser.** The JavaScript was timed in Node, which shares V8 with Chrome. Safari and Firefox were not tried.
- **Timing under load.** The ratio tests take the best of three runs, measure CPU time, and leave a factor of two on each side of the threshold. They passed in every run here, including full runs with another suite running beside them; a machine under heavier load was not tried.

## Files Changed

- `partials/intake.sh`: the assignment arm's name is `{1,64}`; the comment says why.
- `partials/lesson-check.sh`: the wide chain's assignment arm and JWT arm; the comment says why.
- `partials/lesson-check.md`: the BR-13 row of the rule table.
- `tools/adlc/credential_redact.py`: both chains, and the module's note on bounds.
- `tools/adlc/harness_probe.py`: its copy of the intake chain, both spellings.
- `space/toolkit-data.js`: regenerated by `node space/build.mjs`.
- `tools/launch/recording_check.py`: the windowed scan is replaced by a whole-line scan.
- `tools/adlc/tests/test_credential_redact.py`: the scaling tests, the table of real shapes, the shell differential and the bounds.
- `tools/adlc/tests/test_harness_probe_pins.py`, `space/tests/intake.test.js`, `partials/tests/intake.test.sh`, `partials/tests/lesson-check.test.sh`, `tools/launch/tests/test_recording_check.py`: cases for the bound in each copy.
- `.adlc/context/architecture.md`: one note where the third copy is described.
- `CHANGELOG.md`: one entry under Fixed.
- `.adlc/bugs/BUG-295-credential-redaction-quadratic-backtracking.md`: this report.

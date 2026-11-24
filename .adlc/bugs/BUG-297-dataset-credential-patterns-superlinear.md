---
id: BUG-297
title: "Five of the dataset export's own credential patterns backtrack quadratically, or worse, on one long line"
status: resolved
severity: medium
created: 2026-11-24
updated: 2026-11-24
component: "adlc/tools/dataset"
domain: "adlc"
stack: ["python", "regex"]
concerns: ["performance", "security", "availability"]
tags: ["redaction", "credential-regex", "backtracking", "quadratic", "redos", "dataset-export", "residue", "scaling-test"]
introduced_by: [REQ-671]
attribution: derived
---

## Description

`tools/dataset` scrubs every line of every exported artifact with the shared credential chains and then with patterns of its own, and its residue pass searches every scrubbed line with a second, independent set:

- `detectors.JWT_RE` and `detectors.EXTRA_CREDENTIAL`, substituted by `scrub.py`;
- the seven patterns of `residue._EXTRA_CREDENTIAL`, searched by `residue.py`.

They are not copies of the shell chains and no test pins them to one. BUG-295 made the shared chains linear in the length of a line and left these for a bug of their own. Five of them have a repeat, or a lookahead, that can start at any character of a long run, so Python's `re` re-reads the run from every start.

## Reproduction Steps

1. From the repo root, on `main` at `6ac492e`: `python3 -c 'import sys,time; sys.path[:0]=["tools/dataset","tools/adlc"]; import detectors; s="token"*2000; t=time.time(); detectors.EXTRA_CREDENTIAL.search(s); print(time.time()-t)'`. It does not return in 20 seconds.
2. The same with `detectors.JWT_RE` and `s="eyJ"*13334` (40,000 characters): 0.50 s. With 10,000 characters: 0.03 s.
3. The same with `residue._EXTRA_CREDENTIAL[6]` and `s="a"*40000`: 4.7 s. With 10,000 characters: 0.32 s.

## Expected Behavior

Four times the line costs about four times the CPU, for every pattern the export runs over a line.

## Actual Behavior

Measured on `main` at `6ac492e`, Python 3.9.6. Each pattern, and each top-level arm of `EXTRA_CREDENTIAL` and of `residue._EXTRA_CREDENTIAL[0]`, was compiled alone with the pattern's own flags and timed on one line at 10,000 and at 40,000 characters: `search` and `subn`, CPU time, best of three, each case in a child with a 20-second limit. Nineteen lines: `Ab_` repeated, `token` repeated, `secret-` repeated, `eyJ` repeated, `bearer ` repeated, hex digits, `abcdef` repeated, `token` then blanks, a run of `a` then `token` then blanks, `bearer` then blanks, `-u ` repeated, `-u ` then a run with no colon, `aB+/` repeated, `a` repeated, `eyJ` repeated then `.eyJ` and a run of `a`, quotes repeated, `token:` repeated, `sk_` repeated, and `a.` repeated then `@x`.

Linear is ×4 from the first size to the second. Five patterns are superlinear, on these lines (`search`; `>20` means stopped at 20 seconds):

| Pattern | Line | 10,000 | 40,000 | |
|---|---|---|---|---|
| `detectors.JWT_RE` | `eyJ` repeated | 0.031 | 0.503 | ×16.2 |
| `detectors.JWT_RE` | `eyJ` repeated, `.eyJ`, a run | 0.024 | 0.382 | ×15.9 |
| `EXTRA_CREDENTIAL`, key assignment arm | `Ab_` repeated | 1.672 | >20 | |
| `EXTRA_CREDENTIAL`, key assignment arm | `token` repeated | >20 | >20 | |
| `EXTRA_CREDENTIAL`, key assignment arm | `secret-` repeated | >20 | >20 | |
| `EXTRA_CREDENTIAL`, key assignment arm | a run, `token`, blanks | 0.611 | >20 | |
| `residue._EXTRA_CREDENTIAL[0]`, JWT arm | `eyJ` repeated | 0.034 | 0.543 | ×16.1 |
| `residue._EXTRA_CREDENTIAL[3]` | `token` repeated | 0.271 | 4.364 | ×16.1 |
| `residue._EXTRA_CREDENTIAL[3]` | `secret-` repeated | 0.192 | 3.065 | ×15.9 |
| `residue._EXTRA_CREDENTIAL[6]` | `a` repeated | 0.316 | 4.652 | ×14.7 |
| `residue._EXTRA_CREDENTIAL[6]` | hex digits | 0.355 | 5.747 | ×16.2 |
| `residue._EXTRA_CREDENTIAL[6]` | `aB+/` repeated | 0.617 | >20 | |

The key assignment arm is also superlinear on `eyJ` repeated, `abcdef` repeated, `a` repeated, `sk_` repeated, `-u ` then a run, and `eyJ` repeated then `.eyJ` and a run: every line with a long run of letters, underscores or hyphens. `residue._EXTRA_CREDENTIAL[6]` is superlinear on nine of the nineteen lines: every long run of base64 characters that lacks a capital, a small letter or a digit. `subn` gives the same picture and is slower where a pattern matches nothing.

Linear on all nineteen lines, and so left as they are: the other seven arms of `EXTRA_CREDENTIAL` (`hf_`, `ya29.`, `sk_`, `bearer` and `basic`, `-u`, the hex run, the base64 run, which already starts only at the start of a run), the other three arms of `residue._EXTRA_CREDENTIAL[0]`, and `residue._EXTRA_CREDENTIAL[1]`, `[2]`, `[4]` and `[5]`.

Who runs them: `export.py` scrubs every line of every artifact with `detectors.CREDENTIAL_PATTERNS`, and runs the residue pass over each record's scrubbed text and again over the JSONL, the card and the revision it is about to write; `publish.py` runs the residue pass over the files it uploads. The corpus is this repository's own `.adlc/` tree, which no attacker writes, and ordinary prose has no 10,000-character run of letters. A pasted blob, a minified file or a base64 line quoted in a lesson does.

## Environment

- macOS 27.2 (Darwin 27.2.0), arm64. Python 3.9.6.
- Toolkit `main` at `6ac492e`.

## Root Cause

Prior lessons consulted:
- LESSON-744 — Credential redaction chains match inside ordinary identifiers — validate identifier fields by format instead of redacting them
- LESSON-760 — A transcript parser must allow record types, not sniff for message shape: Claude Code's api-request-blob records looked like Human turns
- LESSON-746 — Claude Code session records carry the account email — a credential redaction chain is not enough for a committed transcript
- LESSON-897 — A static check that traces values through shell fails open: admit a closed set of shapes and refuse the rest
- LESSON-898 — A Python pattern that ends in $ admits a trailing newline: end a validating pattern in \\Z or use fullmatch

None of the five describes this failure. LESSON-744 describes what the key assignment arms match inside ordinary identifiers (`compass_heading: northwest` is a hit, through `pass`); the fix keeps that set as it is and the table of real shapes holds two such lines. The failure itself is BUG-295's, in the patterns that bug left: a repeat that can begin at any character of a long run, in front of something that is usually absent.

The mechanism, pattern by pattern. A run here is a maximal stretch of the characters one class matches.

1. **`detectors.JWT_RE`, `eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*`, and the JWT arm of `residue._EXTRA_CREDENTIAL[0]`, `eyJ[A-Za-z0-9_-]+\.eyJ`.** A match can start at each `eyJ`. From there the header repeat reads to the end of the run looking for the dot, and gives the run back a character at a time when there is none. A run dense in `eyJ` is read from each one: n²/6 steps. `JWT_RE` has a second way to the same cost: every `eyJ` in a header run that does end in `.eyJ` reaches the same payload and reads it to its end looking for the second dot.
2. **The key assignment arm of `detectors.EXTRA_CREDENTIAL`**, `["']?[A-Za-z_-]*(?i:secret|…|credential)[A-Za-z_-]*["']?[ \t]*[:=]…`. The identifier repeat in front of the keyword can begin at every character of a run of letters, underscores and hyphens, and reads to the end of the run from each: n²/2 on any such run, keyword or no keyword. Where the run does hold keywords, each start finds each of them, and from each the repeat behind the keyword reads to the end of the run and gives it back: n³ over a constant, which is why 10,000 characters of `token` did not finish.
3. **`residue._EXTRA_CREDENTIAL[3]`**, the same arm without the repeat in front. Each keyword in a run is a start, and from each the repeat behind it reads to the end of the run: quadratic on a run dense in keywords.
4. **`residue._EXTRA_CREDENTIAL[6]`**, `(?=[A-Za-z0-9+/]*[A-Z])(?=[A-Za-z0-9+/]*[a-z])(?=[A-Za-z0-9+/]*[0-9])[A-Za-z0-9+/]{40,}`. Nothing anchors it, so the three lookaheads run from every character of a run of base64 characters, and a lookahead for a class the run lacks reads to the end of the run before it fails: quadratic on any long run with no capital, no small letter or no digit. A long word is such a run. The scrub's own base64 arm has a lookbehind in front and is linear.

The arms that measured linear have neither property, or only one. `hf_[A-Za-z0-9]{30,}` has an unbounded repeat and fails only when fewer than thirty characters follow. The `bearer` and `-u` arms start only at their literal, and the blanks and the value after it are disjoint classes, so nothing is read twice. The hex arms and the scrub's base64 arm begin only at the start of a run.

One property of the two assignment patterns decides what a fix may do. Everything from the repeat in front of the keyword to the repeat behind it lies inside one run of `[A-Za-z_-]`, because the keywords are made of those characters, and what follows (a quote, a blank, `:` or `=`) is outside the class. So whether a run matches depends on two things only: that it holds a keyword, and that the rest of the pattern matches from the end of the run. Which keyword, and where in the run the engine started, change nothing but the cost.

Attribution: `git blame` on the root-cause lines (`tools/dataset/detectors.py` 22 and 31 to 41, `tools/dataset/residue.py` 23 to 34) returns one REQ, REQ-671, which shipped `tools/dataset`. No test there timed a pattern: the cases are short lines.

## Resolution

Each of the five now begins at the start of its run and reads the run once. These are Python patterns with no shell original, so a lookbehind can say "the start of a run", which BUG-295's chains could not.

| Pattern | Before | After |
|---|---|---|
| `residue._EXTRA_CREDENTIAL[0]`, JWT arm | `eyJ[C]+\.eyJ` | `(?<![C])(?=[C]*?eyJ[C])[C]+\.eyJ` |
| `residue._EXTRA_CREDENTIAL[3]` | `(?:secret\|…)[I]*…` | `(?<![I])(?=[I]*(?:secret\|…))[I]*…` |
| `residue._EXTRA_CREDENTIAL[6]` | `(?=[B]*[A-Z])…[B]{40,}` | `(?<![B])(?=[B]*[A-Z])…[B]{40,}` |
| `EXTRA_CREDENTIAL`, key assignment arm | `["']?[I]*(?i:secret\|…)[I]*…` | `["']?(?:(?<![I])(?=[I]*(?i:secret\|…))[I]*\|[I]{0,64}(?i:secret\|…)[I]{0,64})…` |
| `detectors.JWT_RE` | `eyJ[C]+\.eyJ[C]+\.[C]*` | `(?:eyJ[C]{1,255}\|(?<![C])eyJ[C]+\|[C]{255})\.eyJ[C]+\.[C]*` |

`[C]` is `[A-Za-z0-9_-]`, `[I]` is `[A-Za-z_-]` and `[B]` is `[A-Za-z0-9+/]`.

**The residue pass's three.** The residue pass only asks whether a pattern is found on a line (`any(p.search(masked) …)`), so the match may begin somewhere else as long as the same lines are hits. Each new pattern begins only where the character in front is outside the run's class, looks ahead once for what the run must hold (an `eyJ` with a character after it; a keyword; a capital, a small letter and a digit), and then reads the whole run. By the property at the end of Root Cause, that is a hit on exactly the lines the old pattern hit, at any length: a run holds a keyword and the rest matches from its end, or not, wherever the engine starts. For the base64 pattern the old match already began at the start of the run whenever there was one, because a shorter tail of a run holds no class the whole run lacks, so there even the span is unchanged.

**The scrub's key assignment arm.** The scrub substitutes, so what is replaced must not move. The old match always began at the start of the run that holds the keyword (or at a quote in front of it): the repeat in front of the keyword reaches back that far, and the search takes the leftmost start. The first alternative says so directly: at the start of a run, the run holds a keyword, then the whole run. It replaces the same characters as before for a name of any length.

A lookbehind alone would be wrong. A search that has just replaced one match resumes where that match ended, and the lookbehind still sees the characters of the match it has replaced. Four arms of `EXTRA_CREDENTIAL` can end inside a run of name characters, before an underscore for one: the hex run and the `hf_`, `bearer` and base64 arms. `0…0a_token=<value>` is two matches for the old pattern, the hex run and then the assignment; with only the lookbehind the assignment is left in the text. So the arm has a second alternative for a start that is not the start of a run: 64 name characters on each side of the keyword, the bound the shared wide chain uses. It costs a constant at each character and gives the old result whenever the name fits the bound.

**`JWT_RE`.** Its old match began at the first `eyJ` in the run, which no fixed lookbehind can find. Three ways to read the header, in one group:

- `eyJ[C]{1,255}`: a header of up to 255 characters after any `eyJ`, as before. A JWT glued to a word (`prefix-eyJ…`, or straight after a terminal colour code) is read this way.
- `(?<![C])eyJ[C]+`: a header of any length when `eyJ` begins the run, as before. This is where a header sits after a blank, a quote, `=`, `:` or `Bearer `, and a header that carries a certificate chain runs to thousands of characters.
- `[C]{255}`: the last 255 characters of a longer header that is glued to a word. BUG-295's second JWT arm, with the same reason: an exact count gives nothing back.

The payload keeps its `+` and the signature its `*`: once a header and `.eyJ` have matched, fewer than ninety starts share one payload.

What changes, each pinned by `test_bug_297_what_the_bounds_change`:

- A JWT whose header is longer than 255 characters and glued to a word is replaced from 255 characters before the header's dot, so the head of that header stays in the text. The payload and the signature still go.
- The exact-count arm does not ask for `eyJ`: 255 header characters, `.eyJ`, a payload and a dot are a match with no `eyJ` among them, and a short JWT glued to the end of a run of 255 or more header characters takes 255 of them with it. The old pattern needed an `eyJ` and began at it.
- A key-like assignment that begins where another arm's match ended, inside one run of name characters, is read with 64 name characters on each side of its keyword. With a longer name in front, the first characters of the name stay and the value still goes. With more than 64 name characters between the keyword and the `:` or `=`, the assignment is not replaced. The residue pass, which has no such bound, then finds it, and the record is excluded: the case fails closed.

Nothing else changes. `test_bug_297_long_names_and_long_headers_are_still_read_whole` holds a 208-character name and a 3,000-character header to the old output.

After the fix, same machine, same nineteen lines, every pattern and every arm alone: all linear. Seconds at 10,000 and 40,000 characters, `search`:

| Pattern | Line | 10,000 | 40,000 | |
|---|---|---|---|---|
| `detectors.JWT_RE` | `eyJ` repeated | 0.008 | 0.034 | ×4.3 |
| `detectors.JWT_RE` | `eyJ` repeated, `.eyJ`, a run | 0.007 | 0.029 | ×4.2 |
| `detectors.JWT_RE` | `a` repeated | 0.004 | 0.018 | ×4.1 |
| `detectors.EXTRA_CREDENTIAL` | `Ab_` repeated | 0.025 | 0.098 | ×4.0 |
| `detectors.EXTRA_CREDENTIAL` | `token` repeated | 0.220 | 0.905 | ×4.1 |
| `detectors.EXTRA_CREDENTIAL` | `secret-` repeated | 0.171 | 0.686 | ×4.0 |
| `residue._EXTRA_CREDENTIAL[0]` | `eyJ` repeated | 0.0002 | 0.0007 | |
| `residue._EXTRA_CREDENTIAL[3]` | `token` repeated | 0.0004 | 0.0015 | |
| `residue._EXTRA_CREDENTIAL[6]` | `a` repeated | 0.0001 | 0.0006 | |
| `residue._EXTRA_CREDENTIAL[6]` | `aB+/` repeated | 0.0002 | 0.0008 | |

The worst line for the scrub is `token` repeated, at about 23 µs a character: every character that is not the start of a run tries the bounded alternative. The exact-count JWT arm is not free either. `JWT_RE` used to skip a line with no `eyJ` at once, and now reads up to 255 characters from each character of a long run of header characters: 0.018 s for 40,000 letters. On ordinary text, whose runs are words, neither shows: an export of this repository's own tree took 20.1 s with the old patterns and 21.3 s with the new, run side by side, once each.

**Real input.** `export.build` over this repository's `.adlc/` tree at `6ac492e` (774 artifacts, 53 credential replacements) gives the same bytes with the old patterns and the new: the three output files and the report, 5,539,122 bytes of JSON, same SHA-256.

Weighed and not done:

- **The two email patterns.** `detectors.EMAIL_RE` and `residue._EMAIL` measured superlinear on the same nineteen lines: `residue._EMAIL` on twelve of them (3.5 s for 40,000 characters of letters, ×16), because it can begin at any character of a run with no `@`; `detectors.EMAIL_RE` on `Ab_` repeated and `sk_` repeated (0.53 s at 40,000, ×16), because its lookbehind leaves out the underscore its repeat reads. They are not credential patterns, and this bug's scope is those. Until they are fixed, a scrub or a residue pass over one very long line is still superlinear, which is why the scaling test times the credential step and not `scrub_line` or `scan_line` whole. The other dataset patterns (`_HOME`, `_REF`, `_SCRUB_MARK`, `_PLACEHOLDERS`, `SHA_RE`, `PR_REF_RE`, `HOME_PATH_RE`, `PRIVATE_KEY_RE`) and both shared chains measured linear on all nineteen lines.
- **A plain bound on the assignment arms**, 64 characters each side as in the wide chain, with no lookbehind. Simpler to read, but it changes what real input matches: this corpus is full of kebab slugs longer than 64 characters, and a line such as `fix/bug-297-dataset-credential-patterns-…-of-letters: summary1` would stop being a hit for the scrub. A bound in the residue pass alone would be worse: it would stop finding what the scrub had left.
- **A guard on the bounded alternative**, so that it is tried only where another arm can end. It would cut the constant on `token` repeated, and tie the arm to the text of four others.
- **A larger header bound than 255.** Python has no limit, but the wide chain reads the same JWT next with 255, and the anchored alternative already reads a real long header whole.

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`).

Failing-first tests were still written, before any of the fix: `tools/dataset/tests/test_dataset_credential_linear.py`. Each scaling test compares two line lengths and asserts a ratio, never a time: ×4 the input may cost at most ×8 the CPU (linear is 4, quadratic 16). Each timing runs in a child with a 45-second limit, because the unfixed patterns did not finish some lines at all. A target is one of the five patterns, called as the export calls it (`subn` for the scrub's two, `search` for the residue pass's three), or one of the two whole credential steps: every pattern `scrub_line` substitutes, in order, and every pattern `scan_line` searches.

Without the fix (the test file against `tools/dataset` as it is on `main` at `6ac492e`), under a throwaway `HOME` and `ADLC_HOME`:

- `python3 -m pytest tools/dataset/tests/test_dataset_credential_linear.py -q`: 36 failed, 13 passed, in 11 min 24 s. First failing assertion: `BUG-297: no linear arm in EXTRA_CREDENTIAL (…); it backtracks without one`. First failing timing: `BUG-297: JWT_RE on eyJ, repeated took 0.0285 s at 10000 characters and 0.4556 s at 40000: x16.0 for x4 the input`.
- 26 of the 39 scaling cases fail. Ten do not finish in 45 s: seven of the nine `EXTRA_CREDENTIAL` cases, and the scrub's credential step on `Ab_` repeated, `token` repeated and `eyJ` repeated. The other sixteen fail on the ratio, between ×13.8 and ×16.7: one more for `EXTRA_CREDENTIAL`, two for `JWT_RE`, one for `residue[0]`, four for `residue[3]`, five for `residue[6]`, and three for the residue pass's credential step.
- Every one of the five patterns has at least one failing case of its own, so a fix taken out alone fails the file.
- The four comparison tests and the reference test fail by design, on `no linear arm in …`: the old patterns they compare with are today's patterns with the old text put back.

With the fix: 49 passed, in 26 s.

Thirteen scaling cases pass before and after. They time what the fix adds or must not break, among them: `JWT_RE` on header characters with no dot, on long headers each before `.eyJ`, and on `eyJ` at the start of each long run; the bounded alternative on a hex run glued to `token` repeated; the unchanged arms on hex digits, base64 and `bearer`.

The tests that pin the fix from the other side, all passing with it:

- `test_bug_297_reference_patterns_are_the_ones_replaced`: the five old patterns, spelled out, equal today's with the old text put back. So the comparisons below are against the real old patterns.
- `test_bug_297_match_set_unchanged_on_real_shapes`: 77 real-shaped lines (the dataset's own key shapes; assignments with `:`, `=` and quotes in kebab, snake and header spelling; names longer than 64 characters; LESSON-744's kind of false positive; prose that only names a variable; JWTs bare, quoted, assigned, glued to a word, after a terminal colour code, with a 1,600-character payload and with a 3,000-character header; long lines of prose, JSON and base64). For the scrub's two patterns: the same output, the same count and the same spans, and the same output from the whole credential step. For the residue pass's three: the same lines are hits, on the raw line and on the scrubbed one. The old patterns find 12, 50, 16, 23 and 15 matches in the table.
- `test_bug_297_match_set_unchanged_on_random_lines_inside_the_bounds`: 6,000 seeded random lines built from the patterns' own literals and what sits near them, the four non-ASCII letters that fold to ASCII ones included, with no name run over 64 characters and no header run of 255. The same comparisons; 1,460, 2,725, 1,471, 618 and 1,059 matches.
- `test_bug_297_long_names_and_long_headers_are_still_read_whole` and `test_bug_297_what_the_bounds_change`: described under Resolution.

An independent adversarial review of the diff, given the old code beside the new and five claims to break: about a million lines of differential fuzzing (300,000 for each residue pattern, with every Unicode code point checked against the name class under `IGNORECASE`; 80,000 for `EXTRA_CREDENTIAL` with other credentials glued to names; 50,000 for `JWT_RE`) found no difference outside the three under Resolution, and 231 timing pairs at 20,000 and 80,000 characters found no ratio above ×4.5 that held when re-timed. It found one comment on `JWT_RE` that understated what the exact-count alternative does, which is corrected.

The wider runs, with the fix, each under a throwaway `HOME` and `ADLC_HOME`, on this change rebased onto `main` at `6ec040f`:

- `python3 -m pytest tools -q`: 5973 passed, 7 skipped, rc 0, in 47 min 2 s.
- `sh partials/tests/run.sh`: rc 0, 10,081 cases pass, 0 fail.

This report's own text was finished after them, and the change was then rebased over one more commit on `main`, `8c5b4db`, which adds to a spec and touches no code. `python3 -m pytest tools/dataset -q` and `sh tools/lint-skills/check.sh`, which read `.adlc/`, were run again on the final commit.

An earlier full run of the Python suite, on the same change one rebase back, ended 5971 passed, 2 failed: `test_exec_launch.py::test_protection_preflight` and `test_exec_launch.py::test_the_grant_keeps_the_harness_from_trusting_the_repo_itself`, both `the harness did not exit`. The laptop's lid was closed eleven minutes into that run and the machine slept and woke until the lid was opened (`pmset -g log`: `Clamshell Sleep` at 08:17, then maintenance sleeps); those tests wait on a child process against the clock, and `caffeinate -i` does not hold a closed lid awake. The file passed alone straight after, 109 of 109, and the whole suite passed on the next run with the lid open. Neither test reads a credential pattern.

What was not measured:

- **Linux, and other Python versions.** Every run was on macOS with Python 3.9.6. `re` in a later Python was not timed.
- **A real export with a long line in it.** The repository's own tree exports to the same bytes, and has no line of the kind this bug is about; the long lines are the tests' own.
- **Timing under load.** The ratio tests take the best of three runs, measure CPU time, and leave a factor of two on each side of the threshold. They passed in every run here, including one beside a run of the same file against the unfixed patterns and the full run the machine slept through; a machine under heavier load was not tried.

## Files Changed

- `tools/dataset/detectors.py`: `JWT_RE` reads the header three ways; the key assignment arm of `EXTRA_CREDENTIAL` begins at the start of a run or reads 64 characters each side; the comments say why.
- `tools/dataset/residue.py`: the JWT arm of `_EXTRA_CREDENTIAL[0]`, and `[3]` and `[6]`, begin at the start of a run; the comment says why.
- `tools/dataset/tests/test_dataset_credential_linear.py`: new. The scaling tests, the table of real shapes, the seeded random lines, the long shapes and the bounds.
- `tools/dataset/README.md`: one paragraph under Tests.
- `.adlc/context/architecture.md`: one sentence where the dataset export is described.
- `CHANGELOG.md`: one entry under Fixed, and a pointer from BUG-295's.
- `.adlc/bugs/BUG-297-dataset-credential-patterns-superlinear.md`: this report.

## Deployment

- Merged to `main` on 2026-11-24 as `46df645`, the squash of PR #334. The regression gate reported `off` for this project before the merge.
- No staging or production service: the toolkit is installed from a checkout. `tools/dataset` is a maintainer tool run from a clone, so an export has the fix once the clone is at `46df645` or later. Nothing is vendored into a project.
- The lesson from the fix is LESSON-911.
- Still open: the two email patterns under "Weighed and not done", which BUG-298 takes up.

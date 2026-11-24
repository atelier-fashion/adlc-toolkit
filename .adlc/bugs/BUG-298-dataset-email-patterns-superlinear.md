---
id: BUG-298
title: "A whole scrub of one long line, and a whole residue pass over it, are quadratic: the two email patterns, and what is done once for each hit"
status: open
severity: medium
created: 2026-11-24
updated: 2026-11-24
component: "adlc/tools/dataset"
domain: "adlc"
stack: ["python", "regex"]
concerns: ["performance", "security", "availability"]
tags: ["redaction", "email-regex", "backtracking", "quadratic", "redos", "dataset-export", "residue", "scaling-test", "finditer"]
introduced_by: [REQ-671]
attribution: derived
---

## Description

`tools/dataset` scrubs every line of every exported artifact (`Scrubber.scrub_line`) and its residue pass then searches every scrubbed line (`Checker.scan_line`). BUG-297 made the credential patterns of both linear in the length of a line, and left the two email patterns for a bug of their own: `detectors.EMAIL_RE` and `residue._EMAIL` had measured superlinear and are not credential patterns. So a whole scrub or a whole residue pass over one very long line was still superlinear, and BUG-297 could time only the credential step of each.

This bug is the rest of the line. Measuring every other pattern the two functions run found the two email patterns and nothing else superlinear as a pattern, and three more places where the cost is not in a pattern but in how often it is run: each reads the line from its start once for every hit on it.

## Reproduction Steps

1. From the repo root, on `main` at `6ec040f`: `python3 -c 'import sys,time; sys.path[:0]=["tools/dataset","tools/adlc"]; import residue; s="x"*40000; t=time.time(); residue._EMAIL.search(s); print(time.time()-t)'`. It prints about 3.2. With `"x"*10000`: about 0.21.
2. The same with `detectors.EMAIL_RE` and `s="Ab_"*13334`: about 0.48. With 10,000 characters: 0.03.
3. `Scrubber.scrub_line` on `"Dana "*8000`, with a DenyList that names the person `Dana`: 1.4 s. On `"Dana "*2000`: 0.11 s.

## Expected Behavior

Four times the line costs about four times the CPU, for the whole of `Scrubber.scrub_line` and the whole of `Checker.scan_line`.

## Actual Behavior

Measured on `main` at `6ec040f` with BUG-297's fix applied, Python 3.9.6. Forty-seven targets, each timed on one line at 10,000 and at 40,000 characters: CPU time, best of three, each case in a child with a 20-second limit. The targets are every non-credential pattern the two functions run, with `search` and with `finditer` (`_HOME`, `_EMAIL`, `_REF`, `_SCRUB_MARK` and `_PLACEHOLDERS` in `residue.py`; `HOME_PATH_RE`, `EMAIL_RE`, `SHA_RE`, `PR_REF_RE` and `PRIVATE_KEY_RE` in `detectors.py`; the sentence-start pattern in `scrub.py`; the two table-cell patterns); every pattern `Detectors` and `Checker` build from a DenyList (the owner URL, the organization namespace, one per repo entry, the people, the residue pass's token, context, pair, namespace, personal URL and organization patterns), built from a DenyList with an organization repository, a token entry with two aliases, a context entry and two people; and the calls themselves: `email_hits`, `has_denylist_hit`, `line_has_ref`, `scrub_line`, `scrub_text`, `scan_line` and `residue.scan`.

One hundred and fifteen lines: 5,405 cases. The lines are the eight shapes this bug was opened with (letters; letters and underscores; `sk_` repeated; `a.` repeated then `@x`; `a@` repeated; `a@b.` repeated; dots, hyphens and labels after an `@`; a long local part, an `@` and a long domain with no top-level domain), BUG-297's nineteen, and lines for every other rule: addresses with blanks between them and glued by `_`, `.` and `-`; slashes and home paths; hex runs, SHAs and `#` references; the scrub's own placeholders; each kind of DenyList name glued, with blanks, in prose and in table cells; namespaced names and links; prose, JSON and a markdown table.

Linear is ×4 from the first size to the second. A case is called superlinear above ×8.

**The patterns.** Two are superlinear, and no other:

| Pattern | Lines | Example line | 10,000 | 40,000 | |
|---|---|---|---|---|---|
| `residue._EMAIL` | 49 of 115 | letters | 0.211 | 3.174 | ×15.0 |
| | | letters and underscores | 0.213 | 3.355 | ×15.7 |
| | | letters that are not ASCII | 0.242 | 3.658 | ×15.1 |
| | | `x@` then hyphens | 0.211 | 3.284 | ×15.6 |
| | | long local part, `@`, long labels ending in a digit | 0.383 | 6.042 | ×15.8 |
| | | long local part, `@`, long domain, no top-level domain | 0.465 | >20 | |
| `detectors.EMAIL_RE` | 2 of 115 | letters and underscores | 0.030 | 0.475 | ×16.0 |
| | | `sk_` repeated | 0.030 | 0.480 | ×16.1 |

The last `_EMAIL` line is quadratic like the others, with a larger constant: 0.12 s at 5,000 characters, 0.48 s at 10,000 and 1.93 s at 20,000, timed once each. `_EMAIL`'s forty-nine lines are every line with a long stretch free of blanks, `@` and the dozen punctuation marks its local part excludes: hex runs, `token` repeated, `eyJ` repeated, a long name after `acme-org/`, digits. `search` and `finditer` measure the same.

Every other pattern is linear on all 115 lines, alone: `_HOME`, `_REF`, `_SCRUB_MARK`, `_PLACEHOLDERS`, `HOME_PATH_RE`, `SHA_RE`, `PR_REF_RE`, `PRIVATE_KEY_RE`, the sentence-start and table-cell patterns, and every pattern built from the DenyList.

**The calls.** `Checker.scan_line` and `residue.scan` are superlinear on the same forty-nine lines as `_EMAIL` and on no other. `Scrubber.scrub_line` is superlinear on five lines, and only one of them is `EMAIL_RE`'s:

| Call | Line | 10,000 | 40,000 | |
|---|---|---|---|---|
| `Scrubber.scrub_line` | letters and underscores | 0.084 | 0.715 | ×8.5 |
| `Scrubber.scrub_line` | a person's name and a blank, repeated | 0.105 | 1.406 | ×13.3 |
| `Scrubber.scrub_line` | a person's name at the start of each sentence | 0.120 | 1.770 | ×14.7 |
| `Scrubber.scrub_line` | a full name and a blank, repeated | 0.041 | 0.563 | ×13.9 |
| `Scrubber.scrub_line` | a context name in table cells | 0.017 | 0.165 | ×9.5 |
| `Detectors.has_denylist_hit` | a context name in table cells | 0.010 | 0.127 | ×12.9 |
| `Detectors.has_denylist_hit` | a context name in prose | 0.003 | 0.030 | ×9.0 |

Between ×5.5 and ×8, so not called superlinear and not linear either: `scrub_line` on a context name in prose, on the organization's name in prose and on one hit of every rule repeated (×7.0 to ×7.4), and `scan_line` on a context name or the organization's name in prose (×6.6, ×6.7). Timed apart afterwards, the function that replaces spans took 0.0014 s for 2,000 spans in 10,000 characters and 0.026 s for 8,000 in 40,000: ×18.8.

Who runs them: `export.py` scrubs every line of every artifact, and runs the residue pass over each record's scrubbed text and again over the JSONL, the card and the revision it is about to write; `publish.py` runs the residue pass over the files it uploads. A line of the JSONL is a whole record: the longest in an export of this repository is 124,487 characters. The corpus is this repository's own `.adlc/` tree, which no attacker writes, and its lines are prose and JSON, whose runs are words: the export is no slower for this bug today. A pasted blob, a minified file or a long identifier quoted in a lesson is the line this is about.

## Environment

- macOS 27.2 (Darwin 27.2.0), arm64. Python 3.9.6.
- Toolkit `main` at `6ec040f` with BUG-297's fix, which was not merged when this was written: this branch is cut from that fix's branch. `main` itself has the two email patterns and the three per-hit reads as described here; BUG-297 did not touch them.

## Root Cause

Prior lessons consulted:
- LESSON-908 — A regex copied from sed or grep into Python or JavaScript keeps its text and loses its cost: time the copy at two line lengths, and bound every repeat that can start anywhere in a long run
- LESSON-744 — Credential redaction chains match inside ordinary identifiers — validate identifier fields by format instead of redacting them
- LESSON-760 — A transcript parser must allow record types, not sniff for message shape: Claude Code's api-request-blob records looked like Human turns
- LESSON-746 — Claude Code session records carry the account email — a credential redaction chain is not enough for a committed transcript
- LESSON-897 — A static check that traces values through shell fails open: admit a closed set of shapes and refuse the rest

LESSON-908 describes the first half of this failure: a repeat that can start anywhere in a long run, in front of something usually absent, is quadratic in an engine that backtracks, and the test for it compares two line lengths and asserts a ratio. The scaling tests here are that test. Its remedy is to bound the repeat, which a pattern shared with `sed` needs because an ERE has no lookbehind. These two are Python patterns with no shell original, so the repeat is anchored instead, and the one start an anchor loses is tried apart; Resolution says why a bound was not used. LESSON-746 is why the scrub has an email rule at all. None of the five describes the second half, a read of the line for each hit. LESSON-898, not among the five, describes one thing the fix has to keep: a pattern that ends in `$` also matches before a final newline, and both per-hit patterns end in `$`.

There are two mechanisms.

**1. A repeat that begins at every character of a run.** A run here is a maximal stretch of the characters a pattern's local part accepts.

- `residue._EMAIL` is `[^\s@<>()\[\]{}"'`,;|:/=]+@` and a domain. Nothing anchors it, so a search tries every character of a run as a start, and from each the repeat reads to the end of the run looking for the `@`: n²/2 steps on a run of n characters with no `@` after it. With an `@` and a long domain that has no top-level domain, every start also reads the domain and gives it back.
- `detectors.EMAIL_RE` is `(?<![A-Za-z0-9.%+-])[A-Za-z0-9._%+-]+@` and the same domain. Its lookbehind stops a start in the middle of a word, but leaves out the underscore, which the repeat reads. So every character after an underscore is a start, and the repeat reads the rest of the run from each: quadratic on `Ab_Ab_Ab_…` and `sk_sk_sk_…`, linear on a run with no underscore.

**2. A read of the line for each hit.** Each of these is linear in what it is given. It is given the line up to the hit, once for every hit:

- `Detectors.is_prose` and `Checker._named` ask whether a context name stands alone in a table cell with `re.search(r"\|[ \t]*$", line[:start])`: a slice of the line and a search of it from its first character, for every occurrence of the name that reads as prose. A second slice, `line[end:]`, follows when the first search finds a cell.
- The scrub's person rule asks whether a name starts a sentence with `_SENTENCE_START_RE.search(before)`, `(?:^[ \t>*#|-]*|[.!?:][ \t]+)$`, where `before` is the line up to the name. This is the worst of the three, because nothing in the pattern lets the engine skip ahead: 1.4 s for 8,000 names in 40,000 characters.
- `scrub._replace_spans` builds the line again for each span, `out[:s] + rep + out[e:]`, and slices `out[:s]` once more for a replacement that is a function.

With k hits on a line of n characters each costs k·n, and k grows with n.

One property of the two email patterns decides what a fix may do. An address must reach its `@`, and no local-part character is an `@`, so the local part of any match ends exactly where its run ends, and everything after that is the same whatever the start. A run therefore holds a match from one of its starts exactly when it holds one from every start, and the match differs only in where it begins.

Attribution: `git blame` on the root-cause lines (`tools/dataset/residue.py` 46 to 47 and 103 to 121, `tools/dataset/detectors.py` 85 to 88, 167 to 168 and 193 to 194, `tools/dataset/scrub.py` 34, 50 to 56 and 117 to 120) returns one commit and one REQ, REQ-671, which shipped `tools/dataset`. Its tests are short lines.

## Resolution

**The email patterns.** `EMAIL_RE` and `_EMAIL` keep their text: they are still the rule. They are no longer searched. Each has a second pattern beside it that is the rule with one thing added in front, `(?<!` its own local-part class `)`: the start of the run. And each has a function that gives the matches `finditer` gave: `detectors.emails(line)` and `residue._emails(line)`.

The function searches with the anchored pattern. By the property above this finds the same match a search with the rule finds: the leftmost match in a run begins at the start of the run, and a run that holds no match from its start holds none. The anchored pattern reads each run once, and fails at every other character of it on the lookbehind alone.

An anchor alone would be wrong, for the reason BUG-297 recorded: a search that has just found one match resumes where that match ended, and that can be inside a run. Then the start of the run is behind the search, and the rule begins again mid-run. Write `A` and `B` for two addresses (spelled out here, each would be replaced when this report is exported):

- `_EMAIL` begins again at once. An address ends in letters, and what follows may be a local-part character: `A.B`, `A-B`, `A_B`. The rule finds two addresses in each. The anchored pattern finds one.
- `EMAIL_RE` begins again after the next underscore of the run, because that is where its lookbehind lets it: `A_B` is two addresses for the rule, and `A.B` is one.

This matters for what the two functions decide. The scrub replaces each match, so the `B` of `A_B` would be left in the text. The residue pass compares each match with an allow list, so `A.B` would pass whenever `A` is allowed. On 300,000 seeded random lines built from address fragments, the anchored patterns alone gave a different match list from the rule on 7% of lines for the scrub and 30% for the residue pass.

So after each match the function tries the rule itself at the one position where the rule could begin inside the rest of the run: where the match ended, for `_EMAIL`; just past the first underscore of the rest of the run, for `EMAIL_RE`. That is one `match` call at one position, never a search. If it matches, that is the next address, as it was for `finditer`. If it does not, no later start in the same run matches either, by the same property, and the anchored search goes on from where the match ended.

The cost stays linear. The one attempt after a match reads the rest of one run, and the next match begins after that run, so no character is read by two attempts.

Nothing is bounded, so no match moves and none is lost at any length.

**The per-hit reads.** Each question is now answered by reading backwards from the hit:

- `_after_pipe(line, end)`, one in `detectors.py` and one in `residue.py` because the residue pass shares no code with the scrub: step back over blanks from `end` and look for the `|`. It reads the blanks in front of the hit and nothing else. The cell's other side is matched in place, `_CELL_END_RE.match(line, end)`, with no slice.
- `scrub._starts_sentence(line, start, lead)`: true when `start` lies inside the line's leading run of blanks and markdown marks, whose length is computed once for the line, or when stepping back over at least one blank reaches `.`, `!`, `?` or `:`.
- `scrub._replace_spans` goes through the spans once, left to right, and joins the pieces. A replacement that is a function is given the span's text and its start, not a copy of the line in front of it.

Both patterns ended in `$`, which also matches before a final newline (LESSON-898), so both functions step back over one final newline first. The scrub and the residue pass split text on newlines before either is reached, so this changes nothing the export does; it keeps the two functions equal to the patterns on every string, which is what the tests compare.

After the fix, same machine, same 115 lines, fifty targets (the forty-seven and the three new: `detectors.emails`, `residue._emails` and the two anchored patterns): every call is linear on every line. The largest ratio among them is ×4.8, on a case that takes four milliseconds. Seconds at 10,000 and 40,000 characters:

| Call | Line | Before | | After | | |
|---|---|---|---|---|---|---|
| `Checker.scan_line` | letters | 0.237 | 3.458 | 0.023 | 0.092 | ×4.0 |
| `Checker.scan_line` | letters and underscores | 0.244 | 3.505 | 0.027 | 0.108 | ×4.1 |
| `Checker.scan_line` | long local part, `@`, long domain | 0.492 | >20 | 0.022 | 0.087 | ×3.9 |
| `Checker.scan_line` | `token` repeated | 0.318 | 3.951 | 0.107 | 0.443 | ×4.1 |
| `Checker.scan_line` | a context name in prose | 0.006 | 0.041 | 0.005 | 0.019 | ×3.7 |
| `Scrubber.scrub_line` | letters and underscores | 0.084 | 0.715 | 0.054 | 0.226 | ×4.2 |
| `Scrubber.scrub_line` | a person's name and a blank, repeated | 0.105 | 1.406 | 0.009 | 0.035 | ×3.8 |
| `Scrubber.scrub_line` | a person's name at the start of each sentence | 0.120 | 1.770 | 0.009 | 0.037 | ×3.9 |
| `Scrubber.scrub_line` | a context name in table cells | 0.017 | 0.165 | 0.009 | 0.036 | ×3.9 |
| `Scrubber.scrub_line` | one hit of every rule, repeated | 0.009 | 0.064 | 0.007 | 0.028 | ×4.0 |
| `Scrubber.scrub_line` | `token` repeated | 0.311 | 1.294 | 0.334 | 1.337 | ×4.0 |
| `Detectors.email_hits` | letters and underscores | 0.029 | 0.464 | 0.0001 | 0.0003 | |
| `Detectors.has_denylist_hit` | a context name in table cells | 0.010 | 0.127 | 0.002 | 0.008 | ×4.1 |
| `residue._emails` | long local part, `@`, long domain | | | 0.0002 | 0.0008 | |

The slowest line for the scrub is still `token` repeated, at about 33 µs a character: that is BUG-297's bounded alternative, unchanged here. The two rules, searched alone, measure as they did before, which is why nothing searches them: `test_bug_298_the_rules_are_tried_at_one_position_never_searched` reads the sources of `tools/dataset` and fails on any call on either but `match`.

**Real input.** `export.build` over this repository's `.adlc/` tree, as it is on the branch this one was cut from (778 artifacts; 622 replacements, of them 461 DenyList names, 69 home paths, 55 credentials, 23 SHAs, 8 people and 6 links), gives the same bytes with the code before and the code after: the three output files and the report, 5,411,401 bytes, same SHA-256. So does the tree with this report in it. No address is replaced in either: every address in the tree is on the allow list, so the export exercises the address functions only on matches that are then let through. An export took 20.0 s before and 19.5 s after, once each.

Weighed and not done:

- **Bounding the local part**, 64 characters as an address allows, with no anchor or beside one. One pattern and no function. But a bound moves a match: a local part longer than the bound is matched from 64 characters before its `@`, where the rule matched it whole, and in the residue pass an address glued to an allowed one by more than 64 characters of local part would not be found at all. The rule's own matches, at any length, are what the scrub replaces and what the residue pass compares, so they are kept exactly.
- **Putting the underscore into `EMAIL_RE`'s lookbehind and leaving it at that.** It is linear and it is the anchored pattern. It loses the `B` of `A_B`.
- **Changing the rules themselves.** `A.B` is one address for the scrub and two for the residue pass, and the scrub's match of an address inside markdown emphasis begins at the underscore in front of it. Both are as they were; `test_bug_298_an_address_that_begins_where_the_last_one_ended_is_still_found` pins them. A rule that reads addresses differently is a change to what is published, and belongs in a REQ.
- **`tools/adlc/harness_probe.py`**. Its `EMAIL_RE` is the scrub's local part with no lookbehind at all, substituted over a whole probe transcript. It measures superlinear on a long run of letters: 0.086 s at 10,000 characters and 1.378 s at 40,000. It is outside `tools/dataset` and outside this bug.
- **`scrub._home_path_replacement`** and the rest of what is done for each hit were measured with the calls and are linear: each works on the hit's own text.

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`).

Failing-first tests were still written and run against the code before the fix: `tools/dataset/tests/test_dataset_line_linear.py`. Each scaling case compares two line lengths, 10,000 and 40,000 characters, and asserts a ratio, never a time: ×4 the input may cost at most ×8 the CPU. Each timing runs in a child with a 45-second limit. There are 119 cases:

- `Scrubber.scrub_line` and `Checker.scan_line`, whole, on each of 46 line families: BUG-297's seventeen and twenty-nine more (runs with no address; shapes around an `@`; many addresses, with blanks and glued by `_` and `.`; many hits of each other rule; prose). These are the cases BUG-297 could not add.
- `Detectors.email_hits` on eighteen of the families, because the scrub's other steps hide `EMAIL_RE` in a whole `scrub_line`: before the fix that was ×8.5, against ×15.8 for the call alone.
- `Detectors.has_denylist_hit`, and `Checker._named` over every context name on a line, on four families of names in prose and in table cells.
- `scrub._replace_spans` over every person's name on a line.

Without the fix (the test file beside `tools/dataset` as BUG-297 left it), under a throwaway `HOME` and `ADLC_HOME`:

- `python3 -m pytest tools/dataset/tests/test_dataset_line_linear.py -q`: 50 failed, 79 passed, in 4 min 51 s. First failing assertion: `AttributeError: module 'detectors' has no attribute '_EMAIL_RUN_RE'`. First failing timing: `BUG-298: Scrubber.scrub_line on a context name in prose between table cells took 0.0170 s at 10000 characters and 0.1614 s at 40000: x9.5 for x4 the input`.
- 41 of the 119 scaling cases fail, every one on the ratio and none on the time limit: `Checker.scan_line` on 23 families (×8.4 to ×16.4; 0.50 s and 7.4 s on the long local part, `@` and long domain), `Scrubber.scrub_line` on 8 (×8.2 to ×15.6), `Detectors.email_hits` on 2 (×16.0), `Detectors.has_denylist_hit` on 4 (×8.5 to ×13.6), `Checker._named` on 3 (×12.2 to ×15.0) and `scrub._replace_spans` on its one (×16.5).
- Every changed piece has a failing case of its own, so a piece taken out alone fails the file. Two of the whole-function cases fail by little, `scrub_line` on letters and underscores at ×8.2 and `scan_line` on the organization's name in prose between table cells at ×8.4, because the steps that were already linear take most of their time; that is why the pieces are timed alone as well.
- The other nine failures are by design. Seven compare with a piece only the fix has and fail on the missing name; `test_bug_298_the_rules_are_tried_at_one_position_never_searched` fails on `an email rule is run with ['finditer', 'finditer']`; `test_bug_298_span_replacement_unchanged_on_random_spans` fails because the old function gave a replacement function the line in front of the span, not its start.

With the fix: 129 passed, in 57 s.

The tests that hold the fix to the old behaviour, all passing with it:

- `test_bug_298_the_rules_are_the_patterns_they_were`: `EMAIL_RE` and `_EMAIL` are, character for character, the patterns before the fix, and the anchored patterns are those with the lookbehind in front. So a comparison with `finditer` below is a comparison with the code before.
- `test_bug_298_pieces_unchanged_on_real_shapes`: 88 real-shaped lines. Fifty-seven are about addresses: as they are written (in angle brackets, after `mailto:`, in quotes, with a tag, a subdomain, capitals, a letter outside ASCII, a local part of 79 characters), inside markdown emphasis, code and a table, glued to each other by `_`, `.`, `-`, `+`, `%` and nothing, behind an allowed address, in a git remote and a URL; and nineteen that hold no address (`@types/node`, `react@18.3.1`, `user@localhost`, `foo@bar.com9`, a version, prose). Thirty-one are about the per-hit questions: a person's name at the start of a line, after each sentence end, after markdown marks and inside a sentence; a context name in prose, alone in a cell, in a cell with other words, before `.git`; lines with a newline in them. On each line `emails` and `_emails` give the spans `finditer` gives with the rule, and at every position of the line the two `_after_pipe` functions and `_starts_sentence` give what the old search of the line up to that position gives. The rules find 141 and 145 addresses in the table, 5 and 10 of them at a start the anchored pattern alone does not find.
- `test_bug_298_pieces_unchanged_on_random_lines`: 6,000 seeded random lines built from address fragments, names, pipes, sentence ends, newlines and other line-break characters, and letters outside ASCII. The same comparisons: 9,183 and 9,558 addresses, 251 and 961 of them resumed.
- `test_bug_298_scrub_and_residue_unchanged_on_real_shapes`, `…_on_random_lines` (4,000 more seeded lines) and `…_on_every_family` (each of the 46 families at 60 and 700 characters): everything `scrub_line`, `scrub_text`, `scan_line` and `residue.scan` return, for a DenyList with an organization repository and for one without, equals what they return with the six changed pieces put back as they were. The random lines hold 4,824 email replacements, 960 person replacements, 122 capitalised placeholders and 1,215 DenyList replacements.
- `test_bug_298_span_replacement_unchanged_on_random_spans`: 2,000 lines with random spans, in any order and with one repeated, replaced by a string, by nothing and by a function.
- `test_bug_298_an_address_that_begins_where_the_last_one_ended_is_still_found` and `test_bug_298_sentence_starts_and_table_cells_as_before`: the outputs themselves, spelled out.
- `test_bug_298_the_rules_are_tried_at_one_position_never_searched`: described under Resolution.

Beside the tests, the code before and the code after were run in separate processes over 300,000 more seeded random lines, two DenyLists each: every value the four functions return was written out, and the two files are the same bytes.

An independent adversarial review of the diff, given the code before beside the code after and seven claims to break, found no counterexample. For the two address functions against the rules: 400,000 random strings, and every string of up to six tokens over a nine-token alphabet, 597,871 of them. For the two per-hit functions against the patterns they replace: the same 400,000 strings at every position. For everything the four whole functions return, code before against code after: 38,000 random DenyLists, with names that hold dots, spaces, hyphens and underscores, with and without an organization repository, one to four texts each. For cost: 57 hand-built line families, eleven of them built so that the attempt after one match re-reads what the next search reads, and 1,500 random ones, at 20,000 and 80,000 characters; the largest ratio was ×4.4. It found one sentence in the changelog entry that gave the residue pass's position as the place where the scrub's function tries the rule after a match. That sentence is corrected.

The wider runs, with the fix, each under a throwaway `HOME` and `ADLC_HOME`. The last three ran before this branch was rebased onto BUG-297's final commit and before these results were written here; the tree has since changed in three files under `.adlc/` (this report, BUG-297's and one requirement), and in no code. The first ran on this commit:

- `python3 -m pytest tools/dataset -q`: 449 passed, 4 skipped, in 2 min 6 s.
- `python3 -m pytest tools -q`: 6102 passed, 7 skipped, in 47 min 9 s.
- `sh partials/tests/run.sh`: exit 0; 10,081 cases passed and none failed, in 8 min 13 s.
- `sh tools/lint-skills/check.sh`: exit 0, no finding.

What was not measured:

- **Linux, and other Python versions.** Every run was on macOS with Python 3.9.6.
- **A real export with a long line in it.** The repository's own tree exports to the same bytes and has no line of the kind this bug is about; the long lines are the tests' own.
- **Lines longer than 40,000 characters in the tests.** The measurements above stop there too. The independent review timed 20,000 against 80,000.
- **Timing under load.** The ratio tests take the best of three runs, measure CPU time, and leave a factor of two on each side of the threshold.

## Files Changed

- `tools/dataset/detectors.py`: `emails(line)` and the anchored `_EMAIL_RUN_RE` beside `EMAIL_RE`, whose text is unchanged; `email_hits` calls `emails`; `_after_pipe` and `_CELL_END_RE` for `is_prose`.
- `tools/dataset/residue.py`: `_emails(line)` and the anchored `_EMAIL_RUN` beside `_EMAIL`, whose text is unchanged; `scan_line` calls `_emails`; `_after_pipe` and `_CELL_END` for `_named`.
- `tools/dataset/scrub.py`: `_starts_sentence` in place of `_SENTENCE_START_RE`; `_replace_spans` builds the line once and gives a function the span's start.
- `tools/dataset/tests/test_dataset_line_linear.py`: new. The scaling cases, the tables of real shapes, the seeded random lines and the pinned outputs.
- `tools/dataset/README.md`: three sentences under Tests.
- `.adlc/context/architecture.md`: one sentence where the dataset export is described.
- `CHANGELOG.md`: one entry under Fixed, and a pointer from BUG-297's.
- `.adlc/bugs/BUG-298-dataset-email-patterns-superlinear.md`: this report.

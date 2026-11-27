---
id: REQ-721
title: "The exec engine's config checks read a Codex user config that holds multi-line arrays and strings"
status: draft
deployable: false
created: 2026-11-23
updated: 2026-11-27
component: "adlc/harness"
domain: "adlc"
stack: ["python", "toml"]
concerns: ["security", "correctness", "silent-failure", "testing", "unattended"]
tags: ["codex", "exec-engine", "toml", "config", "fail-closed", "validator", "trust", "sandbox", "bypass-config-keys", "multi-line", "parser", "tomllib", "differential-test", "harness", "adapter"]
lane: "full"
lane_reason: "changes the grammar accepted by the reader that two security checks stand on (criteria 1 and 2) and narrows the fail-closed list REQ-655 BR-5 records (criterion 6)"
lane_forced: false
---

## Description

Before every launch and every resume of a Codex exec run, the engine reads the operator's
`~/.codex/config.toml` twice. The bypass scan (`tools/adlc/exec_surfaces.py`, REQ-662 BR-16)
looks for the keys `harness/codex.yml` lists under `bypass_config_keys`, the ones that relax
approval or sandboxing. The trust grant (`tools/adlc/exec_trust.py`, REQ-662 BR-5) appends one
`[projects."<working copy>"]` block and removes exactly that block when the harness exits.
Both read the file with `toml_merge.scan`, the strict line reader REQ-655 wrote for the
renderer's config merge. It takes every value on one line and refuses the file otherwise.

That refusal is deliberate: a config the engine cannot read may relax approval or sandboxing,
so the run must not start (LESSON-716). But the reader refuses more than it needs to. A
multi-line array is the ordinary way to write an MCP server's `args`, and a config that has one
cannot run `/sprint --exec --harness codex` at all. The engine stops with:

```
<home>/.codex/config.toml cannot be read with certainty: multi-line array at line 5, so whether
it relaxes approval or sandboxing is unknown (REQ-662 BR-16); the engine reads this file with a
strict line reader, which takes each value on one line, [...]: put that value on one line, then
run again
```

The operator has to rewrite a file Codex reads without complaint, and keep it rewritten.
REQ-662 deferred the repair to its own requirement ("a tolerant reader for the user config").
This is that requirement.

It does not make the reader tolerant. It teaches the reader three constructs, exactly: a
multi-line array, a multi-line basic string (`"""`) and a multi-line literal string (`'''`).
For each, the reader knows where the value begins and ends, so it knows that no line inside is
a key or a table header and that the line after is read as any other. Everything else the
reader refuses today, it still refuses, and it still refuses whatever it cannot classify.

The decisions this requirement makes:

| # | Question | Decision |
|---|---|---|
| 1 | Which constructs does the reader come to understand? | A multi-line array, a multi-line basic string and a multi-line literal string, as the value of any key, at the top level or in a table (BR-1 to BR-4) |
| 2 | Which stay refusals? | A top-level inline table, a top-level dotted key, `[[array-of-tables]]`, an inline table that spans lines, a construct never closed, and every other refusal the reader has today (BR-6, BR-7) |
| 3 | A watched key whose value spans lines: read or refused? | Neither. It is a **hit**: the run is refused because the key is set, in the words of a bypass hit, not because the file is unreadable (BR-8). A value the toolkit compares with an expected one equals it only in its one-line form (BR-9) |
| 4 | Do the trust append and removal stay byte-exact? | Yes, and a copy of the block's bytes inside a string is content, never the block (BR-10 to BR-13) |
| 5 | `tomllib` where the interpreter has it? | Not in the engine. One reader runs on every interpreter, and `tomllib` is the oracle a differential test holds it to (BR-18 to BR-21) |
| 6 | One reader or a mode for the exec engine? | One reader. The renderer's merge reads the same constructs, and its writes are held to the same rule (BR-5, BR-14). This narrows REQ-655 BR-5 |
| 7 | How is a table named? | By its header's parts, never by their text joined with dots, so a quoted part that holds a dot is one part (BR-25). Decided by the owner on 2026-11-27 |

No gate moves. The bypass keys, the trust block, the lock, the recovery-marker refusal and the
approval protocol stay as REQ-659 and REQ-662 left them.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| Reader | definition | rule | the one classifier of a TOML config in the toolkit. The bypass scan, the trust grant and its pre-flight, and the renderer's merge, list union and drift check all read through it (BR-5) |
| UnderstoodConstruct | kind | enum | `multi-line array` \| `multi-line basic string` \| `multi-line literal string`. The reader knows the first and the last line of each (BR-1 to BR-3) |
| KeyReading | value form | enum | `one-line` (the value's text, as today) \| `spans-lines` (the first and last line of the value; its content is not interpreted) |
| WatchedKey | definition | rule | a key the adapter lists in `bypass_config_keys` for the file being read. A watched key with a `spans-lines` value is a hit (BR-8) |
| ComparedValue | definition | rule | a value the toolkit compares with an expected one: the adapter's owned config values, `trust_level` in the table of the path being granted, and the renderer's owned list. It equals the expected value only in `one-line` form (BR-9) |
| Refusal | file | path | the config that was read |
| Refusal | construct | string | a name from the table below, or one the reader already uses |
| Refusal | line | integer | 1-based. For a construct that spans lines, the line it opens on. Absent only for a whole-file construct (a BOM, a carriage return), where the message says the whole file |
| Refusal | action | string | what the operator can write instead, from the table below (BR-15) |
| CorpusCase | config | text | one TOML config, placeholders only (BR-22) |
| CorpusCase | expected | reading or refusal | the tables in order, each table's keys, each key's value form and its one-line text; or the construct and line of the refusal (BR-19) |

Constructs that stay refusals, and the action each refusal carries:

| Construct | Action the message gives |
|---|---|
| top-level inline table | write that table as a `[table]` header with each key on a line of its own |
| top-level dotted key | write that key under its `[table]` header |
| `[[array-of-tables]]` | write those entries as one array of inline tables, each on one line, under the parent table's key |
| inline table spanning lines | put the inline table on one line, or write it as a `[table]` |
| multi-line string or multi-line array never closed | close it; the message names the line it opens on |
| a line that is not `key = value`, a header, a comment or blank, including text after a closing delimiter | write that line in one of those forms |
| a key whose value does not start on its line | start the value on the key's line |
| duplicate key, duplicate table header | keep one |
| escaped key | spell the key without an escape |
| BOM, carriage return | save the file as UTF-8 with no BOM and with LF line endings |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| config refused as unreadable | the bypass scan or the trust pre-flight meets a construct in the table above | file, construct, line, action. Unchanged in kind; fewer configs raise it |
| bypass hit | a watched key is set to anything but the value the toolkit's own render sets, in either value form | file, key, and for a `spans-lines` value the lines it spans in place of its text (BR-8, BR-17) |
| trust granted, trust revoked | as REQ-662 BR-5 | unchanged |

## Business Rules

Each rule below that refuses names a case beside it that must not be refused (LESSON-440).

### 1. What the reader understands

- [ ] BR-1: **Multi-line array.** A value that opens with `[` on its key's line and closes on a later line is read as one value, at the top level or in a table. Inside it the reader follows nested arrays, strings of all four forms, comments, blank lines, a trailing comma and an inline table written on one line. No line inside it is a key or a table header. A bracket, a `#` or an `=` inside a string changes nothing, and neither does a bracket, a quote or a string delimiter inside a comment: a comment runs to the end of its line and opens nothing. Must not refuse: an MCP server's `args` written one element per line with a trailing comma and a comment.
- [ ] BR-2: **Multi-line basic string.** A value that opens with `"""` is read to its closing `"""`, whether that is on the same line or a later one. The reader applies the format's own rules for where the string ends: a backslash escapes the character after it, so `\"` does not begin a delimiter; one or two quotes may stand directly before the closing delimiter and belong to the string; a backslash that ends a line continues the string. No line inside it is a key, a table header or a comment.
- [ ] BR-3: **Multi-line literal string.** A value that opens with `'''` is read to its closing `'''`, on the same line or a later one. Nothing inside it is an escape; one or two apostrophes may stand directly before the closing delimiter and belong to the string. No line inside it is a key, a table header or a comment.
- [ ] BR-4: **The line after is read.** After the closing delimiter of any of the three, only blanks and a comment may follow on that line; anything else refuses (BR-6). The next line is classified as any line is. A watched key or a table header that follows a multi-line value is seen exactly as it would be after a one-line value. This is the rule a mistake in BR-2 or BR-3 breaks silently, so it has its own acceptance criterion (AC-5). Must not refuse: a closing delimiter followed by blanks and a comment. (informed by LESSON-716)
- [ ] BR-5: **One reader.** Every caller reads the same file the same way: the bypass scan, the trust grant and its pre-flight, and the renderer's merge, list union and drift check. There is no mode in which a file reads cleanly for one caller and is a refused multi-line construct for another. This narrows REQ-655 BR-5, which lists "multi-line strings and arrays" among the constructs the renderer's merge refuses: after this requirement the merge reads them, and BR-14 holds its writes. (informed by REQ-655, LESSON-716, LESSON-756)

### 2. What stays a refusal

- [ ] BR-6: The constructs in the System Model's table refuse, in every caller, wherever they refuse today, and two are named for what they are: an inline table that spans lines is refused as that, at the top level, in a table or inside a multi-line array (today it is reported as a multi-line array); a multi-line string or array still open at the end of the file is refused naming the line it opens on. Must not refuse: an inline table on one line as a key's value inside a table, an inline table on one line as an element of a multi-line array, a dotted key inside a table the toolkit owns no key in, and a quoted header that names another table (`[projects."<path>"]`, `[mcp_servers."<name>"]`), all of which read today.
- [ ] BR-7: **Still fail closed.** A line or a value the reader cannot place in one of the forms it knows refuses the file. The reader never skips a line, never guesses where a value ends, and never reads past a construct it has refused. Understanding three constructs adds no tolerant branch for a fourth. Must not refuse: any config made only of the forms BR-1 to BR-3 and BR-6 say are read. (informed by LESSON-716)

### 3. Keys the checks interpret

- [ ] BR-8: **A watched key whose value spans lines is a hit.** The bypass scan refuses the run as it refuses any bypass key: the message names the file, the key and the line, and says the key relaxes approval or sandboxing. It is never a clean scan, and it is never the unreadable-file refusal, whose advice would send the operator to put the value on one line only to be refused again for the key. This holds for a multi-line array (an empty one included) and for both multi-line string forms, in the user config and in a working copy's config, each against its own key list. Must not hit: a key of the same name written inside a multi-line string or array, a watched key name in a `[profiles.<name>]` table whatever form its value takes, and a key the adapter does not list in a watched table (`[sandbox_workspace_write]`) with a multi-line value.
- [ ] BR-9: **A compared value equals the expected one only on one line.** Where the toolkit compares a value with one it expects, a value that spans lines is not equal, even when its text spells the expected value. So `sandbox_mode = """workspace-write"""` in the user config is a hit (BR-8). A `trust_level` written as a multi-line string in the table of the path being granted is not read as `trusted`: the grant refuses as it does for any operator entry that does not read `trusted`, and writes nothing. An owned key of the renderer's merge that spans lines refuses as a value that is not a plain string does today. The renderer's owned list (`writable_roots` under `--writable-root`) written across lines refuses, naming it; there the advice to write the array on one line is true and stays. Must not refuse: the same keys in their one-line form, which read as they do today.

### 4. The trust write stays byte-exact

- [ ] BR-10: **Grant and revoke around the constructs.** On a user config holding any of the three constructs anywhere, the file after a grant is the file before it plus the block's bytes (and the one newline REQ-662 already adds to a file with no final newline), and the file after the revoke is byte-identical to the file before the grant, mode included. This holds when a multi-line value is the last thing in the file, with or without a final newline. Must not refuse: the realistic config of AC-1. (informed by REQ-662)
- [ ] BR-11: **The block never lands inside a construct.** The grant writes only when the whole file reads, and its own output must read back with `[projects."<path>"]` as a table whose `trust_level` is `trusted`, as today. A file that ends inside an open string or array is refused (BR-6) before a byte is written. Must not refuse: a file whose last line closes a multi-line value and has no final newline (BR-10).
- [ ] BR-12: **A copy of the block inside a value is content.** Text inside a multi-line string or array that spells the block's bytes, its comment line or its header is the operator's text. It is not a trust entry for the path, it is not a block a killed run left, it is never counted when revoke looks for the block, and it is never removed. Must not refuse: a grant and a revoke on a file that holds such a copy; the grant appends the real block and the revoke removes that one and leaves the copy, byte for byte.
- [ ] BR-13: **Revoke does not wait for the whole file to read.** Removing the block must not depend on the rest of the file classifying: a construct BR-6 refuses, written into the file during the run before or after the block, does not stop the removal. Revoke needs to know one thing, that the block's lines stand outside every multi-line string and array. When it cannot know that (a string or array opened before the block and never closed), it leaves the file as it is and warns, naming the header to remove by hand, as it does today for a block edited since the grant. No new status word is added. Must not refuse: a revoke after a top-level inline table was added to the file mid-run.
- [ ] BR-14: **The renderer's writes obey the same rule.** The merge still inserts owned keys before the first table header and the list union still writes only inside its one-line array, and neither write lands inside a multi-line value: a line that looks like a header inside a multi-line string above the first real header is not the insertion point. The re-classification of the output, and the check that every byte outside the insertion is unchanged, stay. Must not refuse: a merge or a `--writable-root` union into a config that holds multi-line `args` in another table. (informed by REQ-655)
- [ ] BR-15: **The check after the revoke names real tables only.** The comparison that logs `trust_file_changed` (REQ-662 BR-5, amended) names a `[projects."<path>"]` table as newly present only when it is a table header, not a line inside a multi-line value. It still warns and refuses nothing. (informed by LESSON-716)

### 5. What a refusal says

- [ ] BR-16: Every refusal of a config by the bypass scan or by the trust pre-flight and grant names the file, the construct, the line and the action, as the Refusal entity defines them. The two checks use the same construct name and the same action for the same construct. The trust refusal gains the action, which it does not give today.
- [ ] BR-17: **No refusal quotes what it does not watch.** No refusal, hit, log event or run note carries text from inside a multi-line value, or the value of any key the check does not watch: an MCP server's `env` and `args` are where an operator's tokens are. A hit on a watched key whose value spans lines gives the key and the lines it spans, not the value.
- [ ] BR-18: **No false advice.** "Put that value on one line" is given only where it is true (BR-9's owned list). The README's Codex section and `tools/adlc/README.md` state the new limit in the same change: which constructs still refuse, and that a multi-line array or string no longer does.

### 6. One reader, held to `tomllib`

- [ ] BR-19: **`tomllib` is not in the engine.** The reader is the same standard-library code on every interpreter the toolkit supports, Python 3.9 included, and no file under `tools/` outside the tests imports `tomllib`. Three reasons: the same config must be read the same way on every machine; the trust write and the renderer's merge need the byte positions a parser's result does not carry; and the refusals of BR-6 distinguish spellings (a dotted key from a table header, an inline table from a table) that parse to the same value. (informed by REQ-655, LESSON-395)
- [ ] BR-20: **A corpus of configs with recorded readings.** The tests carry a corpus of configs, each with its expected reading or refusal (CorpusCase). The reader is asserted against every case on every interpreter, so the Python 3.9 path is held to the same expectations as any other. The corpus holds at least: the realistic config of AC-1; every case named in AC-2 to AC-9; each understood construct at the top level, in a table and as the last value in the file, with and without a final newline; and each of those followed by a watched key, by a table header and by the trust block.
- [ ] BR-21: **The differential test.** Where the interpreter has `tomllib`, every corpus case is also checked against it: (a) a case expected to read parses with `tomllib`, the tables and keys the reader reports are the tables and keys `tomllib` yields, compared part by part, and every one-line string or boolean the reader reports is the value `tomllib` gives; (b) for every watched key of the shipped Codex block and for `trust_level` under each `projects` table, the reader reports the key exactly when `tomllib` has it; (c) a case `tomllib` rejects is a case the reader refuses, with one exception the corpus marks case by case: a file whose only fault is a one-line value the reader does not interpret (a malformed number or date), which the reader reads today and Codex cannot parse at all. A case the reader refuses and `tomllib` accepts is allowed, and its expected refusal names a construct from BR-6.
- [ ] BR-22: **The differential test runs before a release.** On an interpreter with no `tomllib` the test reports a skip that says so. A switch turns that skip into a failure, as `ADLC_REQUIRE_PYYAML=1` does for the YAML-backed tests, and `RELEASING.md`'s test step runs the suite once under an interpreter that has `tomllib` with the switch set. A differential test that only ever skips proves nothing.
- [ ] BR-23: **Fixtures and tests.** Every test runs under a sandbox `HOME` and never opens the operator's real config. No fixture, expected reading or recorded run holds a real key, token, email address, user name or home path: placeholders only.
- [ ] BR-25: **A header's parts stay parts.** The reader reports a table's name as the sequence of its header's parts, each bare or quoted part one element, and never as their text joined with dots. `[projects."/a".b]` is the table (`projects`, `/a`, `b`) and `[projects."/a.b"]` is the table (`projects`, `/a.b`); they are two tables, and every caller that looks a table up (the trust entry for a path, the watched tables of the bypass scan, the renderer's owned tables, the duplicate-header refusal) compares part by part. A `trust_level` under `[projects."/a".b]` says nothing about the path `/a.b`. Must not refuse and must not change: every header that reads today, which names the same table it named, including a quoted part that holds a dot (`[projects."/a.b"]` is still the entry for `/a.b`). (owner's answer of 2026-11-27; informed by LESSON-716)
- [ ] BR-24: **The recorded decisions are amended in the same change.** REQ-655 BR-5 and REQ-662 BR-16 each gain a dated amendment pointing here, saying which constructs the reader now understands. REQ-662's deferral note for "a tolerant reader for the user config" is marked as taken up by this requirement.

## Acceptance Criteria

All under a sandbox `HOME`.

- [ ] AC-1: **The realistic config.** A user config with top-level scalar keys, a top-level multi-line array, a top-level multi-line string, two `[mcp_servers.<name>]` tables whose `args` are written one element per line (one with a trailing comma and a comment), an `env` inline table on one line, and an existing `[projects."<other path>"]` table: the bypass scan returns no hit and no refusal, the trust pre-flight passes, a grant appends exactly the block, and the revoke leaves the file byte-identical to its first state. (BR-1, BR-2, BR-3, BR-10)
- [ ] AC-2: **Arrays.** Each of these reads, and reports its key once with the form `spans-lines`: nested arrays across lines; an element string containing `]`, `[`, `#`, `=` and `"""` inside a literal string; a comment line and a blank line between elements; a comment between elements that holds an apostrophe, a `]`, a `"""` and a `'''`; a closing `]` followed by a comment; an inline table on one line as an element; a multi-line string as an element. (BR-1)
- [ ] AC-3: **Strings.** Each of these reads: a `"""` and a `'''` string closed on the same line; each closed on a later line; a basic string holding `\"""`, which does not close there; a basic string ending `\\"""`, which does; a basic string ending `""""` and one ending `"""""`; a basic string with a line-ending backslash, and one whose line ends in an escaped backslash; a literal string ending `''''` and one ending `'''''`; a literal string holding a backslash before a quote. (BR-2, BR-3)
- [ ] AC-4: **Content is not structure.** Inside each of the three constructs, lines spelling `sandbox_mode = "danger-full-access"`, `[sandbox_workspace_write]` followed by `writable_roots = ["/elsewhere"]`, `approval_policy = "never"`, a `#` comment, and the whole trust block for the run's path: the bypass scan returns no hit, the reading holds no such table, and the path is not read as already trusted. (BR-1, BR-2, BR-3, BR-12)
- [ ] AC-5: **The key after the value is seen.** For every case of AC-2 and AC-3, the same config with `sandbox_mode = "danger-full-access"` on the line after the value yields that hit, and with `[sandbox_workspace_write]` and `network_access = true` after it yields that hit. No case reads clean. (BR-4)
- [ ] AC-6: **Refusals that stay.** A top-level inline table, a top-level dotted key, `[[array-of-tables]]`, text after a closing `"""`, `'''` or `]`, a key whose value starts on the next line, a duplicate key, a duplicate header, an escaped key, a BOM and a carriage return each refuse in the bypass scan and in the trust pre-flight, and the trust file is unchanged. Beside them, each reading with no refusal: an inline table on one line in a table, a dotted key in an `[mcp_servers.<name>]` table, a quoted header naming another table. (BR-6, BR-7)
- [ ] AC-7: **An inline table that spans lines** refuses as that construct, not as a multi-line array, at the top level, as a key's value in a table, and as an element of a multi-line array; the line named is the one the inline table opens on. (BR-6)
- [ ] AC-8: **Never closed.** A `"""` string, a `'''` string and an array that reach the end of the file each refuse naming the line they open on, with and without a final newline; a grant attempted on each writes nothing. (BR-6, BR-11)
- [ ] AC-9: **Watched keys that span lines.** `writable_roots` under `[sandbox_workspace_write]` as a multi-line array, the same array empty, `sandbox_permissions` as a multi-line array, `sandbox_mode = """workspace-write"""` and `approval_policy` as a `'''` string each refuse the run as a bypass hit whose text names the key and its lines and does not contain "cannot be read". Beside them, each with no hit: `sandbox_permissions` as a multi-line array under `[profiles.fast]`; a key the adapter does not list under `[sandbox_workspace_write]` as a multi-line array; `sandbox_mode = "workspace-write"` on one line. The same cases pass against a working copy's config with its own key list. (BR-8, BR-9)
- [ ] AC-10: **`trust_level` that spans lines.** With `[projects."<path>"]` and `trust_level = """trusted"""` for the run's path, the grant refuses, names the entry, and writes nothing. With `trust_level = "trusted"` on one line the grant records `pre_existing` and the revoke leaves the entry, as today. (BR-9)
- [ ] AC-11: **The renderer.** Into a config holding a top-level multi-line array, a multi-line string whose content includes a line spelling `[a]`, and a table with multi-line `args`: the merge inserts the owned keys before the first real header and every other byte is unchanged; a second merge changes nothing; the drift check reads the result as in step; `--writable-root` adds its entry and every other byte is unchanged. An owned key written as a multi-line string refuses and writes nothing. An owned list written across lines refuses, names it, and says to write it on one line. (BR-5, BR-9, BR-14)
- [ ] AC-12: **Byte-exact grant and revoke.** For a config whose last value is each of the three constructs, with and without a final newline, and for one with operator `[projects]` entries before and after a multi-line value: after the grant the file is the original plus the block (plus one newline where there was none), and after the revoke it is byte-identical to the original with its mode unchanged. (BR-10, BR-11)
- [ ] AC-13: **A copy inside a string.** A config whose multi-line string holds the block's exact bytes for the run's path: the grant appends the real block and is neither `pre_existing` nor `adopted`; the revoke removes the appended block only and the file is byte-identical to its first state. The same holds for a revoke built from the path alone after a kill. A config holding only the block's comment line and header inside a string, with no real block, is reported as gone, not as edited. (BR-12)
- [ ] AC-14: **Revoke on a file changed mid-run.** After a grant, a top-level inline table appended after the block, and separately one inserted before it: the revoke removes the block and leaves every other byte. After a grant, a `"""` opened above the block and never closed: the revoke writes nothing and its warning names `[projects."<path>"]`. (BR-13)
- [ ] AC-15: **The check after the revoke.** With a `[projects."/elsewhere"]` line added inside a multi-line string during a run, the `trust_file_changed` note names no new table; with the same line added as a real header, it names it. Neither refuses anything. (BR-15)
- [ ] AC-16: **What a refusal says.** For every refusing case of AC-6, AC-7 and AC-8, the bypass scan's message and the trust check's message each contain the file path, the construct's name, the line (or that the whole file is meant, for a BOM and a carriage return) and the action from the System Model's table, and the two use the same construct name and action. Beside them: a config holding only understood constructs draws no message from either check, and no message other than AC-11's owned-list refusal says to put a value on one line. (BR-16, BR-18)
- [ ] AC-17: **Nothing is quoted.** A config whose MCP `env`, `args` and a multi-line string each hold a marker string, run through every refusing and hitting case above: no refusal, hit, event-log line or run note contains the marker. (BR-17)
- [ ] AC-18: **The corpus on every interpreter.** `python3 -m pytest tools -q` under Python 3.9 asserts every corpus case's expected reading or refusal and passes, and the corpus holds the cases BR-20 lists. For each ending rule of BR-2 and BR-3 and for BR-4 there is a case whose expected reading differs from what a reader without that rule would report. (BR-20)
- [ ] AC-19: **The differential test.** Under an interpreter with `tomllib`, every corpus case satisfies BR-21 (a), (b) and (c). (BR-21)
- [ ] AC-20: **It cannot only skip.** Under Python 3.9 the differential test is reported skipped, with a reason naming the missing module; with the switch set it fails instead. `RELEASING.md`'s gate list runs the suite under an interpreter with `tomllib` and the switch. (BR-22)
- [ ] AC-21: **No `tomllib` in the engine.** A test asserts that no Python file under `tools/` outside a `tests` directory imports `tomllib`. (BR-19)
- [ ] AC-22: **Fixtures.** A test asserts that no corpus file or fixture added here holds an email address, a path under a real home directory (`/Users/<name>`, `/home/<name>`) or a string in the shape of a credential, and every test added here sets `HOME` to a temporary directory before it reads or writes a config. (BR-23)
- [ ] AC-23: **One real run.** The stage-1 live script (`tools/adlc/tests/e2e/codex-exec-live.py`, ASSUME-033) is run once against the installed Codex with a sandbox `HOME` whose `config.toml` is AC-1's: the run launches, and the checksum of the user config taken after the revoke and before any restore equals the one taken before the grant. The run is recorded beside the others in `.adlc/research/harness-probes/codex-exec-manual.md`. (BR-10; informed by LESSON-891, LESSON-889)
- [ ] AC-26: **Header parts.** With `[projects."/a".b]` holding `trust_level = "trusted"` and the run's path `/a.b`: the path is not read as trusted, the grant appends the block and is not `pre_existing`, and the revoke restores the file byte for byte. With `[projects."/a.b"]` holding the same key, the grant records `pre_existing`, as today. A file holding both headers reads as two tables and is not a duplicate-header refusal; the same header written twice still is. A watched table's name written with a quoted part that holds a dot (`["sandbox_workspace_write.x"]`) is not the watched table and not a table under it. The differential test compares these cases part by part. (BR-25, BR-21)
- [ ] AC-24: **Documents.** The README's Codex "Bypass keys" row and `tools/adlc/README.md` state the limit as BR-18 requires; REQ-655 BR-5 and REQ-662 BR-16 carry their amendments and REQ-662's deferral note points here. (BR-18, BR-24)
- [ ] AC-25: **Nothing else moved.** Every existing fail-closed case in `tools/adlc/tests/test_toml_merge.py`, `test_exec_surfaces.py` and `test_exec_trust.py` still refuses, apart from the multi-line array and the two multi-line string cases this requirement turns into readings; `python3 -m pytest tools -q` and `bash tools/lint-skills/check.sh` pass. (BR-5, BR-6, BR-7)

## External Dependencies

- None new. The reader stays standard library on Python 3.9. `tomllib` (standard library from Python 3.11) is used by one test and nowhere else.
- AC-23 needs an installed, signed-in Codex CLI of the version `harness/codex.yml` declares, as every stage-1 live run does.

## Assumptions

- For a file that is valid TOML 1.0, Codex reads the same tables, keys and values that `tomllib` does. Not measured here; AC-23 checks one config against the real CLI.
- A `config.toml` Codex cannot parse does not relax anything: Codex stops, or runs on defaults with the sandbox the argv pins. The reader may therefore refuse more than Codex does, but must never read a file differently from the way Codex reads it.
- An interpreter with `tomllib` is present wherever a release is cut. On a machine with only Python 3.9 the corpus still runs; the differential half does not.
- Operators write multi-line arrays far more often than the constructs that stay refusals. The brief for this requirement states it for MCP `args`; no survey of real configs was made, and no real config was read while drafting.

## Open Questions

All are answered. The owner answered the first two, and the two below them, on 2026-11-27, before `/architect`; the last was answered on 2026-11-24.

- [x] **`[[array-of-tables]]` stays a refusal here. The owner confirmed it on 2026-11-27: keep refusing, no extra rule.** The check the draft proposed was made the same day: the owner's own `~/.codex/config.toml`, a file an installed Codex has been using, holds no line that opens with `[[` (a count of matching lines, 0; the file was not printed, copied or committed). That is one config and one Codex version, not proof that no release writes one, so the refusal keeps the action text of the System Model's table and a config that does hold one is a new requirement. The question as first written: if a Codex release writes one into the user config by itself, an operator clears this requirement's refusal and meets that one next. The repository does not say whether it does. Proposed: check a Codex-written config before `/architect`; if it does, add a rule that reads a `[[name]]` header as a table no watched key lives in, and refuses one whose name is, or is under, `projects` or a watched table.
- [x] **The reader joins a header's parts with dots. The owner confirmed on 2026-11-27: fix it in this requirement (BR-25, AC-26).** Found while drafting: `[projects."/a".b]` and `[projects."/a.b"]` both read as `projects./a.b`, so a `trust_level` under the first is read as trusting the path `/a.b`, and the grant would record `pre_existing` and write nothing. BR-21 (a) compares part by part and would fail on it. The alternative, not taken, was a bug report and a named exception in the corpus.
- [x] **BR-15 changes a function in a file another run owns. The owner answered on 2026-11-27: a one-function edit.** The comparison BR-15 names is `trust_snapshot` in `tools/adlc/sprint_exec.py`, which the REQ-720 run is changing at the same time. The table-aware reading lives in `tools/adlc/exec_trust.py`; this requirement changes only the body of `trust_snapshot` in `sprint_exec.py` and is rebased over REQ-720 before its PR leaves draft.
- [x] **AC-23 cannot be run now. The owner answered on 2026-11-27: ship with AC-23 owed.** The Codex plan is exhausted until 2026-11-30 and a real launch needs the owner's yes each time. The implementation, review and merge go ahead with AC-23 unchecked; the run is owed after 2026-11-30 on the owner's yes, and it is recorded as owed in the PR and at close-out, not as passed.
- [x] **One reader narrows REQ-655 BR-5 (decision 6, BR-5). The owner confirmed it on 2026-11-24, after the spec PR (#316) merged: one reader, no exec-only mode.** The renderer's merge reads the same three constructs, BR-14 holds its writes, and BR-24's amendment to REQ-655 BR-5 is owed with the implementation. The question as first written: the alternative is a mode that only the exec engine's two checks turn on, leaving the renderer's merge as strict as it is. The draft takes one reader because two readings of one file is the fault LESSON-716 describes, and because an operator with multi-line `args` is refused by `--writable-root` today for the same reason. It reverses a recorded rule, so it needed the owner's yes.

## Out of Scope

- A general TOML parser, in the engine or vendored. The reader classifies keys and tables and knows where three kinds of value end; it does not interpret values.
- Reading a top-level inline table, a top-level dotted key or `[[array-of-tables]]` (see the first open question for the last).
- Editing a value that spans lines. The toolkit never rewrites one: the list union into a multi-line `writable_roots` stays a refusal.
- CRLF line endings and a BOM, which stay whole-file refusals.
- JSON configs, and the trust and bypass checks of the Antigravity, Cursor and Copilot stages of REQ-662.
- The other two proposals REQ-662 deferred: what Codex allows inside its sandbox together with the fence runner's git environment, and a token for `answer`.
- What the operator's own MCP servers and rule files allow. REQ-662 BR-19 declares that residual and this requirement does not change it.

## Retrieved Context

- REQ-662 (spec, score 18): Exec adapters for Copilot CLI, Codex, Gemini CLI and Cursor, accepted only on passing REQ-664 probes
- LESSON-756 (lesson, score 14): A framework proven on one adapter has only proven that adapter's branches — audit what the second one reaches first, because those paths have never run
- LESSON-887 (lesson, score 13): On a sandboxed harness an allow rule is an exit from the sandbox, not a pre-approval: render only what has to leave
- REQ-655 (spec, score 13): Codex CLI harness adapter: `harness/codex.yml` and the Codex render targets
- REQ-719 (spec, score 11): The exec engine's open findings from its first real run: `abort` drops a blocked run, the lane check works on a single-branch clone, a fence is held to its caller's PR, an arg file is opened without a window, a rejected run records `rejected`, and Phase 7 reads CI through the forge adapter
- LESSON-889 (lesson, score 11): A script that restores a file when it exits hides what the tool under test wrote to it: compare before you restore
- REQ-682 (spec, score 11): Skill fences run under `/sprint --exec` without widening what the model can run
- LESSON-873 (lesson, score 11): A probe effect built from two side effects can be met by two separate commands: tie it to the admitted command's own output, and never read a refusal from a step the shell runs before the command
- REQ-707 (spec, score 11): A `runner-prefix` variant for the `fence-vs-allowlist` probe: does one absolute-path allow admit the fence runner and nothing past it?
- LESSON-765 (lesson, score 11): A hook can be well-formed and still never run — read the harness's own hook inventory before treating a failed hook probe as a format defect
- REQ-658 (spec, score 11): Antigravity CLI adapter: `agy` as a harness, evidence first, then `harness/antigravity.yml` and the route the evidence supports
- LESSON-891 (lesson, score 10): A test double written from the system's side supplies what the real actor cannot: run the whole flow once with the real actor, against a double no kinder than the real service
- LESSON-893 (lesson, score 10): Codex runs a chained line outside the sandbox only when every command on it has an allow: a tool that needs to leave the sandbox must check that it has
- LESSON-890 (lesson, score 10): A kill sweep keyed on an id two runs can share kills the other run: tag processes with something only this run has
- REQ-659 (spec, score 10): /sprint exec engine — a shell orchestrator that runs one headless harness process per REQ, stops at the merge gate, and performs every one-way move itself after `/sprint approve`

Read in full outside the top 15, the first because the brief names it and the other two because the code under change cites them:

- LESSON-716 (lesson, score 10, rank 20): A validator for a format another reader consumes must parse the way that reader does — enumerate last-wins keys, key spellings and continuations, and fail closed on anything it cannot see
- LESSON-440 (lesson, score 6): Every collision/anomaly detector needs a benign-path AC — a matrix that only tests adversarial shapes ships false positives through a green suite
- LESSON-395 (lesson, score 3): A bootstrap diagnostic cannot depend on anything it diagnoses — adlc doctor is pure stdlib because it runs before the machine is set up

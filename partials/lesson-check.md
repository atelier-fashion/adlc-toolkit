# partials/lesson-check.sh — call-site protocol

`adlc_lesson_check` is the structural guard on lesson capture (REQ-646 BR-3). It
validates the `LESSON-*.md` file a capture step **just wrote** — `/wrapup` Step 4 and
`/bugfix` Phase 6 Step 4 are the only writers — against the v2 schema: the required
`kind` / `evidence` / `confidence` fields, the optional `enforcement` / `generalizes` /
`supersedes` fields, and the `## Lesson` / `## Applies When` sections. Prose asking
for evidence did not hold (25 of 81 lessons lack `## Applies When`), so the rule is
enforced by a partial, not by the prompt (LESSON-012).

This file is the **one home** for the rule set. The SKILL.md capture steps link here
rather than repeating the regexes (LESSON-441's two-copies class). Where the
implementation departed from the REQ's ADR-3 as first drafted, the departure is listed
under [Departures from the original ADR-3](#departures-from-the-original-adr-3).

## Signature

```
adlc_lesson_check <lesson-file>
```

There is no cutoff argument. "New" means "written by a capture step", so the file just
written is new by construction, and the check is never run over the historical corpus
(BR-2). A date literal in a guard is a guard that rots (LESSON-019).

## Return-code registry

| rc | meaning | stdout | stderr | caller action |
|----|---------|--------|--------|---------------|
| 0 | every rule holds | (empty) | (empty) | go on to the `adlc_recheck_id lesson` fence |
| 1 | one or more violations | (empty) | one `<field>: <reason>` line per violation | the repair loop (below) |
| 2 | usage: missing argument, a symlink, a basename that is not `LESSON-<digits>-<slug>.md` (3+ digits, digits only, nothing but `A-Z a-z 0-9 . _ -` in the name), an unreadable file, or no frontmatter block | (empty) | `lesson-check: …` naming the file by its basename only | a caller bug: fix the path, never treat it as a pass |

The `<field>` that starts each rc-1 line is the frontmatter key (`title`, `kind`,
`evidence`, `confidence`, `enforcement`, `generalizes`, `supersedes`, or — for the
home-path and credential scans, which read every frontmatter line — an unknown key
such as `notes`), `frontmatter` for a frontmatter line that sets no key (a `# …`
comment line), or the section heading, written as the heading itself:
`## Lesson: section is empty …`, `## Applies When: section missing …`. It is the name
the repair targets and the `<field>` in the `NO_ENTRY` fallback. A reason never echoes the offending value,
because that value might be a credential, and an rc-2 line prints only the file's
basename with every non-printing byte shown as `?`, so a crafted file name cannot
forge a `<field>: <reason>` line and a home directory in the path never reaches a
transcript.

## Call-site protocol

The fence sits **after** the instruction that writes the lesson file (the model writes
it with its file tool, not in a fence) and **before** the `adlc_recheck_id lesson`
fence. `tools/lint-skills`'s `lesson-check-order` check enforces that order. Source
the partial and call it **in the same fenced block**, because SKILL.md fences share no
shell state (conventions.md "Bash in skills"). The path is a **threaded literal**: the
model substitutes the real path of the file it just wrote. It is never a variable
carried in from another fence, because `cross-fence-var` sanctions no such name
(ADR-1):

```sh
if [ -f .adlc/partials/lesson-check.sh ]; then . .adlc/partials/lesson-check.sh; else . ~/.claude/skills/partials/lesson-check.sh; fi
adlc_lesson_check .adlc/knowledge/lessons/LESSON-<id>-<slug>.md
```

### The repair loop (ADR-4)

- On rc 1, repair **only the named field(s)**. A frontmatter key is rewritten on its
  one line. A named section (`## Lesson`, `## Applies When`) that is missing or empty
  may be added or filled; no other part of the body is regenerated. Then run the fence
  again.
- Repair **at most twice**. After the third failure, delete the draft file and write
  `NO_ENTRY: schema check failed — <field>` to the summary slot (`### Lessons
  captured`). The id allocated for the draft stays spent — a gap in the counter,
  never a reuse.
- **The model keeps the count. The fence does not.** A retry counter in shell would be
  a cross-fence variable (a lint finding), and a `trap` cannot span fences.
- This is **not** a pipeline halt and adds no halt point to `/proceed`. `/wrapup`
  Steps 5–8 run regardless.
- Reject, never redact. The remedy is the repair loop, because an `evidence` that the
  check rewrote silently would be a citation nobody wrote.

### Provenance-classifying harness (BUG-228)

On a harness that classifies preamble provenance (the BUG-228/BUG-230 class, e.g.
Teton Code), running a partial by path pins the session to its local tier. There, run
**none** of the fence. Validate the draft **in-model** against the rule table below
and write `lesson check: in-model (provenance-classifying harness)` in the summary
slot. On that harness the enforcement is honor-system, and BR-15 says so.

## Rule table

All regexes are ERE, matched with `grep -E` (or the awk noted) under `LC_ALL=C`, BSD-
and GNU-safe. Delimiters are explicit `[^…]` classes, because BSD grep silently
ignores a word-boundary escape (LESSON-013). `[[:space:]]` is spelled `[ [:space:]]`
in the partial — the same set — so the file never holds a doubled open-bracket.

| Rule | Check |
|---|---|
| file | rc 2 unless the argument is non-empty, **not a symlink**, has a basename matching the shell glob `LESSON-[0-9][0-9][0-9]*-*.md` whose id segment (between `LESSON-` and the next `-`) is digits only and which holds no byte outside `A-Z a-z 0-9 . _ -` (checked with `tr` under `LC_ALL=C`; a newline, blank, `$`, `:` or non-ASCII byte is refused), and is a readable regular file. |
| normalisation | a leading UTF-8 BOM and a trailing `\r` on every line are dropped before any rule reads the file. |
| frontmatter | the first line that is neither blank nor inside an `<!-- … -->` comment must be exactly `---`; the block closes at the next `---` line (ADR-2). Otherwise rc 2 — a `---` inside the comment, or a horizontal rule below body text, is not the block. |
| keys | a key is `^<key>:([ \t]\|$)`. **Fail closed on spelling:** for each validated key — `title`, `kind`, `evidence`, `confidence`, `enforcement`, `generalizes`, `supersedes` — a frontmatter line matching `^["']?<key>["']?[ \t]*:` that is not `^<key>:([ \t]\|$)` is rejected: `<key>: must be written as "<key>:" followed by a blank` (`supersedes:[LESSON-034]`, `kind:process`, `evidence : x`, `"evidence": x`). A required key present only in a misspelt form gets that line alone, not also `missing`. Each validated key appears **at most once** (`<key>: key appears N times`). Unknown keys are ignored by every rule except the home-path and credential scans. |
| parse | a violation on its key: a quote never closed on the key's line; an unquoted value starting `[` or `{` whose brackets are not closed on the line (`<key>: value continues onto the next line`); or a continuation — the next frontmatter line that is neither blank nor a `#` comment (indented or not) does not start a key, in any spelling (`^["']?[A-Za-z_][A-Za-z0-9_-]*["']?[ \t]*:`). So `supersedes:` + `- LESSON-404` (at column 0 or indented) and `evidence: x` + a plain text line are rejected; an indented `# note` under a key is not. `title` parse errors are reported like any other key's. |
| required keys | `kind`, `evidence`, `confidence` present and non-empty |
| `kind` | `^(process\|domain)$` |
| `confidence` | `^(high\|medium\|low)$` |
| `enforcement` (when present) | `^(none\|lint:[A-Za-z0-9_.-]+\|test:[A-Za-z0-9_./-]+\|script:[A-Za-z0-9_./-]+\|hook:[A-Za-z0-9_.-]+)$`, and a `test:`/`script:` path is repo-relative: `^(test\|script):(/\|(.*/)?\.\.(/\|$))` is rejected. Absent means `none`. |
| `generalizes`/`supersedes` | an unquoted value — a quoted one (`"[LESSON-404]"`) is one string, not a list — whose every entry is `^LESSON-[0-9]{3,6}$` after stripping `[ ] " ' ,` (so `['LESSON-404']` passes). |
| `evidence` citation token (BR-3) | at least one of: **id** `(^\|[^A-Za-z0-9])(BUG\|REQ\|LESSON\|TASK)-[0-9]{3,6}([^0-9]\|$)`; **test name** `(^\|[^A-Za-z0-9_])[Tt]est[A-Z_][A-Za-z0-9_]*` or `\.test\.`; **sha** a maximal `[0-9a-fA-F]` run that is `^[0-9a-f]{7,40}$` and holds at least one digit **and** at least one `a`–`f` letter; **path:line** (awk) a maximal `[A-Za-z0-9_./-]+:[0-9]+` run whose path part does not start with `//`, whose text after its last `/` or `.` holds a letter, which is not a bare host:port (path part holds no `/` and its last part is `com`, `org`, `net`, `io` or `dev`, any case), and which has an `[A-Za-z0-9]+` extension — or no extension and either a `/` or a capitalised basename (`Makefile:12`, `tools/run:5`). IP:port and URL authorities are not citations: `127.0.0.1:8080`, `https://example.com:8080` and `example.com:8080` all fail. Every arm needs its left delimiter: `xBUG-249` is not an id, `my_test_foo` not a test name; a sha with an upper-case letter (`cB177bc`) is not a sha. |
| `evidence` ≠ `title` | compared after stripping one layer of surrounding quotes from both |
| home path (BR-12) | **every frontmatter line** — validated key, unknown key or `#` comment line — **as written** (trailing comment included) must match none of: `/[Uu][Ss][Ee][Rr][Ss]/` (any case, **no left delimiter**) · `(^\|[^A-Za-z0-9_.-])(/home/\|/root/)` · `/var/root/` · `\$[{]?HOME[}]?["']?/` · `[A-Za-z]:\\[Uu][Ss][Ee][Rr][Ss]\\` · `(^\|[^A-Za-z0-9_./-])~[A-Za-z0-9_.-]+/`. Rejected: `/Volumes/Macintosh HD/Users/bob`, `x.-/Users/bob`, `/USERS/bob`, `path=/Users/x`, `[/Users/x]`, `file:///Users/x`, `--dir=/home/x`, `a,/root/x`, `/var/root/x`, `$HOME/x`, `${HOME}/x`, `"$HOME"/x`, `C:\Users\bob`, `~bob/x`, `enforcement: none   # /Users/bob/x`, and — fail-closed, because the second `/` is a delimiter — `/tmp//home/x`. Accepted: `~/.claude/x`, `/dev/null`, `/bin/sh`, `/tmp/home/x`, `https://host/home/x`, `partials/forge.sh:42`. A `/users/` URL path is a false positive the repair loop absorbs. Fix a match by replacing the prefix with `~/` (or, in `enforcement`, a repo-relative path), not by dropping the citation. |
| credential shape (BR-13) | **every frontmatter line**, **as written**, must match none of: `sk-[A-Za-z0-9_-]{20,}` · `(sk\|rk)_(live\|test)_[A-Za-z0-9]{20,}` · `(AKIA\|ASIA\|ABIA\|ACCA\|AIPA\|ANPA\|AROA)[A-Z0-9]{16}` · `(github_pat_\|gh[opsur]_)[A-Za-z0-9_]{20,}` · `glpat-[A-Za-z0-9_-]{20,}` · `npm_[A-Za-z0-9]{36}` · `xox[abprs]-[A-Za-z0-9-]{10,}` · `xapp-[A-Za-z0-9-]{10,}` · `AIza[0-9A-Za-z_-]{35}` · `eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.` · `-----BEGIN [A-Z ]*PRIVATE KEY` · `Bearer [A-Za-z0-9._-]{20,}` · `://[^/ :@]+:[^/ @]+@` (URL user:password) · `[A-Za-z_]*([Ss][Ee][Cc][Rr][Ee][Tt]\|[Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]\|[Pp][Aa][Ss][Ss][Ww][Dd]\|[Aa][Pp][Ii]_[Kk][Ee][Yy]\|[Tt][Oo][Kk][Ee][Nn])[A-Za-z_]*[[:space:]]*=[[:space:]]*[^[:space:]]{8,}` (alternatives joined with `\|`). The assignment keyword matches in any case through bracketed letter classes — never `grep -i`, which would widen every other arm — so `db_password=hunter2hunter2` is caught. Pass: a 19-character `sk-`, `Bearer` + 19, `FOO_API_KEY=` + 7, `GITHUB_TOKEN: was unset in CI (BUG-123)` and `MY_API_TOKEN: abcdefgh12345` (the arm needs `=`). |
| sections | `## Lesson` and `## Applies When` (each compared after trailing blanks are stripped) present — **the first of each** counts — each followed by a non-blank line before the next level-1 or level-2 heading. A heading is 1–6 `#` then a blank or the line's end. A `###`-or-deeper heading neither ends a section nor counts as its content, so a `## Lesson` holding only `### Sub` is empty. A second `## Lesson` ends the first. A line inside a fenced block — from a ```` ``` ```` or `~~~` line to the next line opening with the same three characters — is content, never a heading. |

### How values are read

- One layer of surrounding `"…"` or `'…'` is removed (`\"` inside double quotes and
  `''` inside single quotes are honoured).
- On an **unquoted** value, a trailing ` # comment` is dropped (YAML semantics). The
  template's own lines carry trailing comments (`enforcement: none   # none | …`), and
  a drafter keeps them. A `#` with no blank before it is text (`see#BUG-249`). An
  unquoted value containing `: ` is read whole.
- The home-path and credential rules read **every frontmatter line as written,
  comment included** — a home path or a token behind a ` #`, on an unknown key or on
  a comment line still gets committed.

## Departures from the original ADR-3

ADR-3 in the REQ-646 architecture was first drafted as a narrower rule set. The
implementation departed from that original in the ways below — each deliberate, each
pinned by a case in `tests/lesson-check.test.sh` (case names in parentheses) — and each
has since been ratified in ADR-3's final table. The list stays as the record of *why*
the final table reads as it does, and it is the one place those reasons are kept.

1. **Frontmatter location (ADR-2).** ADR-2 opens the block at the first line that is
   exactly `---`. The partial requires that line to be the first that is neither
   blank nor inside an HTML comment, so a `---` pair inside the comment, or a
   horizontal rule below body text in a frontmatter-less file, is not read as the
   block. A leading BOM and CR line ends are normalised first.
   (`dashes_inside_html_comment_ignored`, `text_before_frontmatter_is_usage_error_2`,
   `crlf_file_passes`, `bom_file_passes`)
2. **rc 2 is wider.** A symlink and a basename that is not `LESSON-<digits>-<slug>.md`
   are usage errors, alongside ADR-1's missing argument, unreadable file and absent
   block. The id segment is 3+ digits and nothing else, and the whole name holds only
   `A-Z a-z 0-9 . _ -` — a newline, blank, `$`, `:` or non-ASCII byte in a name is a
   caller bug, not a lesson. Every rc-2 message names the file by its sanitised
   basename only. (`symlink_is_usage_error_2`, `bad_basename_is_usage_error_2`,
   `basename_id_digits_and_charset_enforced`, `stderr_names_file_by_sanitized_basename`)
3. **Keys.** A key is `<key>:` followed by a blank or the end of the line, and each
   validated key may appear only once. ADR-3 reads keys by name and is silent on
   duplicates, which one reader resolves to the first line and another to the last.
   Spelling **fails closed**: a validated key written `supersedes:[x]`, `kind:process`,
   `evidence : x` or `"evidence": x` sets the key for one reader (YAML, for the last
   two) and nothing for another (every `^<key>:[ \t]` reader, `/review`'s lookup
   among them), so it is rejected on that key — never read as absent and passed over.
   (`duplicate_<key>_rejected` for all seven keys, `duplicate_key_multiline_value_rejected`,
   `key_needs_blank_after_colon`, `key_spelling_no_blank_rejected`,
   `key_spelling_blank_before_colon_rejected`, `key_spelling_double_quoted_key_rejected`,
   `key_spelling_single_quoted_key_rejected`)
4. **A value the parse cannot read is a violation on its field.** This covers an
   opening quote never closed on the key's line — `title` included — a `[` or `{` flow
   collection left open there, and a value continued onto the next line, such as a
   block list or a plain line at column 0. A continuation is the next line that is
   neither blank nor a `#` comment and does not start a key; an indented `# note` is a
   comment, not a continuation. One-line readers never see the continuation, including
   `/review`'s `^supersedes:[ \t][^#]*<id>([^0-9]|$)` lookup (ADR-6), and a YAML
   reader drops the whole lesson (`/spec` Step 1.6 discards a document it cannot
   parse). An unquoted value containing `: ` is **not** rejected: it is read whole,
   because the drafter's natural `evidence: GITHUB_TOKEN: was unset …` would otherwise
   fail a check whose job is citations; a `#` with no blank before it is text, and
   `''` inside single quotes is one quote. (`unterminated_quote_rejected`,
   `unclosed_single_quote_rejected`, `title_parse_error_rejected`,
   `wrapped_value_rejected`, `flow_collection_unclosed_rejected`,
   `continuation_plain_line_rejected`, `list_item_column0_continuation_rejected`,
   `indented_comment_is_not_continuation`, `unquoted_colon_space_accepted`,
   `single_quote_escape_accepted`, `hash_without_blank_is_text`)
5. **`enforcement` paths are repo-relative.** `test:`/`script:` may not start with `/`
   or hold a `..` segment, and the home-path rule runs over `enforcement` — trailing
   comment included — as over every other frontmatter line.
   (`enforcement_absolute_test_path_rejected`, `enforcement_etc_test_path_rejected`,
   `enforcement_opt_script_path_rejected`, `enforcement_parent_segment_rejected`,
   `enforcement_inner_parent_segment_rejected`,
   `enforcement_trailing_parent_segment_rejected`,
   `enforcement_bare_parent_segment_rejected`, `home_path_enforcement_comment_rejected`)
6. **Lists.** `'` joins the stripped set (`['LESSON-404']` passes), and a quoted value
   — double or single — is rejected: `"[LESSON-404]"` is one string to YAML, not a
   list. The 3-6 digit id rule holds inside a list. (`single_quoted_list_entry_accepted`,
   `quoted_scalar_list_rejected`, `single_quoted_scalar_list_rejected`,
   `list_lesson_1000000_rejected`, `list_lesson_99_rejected`)
7. **Citation tokens.**
   - The sha run must hold a digit **and** an `a`–`f` letter. Letters alone are English
     words (`effaced`, `defaced`, `accede`); digits alone are dates and counts
     (`20261026`, `1234567`). A real 7-character sha lacks one or the other about once
     in a thousand — cite it at more length. (`sha_token_does_not_match_effaced`,
     `sha_all_digits_rejected`, `sha_6_rejected`, `sha_7_accepted`, `sha_40_accepted`,
     `sha_41_rejected`, `sha_uppercase_rejected`, `sha_mixed_case_rejected`)
   - The id arm is delimited on both sides, so `LESSON-1000000` is not read as
     `LESSON-100000` and `xBUG-249` is not `BUG-249`. (`id_lesson_1000000_rejected`,
     `id_lesson_999999_accepted`, `id_bug_24_rejected`, `id_glued_prefix_not_a_citation`)
   - The test-name arm is `[Tt]est[A-Z_]…`, not `test_…` alone: `testLoginFails` and
     `TestFoo` are real test names; `latest`, `tests` and `my_test_foo` still are not.
     (`test_name_camel_accepted`, `test_name_go_style_accepted`, `test_word_tests_rejected`,
     `token_test_does_not_match_latest`, `test_token_inside_word_not_a_citation`)
   - IP:port and URL authorities are not citations: the `path:line` arm excludes a
     `//` authority, an `IP:port`, and a bare host:port whose last part is `com`,
     `org`, `net`, `io` or `dev` (`example.com:8080`); it admits an extensionless file
     with a `/` or a capitalised basename.
     (`path_line_url_port_not_a_citation`, `path_line_ip_port_not_a_citation`,
     `path_line_domain_port_not_a_citation`, `path_line_makefile_accepted`,
     `path_line_extensionless_with_slash_accepted`)
8. **Home path (BR-12) is a regex over every frontmatter line, not a whitespace
   tokenizer over two fields.** ADR-3 as drafted split `evidence` on whitespace,
   backtick, quote and parenthesis, which let `path=/Users/x`, `[/Users/x]`,
   `file:///Users/x`, `--dir=/home/x`, `a,/root/x` and `${HOME}/x` through. `/Users/`
   matches in any case with no left delimiter (`/Volumes/Macintosh HD/Users/bob`,
   `x.-/Users/bob`); `/home/` and `/root/` keep a left delimiter so `/tmp/home/x` and
   `https://host/home/x` pass — and `/tmp//home/x` is caught, fail-closed, because
   the second `/` is a delimiter. `/var/root/`, `"$HOME"/` and `C:\Users\` join the
   family. The scan reads every line — an unknown key, a `#` comment line (named
   `frontmatter`), a trailing comment — because whatever sits in the block is
   committed. (`home_path_*_rejected`, `home_lookalike_*_accepted`,
   `home_path_behind_comment_rejected`, `home_path_in_unknown_key_rejected`,
   `home_path_in_frontmatter_comment_rejected`)
9. **Credential shape (BR-13) is a deliberate sixth copy of the chain, wider than
   REQ-415's on every arm but one.** The five existing copies — `wrapup/SKILL.md`,
   `proceed/SKILL.md`, `agents/delegate-pre-pass.md`, `tools/delegate/_common.py`,
   `tools/delegate/emit-telemetry.sh` — **redact** what is sent to a delegate or a
   telemetry line. This copy **rejects** what is about to be committed to the repo, so
   it is not shared with them:
   - a false positive here costs one repair; a miss costs a key rotation and a
     history rewrite, so it errs wide where a redactor, which rewrites text a model
     must still read, errs narrow;
   - the field solicits verbatim transcript quotes, and the `/bugfix` path and the
     `/wrapup` fallback path have no redaction step at all (BR-13).
   It adds GitHub fine-grained and `gho_`/`ghs_`/`ghu_`/`ghr_` tokens, Stripe
   `sk_`/`rk_` live and test keys, GitLab `glpat-`, npm `npm_`, Slack `xox?-` and
   `xapp-`, Google `AIza`, JWTs, PEM private-key headers, URL `user:password@`
   credentials and `SECRET`/`PASSWORD`/`PASSWD` assignments to ADR-3's list, and its
   assignment keyword matches in any case (`db_password=…`) through bracketed letter
   classes, not `grep -i`, which would widen every other arm. It scans every
   frontmatter line as written — `title`, `kind`, `confidence`, `generalizes`,
   `supersedes`, unknown keys and comment lines included.
   **Narrower than REQ-415 on one arm: the NAME_TOKEN assignment needs `=`, not
   `[=:]`**, and an 8+ character value, so prose that names a variable —
   `GITHUB_TOKEN: was unset in CI`, `MY_API_TOKEN: abcdefgh12345` — is not a
   credential. A redactor can afford `[=:]`; a rejecter that fired on the drafter's
   natural sentence about a variable would fail the citations it exists to collect.
   (`credential_*_rejected`, `credential_sk_19_chars_passes`,
   `credential_bearer_19_accepted`, `credential_api_key_7_chars_accepted`,
   `credential_token_prose_passes`, `credential_colon_assignment_accepted`,
   `credential_behind_comment_rejected`, `credential_in_title_rejected`,
   `credential_in_<field>_rejected` for kind, confidence, generalizes and supersedes,
   `credential_in_unknown_key_rejected`, `credential_in_frontmatter_comment_rejected`)
10. **Sections.** A section ends at a level-1 or level-2 heading; a `###`-or-deeper
    heading neither ends it nor counts as its content, so a section holding only
    `### Sub` is empty. Only the first `## Lesson` (and first `## Applies When`)
    counts, and a line inside a ```` ``` ```` or `~~~` fence is never a heading.
    Headings are compared after trailing blanks are stripped. The repair loop may add
    or fill a named section, where BR-3 and ADR-4 said the repair touches frontmatter
    only — a section the check names is a field like any other, and regenerating
    nothing else keeps the body as drafted. (`subheading_under_lesson_accepted`,
    `subheading_only_section_is_empty`, `backtick_fenced_heading_is_not_a_heading`,
    `tilde_fenced_heading_is_not_a_heading`, `only_first_lesson_heading_counts`,
    `level1_heading_ends_section`, `heading_trailing_blanks_accepted`)
11. **Safe under a caller's `set -e`.** A `grep -c` count carries `|| true` inside its
    substitution and every status is captured with `|| _alc_rc=$?`, so a zero count
    never kills the caller; awk reads the file on stdin, so a `name=value`-shaped path
    is never an awk assignment. (`set_e_caller_survives_absent_keys`,
    `awk_assignment_shaped_path_read_as_file`)

## Tests

`tests/lesson-check.test.sh` covers every rule with its benign path, each departure
above, the template and taxonomy shape (TASK-104), the no-date-literal rule over this
partial and the two capture fences, the capture-rules Granularity line, `/review`'s
reverse lookup — the awk program **extracted from `review/SKILL.md`'s lookup line**
and run over a sandbox corpus, so the shipped text is what is tested — the
forbidden-construct grep, and `architecture.md`. It runs under bash, zsh, `/bin/sh`
and dash via `tests/run.sh`, prints `lesson-check.test.sh: <N> cases executed`, and
fails when N is below its floor of 60 — a floor that `summary_guard_fails_short_runs`
tests by running the guard alone. An EXIT trap fails any run that ends without
reaching the summary (`lesson-check.test.sh: aborted before summary`), and
`harness_aborts_without_summary` proves it end to end by running a copy of the harness
cut before the summary. No case skips.

## Executor shell (LESSON-717)

Every `grep` in the partial is spelled `LC_ALL=C command grep`. The Claude Code Bash
tool — the shell the capture fences actually run in — defines `grep` as a function
routed to the CLI's own matcher, whose `-vq` exits 0 on empty input where grep exits
1. On the first real `/wrapup` through this fence that flipped `_alc_ids_ok` and
rejected the template's own `supersedes: []`, while the four-shell harness, which
resolves the real binary, stayed green. `command` bypasses functions and aliases in
sh, bash, zsh and dash. `executor_grep_wrapper_keeps_accept` /
`executor_grep_wrapper_keeps_reject` define an always-0 `grep` function around the
call and assert neither verdict moves; dropping one `command` prefix fails the first.

Used by: `/wrapup` Step 4, `/bugfix` Phase 6 Step 4.

# REQ-646 — Architecture: Lesson schema v2

## Approach

Six additive frontmatter fields on `templates/lesson-template.md`, one sourced POSIX
partial (`partials/lesson-check.sh`, `adlc_lesson_check <path>`) that validates the
lesson file a capture step **just wrote**, four capture-prompt rules carried verbatim
by both capture steps, a bounded repair loop that ends in `NO_ENTRY` rather than a
halt, and two consumers so the fields are not dead data: `/review` stops escalating
on `confidence: low` or superseded lessons, and `/spec` annotates a superseded lesson
in its retrieval summary without touching scoring.

The toolkit is markdown plus a `partials/` and `tools/` exception, so the enforcement
lives in a partial with a shell test harness (bash, zsh, `/bin/sh`, dash) and in a
`tools/lint-skills` check for the one thing a harness cannot see — the *placement* of
the check fence inside two SKILL.md files (LESSON-012: structural, not prose).

Lessons applied: LESSON-012 (structural enforcement), LESSON-013/329/335 (BSD grep, zsh
executor, arg templating), LESSON-019/020/617 (guards rot, cross-fence state, `.` is a
special built-in), LESSON-404 (anchor marker parsers to line start), LESSON-405/619
(the harness is inside the shell matrix; a corpus-executing harness is an execution
surface), LESSON-440 (benign path), LESSON-441 (vendored partial shadows canonical),
LESSON-571/603 (read the producer, not the consumer; a spec-named field is a belief),
LESSON-007/008 (privacy of paths; untrusted citations), LESSON-572 (a field no executor
reads is documentation), LESSON-712 (census every site that performs X).

## Data model changes

`templates/lesson-template.md` — six fields inserted after `updated:` and before the
closing `---`, each on **one line** with a trailing `#` comment. The template's
frontmatter (HTML comment included) closes at line 19 today and at exactly line 25
after the change (BR-1's cap; `/spec` Step 1.6 reads 30 lines).

```yaml
kind: ""            # process | domain — how a skill/agent/pipeline works vs what an implementer must know
evidence: ""        # the moment: a commit sha, BUG-/REQ-/LESSON-/TASK-nnn, path:line, or test name. No home paths.
confidence: ""      # high | medium | low — see the contrast rule in the capture prompt
enforcement: none   # none | lint:<check-id> | test:<path> | script:<path> | hook:<name>
generalizes: []     # LESSON ids this one generalizes
supersedes: []      # LESSON ids this one replaces
```

Every existing lesson is untouched (REQ-262 BR-3). Readers match by name, not
position; `/spec` Step 1.6's prose parse ignores unknown keys by construction. String
values are quoted in the template so a value containing `: ` cannot make the YAML
unparseable and drop the lesson silently.

## Key decisions

### ADR-1 — The check fence takes the lesson path as a threaded literal, and the partial returns 0 / 1 / 2

`tools/lint-skills`'s `cross-fence-var` sanctions only `flag`, `BUG_NUM`, `LESSON_NUM`,
`REQ_NUM` across fences — `LESSON_ID` and any `rc`/counter variable are findings. So the
check fence does not read a path from another fence; the model substitutes the literal
path of the file it just wrote, the way `/spec` Step 1.4 threads `INTAKE_CORPUS`:

```sh
if [ -f .adlc/partials/lesson-check.sh ]; then . .adlc/partials/lesson-check.sh; else . ~/.claude/skills/partials/lesson-check.sh; fi
adlc_lesson_check .adlc/knowledge/lessons/LESSON-<id>-<slug>.md
```

Contract (mirrors `id-recheck.sh`): **0** pass; **1** violation — one `field: reason`
line per violation on stderr, nothing on stdout; **2** usage (missing argument,
unreadable or non-regular file, a symlink, a basename that is not
`LESSON-<digits>-<slug>.md`, no frontmatter — ADR-3's usage row). `_alc_*`-prefixed globals, no `local`, no `[[`, no
arrays, no `\b`, no `mktemp -t`, definition-only at top level (`source-guard.test.sh`
executes every sourcing line it finds in the corpus — LESSON-619).

### ADR-2 — Frontmatter starts at the first non-blank, non-comment line, not line 1

Four lessons (LESSON-020/402/403/404) open with a 3-line HTML comment before `---`, and
the template itself carries a 7-line comment. `attribution.sh`'s `NR==1&&/^---/` awk
would read those as "no frontmatter". The opening `---` must be the first non-blank,
non-HTML-comment line, else rc 2: the partial drops a leading BOM and CR line ends,
skips blank lines and HTML comments, requires the next line to be exactly `---`,
reads to the next `---`, and parses `key: value` by name; unknown keys are ignored. A
`---` inside the comment, or a horizontal rule below body text in a file with no
frontmatter, is not the block. A file with no frontmatter block is usage error 2, not
a violation.

### ADR-3 — Validation rules (ERE, BSD- and GNU-safe)

The final rule table, after the Phase-5 verify pass. `partials/lesson-check.md` is the
one home for the exact regexes (ADR-9); this table records what each rule decides and
why, so a later edit to a regex can be checked against its intent. Delimiters are
explicit `[^…]` classes throughout, because BSD grep silently ignores `\b`
(LESSON-013).

| Rule | Check |
|---|---|
| usage (rc 2) | missing argument; a symlink (the check validates the file the capture step wrote, not what a link points at); a basename that is not `LESSON-<digits>-<slug>.md`; an unreadable or non-regular file; no frontmatter block (ADR-2). Messages name the file by basename only, non-printing bytes shown as `?`, so a crafted name cannot forge a `<field>: <reason>` line and no home directory reaches a transcript |
| frontmatter | the opening `---` must be the first non-blank, non-HTML-comment line, else rc 2 (ADR-2); the block closes at the next `---`. A validated key (`title` and the six v2 keys) is spelled exactly `key:` followed by a blank or the end of the line, and fails closed: any other spelling (`supersedes:[LESSON-404]`, `kind:process`) is a violation on that key, never a silently unset field. A flow value whose `[` or `{` is not closed on the key's line, and any value continued onto the next line (a block list, an indented continuation), are violations on that key. Each validated key appears at most once — a key given twice is a violation on that key, because one-line readers and YAML parsers disagree on which copy wins. In every case the one-line readers (`/spec` Step 1.6, the ADR-6 lookup) would silently read something else |
| parse | a leading BOM and CR line ends are dropped first. An opening quote never closed on the key's line is a violation on that key. One layer of surrounding quotes is removed; on an unquoted value a trailing ` # comment` is dropped. An unquoted value containing `: ` is **not** rejected — decided at the Phase-5 reflector halt: it is read whole, because the drafter's natural `evidence: GITHUB_TOKEN: was unset …` would otherwise fail a check whose job is citations |
| required keys | `kind`, `evidence`, `confidence` present and non-empty |
| `kind` | `^(process\|domain)$` |
| `confidence` | `^(high\|medium\|low)$` |
| `enforcement` (when present) | `none`, `lint:<check-id>`, `hook:<name>`, or `test:` / `script:` followed by a **repo-relative** path — no leading `/`, no `~`, no `..` segment; absent means `none` |
| `generalizes`/`supersedes` entries | a list (never a quoted string) whose every entry is `^LESSON-[0-9]{3,6}$` after stripping `[ ] " ' ,` |
| `evidence` citation token (BR-3) | at least one of: a **sha** — a maximal run of 7–40 lowercase hex that holds at least one digit (an all-letter run is an English word: `effaced`, `accede`) and at least one `a`–`f` letter (an all-decimal run is a number or a date, not a commit); an **id** `(BUG\|REQ\|LESSON\|TASK)-[0-9]{3,6}`, delimited on both sides; a **`path:line`** — a `[A-Za-z0-9_./-]+:[0-9]+` run in which the text after the last `/` or `.` holds a letter (so `127.0.0.1:8080` and `12:30` are not citations), and that has an extension or is extensionless with a `/` or a capitalised basename (`Makefile:12`, `tools/run:5`); IP:port and URL authorities never count; a **test name** — `test_…`, a camelCase `test…` / `Test…` identifier (`testLoginFails`, `TestFoo` — decided at the Phase-5 reflector halt: those are real test names, so a `test_`-only arm would reject genuine citations), or `.test.` — delimited, so a bare `test` inside "latest" never counts |
| `evidence` ≠ `title` | after stripping one layer of surrounding quotes from both |
| home path (BR-12) | in `evidence` and `enforcement`, over the line as written (a trailing comment is committed too): `/Users/`, `/home/` or `/root/` at a delimiter — the start of the value or any character that cannot be part of a path, so a prefix glued to `=` or `:` is still caught; `$HOME/` or `${HOME}/` anywhere; and `~user/` (a `~` followed by a user name) at a token start. `~/`, `/dev/null`, `/bin/sh`, `/tmp/…`, `https://…` and `partials/forge.sh:42` pass |
| credential shape (BR-13) | rejects `title` or any of the six new fields matching the credential family: the REQ-415 chain (`sk-…`, `ghp_…`, `Bearer …`) widened to the AWS key-id prefixes `tools/delegate/_common.py` already uses (`AKIA`, `ASIA`, `ABIA`, `ACCA`, `AIPA`, `ANPA`, `AROA`), the other GitHub token prefixes and fine-grained PATs (`gh[opsur]_…`, `github_pat_…`), Slack `xox?-…` tokens, Google `AIza…` API keys, JWTs (`eyJ….eyJ….`), PEM private-key headers, and an env-var arm — a name containing `SECRET`, `PASSWORD`, `PASSWD`, `API_KEY` or `TOKEN`, then `=` and an 8+ character value. The assignment arm is case-insensitive and requires `=` — narrower than REQ-415's `[=:]` on purpose, so prose like `GITHUB_TOKEN: was unset` passes. The five existing copies redact what is sent to a delegate or a telemetry line, while this one rejects what is about to be committed (the shell copies stay AKIA-only); this superset is recorded here so the sixth copy is a deliberate one |
| sections | a line that is exactly `## Lesson` and one that is exactly `## Applies When`, each followed by at least one non-blank line before the next level-1 or level-2 heading (a `###` sub-heading is content). A missing or empty section is reported with the heading as its `<field>`, which is what ADR-4's repair may add |

Reject, never redact: the step's remedy is the repair loop, and a silently rewritten
`evidence` is a lesson whose citation nobody wrote. The check proves a citation's
*shape*, not that the cited thing exists; `/wrapup`'s delegated path checks existence
(Step 4 delegated item 4: BR-8 and the `evidence` tokens) before the file is written.

### ADR-4 — Repair loop: the model counts, the fence does not

A retry counter in shell would be a cross-fence variable (lint finding) and a `trap`
cannot span fences. The SKILL.md text therefore says: run the fence; on rc 1, repair
only what the check named — the named frontmatter field(s), or, when the `<field>` is
`## Lesson` or `## Applies When`, add that one missing or empty section (the one
narrow body edit allowed, decided at the Phase-5 reflector halt: a section the check
names is a field like any other, and regenerating nothing else keeps the body as
drafted) — never regenerate any other section, and run the fence
again; **at most two repairs**; after the third failure delete the draft file and
write `NO_ENTRY: schema check failed — <field>` to the summary slot. With no file
left, the pre-push recheck is skipped. The id allocated for the draft stays consumed:
a repair-loop `NO_ENTRY` leaves a gap in the counter, unlike a rule-3 `NO_ENTRY`,
which allocates nothing. The model keeps the count. On a provenance-classifying
harness the same loop runs in-model (ADR-8). This is explicitly not a `/proceed` halt
point; `/wrapup` Steps 5–8 run regardless.

### ADR-5 — Fence placement is enforced by a lint check anchored on a line-start marker

`cross-fence-fn` cannot see ordering. A new `tools/lint-skills` check,
`lesson-check-order`, reads `wrapup/SKILL.md` and `bugfix/SKILL.md` and requires, in
file order: a line that is exactly `<!-- lesson-write-point -->` (the write
instruction's anchor), outside every fenced block; then a shell fence with a
non-comment line that calls `adlc_lesson_check` **anywhere on the line** in command
position (line start, after a separator, `!`, `(` or `{`, or after a compound-command
keyword — so `if ! adlc_recheck_id lesson …; then` and `true && adlc_lesson_check x`
are calls, and `adlc_lesson_check_x` is not); then a fence whose non-comment line
calls `adlc_recheck_id lesson` the same way. The marker is matched as a whole line and
rejected inside backticks or any fenced example (LESSON-404 — this document mentions
the marker in prose, which is exactly the decoy the anchoring guards against).

Its findings, one id each:

| Finding | Fires when |
|---|---|
| `missing-write-point` | no own-line `<!-- lesson-write-point -->` outside a fence |
| `missing-check-fence` | no fence calls `adlc_lesson_check` |
| `missing-recheck-fence` | no fence calls `adlc_recheck_id lesson` |
| `check-before-write-point` | the first check call precedes every write point |
| `recheck-before-check` | the recheck call precedes the first check call |
| `missing-harness-line` | no `**Provenance-classifying harness (BUG-228):**` prose line within the 30 lines above a check fence (ADR-8, BR-15) |
| `rules-block-missing` | the `<!-- lesson-capture-rules -->` … `<!-- /lesson-capture-rules -->` block is absent, unclosed or empty |
| `rules-block-missing-granularity` | the block has no line starting `Granularity:` |
| `rules-block-mismatch` | the two skills' blocks differ by a byte (BR-4) |
| `rules-line-not-in-question` | in `/wrapup`, a rule line is missing from the delegated `--question` string, or out of order there |
| `rules-line-unsafe-in-question` | in `/wrapup`, a rule line carries `"`, `$`, a backtick or `\` — a character a double-quoted shell word would end, substitute or escape |

A fixture per finding (good / reordered / decoy / mismatch …) pins it, plus the
whole-tree-clean test.

### ADR-6 — `/review` and `/spec` superseded lookup is a corpus-wide, frontmatter-scoped reverse lookup

The superseding lesson is usually *not* in the 15-lesson relevance set, so "is this
lesson superseded?" cannot be answered from loaded frontmatter. Both skills run one
corpus-wide reverse lookup per lesson:
`find .adlc/knowledge/lessons -maxdepth 1 -type f -name 'LESSON-*.md' -exec awk … {} +`,
where the single-quoted `awk` program strips CRLF line ends and a leading BOM, starts
the frontmatter block only at the first non-blank, non-HTML-comment line (and only
when that line is `---`; any other file is skipped whole), and reads that block for a
`^supersedes:[ \t][^#]*LESSON-<id>([^0-9]|$)` line. The lookup requires a blank after
`supersedes:` — the one key spelling ADR-3's `frontmatter` row accepts — so a body
line or a trailing `# comment` that names the id is not a hit, and `2>/dev/null` on
the `find` makes a missing lessons directory print nothing. The id is
checked against `^LESSON-[0-9]{3,6}$` by the model before substitution and again by a
`case` in the same fence, and reaches `awk` as data (`-v`), so the guard covers the
only substitution site. `find` with a quoted `-name` never hands the shell an
unmatched glob (zsh aborts on one — LESSON-335), and `-exec … +` runs nothing on an
empty match, where GNU `xargs` runs once on empty input.

`/review` runs the lookup **lazily**, in Step 4, only for a lesson a finding matched —
not for all 15 selected in Step 1. It reads `confidence` in Step 1 item 7b; any value
other than `low` (`medium`, `high`, empty, or outside the enum) behaves as absent.
`/review` also **excludes the diff's own lesson files**: Step 1 item 7f lists the
`LESSON-*.md` files the diff under review adds or modifies, and Step 4 ignores their
`confidence` and `supersedes` — a PR must not switch off its own escalation — and says
so in the report when that is why a match escalated. Scoring and the relevance filter
are untouched (BR-7); `/spec`'s annotation is parenthetical in the existing line
format, `LESSON-034 (lesson, score 5, superseded by LESSON-040): …`.

### ADR-7 — Taxonomy sections for fixed enums use a different sentence than the advisory tag sections

`templates/taxonomy-template.md` describes retrieval tags as "advisory … not
enforced". `kind`/`confidence`/`enforcement` are fixed vocabularies enforced by
`adlc_lesson_check`, so their sections keep the `## field (descriptor)` heading and the
shape line but say so, and `enforcement` is documented as a pattern (`lint:<check-id>`
…), not a list. Known limitation, recorded: `/init` copies the taxonomy only when absent
and `/template-drift` does not cover it, so existing consumer repos see the enums only
through the template comments and the capture prompts.

### ADR-8 — Provenance-classifying harnesses get prose, and the spec says it is prose

`harness-skip` fires only on fences calling `adlc_delegate_gate_check`; the check fence
runs a partial by path and would pin a Teton session. Both capture steps carry a
`**Provenance-classifying harness (BUG-228):**` line for the check fence telling the
model to validate in-model against ADR-3's rule table, apply ADR-4's repair loop, and
write `lesson check: in-model (provenance-classifying harness)` in the summary slot.
The line itself **is** lint-covered: `lesson-check-order` raises
`missing-harness-line` when it is not within 30 lines above a check fence (ADR-5).
What no lint can cover is the in-model validation the line asks for — on that harness
the enforcement is honor-system, and BR-15 names that honestly.

### ADR-9 — `partials/lesson-check.md` companion

`partials/README.md` requires a companion for a function-exporting partial with a
return-code contract. The companion carries ADR-1's contract and ADR-3's rule table so
the SKILL.md prose can point at it instead of repeating regexes (one home for the rule
set — LESSON-441's two-copies class). Companions are not vendored; the `.sh` is, through
the existing `partials/*.sh` glob — no sync-surface list changes (BR-9).

### ADR-10 — The workflow close-out leaf is not a third prompt site

`workflows/adlc-sprint.workflow.js`'s close-out prompt routes through `/wrapup
--close-out`, which runs Step 4 and therefore the fence. No engine change; the leaf
inherits BR-2/3/4 by construction.

## Proposed additions to `.adlc/context/architecture.md`

Template-anatomy row for `lesson-template.md` lists the sixteen fields; the "Knowledge
retrieval" paragraph is rewritten to describe the REQ-258 weighted retriever (it still
says "3-tier grep"), the six v2 fields, the `NO_ENTRY` contract, and
`partials/lesson-check.sh` as the structural writer-side guard.

## Task graph

```
Tier 0:  TASK-104 template + taxonomy        TASK-105 partial + companion + harness + run.sh + README
Tier 1:  TASK-106 wrapup Step 4/5  ◄─105     TASK-107 bugfix Phase 6  ◄─105     TASK-108 review + spec  ◄─104
Tier 2:  TASK-109 lint check lesson-check-order  ◄─106, 107
Tier 3:  TASK-110 architecture.md + CHANGELOG  ◄─104..109
```

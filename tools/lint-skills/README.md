# tools/lint-skills — SKILL.md corruption lint

A small offline linter that catches the class of failures that escaped REQ-424
verify: literal-but-broken shell constructs embedded in skill prose. It is NOT
a general markdown linter and NOT a general shell linter.

## What it checks

1. **Sentinel literals** — exact substrings listed in `sentinels.txt` should
   never appear in any `SKILL.md`. Seeded with the REQ-424 corruption
   sequence; one line per known-bad pattern.
2. **Shell-construct balance** — within each ` ```sh `, ` ```bash `, or
   ` ```shell ` fenced block, the linter counts `$(` vs `)` and `$((` vs
   `))`. Imbalance is a finding. Outside-fence text is ignored (skill prose
   may legitimately use unbalanced examples).
3. **Canonical-helper presence** — any SKILL.md that contains the delegation-gate
   disable anchor `ADLC_DISABLE_DELEGATE` (REQ-522 de-branded the surface; the
   legacy `ADLC_DISABLE_KIMI` anchor is retired) must also contain five canonical
   literals, listed in the same order as `CANONICAL_LITERALS` in `check.py`:
   - `skill-flag.sh mark "$flag" start_s ` (the start-time capture marked to the
     flag-file sidecar — REQ-522 ADR-3)
   - `_adlc_emit_step_telemetry ` (the shared resolver call in the SKILL.md
     resolution fence)
   - `"$DELEGATE_TOOLS"/emit-telemetry.sh ` (the emit exec; note the trailing
     space — it proves an invocation, not a path substring. Lives in the partial.)
   - `. .adlc/partials/delegate-gate.sh …` (the gate-source line that wires the
     delegation gate; required so corruption that strips it while leaving a
     disable anchor is caught)
   - `. .adlc/partials/delegate-tools-path.sh …` (the resolver-source line that
     sets `$DELEGATE_TOOLS`; required so corruption that strips it while leaving
     the invocation is caught)

   Each missing literal is a separate finding. The two source-line literals
   are satisfied by the guarded spelling with the ToolkitRoot fallback operand
   (item 9), the only one accepted since TASK-124 retired the REQ-610 one.

   **Canonical follows the indirection (REQ-436 ADR-4).** A literal is
   satisfied if it appears in the SKILL.md text **or** in the text of a
   sourced telemetry partial resolved under the scan root — checked in this
   order: `<root>/partials/*.sh`, then `<root>/.adlc/partials/*.sh`
   (toolkit-self / dogfooding layout vs. consumer-project layout). REQ-436
   relocated the `_adlc_emit_step_telemetry` helper body — and REQ-522 moved
   the `"$DELEGATE_TOOLS"/emit-telemetry.sh ` literal — into
   `partials/emit-step-telemetry.sh`. Without this rule the linter would falsely
   flag `analyze/SKILL.md` as missing that literal: a literal-presence guard
   rots when the thing it guards moves
   behind indirection (LESSON-019 #1), so the guard was generalized in the
   same change. The match is still plain text-substring (no shell parsing);
   the partials are read once per run, not per SKILL.md. A partial whose real
   path resolves outside the scan root is ignored (same symlink-escape
   philosophy as the directory walk).
4. **POSIX-fence (`local` in an `sh`/`shell` fence)** — within a ` ```sh ` or
   ` ```shell ` fenced block, any `local ` declaration at statement position
   (start of line, or after `;`, `&&`, `||`, `then`, `do`, `{`) is a finding.
   `local` is not POSIX; `conventions.md`'s "Bash in skills" mandates
   POSIX-only shell. **` ```bash ` fences are exempt by design (REQ-436
   ADR-6):** many `bash` builds support `local`, and the POSIX-only mandate
   targets `sh`/`shell`, so flagging `bash` would be a false positive in
   legitimately-`bash` blocks. The reported line is the absolute line of the
   offending body line (not the fence-open), so `/analyze` Step 1.9's
   `<file>:<line>:` parser stays accurate.
5. **Argument templating (`arg-templating`)** — a bare `$<digit>` anywhere in
   a SKILL.md (prose, inline code, or fence) is a finding. The Skill tool
   substitutes `$ARGUMENTS` and `$0`–`$9` across the whole SKILL.md body
   *before* any fenced script reaches a shell, so a bare positional — shell
   `$1` or awk `$0`/`$5` — is silently replaced with (or emptied by) the
   invocation's arguments (observed live: `/manifest`'s `index($0,k)` became
   `index(MANIFEST_SELF=REQ-508,k)`). The templating-safe spellings are
   `${1}` for shell positionals and `$(0)`/`$(1)` for awk fields — neither
   contains a `$<digit>` substring, and both are valid shell/awk. `$$1`
   (PID followed by a digit) is exempt. See LESSON-335.
6. **Cross-fence function (`cross-fence-fn`)** — a shell function *defined*
   inside one fenced block but *invoked* only from a *different* fenced block
   in the same SKILL.md is a finding. SKILL.md fenced blocks do not share
   shell state across steps, so the function is undefined at that call site
   (silent `command not found`, swallowed telemetry — the REQ-436 Defect-1
   class). The fix is to move the function into a sourced partial and source
   it in the same fenced block as the call. Conservative against false
   positives: only names that are both *defined* with the `name() {` form
   **and** *invoked* at statement position within a fence are considered;
   prose mentions outside fences are ignored, and a define-and-use within the
   *same* fence is legitimate (never flagged). The finding is anchored at the
   definition line and names an invocation line.
7. **Cross-fence variable (`cross-fence-var`)** — a non-exported variable
   *assigned* in one fenced block but *read* in a *different* fenced block of
   the same SKILL.md is a finding (REQ-522 BR-5). SKILL.md fenced blocks do not
   share shell state across steps, so the read sees an empty value — the exact
   inert-telemetry class REQ-522 fixed (the per-step telemetry state was set in
   one fence and read in the resolution fence, so every run recorded
   `mode=fallback`). The fix is to persist the value via the flag-file sidecar
   (`skill-flag.sh mark`/`read`) or re-derive it in the consuming fence.
   Conservative against false positives: a name is only considered if it is both
   *assigned* (`NAME=`) and *read* (`$NAME`/`${NAME}`) within fences; an
   `export`ed name is EXEMPT (it legitimately crosses via the environment); an
   assign-and-read within the SAME fence is legitimate. The sanctioned carriers
   `$flag` (the telemetry flag-path) and the id-allocation `*_NUM` counters
   (allocate-then-recheck flow, REQ-518 domain) are exempt by name.
8. **Read-bin fallback (`read-bin-fallback`)** — the `ADLC_READ_BIN` call-site
   contract, checked inside shell fences (REQ-609 BR-12, ADR-3).
   `partials/delegate-gate.sh` is the *single* resolver for `adlc-read`: it
   walks `$PATH` itself — never `command -v`, so no shell function, alias, or
   hash-table entry can answer for it — and exports an absolute path or the
   empty string, and nothing else. The correct shape is:

   ```sh
   ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
   if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-gate.sh"; fi
   case "$ADLC_READ_BIN" in /*) ;; *) echo "/<skill>: ADLC_READ_BIN is not an absolute path ('$ADLC_READ_BIN') — refusing to hand over the corpus (re-run install.sh --with-delegation (symlink install; the plugin ships no delegation CLIs), and /init (/adlc:init on the plugin install) to refresh the vendored gate)" >&2; exit 1 ;; esac
   command "$ADLC_READ_BIN" --no-warn --paths … --question "…"
   ```

   All four spellings of the expansion count as an invocation — quoted or bare,
   `$ADLC_READ_BIN` or `${ADLC_READ_BIN}` — when they sit in **command
   position** (line start, after `;`/`&`/`|`/`(`/`{` or a `then`/`do`/`else`,
   optionally behind `command`). Anywhere else the name is an argument, not a
   command, so the refusal message's own `('$ADLC_READ_BIN')` is not mistaken
   for a call. Recognising every spelling is the point: no obligation below can
   be stepped around by respelling the variable.

   A fence that references `$ADLC_READ_BIN` draws a finding when it:

   - **carries a `${ADLC_READ_BIN:-…}` default** — a second resolution of the
     binary at the call site, by a weaker rule, reached in exactly the case
     where the first resolver already declined. With the bare name it hands the
     corpus to whatever the shell resolves, the planted-binary class BUG-209
     recorded. Matched as a fixed string on the expansion operator, not on one
     default value, so the pattern is caught under any default;
   - **invokes without the `command` prefix** — bash and zsh both permit a
     function whose *name* is an absolute path, so `"$ADLC_READ_BIN" --paths …`
     runs that function rather than the file the resolver proved is on disk, and
     the function receives the corpus. The gate's own probe already went through
     `command`; the call sites, which are the ones holding the corpus, did not;
   - **invokes with no preceding `case "$ADLC_READ_BIN" in /*)` guard** — or
     with the guard placed *after* the invocation. `[ -n "$ADLC_READ_BIN" ]` is
     not enough: a consumer repo whose vendored `delegate-gate.sh` predates
     REQ-609 still exports the **bare name** on a `$PATH` hit, and a non-empty
     test passes that straight through. The refusal must precede the handover,
     and where a fence marks telemetry it goes **before**
     `skill-flag.sh mark "$flag" invoked 1`, so a refusal is recorded as *not*
     invoked;
   - **invokes unquoted** — `command $ADLC_READ_BIN --paths …` hands the path
     to word-splitting and pathname expansion *before* it is a command name, so
     a resolved `/Users/a b/bin/adlc-read` runs `/Users/a` with the rest as
     arguments and one carrying a glob character runs whatever matches. That is
     the shell re-deriving the binary the resolver already proved, which is the
     whole of BUG-209 restated without quotes;
   - **copies the value into another variable, or hands it to `eval`** —
     `READER="$ADLC_READ_BIN"; command "$READER" …` moves the resolver's answer
     into a name no guard covers and no check knows, and `eval` re-parses its
     argument as shell source, undoing the quoting and restoring function and
     alias lookup whatever prefix is written inside the string. The resolver's
     value must be invoked directly, as `command "$ADLC_READ_BIN"`.

   **Comment lines are skipped by every one of these checks.** A `#`-prefixed
   line hands nothing to anything, so a retired invocation kept beside its
   replacement — the ordinary way a call site is edited — is not a finding; and
   in the other direction a commented-out guard does not satisfy the ordering
   obligation, which would otherwise be satisfiable by pasting a comment above
   the invocation (the guard-rot class LESSON-019 names).

   Only shell fences are scanned, so prose describing a retired shape is never
   flagged — the same structural posture as `forge-direct-gh` (LESSON-012).

   This is the **one** check that also walks `agents/*.md`, via a separate walk
   (`find_read_bin_extra_files`) rather than a widening of `find_skill_files`:
   `agents/delegate-pre-pass.md` hands a redacted diff to the delegate exactly
   as a skill does, so BR-12's obligations are its obligations — while the other
   checks encode a *skill's* contract and would be false positives on an agent
   prompt file. Agent files are not added to the `scanned N SKILL.md file(s)`
   count, so they can never mask a dead skill walk (REQ-595 BR-5).
9. **Unguarded partial source (`unguarded-source`)** — how a fence sources a
   partial (REQ-610 BR-3/BR-5, ADR-2). `.` is a POSIX **special built-in**, so a
   failed source is fatal: a non-interactive `sh` *exits* rather than returning
   non-zero. The retired two-level shape — `. <local> 2>/dev/null || . <canonical>`
   — therefore kills the whole block at its first line on any machine with no
   vendored `.adlc/partials/` copy, because the `||` arm is never reached. There
   is exactly **one** accepted spelling, on a single line:

   ```sh
   if [ -f .adlc/partials/<name>.sh ]; then . .adlc/partials/<name>.sh; else . "$ADLC_TOOLKIT_ROOT/partials/<name>.sh"; fi
   ```

   It follows the fence's root line (item 15), which resolves
   `$ADLC_TOOLKIT_ROOT` to the running install (REQ-669 BR-5, ADR-1). The
   repo-local copy is *tested* before it is sourced, never guessed at with
   `||`. `[ -f ]` rather than `[ -r ]`: an existing-but-unreadable vendored copy
   then fails loudly at the `.` instead of silently falling through to canonical
   and hiding a permissions problem. One line, so Skill `$<digit>` argument
   templating cannot split it and `cross-fence-fn`'s line-based parsing still
   sees one statement. The regex carries a **backreference**, so all three
   `<name>`s must agree — a line that guards `forge.sh` and then sources
   `intake.sh` is a finding, not a pass. A trailing `#` comment is allowed.

   **Retired operand (REQ-669 TASK-124).** The REQ-610 operand
   `~/.claude/skills/partials/<name>.sh` was accepted in the same position
   while TASK-122 to TASK-124 rewrote the corpus. TASK-124 retired it: the old
   operand is now a finding on every walked surface, partials included, and a
   line that is otherwise the guarded spelling gets a message saying the
   `else` arm is what has to change (`check.py` keeps the operand as
   `RETIRED_REQ610_OPERAND` for that message alone). Finding messages name only
   the new spelling.

   **Inside a partial.** A partial that sources another partial
   (`partials/*.sh`, `.adlc/partials/*.sh`) carries no root line, and it is
   also sourced by test harnesses and older SKILL.md text that never ran one.
   So there, and only there, the guarded line may end in the ADR-2
   default-expansion operand
   `"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/partials/<name>.sh"`
   (`PARTIAL_SOURCE_OPERAND`, REQ-669 TASK-123). The same line in a fence is a
   finding, and a default-expansion operand sourced without the guard is a
   finding everywhere.

   This check walks five file families — `*/SKILL.md`, `agents/*.md`,
   `proceed/phase*.md`, the partials' companion docs `partials/*.md` (whose
   copy-paste fences are where a call-site spelling originates), and the partials themselves (`partials/*.sh` and a
   consumer's `.adlc/partials/*.sh`, where every non-comment line is executable,
   so the whole file is treated as one fence). The last family was added after
   `id-recheck.sh` turned out to carry a three-level `. A || . B || . C` chain on
   continuation lines that no markdown walk and no line-anchored extraction could
   see; the `dash` pass in `partials/tests/run.sh` found it. None of the extra
   families count toward the `scanned` figure.

   Two rules, both on every walked file:

   - **inside a shell fence** (or anywhere in a partial), a non-comment line with a `.`
     (or bash-only `source`, which `dash` lacks entirely) at statement position
     (start of line, or after `;`, `&&`, `||`, `then`, `do`, `{`) whose operand is one
     of the toolkit's **convention paths** — `.adlc/partials/<name>.sh`,
     `$ADLC_TOOLKIT_ROOT/partials/<name>.sh` (braced or not),
     `~/.claude/skills/partials/<name>.sh`, `$HOME/.claude/skills/partials/<name>.sh` —
     must match that spelling exactly. So the new operand sourced alone, or
     `||`-chained behind the repo-local copy, is a finding like the old one. A
     source through any other variable path
     (`. "$D/partials/x.sh"` behind the author's own `[ -f ]`) is deliberately out of
     remit: the two-level spelling would point a consumer's own partial at a
     `$ADLC_TOOLKIT_ROOT/partials/<their-name>.sh` that does not exist;
   - **anywhere in the file** — prose, inline code, fence comment — the retired
     `. <local> 2>/dev/null || . <fallback>` shape is a finding, with either
     fallback operand. A SKILL.md sentence instructing the agent to type the
     line is as executable as a fence (`analyze/SKILL.md` Step 1.5 carried
     exactly such a sentence), and a fence comment quoting it is one paste away
     from being live. A retired fence line matches both rules and is deduped by
     line number into one finding.

   **` ```bash ` fences are NOT exempt** — the opposite of `posix-fence`, and
   deliberately so: the fence label does not choose the shell that executes the
   block (`partials/tests/run.sh` and consumers run fences under `/bin/sh`
   regardless of the label), and a fatal `.` is a property of the executing
   shell, not of the label.

   Two rejected alternatives, for the record: `command . <local> || . <canonical>`
   still exits under macOS `/bin/sh`; `[ -f A ] && . A || . B` double-sources
   whenever `A`'s final status is non-zero — which, for a function-defining
   partial, is whatever its last top-level statement returned, a property no
   partial author is thinking about.

   Benign and fixture-pinned as must-not-fire: the canonical spelling itself,
   and the **executable-partial macro** `sh <local> 2>/dev/null || sh <canonical>`
   (partials README model 1), whose command is `sh`, not `.` — an absent file is
   an ordinary command failure (exit 127), the `||` arm does run, and no guard
   is needed.

   This check walks `agents/*.md` **and** `proceed/phase*.md` (via
   `find_phase_files`) in addition to every `SKILL.md`: the retired spelling
   lived in all three families. Like the agents walk, neither extra walk feeds
   the `scanned N SKILL.md file(s)` count, so a companion file can never mask a
   dead skill walk (REQ-595 BR-5).
10. **Lesson check order (`lesson-check-order`)** (keyed on the skill unit since
    REQ-661, see "Skill units and companions"): the two lesson-capture steps
    (`/wrapup` Step 4, `/bugfix` Phase 6 Step 4) write the lesson, then validate
    it, then recheck its id, in that file order (REQ-646 ADR-5). Runs on
    `wrapup/SKILL.md` and `bugfix/SKILL.md` only, keyed on the directory name.
    A marker counts only on a line that is the marker and nothing else, outside
    every fenced block (```` ``` ```` or `~~~`, any language): a backticked or
    prose mention, or a copy inside an example fence, is a decoy (LESSON-404).
    Fences nest
    length-aware: a fence closes only on a line of its own character (backtick
    or tilde), at least as long as its opening run, with nothing else on it,
    and an unclosed fence runs to EOF — so a ```` ````markdown ```` fence holds
    ```` ``` ```` lines as body. Calls are read only from **top-level** shell
    fences (`sh`/`bash`/`shell`, behind ```` ``` ```` or `~~~`): a
    ```` ```sh ```` example nested inside an outer non-shell fence
    (```` ````markdown ````, `~~~text`, …) calls nothing. Both calls are found
    in command position — at the line start, after `;` `&` `|` `!` `(` `{`, or
    after `if`/`then`/`else`/`elif`/`do`/`while`/`until` — because both skills
    spell the recheck `if ! adlc_recheck_id lesson "$LESSON_ID"; then`. They
    are searched in the line's code only: a `#` comment, whole-line or
    trailing (`: # adlc_recheck_id lesson L`), and a quoted string
    (`echo "adlc_lesson_check x"`) call nothing — so spell the call in command
    position, not inside a `"$(…)"`. `adlc_lesson_check_x`,
    `adlc_recheck_idx` and `adlc_recheck_id lessons` are different calls. One
    write point above the first check call anchors every check. In `/wrapup`
    the delegated question is the double-quoted `--question "…"` argument on
    the top-level shell-fence line whose code runs `command "$ADLC_READ_BIN"`;
    it ends at the first unescaped `"` (a `\"` does not end it). A question
    wrapped over several source lines is read as written, NOT joined: it may
    break between rule lines, but a rule line split across a break (even by a
    `\` continuation) is `rules-line-not-in-question`, with a message naming
    the wrap — keep each rule on one source line. Each finding message starts
    with one of these ids (they ride in the message, under the one check name):

    | Finding id | Fires when |
    |---|---|
    | `missing-write-point` | no own-line `<!-- lesson-write-point -->` outside a fenced block |
    | `missing-check-fence` | no top-level shell fence calls `adlc_lesson_check` in a line's code (comments and quoted strings excluded) |
    | `missing-recheck-fence` | no top-level shell fence calls `adlc_recheck_id lesson` in a line's code (comments and quoted strings excluded) |
    | `check-before-write-point` | no write point sits above the first `adlc_lesson_check` call (reported on each check fence above the first write point) |
    | `recheck-before-check` | an `adlc_recheck_id lesson` call sits above the first `adlc_lesson_check` call, in another fence or the same one |
    | `rules-block-missing` | no own-line `<!-- lesson-capture-rules -->` … `<!-- /lesson-capture-rules -->` block outside a fenced block, or it is unclosed or holds only blank lines |
    | `rules-block-missing-granularity` | the block has no line starting `Granularity:` |
    | `rules-block-mismatch` | the two files' blocks differ byte-for-byte (reported once, on `bugfix/SKILL.md`, at the first differing line — including a line one copy has and the other lacks) |
    | `rules-line-not-in-question` | `wrapup` only: a non-empty block line (stripped) is not in the `--question` argument, or occurs there only before the previous rule line's match, or only wrapped across a line break — the rules must appear verbatim and in block order. Reported once, on the first such line; with no `--question` line at all, on the block's first rule line |
    | `rules-line-unsafe-in-question` | `wrapup` only: a block line holds `"`, `$`, a backtick or `\` — inside the double-quoted argument it would end the string, substitute, or escape, so the delegate would not receive it as written |

    `templates/` and `.adlc/` are not read. The block comparison is a per-root
    check: it reads `<root>/wrapup/SKILL.md` and `<root>/bugfix/SKILL.md`
    (decoded from bytes, so a CRLF difference counts) and yields nothing when
    either is absent or resolves outside the root. A missing, unclosed or blank
    block is already `rules-block-missing` on its own file, so it is not also a
    mismatch.

11. **Lane vocabulary (`lane-vocabulary`)** (REQ-652 BR-17, ADR-13): the lite
    lane's closed sets (lane `lite`/`full`, the escalation triggers, the actors,
    and the lane check's `pass`/`escalate`/`error`) are defined once, in the
    `<!-- lane-vocabulary -->` block of `partials/lane-check.md`. The block's
    open marker must start a line (LESSON-404), so a prose mention of it is not
    read as the definition. The check then scans every writer and reader of a
    lane value, the explicit `LANE_SITES` tuple (`spec`, `proceed` and every
    `proceed/phase*.md` companion, `wrapup`, `status`, `sprint`,
    `agents/pipeline-runner.md`, `workflows/adlc-sprint.workflow.js` and
    `templates/requirement-template.md`), and reports any value outside its set
    written as `lane: "…"`, `"lane": "…"`, `trigger=…`, `trigger: …`,
    `actor: …`, `lane_check=…`, or in prose as ``trigger `…` `` or
    ``actor `…` ``. A value is a quoted string or a bare lowercase token, so a
    placeholder such as `trigger=<t>` or a structure such as `lane: {` is not
    read as one. A missing, empty or incomplete vocabulary block is a finding,
    and so is a `LANE_SITES` file that no longer exists. The check is per-root
    and inert unless `partials/lane-check.md` or `proceed/phases-lite.md`
    exists; either one arms it, so deleting the vocabulary file alone does not
    disarm it. The same change adds `/proceed` Step 0 to the
    `retrieval-status-parity` check's `LIFECYCLE_WRITE_SITES`, because a lite
    REQ gets `status: approved` from it (BR-18); since REQ-661 that site is
    `proceed/phase-0-setup.md`, where Step 0 now lives.

12. **Manifest parity (`manifest-parity`)** (REQ-665 BR-1, BR-2, BR-3, BR-4,
    BR-5, BR-7, ADR-1 to ADR-9; REQ-669 BR-1, BR-12, BR-20, ADR-3;
    it absorbed REQ-669's `plugin-manifest` and kept every rule and its arming):
    every plugin manifest stays in step with the tree, with the other manifests
    and with `VERSION`. This repo is both the Claude Code marketplace and the
    plugin, and Cursor and Copilot CLI read manifests of their own. The set is
    `MANIFEST_REGISTRY`, defined once in `check.py`. Each entry also lists the
    top-level keys its vendor documents. Adding a harness starts with one entry
    and one file; the bump in `RELEASING.md` and `plugin-sandbox.sh`, and the
    README subsection, follow:

    | Harness | Manifest | Companion | `agents` | `hooks` |
    |---|---|---|---|---|
    | `claude` | `.claude-plugin/plugin.json` | `.claude-plugin/marketplace.json` | `canonical`: absent, or lists every `agents/*.md` | `default`: no shape rule, `hooks/hooks.json` is read by default, and `execution-key` refuses an inline definition |
    | `cursor` | `.cursor-plugin/plugin.json` | none | `empty`: present and `[]` | `empty`: present and `{}` |
    | `copilot` | `.github/plugin/plugin.json` | none | `empty`: present and `[]` | `empty`: present and `{}` |

    Each rule leads its finding's message, so a line reads
    `<file>:<line>: manifest-parity: version-mismatch: …`, and the clause after
    the em dash is the exact edit, naming the file (ADR-3, LESSON-572):

    | Rule | Fires when |
    |---|---|
    | `set-incomplete` | an armed root is missing a manifest in the registry. With every manifest gone it fires once per manifest, never a silent pass (LESSON-019) |
    | `unparseable` | a manifest or companion cannot be read, resolves outside the checkout through a symlink, is not UTF-8, is not strict JSON (a repeated key, `NaN` or `Infinity` included), is nested too deeply to parse, or is not a top-level object |
    | `name-mismatch` | a manifest's `name` is not the literal `MANIFEST_SET_NAME`, `adlc`, so a set renamed in step still fails: `session-start.sh` and `adlc doctor` recognise a copy by that name |
    | `version-mismatch` | a manifest's `version` is not the trimmed content of `VERSION`, once per manifest. A missing or empty `VERSION` is one finding |
    | `skill-missing` | a root-level `<dir>/SKILL.md` is not reachable through `skills`, or `skills` is absent or is not a path string or an array of them |
    | `skill-extra` | a `skills` entry is a directory outside the skill set, a skill directory resolves outside the checkout, or a top-level `skills` exists of any kind: Claude Code scans it beside the key, so it would double the catalog (BR-2, ADR-8) |
    | `dangling-entry` | a `skills` entry names no directory, or does not start with `./`, even beside a twin that does |
    | `agents-ref-invalid` | `agents` breaks the harness's shape above (BR-3) |
    | `hooks-ref-invalid` | `hooks` breaks the harness's shape above (BR-4) |
    | `path-missing` | a value under `MANIFEST_PATH_KEYS` is not a `./` path with no `..` segment that exists inside the checkout, symlinks resolved, or a companion file does not exist. Only `logo` and `icon` may hold an `https` URL. An inline value is left to `execution-key`, a machine path to `machine-path`, and `agents` and `hooks` on an `empty` entry to their shape rules |
    | `unknown-key` | a top-level key the registry does not list for that harness, or a key `marketplace.json` does not list, at its top level or in its entry |
    | `machine-path` | a string value at any depth starts with `/` or `~/`, is `~`, names `$HOME` or `%USERPROFILE%` in any spelling, is a Windows path, holds a home path such as `/Users/` in any case, or is a URL form other than `https` with a host and no userinfo. What follows an `https` URL in the same value is still read |
    | `execution-key` | a manifest carries a key under `MANIFEST_EXEC_KEYS`, in any form, a path key holds an inline definition, or a file under `MANIFEST_DEFAULT_EXEC_FILES` exists. No path rule can read those, and a harness acts on them at install or at session start (BR-4, LESSON-749) |

    Two gaps are declared, not chased: a percent-encoded home path in a free string,
    and a symlink inside the checkout whose target is an absolute path that also
    resolves inside it, which would dangle on another machine.

    REQ-669's rows all still hold, under this one check id. The reserved-name,
    marketplace and `bin` rows keep their wording and carry no rule tag; the
    others are reported under the rule above that covers them. Each of these is
    one finding:

    | Fires when |
    |---|
    | a manifest is missing, is not UTF-8 or JSON, is not a top-level object, or uses `NaN`/`Infinity` |
    | a JSON object repeats a key, at any depth. `json.loads` keeps the last value and the plugin loader may keep another, so the parse uses an `object_pairs_hook` that rejects the repeat (LESSON-716). `claude plugin validate --strict` passes such a file |
    | `plugin.json` `version` is not the trimmed content of `VERSION`, or `VERSION` is missing |
    | the plugin `name` is not kebab-case, or starts with a reserved prefix in `PLUGIN_RESERVED_NAME_PREFIXES`: `claude`, `anthropic` or `cc-plugin-` (case-insensitive). The three cover every prefix requirement.md's PluginManifest entity forbids (`claude-`, `anthropic-`, `anthropics-`, `cc-plugin-`). `cc-tools` and `ccplugin-x` are clean |
    | a root-level `<dir>/SKILL.md` is not reachable through `skills`: reachable means `skills` is `"./"` or `"."`, or an array holding one of them or `"./<dir>"`. An entry that does not start with `./` reaches nothing, as in the loader. A missing `skills` field is one finding |
    | an `agents` field is present but omits an `agents/*.md`. The field replaces the default `agents/` scan, so the manifest carries none |
    | `marketplace.json` `plugins` does not have exactly one entry, the entry's `name` is not `adlc`, or its `source` is not `"./"` |
    | a top-level `CLAUDE.md` exists, of any kind (`os.path.lexists`). Claude Code does not load one at a plugin root and warns, which fails `claude plugin validate .claude-plugin/plugin.json --strict`, and `adlc harness render --harness claude` writes one when none exists. The toolkit's own is `.claude/CLAUDE.md` (BUG-258) |
    | a top-level `bin` exists, of any kind: a directory, a file, or a symlink (a dangling one included; the test is `os.path.lexists`). Directory listings reach Claude Code users through the claude.ai sync path, which rejects a plugin with one, so executables go under `scripts/` (ADR-4) |

    The skill set uses the loader's rule from the architecture probe: one level
    below the root, hidden directories (`.adlc/`, `.claude/`) excluded, so a
    `SKILL.md` under `tools/` is not a skill. The check is per-root. It is
    inert unless the root has `.claude-plugin/` or is a versioned skills root
    (`VERSION` plus a root-level `<dir>/SKILL.md`). Either one arms it, so
    deleting every manifest turns into findings, not a silent pass (LESSON-019).
    `scan_plugin_manifest` also returns the number of manifests and companions
    it read, 4 on a complete root, and every test asserts it is non-zero.
    The acceptance tests are `tests/test_manifest_parity.py`, one firing test per
    rule, and REQ-669's cases stay in `tests/test_plugin_manifest.py`. Fixture
    trees are in `tests/fixtures/plugin-manifest/`, a name ADR-1 kept. Their
    skills are stored as `SKILL.fixture.md` and renamed when a test stages them,
    so neither this lint's `SKILL.md` walk nor the plugin loader ever sees a
    fixture skill.

    BR-1's install commands are checked by a test rather than a lint rule,
    because they live in the README:
    `test_readme_install_commands_match_the_manifests` requires `claude plugin marketplace add atelier-fashion/adlc-toolkit` and
    `claude plugin install adlc@adlc-toolkit`, each verbatim on a line of
    README.md, every `claude plugin install <plugin>@<marketplace>` line there to
    type plugin.json's and marketplace.json's `name`s, and the added repo to be
    plugin.json's `repository`. `test_readme_install_check_fires_on_drift` edits
    each side in turn and expects a problem. REQ-665's README section is pinned
    the same way, in `tests/test_manifest_parity.py`:
    `test_readme_alternative_section_parts` requires one subsection per registry
    entry but `claude`, each with its install, what loads, what does not, coexistence,
    update and trade-off, and `test_docs_name_the_new_check` reads the documents
    for the name this check replaced.

13. **Toolkit root line (`toolkit-root-line`)** (REQ-669 ADR-1, BR-3, BR-4):
    every shell fence that reads `$ADLC_TOOLKIT_ROOT` carries the canonical
    root line, byte-exact, on its own line before the first read:

    ```sh
    ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
    ```

    `check.py` pins it as `TOOLKIT_ROOT_LINE`, and conventions.md 'Bash in
    skills' explains the arm order. Walking each fence's non-comment lines in
    order, two things are findings, and each fence reports only its first:

    | Fires when |
    |---|
    | a line reads the variable (`$ADLC_TOOLKIT_ROOT`, `${ADLC_TOOLKIT_ROOT}`, `${ADLC_TOOLKIT_ROOT:-…}`) and no root line sits above it in the same fence. That covers a fence with no root line, a root line placed after the first read, and a fence that leans on an earlier fence's root line. Fenced blocks share no shell state, and `cross-fence-var` exempts exported names, so this rule is what catches the cross-fence read |
    | any other line assigns `ADLC_TOOLKIT_ROOT` at statement position, optionally behind `export` or `readonly`. That is a variant of the root line (the message gives the first differing column) or a re-assignment after it. Every one-character edit of the root line leaves at least one of its four assignments in place, so every such edit lands here, and the suite checks each deletion and substitution |

    Leading indentation is allowed. Anything after the line, even one trailing
    space or a comment, makes it a variant. The rejected
    `${CLAUDE_PLUGIN_ROOT:-…}` form and the unbraced `$CLAUDE_PLUGIN_ROOT` are
    variants: Claude Code rewrites only the braced, unadorned token. A fence
    that never names the variable needs no root line. `bash` fences are not
    exempt, for the reason item 9 gives. Prose, non-shell fences and comment
    lines are not read. The check walks the same markdown families as item 9
    (`*/SKILL.md`, `agents/*.md`, `proceed/phase*.md`, `partials/*.md`), and
    none of them count toward `scanned`. It does not walk `partials/*.sh`: a
    partial reads the root through the ADR-2 default-expansion spelling
    `"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/…"` and never carries the
    root line. `partials/tests/toolkit-root.test.sh` runs the copy of the
    line in conventions.md under bash, zsh, `/bin/sh` and dash, and
    `test_conventions_documents_root_line_and_spelling_byte_exact` pins that
    copy to `TOOLKIT_ROOT_LINE`.

14. **Dispatch has fallback (`dispatch-has-fallback`)** (REQ-666 BR-3, BR-12;
    REQ-669 ADR-6, BR-9, BR-4; it absorbed REQ-669's `dispatch-fallback`): a
    harness may have no agent tool, a subagent cannot dispatch further, and the
    toolkit's agents are offered by bare name on the symlink install and as
    `adlc:<name>` on the plugin install, where a name the session does not offer
    can silently become a generic agent instead of failing. So every step that
    dispatches a toolkit agent carries the canonical dispatch paragraph, which
    says to dispatch when the harness can and otherwise run each checklist inline
    from `.adlc/agents/<name>.md` (`$ADLC_TOOLKIT_ROOT/agents/<name>.md`, naming
    `/init` (`/adlc:init` on the plugin install), when that directory is absent),
    to use the name form the Agent tool lists, and to keep an inline audit
    read-only. A step that cannot run without subagents (`/sprint`) carries the
    explicit-stop block, `<!-- dispatch-requires-subagents -->`, instead. A step
    that dispatches an agent with no toolkit checklist ("Launch Explore agents",
    "launch 3 agents using the Agent tool") owes at least the paragraph's leading
    clause, "If this harness can run subagents", with an inline arm that fits.
    Only an imperative counts as such an instruction: the base verb at the start
    of a clause, or "using the Agent tool"; "dispatched via the Agent tool" and
    "the dispatch prompt" do not.

    The sentence is **not** copied into `check.py`. It lives once, between the
    line-start markers `<!-- dispatch-fallback-sentence -->` and
    `<!-- /dispatch-fallback-sentence -->` in `.adlc/context/conventions.md`
    'Agent dispatch patterns', and the check reads it from there once per run.
    The scan root's own conventions.md is the source whenever the root has one.
    A missing, empty or unclosed block there, or one that exists only inside a
    fenced example, is a finding on every file that names a dispatch, so
    deleting it cannot disarm the check. Only a root with no conventions.md at
    all (a fixture root) reads the copy in the checkout the lint lives in. The
    agent names are the stems of `<root>/agents/*.md`, with the same fallback.

    A step is a `##` or `###` region; deeper headings belong to the step above
    them. A mention is one of:

    | Shape | Example |
    |---|---|
    | the bold list-item form | `1. **reflector** agent — …` |
    | a dispatch verb (`dispatch`, `launch`, `spawn` and their forms), then `<name> agent` in the same clause, bare, backticked, bold or `adlc:`-prefixed | ``Dispatch the `reflector` agent``, ``dispatch one `lite-reviewer` agent`` |
    | `launch … agents`, when the same or the next paragraph names a toolkit agent | `Launch 3 formal exploration agents …` followed by the list |

    Each step with a mention must contain the sentence, compared after
    collapsing whitespace, so a hard-wrapped or indented copy counts. One
    finding per step, at its first mention. A mention above the first `##`/`###`
    heading (a file's introduction) is satisfied by the sentence anywhere in the
    file. These are **not** mentions, and the suite pins each as must-not-fire:
    a cross-reference with no dispatch verb ("see the reflector's checklist in
    `/reflect`", "(the `reflector` agent)", "the reflector agent returns"), a
    verb after `not`, `never`,
    `cannot`, `n't`, `without`, `before` or `after` ("Do not attempt to launch
    reviewer or reflector agents"), `agent's`, any fenced line, and a Claude
    Code built-in such as "Launch Explore agents". The sentence's own text is
    removed before matching, so it never reads as a dispatch.

    The check walks `*/SKILL.md` and, through the same extra walk as items 9
    and 15 (`find_phase_files`), `proceed/phase*.md` and `partials/*.md`,
    because `/proceed`'s Phase 4 and lite Phase 5 dispatch steps live in
    companion files and a partial's companion doc can carry a dispatch step too.
    `test_dispatch_fallback_walks_partials_md` pins the `partials/*.md` walk
    (fires without the sentence, clean with it). Neither extra walk
    counts toward `scanned`. `agents/*.md` is not walked: an agent cannot
    dispatch, and `pipeline-runner.md` only says not to. The workflow engine
    names agents in code, so it is held to the same rule by
    `workflows/tests/helpers.test.js` instead: every `agentType` goes through
    `agentTypeFor(name, AGENT_NS)`. `test_dispatch_fallback_repo_clean` runs the
    check on the real tree and also asserts that each dispatching file has a
    mention and carries the sentence, so a clean run cannot be vacuous
    (LESSON-019).

15. **No harness path (`no-harness-path`)** (REQ-666 BR-13, ADR-5; REQ-669
    BR-13, BR-2, ADR-9; it absorbed REQ-669's `toolkit-path` and lifted
    `TOOLKIT_PATH_EXCEPTIONS` whole): no literal harness home path on the
    plugin-reachable surface. In the Markdown families (`*/SKILL.md`,
    `proceed/phase*.md`, `*/references/*.md`, `agents/*.md`, `partials/*.md`, and Markdown under
    `presets/` and `templates/`) that is any home of the five harnesses:
    `~/.claude`, `$HOME/.claude` in every brace and default form, and the same
    for `.codex`, `.copilot`, `.gemini` and `.cursor`. In code it is the toolkit
    spellings below and the four other harness homes (`OTHER_HARNESS_SPELLINGS`);
    a general `~/.claude` path in code is item 17's (`adlc-home`), which leaves
    a line holding a toolkit spelling to this check, so each line is reported
    once. Text names machine state through REQ-654's default-expansion spelling,
    `${ADLC_HOME:-$HOME/.claude}/…`. The rest of this item is the toolkit part,
    unchanged from `toolkit-path`: no literal toolkit read path. The plugin route has no
    `~/.claude/skills` and no `~/.claude/agents`, so a read through either
    names a file that is not there, or the clone on a doubled machine. Reads go
    through ToolkitRoot: `$ADLC_TOOLKIT_ROOT/…` after a fence's root line, the
    default-expansion spelling in a partial, `tools/adlc/toolkit_root.py` in
    Python.

    The surface is `TOOLKIT_PATH_SURFACES`, one entry per family: `*/SKILL.md`,
    `proceed/phase*.md`, `*/references/*.md`, `agents/*.md`, `partials/*.sh`, `partials/*.md`,
    `workflows/*.js`, `tools/**`, `presets/*` and `templates/*`. The two
    companion families come from `skill_companions`, the helper the per-file
    walk uses, so both read the same companion set (REQ-661 BR-7). In `tools/**`
    only code files are read: `.py`, `.sh`, `.js`, and any other non-Markdown
    file that opens with `#!`. The presets and templates ship in the plugin and
    are what a user copies from, so a path in them is one the user types. The
    flagged spellings are `TOOLKIT_PATH_SPELLINGS`, each in a `~`, `$HOME`,
    `${HOME}` and `${HOME:-}` form for both directories: `~/.claude/skills`,
    `$HOME/.claude/skills`, `${HOME}/.claude/skills`,
    `${HOME:-}/.claude/skills`, `~/.claude/agents`, `$HOME/.claude/agents`,
    `${HOME}/.claude/agents` and `${HOME:-}/.claude/agents`. Each is a plain
    substring match, never `\b` (LESSON-013). In a `.py` file the check also
    flags a path built from parts, `TOOLKIT_PATH_PY_JOIN_RE`: a quoted `.claude`
    then a quoted `skills` or `agents` joined by `,` or `/`
    (`os.path.join(home, ".claude", "skills")`, `Path.home() / ".claude" /
    "agents"`), or a quoted `.claude/skills` or `.claude/agents`.
    `".claude", "adlc"` and `".claude", "skills-cache"` are clean, and the
    shape is not looked for outside Python. One finding per line, naming every
    spelling the line holds.

    The exceptions are one constant, `TOOLKIT_PATH_EXCEPTIONS`. Each literal is
    matched byte-exact, never as a pattern, so a near-miss of an exempt
    spelling is a finding:

    | Kind | Exempt | Why |
    |---|---|---|
    | line | the canonical root line (`TOOLKIT_ROOT_LINE`), leading indentation aside | its symlink arms are ToolkitRoot on the symlink route. A trailing space or comment, or a `${HOME}` arm, is a variant and fires |
    | line | `CLAUDE_PROJECT_SKILLS = ".claude/skills"` (`PROBE_PROJECT_SKILLS_LINE`) | `adlc harness probe` (REQ-664) writes Claude Code's project-local skills directory into the throwaway repository it builds; the path is joined to that repository, never to a home. A test holds the line to `tools/adlc/harness_probe.py` verbatim |
    | token | `"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/`, opening quote and trailing slash included | the ADR-2 default-expansion spelling a partial uses, since it carries no root line. It is removed before the search, so the rest of the line is still checked. The unquoted and `${HOME}` forms are not this literal |
    | file | `install.sh` | the symlink installer, which the plugin route never runs |
    | file | `tools/adlc/checks.py` | the doctor's route checks inspect the symlink install on purpose (ADR-7). The exception is whole-file, so a test holds it to that purpose (below) |
    | file | `tools/lint-skills/check.py` | the lint's own rule table: it spells every pattern it polices |
    | token | `${ADLC_HOME:-$HOME/.claude}` | REQ-654's default-expansion spelling of the machine-state home (REQ-666): the path is named through the variable that owns it, the literal is only its default |
    | marker | a line carrying `adlc-home: claude-code`, `adlc-home: alias` or `adlc-home: default` (in Markdown as an HTML comment) | REQ-654's marker, one mechanism for both checks: the line keeps its literal on purpose and says why. An unknown kind is `adlc-home`'s finding |
    | comment | a whole-line HTML comment in a Markdown file | the agents' rendered `model:` header names the machine config's default location (REQ-666) |
    | file | `tools/adlc/harness_probe.py` | REQ-664's §6 probes edit the other harnesses' user files and read their session stores by design (REQ-666) |
    | file | `partials/session-transcript.sh` | REQ-660 BR-9: `/wrapup`'s transcript walk reads the Codex, Copilot and Gemini session stores, those harnesses' own data directories, which an `adlc-home` marker would mislabel. The exception is whole-file, so `test_session_transcript_exception_names_only_its_three_roots` holds it to those three roots, and `adlc-home` still reads the file |
    | comment | `#` in shell, Python and the shell fences of a Markdown file; `//` and `/* … */` in JavaScript, except under `presets/` and `templates/` (`TOOLKIT_PATH_INSTRUCTION_DIRS`) | a comment is not a read. A Markdown heading is not a comment, and a trailing comment does not exempt its code line. In a preset or a template a `#` line is the user's instruction (the preset header says `#   cp "$ADLC_TOOLKIT_ROOT/presets/<x>.yml" .adlc/config.yml`), so no comment line there is exempt |
    | tree | `tests/` and `fixtures/`, at any depth below the root | they plant the spellings on purpose |

    The file exceptions are root-relative paths, so `tools/delegate/install.sh`
    is checked. `tools/adlc/checks.py` is set aside whole, and ADR-2 replaced
    `_partial_path`'s `~/.claude/skills` fallback in that very file, which is
    where a regression would land unseen. So
    `test_checks_py_names_the_symlink_install_only_where_it_inspects_it` reads
    the committed file and requires every line that names the symlink install
    (a flagged spelling, a `.claude`/`skills` join, or a
    `_claude_home(), "skills"` join, docstrings and comments included) to sit
    in one of `CHECKS_PY_INSPECTORS`: `_symlink_install`,
    `check_doubled_install`, `check_skills_symlink` and `check_agents_symlink`.
    Each of the four must name it, so the list cannot go stale, and
    `test_checks_py_guard_fires_on_a_partial_path_fallback` plants each
    fallback shape in `_partial_path` and expects it reported.

    The check is per-root and armed like `manifest-parity` (`is_plugin_root`):
    only a plugin root has a plugin-reachable surface, so a consumer repo is
    never read. Like every walk here it keeps to the scan root and tests only
    the path components below it, so a root inside `.worktrees/` is scanned in
    full. The `tools/**` walk never enters a hidden directory (a nested
    `.claude/worktrees/` or `.worktrees/` checkout, `.git`), `node_modules` or
    `__pycache__`, and `*/SKILL.md` uses the loader's one-level rule. The walk
    is `_scan_surfaces`, shared with `builtin-collision`: a file two surfaces
    yield counts under each and is read once, and both checks share the
    `tests/`/`fixtures/` tree test (`_toolkit_path_tree_excepted`).
    `scan_toolkit_path` returns the files read per surface and the file
    exceptions it set aside, and
    `test_repo_root_clean_and_every_surface_scanned` fails if any surface read
    nothing (LESSON-019). Fixture trees are in `tests/fixtures/toolkit-path/`.

16. **Built-in collision (`builtin-collision`)** (REQ-669 BR-10, ADR-5,
    TASK-133): a skill name Claude Code also owns is never printed bare as an
    instruction. Claude Code 2.1.258 resolves a bare `/<name>` to the first
    command whose name matches exactly, so on the plugin install a bare `/init`
    reaches Claude Code's built-in CLAUDE.md generator, not `/adlc:init`. The
    watched names are `BUILTIN_COLLISION_NAMES`: `init` and `status` (built-in
    commands) and `review` (an alias of the bundled `code-review` skill).

    A line fires when it mentions a watched name as an instruction and does not
    also carry `/adlc:<name>`. A mention is an instruction when one of these
    verbs comes right before the slash token: run, re-run, rerun, running,
    re-running, invoke, type, recommend (running), "proceed to", "ready for",
    before, "note for", use or try. It is also one when one of these phrases
    comes right after it: first, "there too", "to vendor", "to refresh",
    "to scaffold", "to set up", "if missing" or "to copy". These are
    `BUILTIN_COLLISION_VERB_RE` and `BUILTIN_COLLISION_TAIL_RE`, the same
    patterns as the e2e audit `builtin_collision_static`. A test keeps the two
    equal. A noun mention does not fire: a heading, a table cell naming the
    skill, "the `/<name>` skill copies…", or a path component such as
    `$ADLC_TOOLKIT_ROOT/<name>/SKILL.md`. Comment lines are checked, because a
    reader follows an instruction in a comment too. One finding per line,
    naming every bare name on it.

    The fix is the dual spelling from conventions.md, "Skill names Claude Code
    also owns", on the same line as the bare name. The form depends on where
    the text appears: Markdown prose, a quoted runtime string, or a `!` preamble
    line that allows neither backticks nor parentheses.

    The surface is `BUILTIN_COLLISION_SURFACES`. It is no-harness-path's surface
    (`*/SKILL.md`, `proceed/phase*.md`, `*/references/*.md`, `agents/*.md`, `partials/*.sh`,
    `partials/*.md`, `workflows/*.js`, `tools/**`, `presets/*`, `templates/*`)
    plus the shipped families the e2e audit also reads: `proceed/*.md`,
    `workflows/*.md`, `scripts/*`, `hooks/*`, `ETHOS.md` and `tools/delegate/*`.
    So a clean lint leaves that audit no bare line to fail on. It also reads the
    two root docs a reader follows step by step, `README.md` (install and
    setup) and `RELEASING.md` (the release sequence). `CHANGELOG.md` is not
    read: its released entries record what shipped and are not rewritten, so a
    bare instruction in a new `[Unreleased]` entry is fixed by hand. Each
    surface is listed once. The check is
    walked and armed like `no-harness-path` (`is_plugin_root`), and a file two
    surfaces yield is read once. Of no-harness-path's exceptions only the `tests/`
    and `fixtures/` trees apply. The doctor's remediations in
    `tools/adlc/checks.py` are printed to the user, so they are checked.
    Fixture trees are in `tests/fixtures/builtin-collision/`.

    When a Claude Code upgrade adds a built-in that shares a skill's name,
    `builtin_collision_static` reports it. Add the name to
    `BUILTIN_COLLISION_NAMES`, then dual-spell the lines this check names.

17. **ADLC home (`adlc-home`)** (REQ-654 BR-13, ADR-9): no new literal
    home-directory `.claude` path in code. The toolkit's machine state (the id
    counters and their locks, the reservations ledger, the machine config, the
    delegate venv, the skills view) lives under `ADLC_HOME`, default
    `~/.claude`, and code reads it through `adlc_home` in
    `partials/adlc-home.sh` or `tools/adlc/adlc_home.py`. A literal written
    anywhere else silently closes that seam again (LESSON-012).

    The surface is `ADLC_HOME_SURFACES`: `partials/*.sh`, `tools/**` (code
    files, walked as no-harness-path walks them), `install.sh` and `scripts/*`.
    The spellings are `ADLC_HOME_SHELL_RE` (`~/.claude`, `$HOME/.claude` in every
    brace, default, quoted and escaped form, and `$<var>/.claude` for a variable
    whose name holds `home`) and, in Python, `ADLC_HOME_PY_JOIN_RE`
    (`expanduser("~")`, `Path.home()` or a `*home*` name joined with
    `".claude"`). `.claude` must end the component, so `.claude-plugin` and
    `.claude.json` never match, and a repo-relative `.claude/worktrees` is not a
    home path.

    Not checked: `#` comment lines, Python docstrings (found with `ast`), the
    `tests/` and `fixtures/` trees, this lint's own `check.py`, the canonical root
    line and REQ-669's default-expansion token
    `"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/`. A line that keeps a literal
    on purpose says why with a marker on the line: `# adlc-home: claude-code`
    (a path Claude Code owns: its config dir and plugin cache, `settings.json`,
    `CLAUDE.md`, its skills and agents mounts), `# adlc-home: alias` (one of the
    two compatibility aliases, `~/.claude/skills` and
    `~/.claude/adlc/plugin-root`) or `# adlc-home: default` (a resolver's
    default arm, or a message that names the default for a human). Any other
    marker kind is a finding, so a typo cannot exempt a line. The marker is the
    only exemption mechanism, so every exemption is visible where it is made.

    Distinct from `no-harness-path` (item 15), which owns every harness home in
    text and the toolkit and foreign-harness paths in code; a code line holding a
    toolkit spelling is left to it. `scan_adlc_home` returns the files read per surface, and
    `test_every_surface_is_scanned` fails if any surface read nothing. Fixture
    trees are in `tests/fixtures/adlc-home/`.

18. **ETHOS line (`ethos-line`)** (REQ-666 BR-2, AC-3): the ETHOS `!` line is
    the one preamble line a skill keeps (plan M6). The check reads the canonical
    line from `.adlc/context/conventions.md` "Ethos injection pattern" (the
    scan root's copy, or the lint checkout's for a root with none; a copy
    without the line is one finding, so deleting it cannot disarm the check)
    and requires it exactly once, byte-identical, outside any fence, in every
    `*/SKILL.md`. A missing line, a line that starts like it but differs, and a
    second copy are each a finding, and so is any other inline bang command in a
    skill's prose: context reads belong in the `# adlc-context` fence. Per root,
    armed like `manifest-parity` (`is_plugin_root`). The same walk reads each
    skill's companions in companion mode (REQ-661 BR-7): a companion carries
    **zero** ETHOS lines, because only `SKILL.md` is preprocessed, so a copy
    there is a finding; the near-line and inline-bang rules are unchanged, and a
    companion is never owed the line. Tests: `tests/test_ethos_line.py`,
    `tests/test_skill_units.py`.

19. **Description budget (`description-budget`)** (REQ-666 BR-7, AC-7): every
    harness loads every skill description at session start, and Claude Code
    truncates its listing at 1 536 characters for `description` plus
    `when_to_use`. Each `description:` (quotes removed) must be at most
    `DESCRIPTION_BUDGET` (512) Unicode code points, counted with `len(str)`,
    never bytes. The check prints `description-budget: <N> skill
    description(s), <total> code points in all` to stderr whenever it runs.
    Per root, armed like `manifest-parity`. Tests:
    `tests/test_description_budget.py`.

20. **Skills reference validator (`skills-ref`)** (REQ-666 BR-11, AC-10): when
    a `skills-ref` executable is on PATH, every `*/SKILL.md` is validated with
    `skills-ref validate <dir>` and a non-zero exit is a finding. The validator
    rejects keys outside the Agent Skills spec, and `argument-hint` is one Claude
    Code reads at the top level, so each skill is validated from a copy staged
    under the system temp directory (removed afterwards) whose frontmatter
    omits `SKILLS_REF_HARNESS_KEYS`; the directory name is kept, so a `name:`
    mismatch still fails. The skill's companions are staged beside it at their
    paths under the skill (REQ-661 BR-7), so the directory is validated once,
    `references/` included, and never per companion. Without the validator the check prints one `skills-ref:
    SKIP` line naming `pip install skills-ref` and adds no finding, so the lint
    stays offline and stdlib-only (REQ-425 BR-1). Per root, armed like
    `manifest-parity`. Tests: `tests/test_skills_ref.py`, with a fake validator.
    The run against the real validator is a manual, recorded step.

21. **Skill line budget (`skill-line-budget`)** (REQ-661 BR-2, ADR-8): the
    Agent Skills specification keeps a `SKILL.md` under 500 lines. Every
    `SKILL.md` the walk yields is counted as `wc -l` counts (newlines), and one
    at `SKILL_LINE_BUDGET` (500) or more is one finding at line 1 naming the
    count and the budget. One threshold for every `SKILL.md`, with no allowlist
    and no override. It is not routed through `skills-ref`: that validator checks
    frontmatter rather than body length, and it is optional (item 20 SKIPs
    without it), so the budget would otherwise be enforced nowhere. A skill over
    the budget moves whole steps into `<skill>/references/` and leaves a
    read-and-follow pointer (see "Skill units and companions" below). Tests:
    `tests/test_skill_units.py` (a 500-line fixture fires, a 499-line one does not).

22. **Companion templating (`companion-templating`)** (REQ-661 BR-6, ADR-8):
    Claude Code preprocesses `SKILL.md` only, so a companion carries none of what
    that preprocessing feeds. Each argument placeholder in `ARGUMENT_PLACEHOLDERS`
    (`<request>`, `<req-ids>`, the tokens REQ-666 ADR-1 fixed, matched exactly,
    never as a generic angle-bracket pattern) and `$ARGUMENTS`, anywhere in a
    companion, is a finding on that line: a fence or sentence that consumes the
    skill argument stays in `SKILL.md`, beside the prose that fills it. So is a
    bang-backtick macro on a line outside every fence. Companions only. After
    REQ-666 this is the one check that guards companions for argument tokens
    (`arg-templating` covers bare `$<digit>` everywhere). Tests:
    `tests/test_skill_units.py`.

23. **Session gitignore (`session-gitignore`)** (REQ-660 BR-7, BR-15, AC-12): a
    session sidecar under `.adlc/.session/` names a local transcript path, so the
    line has to stay in the gitignore lines `init/SKILL.md` writes or sidecars
    start reaching consumer commits through a later edit. The check reads the
    `### Step 5` section of `SESSION_GITIGNORE_SITE`, from that heading to the
    next heading of level 3 or above outside a fence (the gitignore comments in
    the fence read as headings), and requires `.adlc/.session/` as a whole line
    inside a fence there, compared exactly because a leading space is part of a
    gitignore pattern. A mention in prose, a longer line that contains it and a
    copy in another step do not satisfy it (LESSON-404). A missing line is one
    finding on the Step 5 heading; a missing heading or an unreadable file is one
    finding naming the file, never a skip. Per root, armed by `is_plugin_root` and
    the site existing, so a plugin root holding no `init/SKILL.md` is inert. On
    the real tree `test_real_tree_passes` reads the site itself, so deleting the
    file cannot disarm the guard. That test also holds this repo's own
    `.gitignore`, which the check does not read. Tests:
    `tests/test_session_gitignore.py`.

## REQ-657: the harness adapter framework's checks

- **`allowlist-fidelity`** renders `templates/permissions.yml` at the scope each
  adapter's allowlist lives at (`project`, or `printed` for Copilot CLI) through every
  shipped adapter (`harness/*.yml`) and prints one line per
  `(harness, entry, command)`: `exact`, `widened:<spelling>`, `inexpressible`,
  `deny-unsupported` or `residual:exact-deny` (there is no `narrowed`), then, per
  adapter, what will prompt, what has no hard deny, what was widened and the adapter's
  `fidelity_notes`. It fails on a
  non-`exact` verdict the adapter's `accepted_fidelity` does not list at that scope,
  on a rendered allow whose first token runs its arguments (`env`, `xargs`, `sudo`,
  `python*`, …), on a rendered allow that matches a deny-tier command (plain, `git -C . …`,
  `NAME=1 …` or `bash -lc '…'`) in a shape whose `deny_under_allow` record is not a
  valid pass, on a `source: probe` record reading `pass` that differs from REQ-664's result file
  (`.adlc/research/harness-probes/<name>.json`), and on a `fence.partial-source`
  rendered as a first-token wildcard. The report ends with the declared residuals.
- **`render-parity`** calls the function `adlc harness render --check` calls and
  reports every golden under `harness/<name>/rendered/` and every in-tree render
  (the agents' `model:` lines, the toolkit's `.claude/settings.json`) that is
  `drifted` or `missing-golden`. A printed surface's golden is
  `printed-permissions.txt`; a copy harness's is `agents.json`, each agent's file name
  and `tools:` line, so a body edit to `agents/*.md` does not touch `harness/**`.
  `adlc harness render --write-goldens` rewrites them.
- **`harness-loss-table`** (REQ-656) holds each `<!-- harness-loss: <name> -->` block in
  the root `README.md` to its adapter. It derives the expected facts from the adapter
  and a fresh render (committed allowlist, granularity, deny mechanism, the omitted
  bases and prefixes, the widths) and fails on a missing row, a contradicted fact, a
  missing declared-residuals statement, a claim that the allowlist is the gate, or a
  claim that Copilot's chained-command matching is verified. `LOSS_TABLE_HARNESSES`
  names the harnesses it holds.
- **`unguarded-source`** also walks `templates/hooks.yml` and every committed hook
  render, one hook-command line at a time.
  It also fails a hook command holding the braced `${CLAUDE_PLUGIN_ROOT}`, because
  Claude Code never runs a project hook that does (REQ-660 ADR-8). A hook spells the
  root line `HOOK_ROOT_LINE`, the canonical line with that token unbraced.
- **`retired-settings-template`** reports a skill, companion, agent, partial or
  partial doc that still names the deleted Claude settings template.
- **`sync-surface-parity`** knows the seventh surface, `harness-config`.

<!-- declared-residuals -->
**Declared residuals (REQ-657 BR-18).** Allowlist and prefix-deny matching cannot be made a gate, and the adapter framework does not pretend it can. `allowlist-fidelity` closes spellings, not this list:

- Allowlist matching is spelling-level. The lint evaluates a closed set of spellings; a deny-tier command reached in any other spelling is not seen.
- Allows that execute their arguments (`find -exec`, `awk`, `sed e`, `npx`, `npm run` / `npm exec`, `git rebase --exec`, `git fetch --upload-pack`) and `gh api` can reach a deny-tier command in a spelling the deny does not match.
- Semantic equivalents of a deny-tier command (`git restore`, `git checkout -f`, `git worktree remove --force`, `gcloud` deploys, `npm publish`) are outside the deny tier.
- This is the same exposure Claude's template has today (Rule A grandfathers it); no adapter makes it worse, and none claims to close it.
- The allowlist is never the gate (Rule B). The orchestrator's structural gates (REQ-659) are.
<!-- /declared-residuals -->

## Skill units and companions (REQ-661)

A skill **unit** is a `SKILL.md` and its companions: `<skill>/references/*.md`
(the Agent Skills layout, one level deep, no nesting), and for `/proceed` its
`proceed/phase*.md` files, which stay beside `SKILL.md` (BR-12). The one helper
is `skill_companions`; `find_skill_units` builds the units from
`find_skill_files`, so a companion is walked exactly when its `SKILL.md` is,
under the same pruning (`SKIP_DIR_PARTS`, BUG-254's `.claude/worktrees` pair, the
root-relative rule and the symlink-escape guard). A root's `proceed/phase*.md`
files are walked even when it has no `proceed/SKILL.md`.

- **Every per-file check walks the companions** with the rules it applies to
  `SKILL.md` (BR-7): `sentinel`, `balance`, `canonical-helper`, `posix-fence`,
  `arg-templating`, `cross-fence-fn`, `cross-fence-var`, `forge-direct-gh`,
  `read-bin-fallback`, `unguarded-source`, `toolkit-root-line` and
  `dispatch-has-fallback`, plus `companion-templating`. `ethos-line` reads them in
  companion mode, `skills-ref` stages them, `no-harness-path` and
  `builtin-collision` read them as the `*/references/*.md` and
  `proceed/phase*.md` surfaces, and `description-budget` has nothing to read in
  them. `skill-line-budget` counts `SKILL.md` only.
- **The unit is one scope** for `cross-fence-fn`, `cross-fence-var` and
  `canonical-helper` (BR-8): the fences of every file in the unit are numbered as
  one sequence, so a function or non-exported variable shared between a
  `SKILL.md` fence and a companion's is the same finding as a within-file split.
  A within-file finding keeps its old file, line and message; a cross-file one is
  reported at the call or read site and names the defining file. A canonical
  literal anywhere in the unit satisfies `canonical-helper`.
- **`scanned` counts `SKILL.md` only** (BR-9): a dead skill walk is not maskable
  by companion files.
- **Per-root site lists follow the content** (BR-10). `LIFECYCLE_WRITE_SITES`,
  `RETRIEVAL_READER_SITE`, `LANE_SITES` and `LESSON_RULES_PARITY_SITES` name the
  file that holds each block today, and a move updates the list in the same
  change. Once a check is armed (its gate file exists: `spec/SKILL.md` for
  `retrieval-status-parity`, `wrapup/SKILL.md` and `bugfix/SKILL.md` for
  `lesson-rules-parity`, the vocabulary file or `proceed/phases-lite.md` for
  `lane-vocabulary`), a listed site that is missing is a finding naming the path
  and the constant, and a listed site whose block now lives in another file of
  the same unit is a finding naming that file (`moved_within_unit`) — never a
  silent pass. `lane-vocabulary` also scans every companion of a listed
  `<skill>/SKILL.md`. `lesson-check-order` and `lesson-question-coverage` are
  keyed on the **unit's** name, so `wrapup/references/x.md` belongs to `wrapup`
  rather than `references`, and run on the unit's capture file, the first file
  holding a write point, a check or recheck fence, or the rules block; one of
  those in a second file of the unit is `capture-step-split` (BR-5).
  `sync-surface-parity` reads `init/SKILL.md` and `template-drift/SKILL.md` only
  and is unchanged. Tests: `tests/test_site_lists_follow_content.py`.
- `partials/*.md` is not a skill companion. It keeps the three checks it had
  (`unguarded-source`, `toolkit-root-line`, `dispatch-has-fallback`): those files
  are documentation the Skill loader never templates, and the wider checks report
  false positives on their examples.

## Usage

```sh
# From the repo root
python3 tools/lint-skills/check.py
# or
sh tools/lint-skills/check.sh
```

Findings are written to stdout in the format
`<file>:<line>: <check-name>: <message>`. Every run also writes the work done to
stderr — `skill-md-corruption: scanned <N> SKILL.md file(s)` — so a caller can
read the count directly instead of inferring it from a green exit.

| Exit | Meaning |
|---|---|
| `0` | clean pass — at least one file scanned, no findings |
| `1`–`254` | `min(findings, 254)` |
| `255` | **vacuous scan** — zero `SKILL.md` files were walked |

A run that finds nothing because it *scanned* nothing is a failure, not a pass
(REQ-595 BR-5). REQ-435 fixed the vacuous *walk* — a scan root that itself sits
under `.worktrees` / `.git` / `node_modules` is no longer skipped into oblivion —
but a root that genuinely contains no `SKILL.md` still exited 0, which is the
same confident green one layer down. Status `255` names that case explicitly, and
the findings cap sits one lower (`254`) so a saturating findings run can never be
mistaken for it. POSIX exit statuses are 8-bit, so the distinct value had to be
carved out of the top of the findings range rather than placed above it.

The usual cause is a wrong `--root`. The stderr message says so.

`/analyze` runs the same check at Step 1.9 and surfaces results as a
`skill-md-corruption` audit dimension.

## Adding a new sentinel

A new corruption shape escaped detection? Append one literal line to
`sentinels.txt`. Comments (`#`-prefixed) and blank lines are ignored. The
linter picks up the new sentinel on its next run — no code changes needed.

## Tests

```sh
pytest tools/lint-skills/tests/ -q
```

Or run together with the delegation suite:

```sh
pytest tools/delegate/tests/ tools/lint-skills/tests/ -q
```

## Constraints

- Python 3 stdlib only (`argparse`, `json`, `os`, `posixpath`, `re`,
  `pathlib`, `shutil`, `subprocess`, `sys`, `tempfile`). No third-party packages.
  No network.
- POSIX `sh`-compatible wrapper. Tested on macOS and Linux.
- Read-only against the repo. No logs, no cache, and no temp files except the
  `skills-ref` check's staged copies, which live under the system temp directory
  only while the installed validator runs (item 20).

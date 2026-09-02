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

   Each missing literal is a separate finding.

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
   if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . ~/.claude/skills/partials/delegate-gate.sh; fi
   case "$ADLC_READ_BIN" in /*) ;; *) echo "/<skill>: ADLC_READ_BIN is not an absolute path ('$ADLC_READ_BIN') — refusing to hand over the corpus (re-run install.sh --with-delegation, and /init to refresh the vendored gate)" >&2; exit 1 ;; esac
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
   if [ -f .adlc/partials/<name>.sh ]; then . .adlc/partials/<name>.sh; else . ~/.claude/skills/partials/<name>.sh; fi
   ```

   The repo-local copy is *tested* before it is sourced, never guessed at with
   `||`. `[ -f ]` rather than `[ -r ]`: an existing-but-unreadable vendored copy
   then fails loudly at the `.` instead of silently falling through to canonical
   and hiding a permissions problem. One line, so Skill `$<digit>` argument
   templating cannot split it and `cross-fence-fn`'s line-based parsing still
   sees one statement. The regex carries a **backreference**, so all three
   `<name>`s must agree — a line that guards `forge.sh` and then sources
   `intake.sh` is a finding, not a pass. A trailing `#` comment is allowed.

   This check walks four file families — `*/SKILL.md`, `agents/*.md`,
   `proceed/phase*.md`, and the partials themselves (`partials/*.sh` and a
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
     `~/.claude/skills/partials/<name>.sh`, `$HOME/.claude/skills/partials/<name>.sh` —
     must match that spelling exactly. A source through a variable path
     (`. "$D/partials/x.sh"` behind the author's own `[ -f ]`) is deliberately out of
     remit: the two-level spelling would point a consumer's own partial at a
     `~/.claude/skills/partials/<their-name>.sh` that does not exist;
   - **anywhere in the file** — prose, inline code, fence comment — the retired
     literal is a finding. A SKILL.md sentence instructing the agent to type the
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

- Python 3 stdlib only (`argparse`, `re`, `pathlib`, `sys`). No third-party
  packages. No network.
- POSIX `sh`-compatible wrapper. Tested on macOS and Linux.
- Read-only against the repo. No temp files, no logs, no cache.

# Conventions — ADLC Toolkit

## Code is markdown, not code

Every skill and agent is a markdown file. No TypeScript, no Python, no package.json. Claude Code interprets the markdown at invocation time. This matters:

- **No build step**: edits take effect immediately via the symlink install
- **No test runner**: "tests" are dogfooding — invoke the skill on a real REQ and see if it produces the expected artifacts
- **Linting is minimal**: markdown formatting, frontmatter validity, and bash syntax in `!`...`` macros. Nothing else.

**Exception — `tools/`:** the `tools/` directory may contain real executable code (e.g. `tools/delegate/`, a set of Python delegation CLIs with its own `install.sh`). It is exempt from the markdown-only rule and from the symlink-install model — those tools are installed by running their `install.sh`, not via the skills symlink. Each `tools/<name>/` subdirectory carries its own README.

**Exception — `space/` and `workflows/`:** both hold zero-dependency JavaScript tested with Node's built-in runner (`node --test 'space/tests/*.test.js'`, `node --test 'workflows/tests/*.test.js'`), with no package manager. `space/` is the static Hugging Face Space for `/spec` intake (REQ-670). It has a build step, `node space/build.mjs`, which generates `space/toolkit-data.js` from the toolkit; `--check` fails on drift. Neither directory holds a `SKILL.md`, so neither is a skill.

## File and directory naming

- Skill directories: lowercase, single word or hyphenated (`spec`, `bugfix`, `template-drift`)
- Skill files: always `SKILL.md` (uppercase, singular) inside the skill directory
- Agent files: `agents/<agent-name>.md`, hyphenated lowercase
- Templates: `templates/<artifact>-template.md`
- IDs: `REQ-xxx` (zero-padded to 3 digits), `TASK-yyy`, `BUG-zzz`, `LESSON-nnn` — always uppercase prefix, always 3 digits minimum
- Slugs: lowercase kebab-case, ≤6 words, no dates, no bare numbers

## Frontmatter conventions

All artifact types use YAML frontmatter. Dates in ISO format (`YYYY-MM-DD`). Arrays use JSON inline syntax (`tags: [a, b, c]`). Status enum values are lowercase strings.

**Required vs optional** varies per template. Generally: `id`, `title`, `status`, `created` are required; everything else is optional. When adding new fields, prefer additive — do not rename existing fields without a migration plan.

## Ethos injection pattern

Every skill begins with:

```markdown
## Ethos

!`test -s .adlc/ETHOS.md && cat .adlc/ETHOS.md || echo No ethos found — run /init, or /adlc:init on the plugin install, to vendor .adlc/ETHOS.md`
```

The line reads the **project's vendored copy only**: `/init` writes `.adlc/ETHOS.md` into every consumer project and `/template-drift` keeps it current, and the `test -s` is REQ-416 H1 — an empty copy must fall through to the notice, not swallow the ethos. It names no path outside the session root and runs no interpreter (BUG-218), so it reads the same in a main checkout, a worktree and a subagent. It is the one `!` preamble line a skill keeps: on Claude Code it is the only path that reaches a skill invoked inside a subagent (plan M6), and `tools/lint-skills`' `ethos-line` check holds it byte-identical, exactly once, in every `SKILL.md`. Every other context read is a run-and-read fence (see "Context loading pattern"). `partials/ethos-include.sh` still exists for consumer projects whose vendored skills predate this line; do not reintroduce it, or a `~/` fallback, at a call site. Never hardcode the ethos body inside a skill.

## Delegation pattern (provider-agnostic)

Skills that delegate bulk reads or drafting to the configured delegate (`adlc-read` /
`adlc-write`) MUST source the shared gate predicate rather than inlining
`command -v adlc-read >/dev/null 2>&1 && …`. The canonical predicate lives in
`partials/delegate-gate.sh` and defines `adlc_delegate_gate_check()` with a 0/1/2 contract
(REQ-522 retired the legacy `kimi-gate.sh` back-compat alias):

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-gate.sh"; fi
adlc_delegate_gate_check; gate=$?
case $gate in
  0) ;;  # delegated
  1) ;;  # disabled (ADLC_DISABLE_DELEGATE=1, or not opted-in — BR-11)
  2) ;;  # unavailable (adlc-read did not resolve)
esac
```

The invocation fence sources the partial again — fenced blocks share no shell state —
and invokes the **absolute path** the gate exported, refusing anything that is not an
absolute path in that same fence before any corpus is handed over (REQ-609 BR-12):

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-gate.sh"; fi
case "$ADLC_READ_BIN" in /*) ;; *) echo "/<skill>: ADLC_READ_BIN is not an absolute path ('$ADLC_READ_BIN') — refusing to hand over the corpus (re-run install.sh --with-delegation (symlink install; the plugin ships no delegation CLIs), and /init (/adlc:init on the plugin install) to refresh the vendored gate)" >&2; exit 1 ;; esac
command "$ADLC_READ_BIN" --no-warn --paths ... --question "..."
```

Three properties, all three enforced by `lint-skills`' **`read-bin-fallback`** check
(the same structural posture as `forge-direct-gh`, LESSON-012 — and the one check
that also walks `agents/*.md`, since the pre-pass agent hands over a corpus too):

- **No bare-name default.** Falling back to the plain command name was a second
  resolver at the call site, by the weakest rule available, reached in exactly the
  case where the first resolver had already declined — and the gate now resolves by
  walking `$PATH` itself precisely so the shell's lookup machinery cannot answer
  (REQ-609 BR-11).
- **The guard tests the *shape* of the value**, not just that it is non-empty. The
  canonical gate exports an absolute path or empty, but a project whose vendored
  `.adlc/partials/delegate-gate.sh` predates REQ-609 still exports the plain command
  name on a `$PATH` hit, and `[ -n … ]` hands that back to the shell to resolve.
- **`command` on every invocation.** bash and zsh both permit a function whose name
  is an absolute path, so without the prefix a planted function — not the file the
  resolver proved is on disk — receives the corpus. The gate's own probe already
  used `command`; the call sites did not (REQ-609 ADR-3).

Skills refuse by exiting non-zero; `agents/delegate-pre-pass.md`, whose contract
forbids a non-zero exit, refuses into its degraded empty-candidates object instead
and records `gate=fail`/`mode=fallback`/`reason=no-binary` — never `api-error`,
which asserts a call that in this branch never happened.

A hostile in-process shell can shadow `command` itself with a function of that name;
that is out of the threat model (everything in the process is code the operator ran
on purpose) and it cannot cause transmission anyway, because only Python authorizes.
Likewise, a project's vendored `.adlc/partials/*.sh` are trusted as repo-local code —
there is no digest pin on them yet; that is a follow-up, not something this pattern
relies on.

The reason is exported as `ADLC_DELEGATE_GATE_REASON`. Delegation is **opt-in** (off by
default on fresh installs) — enabled by `ADLC_DELEGATE_ENABLED=1`, `delegate.enabled: true`
in the machine config (`<ADLC_HOME>/adlc/config.yml`, default `~/.claude/adlc/config.yml`), or an already-set legacy `KIMI_API_KEY`/`MOONSHOT_API_KEY`
(key continuity, data — REQ-515 BR-11), resolved in that precedence order.

An explicit `delegate.enabled: false` turns delegation **off** and outranks the legacy
key; an *absent* `enabled` key yields to it. Collapsing those two was BUG-205.

That config is parsed by PyYAML behind a **closed schema** in one loader
(`tools/delegate/_machine_config.py`, shared with `tools/adlc/forge_config.py` — REQ-609).
Unknown keys, a non-boolean `enabled`, a nested mapping, a repeated key anywhere in the
document, and a non-regular file at the path are all **refused**, not skipped: a reader
that skips what it does not understand fails open, and this one gates exfiltration.

**Where that cascade is resolved (REQ-603):** in Python, once. The shell gate may
*withhold* delegation — `no-binary`, and the `ADLC_DISABLE_DELEGATE` veto — but may
never *grant* it; every path that concludes "delegated" runs through
`_common.resolve_gate_verdict()` via one `adlc-read --print-gate` call. The veto is
the single deliberate duplication, safe because a veto can only return *disabled*,
and enforced by a cross-layer test that drives both layers over one input vector.
Do not add an authorizing arm to the gate: BUG-205 and BUG-209 are the two
directions that invariant has already been violated from.

Per-step telemetry state crosses the create → gate → invoke → resolve fenced blocks via
the **flag-file sidecar** (`partials/delegate-tools-path.sh`'s `skill-flag.sh mark`/`read`),
never via shell variables, because fenced blocks do not share shell state (REQ-522 BR-4).
The shared resolver `_adlc_emit_step_telemetry <skill> <step>` in
`partials/emit-step-telemetry.sh` reads those marks back and emits one telemetry record.

**Timeout.** Give the delegated `adlc-read` call a shell timeout of at least
120 s (Claude Code's Bash default): it is a network round trip over a multi-file
corpus, and a killed call only falls through to the fallback after the wait.

See `partials/delegate-gate.md` for the full protocol — return-code contract, the
canonical stderr emit templates parameterized by `<skill>` and `<purpose>`, and the BR-4
one-line-per-invocation rule. Per-skill stderr messages and fallback bodies stay inline at
the call site; only the predicate is shared.

## Forge adapter (provider-agnostic PR operations)

Skills that touch the pull-request lifecycle MUST route every PR operation through
the forge adapter (`partials/forge.sh`), never by shelling out to `gh pr` directly.
This makes a project portable between GitHub and Azure DevOps as a config change.
Source the sourceable partial and call the op **in the same fenced block** (the
cross-fence rule above):

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . "$ADLC_TOOLKIT_ROOT/partials/forge.sh"; fi
out=$(adlc_forge_pr_view "$pr" --fields state,url); rc=$?
```

The op set is `adlc_forge_pr_{create,ready,edit,view,list,merge,comment}`. The
GitHub backend (`gh`) is byte-compatible with the previous direct calls; the Azure
DevOps backend uses `az repos`. Provider resolution is per-project `.adlc/config.yml`
`forge.provider` > machine config > `auto` (origin-URL detection; unrecognized host
fails loud). Results/errors are normalized to one vocabulary (`state ∈
{OPEN,MERGED,CLOSED}`; error classes `auth-missing` | `pr-not-found` |
`merge-blocked-by-policy` | `feature-unsupported` | `network`, with raw backend stderr
preserved beneath the class). `forge.auth` stores a credential **source name** only
(`gh`/`az`/an env-var NAME holding a PAT) — never a key value (a key-shaped value is
refused). Two ops stay direct on purpose: `gh pr diff` (local read-only convenience)
and `gh pr checks` (CI-status polling, out of scope). The `tools/lint-skills`
`forge-direct-gh` check rejects any new direct `gh pr <op>` in a SKILL.md shell fence.
Full contract: `partials/forge.md`.

## Context loading pattern

A skill loads its context with one **run-and-read fence** under its `## Context` heading (REQ-666 BR-2). Its first line is the marker comment `# adlc-context`; the sentence before it tells the model to run the block first, with its shell tool, and read the output before continuing. Each read is a label and the command with its notice:

```sh
# adlc-context
echo '--- Conventions'
cat .adlc/context/conventions.md 2>/dev/null || echo 'No conventions found'
```

Every command ends in `|| echo '<notice>'`, so an absent file prints the notice and the fence exits 0; a failing command never aborts the invocation, as a `!` line's did on Claude Code. Read the consumer project's `.adlc/...` copy; a fence that also lists a toolkit file starts with the root line and reads `$ADLC_TOOLKIT_ROOT/...` (see "Bash in skills"). Compose the reads from commands the routine tier of `templates/permissions.yml` already pre-approves (`cat`, `grep`, `ls`, `test`, `find`, `echo`, `pwd`, `which`, read-only `git` subcommands), or add the command there in the same change and re-render the goldens (`adlc harness render --check` names them), so no invocation gains a prompt. The ETHOS line is the one `!` preamble line a skill keeps (see "Ethos injection pattern"); `tools/lint-skills`' `ethos-line` check flags any other inline bang command in a skill's prose.

Never hardcode paths; always allow the skill to degrade gracefully when a file is absent.

For shared multi-line snippets that would otherwise duplicate across many SKILL.md files, extract a POSIX shell partial under `partials/<name>.sh` and source it from each call site (see "Ethos injection pattern" above and the architecture.md "Partials" subsection). This keeps each SKILL.md focused on its own instructions and ensures updates land everywhere consistently.

## Prerequisites block

Every skill that depends on the `.adlc/` scaffold must have a `## Prerequisites` section that stops with a clear "run `/init` (`/adlc:init` on the plugin install) first" message if required files are missing. Do not silently produce broken output when context is absent.

## Skill names Claude Code also owns

Skill text prints next steps by bare name, such as "run `/validate`", and on both install routes a bare name reaches the skill (REQ-669 ADR-5), except where Claude Code owns the name too. Claude Code 2.1.258 resolves a bare `/<name>`, typed or sent through the Skill tool, to the first command whose name matches exactly. So on the plugin install a bare `/init` reaches Claude Code's built-in CLAUDE.md generator, not `/adlc:init` (REQ-669 `verification.md`, "Built-in command collision audit").

The watched names are `BUILTIN_COLLISION_NAMES` in `tools/lint-skills/check.py`: `init` and `status`, which are built-in commands, and `review`, which is an alias of the bundled `code-review` skill. Any line that tells the user or the model to run one of them prints both spellings on that same line, in the form for where the text appears:

| Where | Form |
|---|---|
| Markdown prose, including a quoted message the skill tells the model to say | `` `/init` (`/adlc:init` on the plugin install) `` |
| a quoted runtime string, such as `echo "…"` in a fence or a Python string | `/init (/adlc:init on the plugin install)` |
| a `!` preamble line, which allows neither backticks nor parentheses (BUG-220) | `/init, or /adlc:init on the plugin install` |

Replace `init` with `review` or `status` for the other names, and keep the words as written so the text stays the same everywhere. A name used as a noun stays bare: a heading, a table cell naming the skill, or "the `/init` skill copies…". The skill is not renamed, because on the symlink install the bare name still reaches it. The other skill names collide with nothing and stay bare.

`tools/lint-skills`' **`builtin-collision`** check enforces this. It fails an instruction-style mention of a watched name (a verb such as run, re-run, "ready for" or before right before the slash token, or a phrase such as first or "if missing" right after it) on a line that does not also carry `/adlc:<name>`. When a Claude Code upgrade adds a built-in that shares a skill's name, `builtin_collision_static` in `tools/adlc/tests/e2e/plugin-sandbox.sh` reports it. Add the name to `BUILTIN_COLLISION_NAMES` and dual-spell the lines the lint then names.

## Bash in skills

- Keep bash minimal — prefer Claude's own tool calls (Read, Grep, Glob, Edit, Write) over shell
- Bash is fine for deterministic operations: counter increments, directory creation, git commands, file globbing
- **POSIX-only**: no GNU-specific flags. Use `grep -oE` (not `-oP`), use `mkdir` locks (not `flock`), use `sed 's/old/new/'` not `-i ''` on macOS directly — prefer `perl` for in-place edits or write a temp file
- Quote file paths with spaces: `"$path"`
- Avoid `cd` — prefer absolute paths so commands work from any working directory
- **Never write a destructive command whose safety depends on a variable being non-empty.** `rm -rf "$(dirname "$VAR")"` becomes `rm -rf .` the moment `$VAR` is empty, and a guard sitting a few lines above it in a SKILL.md is one careless edit from being bypassed. Put the guards in a partial, next to the deletion, where they cannot drift from it — check the path is non-empty, that it lives under a real temp root, and that its basename is one the toolkit itself created. `partials/intake.sh`'s `adlc_intake_cleanup` is the reference (REQ-594).

**Substituting a value into a fence (REQ-666 BR-1).** A skill never writes `$ARGUMENTS`: Claude Code substitutes it before the model reads the file, and every other harness shows the model the literal string. Its Input section says in prose that the argument is whatever follows the skill name in the invocation (Claude Code also appends an `ARGUMENTS:` line when nothing in the text receives it), and what the skill does with none. A fence that needs a value the model holds, such as the request, carries an angle-bracket placeholder inside single quotes (`adlc_intake_detect '<request>'`), and the model replaces the placeholder **and its quotes** with the value as one single-quoted literal, every `'` in the value written `'\''`. So `it's $5` becomes `'it'\''s $5'`. Where the command reads stdin, a quoted-delimiter here-doc (`<<'EOF'`) is the alternative and needs no escaping. Never substitute into double quotes: a backtick or `$` in the value would run. An unescaped apostrophe ends the quote early, and the command becomes a syntax error that runs nothing, which for `/spec`'s intake probe silently skips the intake gate. The `${1}`/`$(0)` dodges stay, because Claude Code substitutes `$0`–`$9` whether or not `$ARGUMENTS` appears (`arg-templating`, LESSON-335).

**Fenced blocks do not share shell state across steps.** Each ```sh fenced block in a SKILL.md may be an independent shell invocation — shell functions and non-exported variables defined in one fenced block are NOT visible in another (the Claude Code Bash-tool contract: "the working directory persists between commands, but shell state does not"). Therefore a shared shell **function** MUST be sourced from a `partials/*.sh` at *each* call site, in the **same fenced block as the invocation**, and MUST NEVER be defined in one fenced block and invoked from another (the silent-`command not found` telemetry-loss class — REQ-436, REQ-424). The canonical pattern is `partials/delegate-gate.sh` and `partials/emit-step-telemetry.sh`: a function-exporting partial sourced with the guarded two-level spelling (below) immediately before it is called. This is enforced structurally, not by prose/honor-system (LESSON-012): the `tools/lint-skills` `cross-fence-fn` check flags any function defined in one fence but invoked from a different fenced block in the same SKILL.md.

**A fence may live in a companion (REQ-661).** A step moved into `<skill>/references/*.md`, or `/proceed`'s `proceed/phase*.md`, takes its fences with it, byte for byte, and every rule above applies there unchanged: the root line, the guarded source, POSIX shell, no bare `$<digit>`. The skill's `SKILL.md` and its companions are one **unit**, and the cross-fence rules apply across the unit: a function or non-exported variable defined in a `SKILL.md` fence is just as undefined in a companion's fence, which runs in its own shell and is read in a separate step besides, so `cross-fence-fn` and `cross-fence-var` judge the unit's fences as one sequence, and a canonical literal anywhere in the unit satisfies `canonical-helper`. Two things never move into a companion, because only `SKILL.md` is preprocessed: a fence or sentence that consumes the skill argument (the placeholder rule above), and the ETHOS `!` line. `tools/lint-skills`' `companion-templating` check reports either one in a companion. A `SKILL.md` stays under 500 lines (`skill-line-budget`); see architecture.md "Skill anatomy" for the read-and-follow pointer a moved step leaves behind.

**Resolve ToolkitRoot with the root line (REQ-669 ADR-1).** The toolkit runs from one of two installs: the symlink route (`~/.claude/skills` pointing at a clone) or the Claude Code plugin route (a cache copy under `~/.claude/plugins/cache/`). A fence that reads a toolkit-owned file (a partial, a tool, a template) first resolves that directory, ToolkitRoot, with exactly one canonical line. Write it byte-exact, on its own line, before the fence's first `$ADLC_TOOLKIT_ROOT`:

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
```

Its four arms run in this order, and the first non-empty one wins:

1. `${CLAUDE_PLUGIN_ROOT}`. On the plugin route Claude Code rewrites this exact token in the skill text to the cache path before any shell sees it. On the symlink route the token reaches the shell as written, and the variable is not in the Bash tool environment, so it expands empty.
2. `$HOME/.claude/skills`, when `~/.claude/skills/partials` exists: the symlink install. It comes before the pointer, so on a machine with both installs a symlink-route skill still reads the clone (REQ-669 BR-3), and `adlc doctor` reports the doubling.
3. The path in `~/.claude/adlc/plugin-root`, which the plugin's SessionStart hook writes. It covers plugin skill text that Claude Code did not substitute, such as a subagent reading a SKILL.md through the Read tool.
4. `$HOME/.claude/skills` as a literal default. On a machine with neither install, the partial source that follows then fails loudly and names the path.

**Never write `${CLAUDE_PLUGIN_ROOT:-…}`**, and never the unbraced `$CLAUDE_PLUGIN_ROOT`, in a fence. A hook command in `templates/hooks.yml` is the one place that does the opposite: it must be unbraced, because Claude Code never runs a project hook holding the braced token (REQ-660 ADR-8), and `unguarded-source` enforces it. Only the braced, unadorned token is substituted (verified on Claude Code 2.1.258, REQ-669 `verification.md` row 1). A default form reaches the shell as written, so on the plugin route it would silently read `~/.claude/skills`. The line is POSIX: no `[[`, no `local`, no `case` inside `$( )`. `${CLAUDE_PLUGIN_ROOT}` without `:-` is an error only under `set -u`, which no fence sets. The line is per fence. Fenced blocks share no shell state, and the `export` does not carry the value across them either, so every fence that reads `$ADLC_TOOLKIT_ROOT` carries its own copy, and a fence that does not read it carries none. Partials never carry it: a partial that needs a toolkit file reads `"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/…"` (REQ-669 ADR-2), and that default-expansion spelling is for partials only. The `tools/lint-skills` `toolkit-root-line` check pins the bytes: a read with no root line above it in the same fence is a finding, and so is any other line that assigns `ADLC_TOOLKIT_ROOT`. `partials/tests/toolkit-root.test.sh` runs the line quoted above, taken from this file, under bash, zsh, `/bin/sh` and dash.

**Source a partial with the guarded two-level form.** There is exactly one canonical spelling, on a single line, after the fence's root line:

```sh
if [ -f .adlc/partials/<name>.sh ]; then . .adlc/partials/<name>.sh; else . "$ADLC_TOOLKIT_ROOT/partials/<name>.sh"; fi
```

The fallback operand is double-quoted because ToolkitRoot is a path, and `$HOME` can contain a space. **Retired (REQ-669 TASK-124):** the REQ-610 spelling, whose `else` arm is `. ~/.claude/skills/partials/<name>.sh`, was accepted by `unguarded-source` while TASK-122 to TASK-124 rewrote the corpus. TASK-124 removed that acceptance, so the old operand is now a finding.

`.` is a POSIX **special built-in**, and POSIX requires a non-interactive shell to *exit* when a special built-in fails (XCU 2.8.1, "Consequences of Shell Errors"). So under `dash` and under `bash` in posix mode — which is what macOS ships as `/bin/sh` — dot-sourcing an absent repo-local copy kills the whole block before any fallback can run; under bash and zsh it is merely a non-zero status, which is why this stayed latent (REQ-610, observed 2026-09-01). The repo-local copy is therefore proven to exist with `[ -f ]` before it is sourced, and never guessed at with `||`. Two forms that look like fixes and are not: **`command .`** — still exits under macOS `/bin/sh` (it only rescues `dash`); and **`[ -f A ] && . A || . B`** — when `A` exists but its last command returns non-zero, the `||` arm fires as well and the canonical copy is sourced *on top of* the repo-local one, inverting the repo-local-first precedence LESSON-441 depends on. The retired shape, `. <local> 2>/dev/null || . <canonical>`, is rejected by the `tools/lint-skills` `unguarded-source` check in fences and in prose alike; its `2>/dev/null` is also what made the original failure silent, so the guarded form suppresses **no** stderr — a missing canonical copy or a syntax error in a vendored one must reach stderr naming the path. `[ -f ]` rather than `[ -r ]`: an existing-but-unreadable vendored copy then fails loudly at the `.` instead of silently falling through and hiding a permissions problem. The executable-partial `!`-macro form (`sh <local> || sh <canonical>`) needs no guard — `sh <file>` is an ordinary command, so it fails with exit 127, never fatally. The **final canonical arm is deliberately unguarded**: its absence means the toolkit is not installed, which is unrecoverable, so it fails loudly (fatal under `sh`, an error line under bash/zsh) rather than being tested and skipped. That arm trusts `$HOME` — it dot-sources whatever `$ADLC_TOOLKIT_ROOT/partials/` resolves to, and the root line resolves that through `$HOME` (its symlink, pointer-file and default arms) — so the toolkit is not safe to invoke with an attacker-controlled `HOME` (a CI runner that points `HOME` at the workspace, `sudo` without `-H`); that was already true under bash/zsh and is now true under `sh` as well, because the arm is now reachable there. One `set -e` caveat: the retired `. A || . B` sat in an `||` list and was exempt from `errexit`, whereas `. A` inside an `if` branch is not — so under a `set -e` fence a vendored partial whose last top-level statement returns non-zero would abort the block. No fence sets `-e` today and every partial ends on a zero-status statement; if you add `set -e` to a fence, keep it that way.

**Machine-state paths come from `ADLC_HOME` (REQ-654).** Code that needs the id counters, a lock dir, the reservations ledger, the machine config or the delegate venv derives the path from `ADLC_HOME` (default `~/.claude`): in a partial through `partials/adlc-home.sh` (`adlc_home`, `adlc_machine_config`), in Python through `tools/adlc/adlc_home.py`, never by writing `~/.claude` or `$HOME/.claude`. **Fences keep the literal while code reads the variable because the literals a fence carries — the root line's `$HOME/.claude/skills` and `$HOME/.claude/adlc/plugin-root` — are compatibility aliases that every vendored partial and every older skill text also resolves through, so `install.sh` keeps them valid on every machine, whereas machine state is the toolkit's own and has exactly one resolver.** Do not "fix" either into the other. A line in `tools/`, `scripts/`, `install.sh` or a partial that must keep a home-directory `.claude` literal, because it names a path Claude Code owns, one of those two aliases, or the default itself, says so with `# adlc-home: claude-code`, `# adlc-home: alias` or `# adlc-home: default` on that line; `tools/lint-skills`' `adlc-home` check fails on any other.

## Harness adapters are data (REQ-657)

Adding a harness is: one adapter file `harness/<name>.yml` (the name `adlc harness detect` knows), golden renders under `harness/<name>/rendered/` that `render-parity` holds equal to the renderer, an `accepted_fidelity` map that accepts in writing every allowlist entry the harness cannot express (`allowlist-fidelity` fails on any it does not), and, only when the harness reads a file format no shipped renderer writes, one format renderer registered in `tools/adlc/harness_render.FORMATS`. It is never a branch on the harness name: no code in `tools/adlc` compares a harness name, and a capability, path, event or doctor row a harness needs is a field of its adapter. A field every adapter must carry comes with a `schema_version` bump that adds it to `harness/claude.yml` and its goldens in the same change. Permission sources are argv token lists, never shell text: the renderer spells fences and `git -C` per harness, and the allowlist is described as a convenience for the routine tier, never as what stops a deny-tier command (Rule B). A harness that needs an optional field names `schema_version: 2` (REQ-656); a harness with a user-facing section in the root `README.md` adds its name to `LOSS_TABLE_HARNESSES`, so `harness-loss-table` holds that section to the adapter. Check a vendor's documented file layout and hook output contract before writing a format renderer: two of the plan's surveyed formats were not what the adapter would have needed (LESSON-716, LESSON-755). `adlc harness render --write-goldens` rewrites every golden after a change to `templates/permissions.yml`, `templates/hooks.yml` or an adapter.

**Why the deny tier renders as `prompt` on Codex (REQ-655).** Its committed render says `decision="prompt"`, so a person in a session can still approve a one-way move, and `decision="forbidden"` belongs to the exec engine's render, in a file of its own, where no one is there to approve anything (REQ-662). Rule B is the reason both are safe to say: the allowlist is a convenience for the routine tier and neither decision is the gate. A deny-tier `prompt` rule matches plain argv only, and what stops the wrapped spelling is the sandbox. An omitted `allow` stays omitted: at schema 3 a restoration needs a passing probe row, the by-hand `strictest-wins` result, and a deny whose every added token is a fixed word, because `git push origin --force` matches `["git", "push"]` and no token prefix can tell it apart.

## Agent dispatch patterns

- **Parallel review**: dispatch 5–6 review agents in a single message (`correctness-reviewer`, `quality-reviewer`, `architecture-reviewer`, `test-auditor`, `security-auditor`, `reflector`). Read-only mandate: every agent must be told "Report findings only. Do not apply fixes."
- **Parallel implementation**: `task-implementer` agents dispatched one per independent task. Group into dependency tiers.
- **Subagent mode**: when a skill runs inside a subagent (e.g., via `/sprint`'s `pipeline-runner`), do NOT dispatch further subagents. Execute sequentially in-context instead, reading each checklist from `.adlc/agents/<name>.md` (the dispatch paragraph's inline arm).
- **Dispatch on every harness (REQ-666 BR-3, BR-4; REQ-669 ADR-6, BR-9)**: a harness may have no agent tool at all, a Claude Code subagent cannot dispatch further, and the two install routes offer the toolkit's agents under different names (bare on the symlink install, `adlc:<name>` on the plugin install, REQ-669 `verification.md` row 7), where a name the session does not offer silently becomes a generic `general-purpose` agent without the checklist (row 7, evidence E3). So every step that dispatches agents carries the canonical **dispatch paragraph** below, copied whole, and never relies on a dispatch error to trigger the fallback. Its inline arm reads the checklist from the project's vendored copy, `.adlc/agents/<name>.md` (`/init` writes it, REQ-666 BR-8), because a harness whose reads are jailed to the session root, and a Claude Code subagent in a worktree, cannot reach the install. A step that cannot run without subagents (`/sprint`) carries the **explicit-stop block** instead. The text between each pair of markers is the only copy: `tools/lint-skills`' `dispatch-has-fallback` check reads both blocks from here and requires one of them, whitespace-normalized, in every `##`/`###` step of a `SKILL.md`, `proceed/phase*.md` or `partials/*.md` that names a dispatched toolkit agent; a step that dispatches any other agent (a harness built-in such as Explore, or "launch 3 agents using the Agent tool") owes at least the paragraph's leading clause, "If this harness can run subagents", with an inline arm that fits it. Edit the blocks here and nowhere else, then copy them into each step the check names.

<!-- dispatch-fallback-sentence -->
If this harness can run subagents, dispatch these agents in parallel; if it cannot, or you are a subagent, run each checklist inline from `.adlc/agents/<name>.md`. Agent names are bare on the symlink install and `adlc:`-prefixed on the plugin install (`adlc:<name>`): before dispatching, check which form the Agent tool lists and use that one, and do not wait for an error, because a name it does not list can silently run a generic agent without the checklist; if neither form is listed, say which agent is missing and run its checklist inline. When `.adlc/agents/` is absent, say that `/init` (`/adlc:init` on the plugin install) vendors it, then read `$ADLC_TOOLKIT_ROOT/agents/<name>.md` (the toolkit root is the parent of this skill's base directory) where your file tool can reach it; never improvise a checklist. An inline run of a review or audit agent is read-only: report findings, apply no fixes, and run no test runner, build tool, package manager or interpreter.
<!-- /dispatch-fallback-sentence -->

<!-- dispatch-requires-subagents -->
This step requires a harness that can run subagents: if this harness cannot, or you are a subagent, stop here and say so, and run each REQ with `/proceed` instead. Agent names are bare on the symlink install and `adlc:`-prefixed on the plugin install (`adlc:<name>`): before dispatching, check which form the Agent tool lists and use that one, and do not wait for an error, because a name it does not list can silently run a generic agent without the checklist; if neither form is listed, say which agent is missing and stop.
<!-- /dispatch-requires-subagents -->

The workflow engine names its agents in code instead, so it cannot carry the sentence: `/sprint` passes `args.agentNamespace` (`adlc:` on the plugin route, `""` otherwise) and every `agentType` goes through the pure `agentTypeFor(name, ns)` helper (`workflows/README.md`).

## Verification obligations

A task file may carry an optional `## Verification` section mapping the rules it
discharges to the artifacts that prove them (REQ-595). `/architect` Step 4.5
emits it; `/validate`'s obligation-coverage gate reads it. The shape is a
four-column table — `rule | kind | artifact | benign_path` — defined in
`templates/task-template.md`.

- **Rule addressing**: `BR-<n>` uses the number written in the REQ. `AC-<n>` uses
  the **1-based ordinal** within the REQ's `## Acceptance Criteria` list, since
  the requirement template does not print AC numbers.
- **`kind` is a closed two-value enum**: `test-case` | `structural-check`.
  `dogfood` is deliberately excluded — it cannot report an executed-work count.
  Resolution is **surface first**: a task whose files are all `*.md` maps to
  `structural-check` (this repo's skills have no test runner — their real
  verification is a structural check in `tools/lint-skills`); any other surface
  maps to `test-case`, with the artifact shape read from that repo's
  `.adlc/config.yml` `stack:` when present. No framework name is ever hardcoded
  in a skill.
- **`benign_path: yes`** marks an obligation that includes a must-not-fire case.
  Any rule describing detection, refusal, or a halt needs one — a detector
  validated only against adversarial inputs ships broken and passes its own suite.
- **The section is optional.** A task file without it stays valid; the coverage
  gate reports the gap and does not block.

**Gate posture (epoch 1)**: coverage and benign-path findings are **advisory** —
surfaced as warnings, non-blocking, so the REQs written before obligations
existed do not all fail on day one. The vacuous-run check is **blocking**: a
verification run that exits 0 having scanned zero files or executed zero cases is
a failure, not a pass. Promotion of the advisory checks to blocking is a separate
follow-up REQ, taken once the corpus carries obligations.

## Pipeline state

Skills that span multiple phases (`/proceed`) write a `pipeline-state.json` next to the REQ spec. This lets a long-running pipeline resume from interruption without replaying phases. Every phase update writes the state file atomically.

New state keys are **additive and optional**, and each one defines what its absence means, so an older state file parses and runs unchanged (`conflictsResolved`: none resolved; `closeOut`: not recorded). The `lane` object (REQ-652) follows the same rule: it is written only when the spec carries a `lane` key, and a state file without it is a full-lane run. The spec frontmatter, not the state file, is the authority on a REQ's lane.

A key whose value is a fact for a later reader is written by code, at the moment the fact occurs, never by hand at close-out (LESSON-626, LESSON-012). REQ-648's `harness`, `validateAttempts`, `verify` and `lessonsWritten` are written by `tools/delegate/emit-run-outcome.sh record-*` into the primary-path copy, and absent means `-` or `0` in the run-outcome line built from them.

## Commits and branches

- Branch naming: `feat/REQ-xxx-short-description` for features, `fix/bug-xxx-short-description` for bugs
- Commit message format: `<type>(<scope>): <description> [TASK-xxx]` — types are `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
- The TASK-xxx (or REQ-xxx) trailer is required for work tracked through the pipeline
- A `Lessons: LESSON-xxx, LESSON-yyy` trailer acknowledges each supplied lesson the change applies (REQ-647). `/proceed` Phase 5 Step B reads these trailers, and the task's `## Verification` block, and lists applicable lessons nobody acknowledged as Info findings. A mention only in an agent's report is not seen.
- Co-author trailer is added by Claude Code automatically when committing on behalf of the user

## What NOT to do

- **Don't create new skill directories casually**: each new skill is a commitment to maintain. Prefer extending an existing skill unless the new responsibility is genuinely orthogonal.
- **Don't bypass ethos**: the ETHOS principles (especially #4 Verify, Don't Trust and #5 Process Is Not Optional) exist because shortcuts silently fail. If you're tempted to skip a validation gate or add a `--no-verify` flag, surface the tension to the user instead.
- **Don't duplicate context loading logic**: if the same bash macro appears in three or more skills, extract it to `partials/<name>.sh` and source it from each call site (see the Ethos injection pattern above).
- **Don't hardcode project-specific paths**: skills must work for any consumer project, not just atelier-fashion.
- **Don't edit `templates/` without considering downstream**: consumer projects that ran `/init` got a copy of the templates. Template changes propagate via `/template-drift` detection, not auto-update.

## Testing changes

Because this is a symlink-install, there is no staging layer. To validate a skill change:

1. Commit the change in this repo
2. Open a Claude Code session in a consumer project (atelier-fashion is the primary test bed)
3. Invoke the changed skill on a real or synthetic REQ
4. Verify the artifacts it produces match the intended behavior
5. Revert if it breaks

The toolkit's own `/proceed REQ-xxx` pipeline can also exercise changes end-to-end, as in REQ-258.

# Conventions — ADLC Toolkit

## Code is markdown, not code

Every skill and agent is a markdown file. No TypeScript, no Python, no package.json. Claude Code interprets the markdown at invocation time. This matters:

- **No build step**: edits take effect immediately via the symlink install
- **No test runner**: "tests" are dogfooding — invoke the skill on a real REQ and see if it produces the expected artifacts
- **Linting is minimal**: markdown formatting, frontmatter validity, and bash syntax in `!`...`` macros. Nothing else.

**Exception — `tools/`:** the `tools/` directory may contain real executable code (e.g. `tools/delegate/`, a set of Python delegation CLIs with its own `install.sh`). It is exempt from the markdown-only rule and from the symlink-install model — those tools are installed by running their `install.sh`, not via the skills symlink. Each `tools/<name>/` subdirectory carries its own README.

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

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`
```

The partial itself emits the canonical fallback chain (consumer-project ETHOS.md first, then toolkit-root, then graceful "No ethos found" message). The two-level fallback at the call site (project `partials/` first, then global `~/.claude/skills/partials/`) ensures the macro still works in consumer projects that haven't re-run `/init` after the toolkit shipped the partial. Never hardcode the ethos body inside a skill — always source the partial.

## Delegation pattern (provider-agnostic)

Skills that delegate bulk reads or drafting to the configured delegate (`adlc-read` /
`adlc-write`) MUST source the shared gate predicate rather than inlining
`command -v adlc-read >/dev/null 2>&1 && …`. The canonical predicate lives in
`partials/delegate-gate.sh` and defines `adlc_delegate_gate_check()` with a 0/1/2 contract
(REQ-522 retired the legacy `kimi-gate.sh` back-compat alias):

```sh
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . ~/.claude/skills/partials/delegate-gate.sh; fi
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
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . ~/.claude/skills/partials/delegate-gate.sh; fi
case "$ADLC_READ_BIN" in /*) ;; *) echo "/<skill>: ADLC_READ_BIN is not an absolute path ('$ADLC_READ_BIN') — refusing to hand over the corpus (re-run install.sh --with-delegation, and /init to refresh the vendored gate)" >&2; exit 1 ;; esac
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
in `~/.claude/adlc/config.yml`, or an already-set legacy `KIMI_API_KEY`/`MOONSHOT_API_KEY`
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
if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . ~/.claude/skills/partials/forge.sh; fi
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

Skills load context via `!bash` macros under a `## Context` section. Use the same fallback chain: prefer consumer-project `.adlc/...`, fall back to `~/.claude/skills/...`. Example:

```markdown
- Conventions: !`cat .adlc/context/conventions.md 2>/dev/null || echo "No conventions found"`
```

Never hardcode paths; always allow the skill to degrade gracefully when a file is absent.

For shared multi-line snippets that would otherwise duplicate across many SKILL.md files, extract a POSIX shell partial under `partials/<name>.sh` and source it from each call site (see "Ethos injection pattern" above and the architecture.md "Partials" subsection). This keeps each SKILL.md focused on its own instructions and ensures updates land everywhere consistently.

## Prerequisites block

Every skill that depends on the `.adlc/` scaffold must have a `## Prerequisites` section that stops with a clear "run `/init` first" message if required files are missing. Do not silently produce broken output when context is absent.

## Bash in skills

- Keep bash minimal — prefer Claude's own tool calls (Read, Grep, Glob, Edit, Write) over shell
- Bash is fine for deterministic operations: counter increments, directory creation, git commands, file globbing
- **POSIX-only**: no GNU-specific flags. Use `grep -oE` (not `-oP`), use `mkdir` locks (not `flock`), use `sed 's/old/new/'` not `-i ''` on macOS directly — prefer `perl` for in-place edits or write a temp file
- Quote file paths with spaces: `"$path"`
- Avoid `cd` — prefer absolute paths so commands work from any working directory
- **Never write a destructive command whose safety depends on a variable being non-empty.** `rm -rf "$(dirname "$VAR")"` becomes `rm -rf .` the moment `$VAR` is empty, and a guard sitting a few lines above it in a SKILL.md is one careless edit from being bypassed. Put the guards in a partial, next to the deletion, where they cannot drift from it — check the path is non-empty, that it lives under a real temp root, and that its basename is one the toolkit itself created. `partials/intake.sh`'s `adlc_intake_cleanup` is the reference (REQ-594).

**Fenced blocks do not share shell state across steps.** Each ```sh fenced block in a SKILL.md may be an independent shell invocation — shell functions and non-exported variables defined in one fenced block are NOT visible in another (the Claude Code Bash-tool contract: "the working directory persists between commands, but shell state does not"). Therefore a shared shell **function** MUST be sourced from a `partials/*.sh` at *each* call site, in the **same fenced block as the invocation**, and MUST NEVER be defined in one fenced block and invoked from another (the silent-`command not found` telemetry-loss class — REQ-436, REQ-424). The canonical pattern is `partials/delegate-gate.sh` and `partials/emit-step-telemetry.sh`: a function-exporting partial sourced with the guarded two-level spelling (below) immediately before it is called. This is enforced structurally, not by prose/honor-system (LESSON-012): the `tools/lint-skills` `cross-fence-fn` check flags any function defined in one fence but invoked from a different fenced block in the same SKILL.md.

**Source a partial with the guarded two-level form.** There is exactly one canonical spelling, on a single line:

```sh
if [ -f .adlc/partials/<name>.sh ]; then . .adlc/partials/<name>.sh; else . ~/.claude/skills/partials/<name>.sh; fi
```

`.` is a POSIX **special built-in**, and POSIX requires a non-interactive shell to *exit* when a special built-in fails (XCU 2.8.1, "Consequences of Shell Errors"). So under `dash` and under `bash` in posix mode — which is what macOS ships as `/bin/sh` — dot-sourcing an absent repo-local copy kills the whole block before any fallback can run; under bash and zsh it is merely a non-zero status, which is why this stayed latent (REQ-610, observed 2026-09-01). The repo-local copy is therefore proven to exist with `[ -f ]` before it is sourced, and never guessed at with `||`. Two forms that look like fixes and are not: **`command .`** — still exits under macOS `/bin/sh` (it only rescues `dash`); and **`[ -f A ] && . A || . B`** — when `A` exists but its last command returns non-zero, the `||` arm fires as well and the canonical copy is sourced *on top of* the repo-local one, inverting the repo-local-first precedence LESSON-441 depends on. The retired shape, `. <local> 2>/dev/null || . <canonical>`, is rejected by the `tools/lint-skills` `unguarded-source` check in fences and in prose alike; its `2>/dev/null` is also what made the original failure silent, so the guarded form suppresses **no** stderr — a missing canonical copy or a syntax error in a vendored one must reach stderr naming the path. `[ -f ]` rather than `[ -r ]`: an existing-but-unreadable vendored copy then fails loudly at the `.` instead of silently falling through and hiding a permissions problem. The executable-partial `!`-macro form (`sh <local> || sh <canonical>`) needs no guard — `sh <file>` is an ordinary command, so it fails with exit 127, never fatally. The **final canonical arm is deliberately unguarded**: its absence means the toolkit is not installed, which is unrecoverable, so it fails loudly (fatal under `sh`, an error line under bash/zsh) rather than being tested and skipped. That arm trusts `$HOME` — it dot-sources whatever `~/.claude/skills/partials/` resolves to — so the toolkit is not safe to invoke with an attacker-controlled `HOME` (a CI runner that points `HOME` at the workspace, `sudo` without `-H`); that was already true under bash/zsh and is now true under `sh` as well, because the arm is now reachable there. One `set -e` caveat: the retired `. A || . B` sat in an `||` list and was exempt from `errexit`, whereas `. A` inside an `if` branch is not — so under a `set -e` fence a vendored partial whose last top-level statement returns non-zero would abort the block. No fence sets `-e` today and every partial ends on a zero-status statement; if you add `set -e` to a fence, keep it that way.

## Agent dispatch patterns

- **Parallel review**: dispatch 5–6 review agents in a single message (`correctness-reviewer`, `quality-reviewer`, `architecture-reviewer`, `test-auditor`, `security-auditor`, `reflector`). Read-only mandate: every agent must be told "Report findings only. Do not apply fixes."
- **Parallel implementation**: `task-implementer` agents dispatched one per independent task. Group into dependency tiers.
- **Subagent mode**: when a skill runs inside a subagent (e.g., via `/sprint`'s `pipeline-runner`), do NOT dispatch further subagents. Execute sequentially in-context instead.

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

## Commits and branches

- Branch naming: `feat/REQ-xxx-short-description` for features, `fix/bug-xxx-short-description` for bugs
- Commit message format: `<type>(<scope>): <description> [TASK-xxx]` — types are `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
- The TASK-xxx (or REQ-xxx) trailer is required for work tracked through the pipeline
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

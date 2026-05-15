# Conventions — ADLC Toolkit

## Code is markdown, not code

Every skill and agent is a markdown file. No TypeScript, no Python, no package.json. Claude Code interprets the markdown at invocation time. This matters:

- **No build step**: edits take effect immediately via the symlink install
- **No test runner**: "tests" are dogfooding — invoke the skill on a real REQ and see if it produces the expected artifacts
- **Linting is minimal**: markdown formatting, frontmatter validity, and bash syntax in `!`...`` macros. Nothing else.

**Exception — `tools/`:** the `tools/` directory may contain real executable code (e.g. `tools/kimi/`, a set of Python delegation CLIs with its own `install.sh`). It is exempt from the markdown-only rule and from the symlink-install model — those tools are installed by running their `install.sh`, not via the skills symlink. Each `tools/<name>/` subdirectory carries its own README.

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

## Agent dispatch patterns

- **Parallel review**: dispatch 5–6 review agents in a single message (`correctness-reviewer`, `quality-reviewer`, `architecture-reviewer`, `test-auditor`, `security-auditor`, `reflector`). Read-only mandate: every agent must be told "Report findings only. Do not apply fixes."
- **Parallel implementation**: `task-implementer` agents dispatched one per independent task. Group into dependency tiers.
- **Subagent mode**: when a skill runs inside a subagent (e.g., via `/sprint`'s `pipeline-runner`), do NOT dispatch further subagents. Execute sequentially in-context instead.

## Pipeline state

Skills that span multiple phases (`/proceed`) write a `pipeline-state.json` next to the REQ spec. This lets a long-running pipeline resume from interruption without replaying phases. Every phase update writes the state file atomically.

## Commits and branches

- Branch naming: `feat/REQ-xxx-short-description` for features, `fix/bug-xxx-short-description` for bugs
- Commit message format: `<type>(<scope>): <description> [TASK-xxx]` — types are `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
- The TASK-xxx (or REQ-xxx) trailer is required for work tracked through the pipeline
- Co-author trailer is added by Claude Code automatically when committing on behalf of the user

## What NOT to do

- **Don't create new skill directories casually**: each new skill is a commitment to maintain. Prefer extending an existing skill unless the new responsibility is genuinely orthogonal.
- **Don't bypass ethos**: the five principles (especially #4 Verify, Don't Trust and #5 Process Is Not Optional) exist because shortcuts silently fail. If you're tempted to skip a validation gate or add a `--no-verify` flag, surface the tension to the user instead.
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

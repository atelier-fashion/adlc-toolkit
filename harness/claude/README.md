# harness/claude — the Claude Code adapter (REQ-657)

`harness/claude.yml` is data. `tools/adlc/harness_adapter.py` validates it (an
unknown key, a missing canonical hook event or a literal home path is a loud error),
and `tools/adlc/harness_render.py` renders the toolkit's canonical sources through
it. Copilot CLI and Cursor (REQ-656) ship beside it, with their own READMEs here; Codex
(REQ-655) and Gemini CLI (REQ-658) add theirs as data files against the same schema.

| Surface | Where | How |
|---|---|---|
| permissions | `.claude/settings.json` (project) | rendered from `templates/permissions.yml`: the routine tier as `allow`, the deny tier as `ask` (`deny_tier_render: {project: confirm}`) |
| hooks | `.claude/settings.json` (project) | rendered from `templates/hooks.yml`: `SessionStart` (`startup\|resume\|clear`) runs `ethos-inject` and `session-record`; `SessionStart` with the `compact` matcher re-runs `ethos-inject`. Copilot CLI and Cursor read this file as-is (`read_by`), so the commands carry no `--harness` argument |
| instructions | `CLAUDE.md` (project) | `@AGENTS.md` plus the Claude-specific lines; an existing file only gains the import line |
| agents, skills | `$HOME/.claude/agents`, `$HOME/.claude/skills` | `mounted`: install.sh's symlinks serve the canonical files, so `adlc agents render --harness claude` is the in-place `model:` stamp |

`rendered/settings.json` is the golden render. `adlc harness render --check` and the
`render-parity` lint hold it, and the toolkit's own `.claude/settings.json`, equal to
what the renderer writes; REQ-655 BR-13 and REQ-666 BR-15 point at it in place of
the deleted settings template.

What it declares, and why:

- **`allowlist_granularity: prefix`.** `Bash(<prefix>:*)` matches the command text by
  word-boundary prefix. `deny_under_allow.prefix` is `grandfathered`: the `ask` of
  `git push --force` under the allow `git push:*` is today's precedence, kept by
  Rule A; it is not a probe result. `git.push.force`'s `residual:exact-deny` (the
  allow matches `git push --force origin feature`) is accepted for the same reason.
- **`fence.partial-source`** is `inexpressible` at project scope: a committed
  opening-token prefix would be a new pre-approval (Rule A). At `exec` scope it is
  `fence_broad_spelling`, reported `widened`.
- **Trust** is `user-config-entry`: Claude Code 2.1.258 ignores a project's
  `permissions.allow` in a workspace that has not been trusted (ASSUME-010,
  REQ-664's probe). Declared, not exercised; nothing in the framework writes it.
- **`subagent_start_hook: no`.** The installed binary's hook schema has
  `SubagentStart`, but it takes context only as JSON `additionalContext`, and a live
  check was not possible; see REQ-657's Deferred section.

<!-- declared-residuals -->
**Declared residuals (REQ-657 BR-18).** Allowlist and prefix-deny matching cannot be made a gate, and the adapter framework does not pretend it can. `allowlist-fidelity` closes spellings, not this list:

- Allowlist matching is spelling-level. The lint evaluates a closed set of spellings; a deny-tier command reached in any other spelling is not seen.
- Allows that execute their arguments (`find -exec`, `awk`, `sed e`, `npx`, `npm run` / `npm exec`, `git rebase --exec`, `git fetch --upload-pack`) and `gh api` can reach a deny-tier command in a spelling the deny does not match.
- Semantic equivalents of a deny-tier command (`git restore`, `git checkout -f`, `git worktree remove --force`, `gcloud` deploys, `npm publish`) are outside the deny tier.
- This is the same exposure Claude's template has today (Rule A grandfathers it); no adapter makes it worse, and none claims to close it.
- The allowlist is never the gate (Rule B). The orchestrator's structural gates (REQ-659) are.
<!-- /declared-residuals -->

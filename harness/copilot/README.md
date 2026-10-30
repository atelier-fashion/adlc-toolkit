# harness/copilot — the GitHub Copilot CLI adapter (REQ-656)

`harness/copilot.yml` is data, validated by `tools/adlc/harness_adapter.py` and rendered
by `tools/adlc/harness_render.py`. The install steps, the "What is lost" table and the
declared residuals are in the root `README.md`, where `tools/lint-skills`'
`harness-loss-table` holds them to this adapter.

| Surface | Where | How |
|---|---|---|
| agents | `$HOME/.copilot/agents/<name>.agent.md` | rendered copies, user-level only: `adlc harness install --harness copilot` or `adlc agents render --harness copilot`. A project render never writes them |
| permissions | a printed line | no committed form exists. `/init --harness copilot` prints one `copilot --allow-tool … --deny-tool …` line to paste into a shell alias |
| hooks | `.github/hooks/adlc.json` (project) | `sessionStart` carries `ethos-inject` and `session-record`; `subagentStart` carries `ethos-inject` |
| instructions | `AGENTS.md` (project) | the one instruction file |
| skills | `$HOME/.agents/skills` | the skills-only view install.sh mounts |

`rendered/` holds the goldens: `adlc.json`, `printed-permissions.txt` and `agents.json`,
each agent's file name and `tools:` line. `adlc harness render --check` holds them equal
to the renderer; `adlc harness render --write-goldens` rewrites them.

What it declares, and why:

- **Everything here is the vendor docs as read on 2026-10-30, not a run.** No `copilot`
  binary was available, and the dogfood (REQ-656 BR-13) is owed. What a probe would decide
  stays unverified: all four `deny_under_allow` shapes, and every `tier_map` entry, so no
  agent carries `model:`.
- **`allowlist_granularity: token-prefix`** is the plan's "subcommand prefix". REQ-657's
  `subcommand` caps a spelling at two tokens, which would turn `gh pr view` into `gh pr`
  and every deny into two tokens.
- **`deny_tier_render: {user: deny}`.** The printed line is the user-scope render, so it
  carries one hard `--deny-tool` per argv prefix of the deny tier, always spelled `:*`.
- **`hook_output: ethos-inject: json:additionalContext`.** Copilot takes hook context only
  as JSON and ignores plain stdout.
- **`subagent_start_hook: "no"`** although `subagentStart` is rendered: nothing yet shows
  it reaching a subagent, so the ETHOS-first line stays in every rendered agent.

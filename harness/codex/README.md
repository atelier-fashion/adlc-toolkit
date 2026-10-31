# harness/codex — the Codex CLI adapter (REQ-655)

`harness/codex.yml` is data, validated by `tools/adlc/harness_adapter.py` and rendered by
`tools/adlc/harness_render.py`. The install steps, the "What is lost" table and the
declared residuals are in the root `README.md`, where `tools/lint-skills`'
`harness-loss-table` holds them to this adapter. The evidence is in the REQ-655 spec's
Assumptions and in `.adlc/research/harness-probes/codex.json`.

| Surface | Where | How |
|---|---|---|
| agents | `$HOME/.codex/agents/<name>.toml` | rendered TOML roles, user-level only: `adlc harness install --harness codex` or `adlc agents render --harness codex`. `.codex/agents/` is never written |
| permissions | `.codex/rules/adlc.rules` (project), `$HOME/.codex/rules/adlc.rules` (user) | `allow` for the routine tier, `prompt` for the deny tier; the user file holds the three delegation rules and is written only with delegation installed |
| hooks | `.codex/hooks.json` (project) | `SessionStart` carries `ethos-inject` and `session-record`, `SubagentStart` carries `ethos-inject`. Inert until a person reviews them |
| config | `.codex/config.toml` (project), `$HOME/.codex/config.toml` (user) | merged; the project file owns `sandbox_mode` and `approval_policy`, and the user file's one owned key is written only by `--writable-root` |
| instructions | `AGENTS.md`, `$HOME/.codex/AGENTS.md` | the project file is the canonical one; the user file takes the delegation routing block |
| skills | `$HOME/.agents/skills` | mounted by `install.sh` (REQ-654); nothing here |

`rendered/` holds the goldens `render-parity` compares: `adlc.rules`, `hooks.json`,
`config.toml`, and `agents.json`, which records which agents carry the restraint sentence
in place of a `tools:` line. `adlc harness render --write-goldens` rewrites them.

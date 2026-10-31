# harness/antigravity — the Antigravity CLI adapter (REQ-658)

`harness/antigravity.yml` is data, validated by `tools/adlc/harness_adapter.py` and rendered
by `tools/adlc/harness_render.py`. The install steps, the "What is lost" table and the
declared residuals are in the root `README.md`, where `tools/lint-skills`'
`harness-loss-table` holds them to this adapter. The evidence is
`.adlc/research/antigravity-compatibility.md`, and
`.adlc/research/harness-probes/antigravity.json` is the probe result.

| Surface | Where | How |
|---|---|---|
| agents | `$HOME/.gemini/config/agents/<name>.md` | rendered copies, user-level only: `adlc harness install --harness antigravity`. A file without the generated line is the user's, and is refused |
| skills | `$HOME/.gemini/config/skills.json` | one file naming the skills view, or ToolkitRoot when no view exists. An existing file is kept, and the render says what to add |
| hooks | `.agents/hooks.json` (project) | one named hook, `adlc`, with `ethos-inject` and `session-record` under `SessionStart` |
| instructions | `AGENTS.md` | the canonical file, read as an always-on rule |
| permissions | none | printed: `adlc harness render --harness antigravity --surface permissions`. No file in a repository supplies them |

`rendered/` holds the goldens `render-parity` compares: `hooks.json`, `skills.json`,
`printed-permissions.txt` and `agents.json`, which records each agent's `tools:` line.
`adlc harness render --write-goldens` rewrites them.

# harness/cursor — the Cursor adapter (REQ-656)

`harness/cursor.yml` is data, validated by `tools/adlc/harness_adapter.py` and rendered
by `tools/adlc/harness_render.py`. The install steps, the "What is lost" table and the
declared residuals are in the root `README.md`, where `tools/lint-skills`'
`harness-loss-table` holds them to this adapter.

| Surface | Where | How |
|---|---|---|
| permissions | `.cursor/cli.json`, `.cursor/permissions.json` (project) | the agent CLI's file carries `permissions.allow` and `permissions.deny`; the IDE's file has a different schema and carries the same allow set as `terminalAllowlist`, with no deny |
| agents, hooks | `via:claude` | Cursor reads Claude Code's agents and `.claude/settings.json` hooks itself, so nothing is rendered. Run `/init --harness claude,cursor`: `/init --harness cursor` alone leaves the hooks surface unserved |
| instructions | `AGENTS.md` (project) | the one instruction file |
| skills | `$HOME/.agents/skills` | the skills-only view; Cursor also reads the clone root, so every skill is discovered twice |

`rendered/` holds the goldens, `cli.json` and `permissions.json`. `adlc harness render
--check` holds them equal to the renderer; `adlc harness render --write-goldens` rewrites
them.

What it declares, and why:

- **Everything here is the vendor docs as read on 2026-10-30, not a run.** No `agent`
  binary was available, and the dogfood (REQ-656 BR-13) is owed. All four
  `deny_under_allow` shapes read `unverified`.
- **`deny_tier_render: {project: deny}`**, a stated departure from `claude`'s `confirm`:
  `cli.json` is the only place a deny can live, and `agent -p` has no confirm form. A
  person in a Cursor session cannot approve a denied one-way move; they run it from their
  own shell.
- **No `Shell(git)` and no `Shell(gh)`.** Command-base matching cannot put `git push
  --force` behind a deny without denying all of git, and whether a finer deny beats a base
  allow is unverified (OQ-8, OQ-9). So those routine entries are omitted and prompt, and
  the shared-base deny-tier entries are `deny-unsupported`.
- **`gcloud.read` is withheld.** `Shell(gcloud)` would pre-approve `gcloud run deploy`.
- **`subagent_start_hook: "no"`.** Cursor's reader of Claude-format hooks does not map
  `SubagentStart`.

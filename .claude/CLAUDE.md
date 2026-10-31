@../AGENTS.md

## Claude Code

- This file lives here, not at the repo root, because the repo is also the plugin:
  a root `CLAUDE.md` fails `claude plugin validate .claude-plugin/plugin.json
  --strict`. `adlc harness render --harness claude` writes one when none exists, so
  delete what it writes here; the `manifest-parity` lint refuses it.
- `.claude/settings.json` is rendered by `adlc harness render --harness claude`
  from the ADLC toolkit's `templates/permissions.yml` and `templates/hooks.yml`.
  Commit it: it is shared by the team. Personal overrides go in
  `.claude/settings.local.json`.
- Claude Code applies the committed allowlist only in a trusted workspace: accept
  the trust dialog once per checkout.
- Its deny tier is Claude Code's `ask` list, so a person confirms each one-way
  move in session. The allowlist is a convenience, not a safety gate.

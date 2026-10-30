## Claude Code

- `.claude/settings.json` is rendered by `adlc harness render --harness claude`
  from the ADLC toolkit's `templates/permissions.yml` and `templates/hooks.yml`.
  Commit it: it is shared by the team. Personal overrides go in
  `.claude/settings.local.json`.
- Claude Code applies the committed allowlist only in a trusted workspace: accept
  the trust dialog once per checkout.
- Its deny tier is Claude Code's `ask` list, so a person confirms each one-way
  move in session. The allowlist is a convenience, not a safety gate.

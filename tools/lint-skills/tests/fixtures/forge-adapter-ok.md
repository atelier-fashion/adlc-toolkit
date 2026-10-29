# Fixture: adapter usage + exempt gh ops — no findings expected (REQ-520 BR-1)

PR ops route through the adapter, and the two exempt direct ops (`gh pr diff`,
`gh pr checks`) are allowed.

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . "$ADLC_TOOLKIT_ROOT/partials/forge.sh"; fi
adlc_forge_pr_merge "$prUrl" --squash --delete-branch
adlc_forge_pr_view "$prUrl" --fields state,url
```

```sh
gh pr diff "$prUrl"
gh pr checks "$prUrl"
```

No `forge-direct-gh` finding expected.

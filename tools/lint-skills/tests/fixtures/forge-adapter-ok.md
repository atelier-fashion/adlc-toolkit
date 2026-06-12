# Fixture: adapter usage + exempt gh ops — no findings expected (REQ-520 BR-1)

PR ops route through the adapter, and the two exempt direct ops (`gh pr diff`,
`gh pr checks`) are allowed.

```sh
. .adlc/partials/forge.sh 2>/dev/null || . ~/.claude/skills/partials/forge.sh
adlc_forge_pr_merge "$prUrl" --squash --delete-branch
adlc_forge_pr_view "$prUrl" --fields state,url
```

```sh
gh pr diff "$prUrl"
gh pr checks "$prUrl"
```

No `forge-direct-gh` finding expected.

# Fixture: direct `gh pr` op in a shell fence — must be flagged (REQ-520 BR-1)

PR-lifecycle ops must route through `partials/forge.sh`. A direct `gh pr merge`
inside a shell fence is exactly what the `forge-direct-gh` check guards against.

This prose mentions `gh pr merge` outside any fence and must NOT be flagged.

```sh
gh pr merge "$prUrl" --squash --delete-branch
```

Expect one `forge-direct-gh` finding naming the `merge` op.

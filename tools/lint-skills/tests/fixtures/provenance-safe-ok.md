# Fixture: BUG-230 provenance-safe fences that stay in the grammar (clean).

A marked fence with a `<placeholder>` the model substitutes, and an UNMARKED
fence full of `$`, quotes and pipes — the check only reads marked fences.

```bash
# provenance-safe (BUG-230)
git rev-parse --abbrev-ref origin/HEAD
git log --no-walk --branches --decorate --date short
git branch --merged <default>
git diff-tree -r --no-commit-id 4b825dc642cb6eb9a060e54bf8d69288fbee4904 HEAD
```

```bash
CUTOFF=$(date -v-90d +%Y-%m-%d)
git for-each-ref --format='%(refname)' | awk '{print}'
```

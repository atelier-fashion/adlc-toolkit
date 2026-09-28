# Fixture: BUG-230 provenance-safe fence with five out-of-grammar lines.

Exactly five `provenance-safe-fence` findings, one per offending line.

```bash
# provenance-safe (BUG-230)
git log --no-walk --branches --format=%cs
CUTOFF=$(date -v-90d +%Y-%m-%d)
tools/lint-skills/check.sh
awk '{print}' README.md
git show HEAD
git status
```

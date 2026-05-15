# Clean SKILL.md fixture — no findings expected

This file exists only to verify the linter does not false-positive on a
benign skill.

```sh
echo "balanced $(date -u +%s)"
```

```bash
total=$(( 1 + 2 ))
echo $total
```

No Kimi gate here, so canonical-helper does not apply.

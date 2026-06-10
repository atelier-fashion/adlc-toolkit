---
name: arg-templating-fixture
description: Fixture with bare $<digit> positionals that Skill templating clobbers.
---

# Fixture: bare positionals

Prose mention of a positional like $1 is also templated.

```sh
emit() { awk -v k="$1" 'index($0,k)==1{print}'; }
safe() { awk -v k="${1}" 'index($(0),k)==1{print}'; }
echo "pid-then-digit $$1 is exempt"
```

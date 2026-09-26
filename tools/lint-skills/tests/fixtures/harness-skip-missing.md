# Fixture: BUG-228 gate fence with no harness-skip line.

Exactly one `harness-skip` finding, on the fence's opening line.

```sh
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . ~/.claude/skills/partials/delegate-gate.sh; fi
adlc_delegate_gate_check; gate=$?
```

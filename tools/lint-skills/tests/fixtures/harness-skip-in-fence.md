# Fixture: BUG-228 harness-skip line only inside a fence.

A copy inside a fence is not an instruction to the model, so it does not count.

```sh
echo '**Provenance-classifying harness (BUG-228):** on such a harness, skip this step's shell and take the fallback path.'
```

```sh
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . ~/.claude/skills/partials/delegate-gate.sh; fi
adlc_delegate_gate_check; gate=$?
```

# Fixture: BUG-228 harness-skip line present (clean).

The line sits in prose above the gate fence. A second fence only *mentions* the
gate call in a comment, which is not a call, so it needs no line of its own.

**Provenance-classifying harness (BUG-228):** on such a harness, skip this step's shell and take the fallback path.

Before the gate check, gate:

```sh
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . ~/.claude/skills/partials/delegate-gate.sh; fi
adlc_delegate_gate_check; gate=$?
```

Padding line 0.
Padding line 1.
Padding line 2.
Padding line 3.
Padding line 4.
Padding line 5.
Padding line 6.
Padding line 7.
Padding line 8.
Padding line 9.
Padding line 10.
Padding line 11.
Padding line 12.
Padding line 13.
Padding line 14.
Padding line 15.
Padding line 16.
Padding line 17.
Padding line 18.
Padding line 19.
Padding line 20.
Padding line 21.
Padding line 22.
Padding line 23.
Padding line 24.
Padding line 25.
Padding line 26.
Padding line 27.
Padding line 28.
Padding line 29.
Padding line 30.
Padding line 31.
Padding line 32.
Padding line 33.
Padding line 34.

```sh
# adlc_delegate_gate_check is retired here
true
```

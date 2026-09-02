---
id: ASSUME-003
title: "The system python3 carries PyYAML because Apple ships it"
status: invalidated
req: REQ-609
created: 2026-09-01
resolved: 2026-09-02
---

## Assumption

`$PATH`'s `python3` on the reference Mac can `import yaml` because Apple ships
PyYAML with the system interpreter, so a tool that runs under bare `python3`
(the `adlc` umbrella, `adlc doctor`'s probes, `partials/forge.sh`) could rely
on the parser being there without an install step.

## Context

REQ-609 made PyYAML the parser for the governance config. Its BR-8 asked for one
managed interpreter, and the draft measured "two interpreters today" but
explained the system one's PyYAML as Apple-shipped — which would have made the
venv-absent fallback safe everywhere.

## Resolution

Invalidated at Phase 5 (reflector). The module lives at
`~/Library/Python/3.9/lib/python/site-packages/yaml/`, a user-site
`pip install --user`; `python3 -s -c 'import yaml'` fails. A fresh Mac has PyYAML
only inside `~/.claude/delegate-venv` after `install.sh --with-delegation`, and
a child process with a redirected `HOME` loses the user-site copy entirely.
Consequences landed in the same REQ: the interpreter rule checks the venv's
`site-packages/yaml` directory rather than the interpreter; `partials/forge.sh`
applies it too; `adlc doctor` reports the interpreter actually selected; the
tests hand child interpreters the parent's package explicitly.

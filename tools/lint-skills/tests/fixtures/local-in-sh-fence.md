# Fixture: `local` in a sh/shell fence (flagged) vs a bash fence (exempt).

REQ-436 ADR-6 / BR-8: a `local` declaration at statement position inside an
sh or shell fenced block is a POSIX violation and must be flagged
(`posix-fence`). The identical construct inside a bash fenced block is exempt
by design — many bash builds support `local`; the POSIX-only mandate targets
sh/shell. This fixture exercises the sh positive, the shell positive, and the
bash exemption so the test asserts each flagged line AND the un-flagged one.
(No prose line begins with a triple-backtick language token, so the fence
parser sees only the three real fenced blocks below.)

```sh
x=1
local x=1
echo "$x"
```

The shell-tagged block below is also flagged (shell is treated like sh):

```shell
z=3
local z=3
echo "$z"
```

The bash-tagged block below has the same `local` construct and must NOT be
flagged (bash-exempt):

```bash
y=2
local y=2
echo "$y"
```

End.

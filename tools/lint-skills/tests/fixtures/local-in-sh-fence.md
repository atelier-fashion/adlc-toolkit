# Fixture: `local` in a ```sh fence (flagged) vs a ```bash fence (exempt).

REQ-436 ADR-6 / BR-8: a `local` declaration at statement position inside a
```sh (or ```shell) fence is a POSIX violation and must be flagged
(`posix-fence`). The identical construct inside a ```bash fence is **exempt
by design** — many `bash` builds support `local`; the POSIX-only mandate
targets `sh`/`shell`. One fixture exercises both the positive and the
exemption so the test asserts the exact flagged line AND the un-flagged one.

```sh
x=1
local x=1
echo "$x"
```

The ```bash block below has the same `local` construct and must NOT be
flagged (bash-exempt):

```bash
y=2
local y=2
echo "$y"
```

End.

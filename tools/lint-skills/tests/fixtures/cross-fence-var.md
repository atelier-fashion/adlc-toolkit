# Fixture: a variable assigned in one fenced block, read in another.

`captured` is assigned in the first fenced block and read in a SECOND fenced
block. SKILL.md fenced blocks do not share shell state across steps, so the
read sees an empty value — the inert-telemetry class REQ-522 fixed. One
`cross-fence-var` finding naming `captured` is expected.

Step one assigns it:

```sh
captured=$(date -u +%s)
echo "step one set captured=$captured"
```

Step two reads it from a DIFFERENT fenced block (empty at runtime):

```sh
echo "step two sees captured=$captured"
```

An EXPORTED variable crossing fences is exempt — `shared` below must NOT be
flagged:

```sh
export shared=hello
```

```sh
echo "$shared"
```

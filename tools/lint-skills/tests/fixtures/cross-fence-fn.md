# Fixture: shell function defined in one fence, invoked in a different fence.

REQ-436 ADR-7 / BR-10: `myfn` is **defined** in the first ```sh fenced block
but **invoked** only from a *separate* ```sh fenced block. SKILL.md fenced
shell blocks do not share shell state across steps, so `myfn` is undefined at
its call site — exactly the Defect-1 silent-telemetry-loss class the
`cross-fence-fn` check structurally guards against.

Fence A — defines the function:

```sh
myfn() {
    echo "in myfn"
}
```

Some prose between the fences. `myfn` mentioned here in prose must be ignored
(only statement-position invocations inside fences count).

Fence B — invokes it from a different shell:

```sh
myfn
```

Expect one `cross-fence-fn` finding naming `myfn`.

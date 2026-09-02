# Fixture: the retired source spelling in PROSE (REQ-610 BR-5, rule 2)

Every fence here is canonical, so rule 1 is silent. What is wrong is a sentence:
prose that spells the retired line out is an instruction to type it, and
`analyze/SKILL.md` Step 1.5 carried exactly such a sentence — as executable as a
fence, one paste away from being live. That is why rule 2 reads every line of
the file, not just fence bodies.

```sh
if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . ~/.claude/skills/partials/forge.sh; fi
adlc_forge_pr_view 123
```

The offending sentence, and the only expected finding: before running the step,
source the adapter with `. .adlc/partials/forge.sh 2>/dev/null || . ~/.claude/skills/partials/forge.sh` and then call it.

```shell
if [ -f .adlc/partials/id-alloc.sh ]; then . .adlc/partials/id-alloc.sh; else . ~/.claude/skills/partials/id-alloc.sh; fi
```

A whitespace-aligned variant, as the corpus really carried in
`agents/delegate-pre-pass.md`: `. .adlc/partials/forge.sh   2>/dev/null  ||  . ~/.claude/skills/partials/forge.sh`.

Expect exactly two `unguarded-source` findings, one on each prose line above.

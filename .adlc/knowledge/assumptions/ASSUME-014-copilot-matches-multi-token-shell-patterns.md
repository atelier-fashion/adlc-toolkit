---
id: ASSUME-014
title: "Copilot CLI matches a multi-token `shell(<argv>:*)` pattern, on both --allow-tool and --deny-tool"
status: unresolved
req: REQ-656
created: 2026-10-30
resolved:
---

## Assumption

The printed line spells `--allow-tool 'shell(gh pr view:*)'` and
`--deny-tool 'shell(git push --force:*)'`, assuming Copilot treats a multi-word stem
as a prefix, with `:*` meaning "the stem followed by a space". The page documents `:*`
with a one-word stem (`shell(git:*)`) and shows `shell(git push)` as a deny, but states
no rule for several words, and does not say whether a bare `shell(git push)` takes
trailing arguments.

## Context

`harness/copilot.yml` declares `token-prefix` on this reading (REQ-656 ADR-1, ADR-2). A
pattern that fails to match costs a prompt on an allow. On a deny it loses the hard deny,
but the command still prompts, because BR-6 omits the routine prefix that would have
allowed it. So a wrong assumption fails closed on every command the line names. It would
not hold for a deny the operator relies on while also allowing the base by hand, which is
why the README does not call the allowlist a gate.

## Resolution

Unverified: no `copilot` binary was available. Resolve at the REQ-656 dogfood (BR-13), or
with REQ-664's `deny-under-allow` and `wrapped-allow` results for `copilot`. Then set
`status: validated`, or change the spellings and the goldens together.

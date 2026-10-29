---
id: TASK-126
title: "Agents dispatch on both routes: canonical dispatch sentence with inline fallback, workflow agent namespace, and its lint"
status: complete
parent: REQ-669
created: 2026-10-28
updated: 2026-10-28
dependencies: [TASK-124]
---

## Description

Apply architecture ADR-6. Each skill that dispatches an agent gets the canonical dispatch sentence once per dispatch step. Today only `/adversary` has an inline fallback when an agent is missing. The ten `~/.claude/agents/` prose mentions become `$ADLC_TOOLKIT_ROOT/agents/`. The workflow engine names agents in code, so it gains a pure helper that prefixes them with the namespace `/sprint` passes in. TASK-120's agent-name rows fix the namespace value. If they show plugin agents dispatch by bare name, the namespace is `""` on both routes, and the helper and arg stay as a no-op seam.

## Files to Create/Modify

- `review/SKILL.md` — the canonical sentence at each dispatch step. The `~/.claude/agents/` prose is rewritten.
- `reflect/SKILL.md` — the canonical sentence at each dispatch step. The `~/.claude/agents/` prose is rewritten.
- `architect/SKILL.md` — the canonical sentence at each dispatch step. The `~/.claude/agents/` prose is rewritten.
- `optimize/SKILL.md` — the canonical sentence at each dispatch step. The `~/.claude/agents/` prose is rewritten.
- `analyze/SKILL.md` — the canonical sentence at each dispatch step. The `~/.claude/agents/` prose is rewritten.
- `proceed/SKILL.md` — the canonical sentence at each dispatch step. The `~/.claude/agents/` prose is rewritten.
- `sprint/SKILL.md` — the canonical sentence at each dispatch step. The `~/.claude/agents/` prose is rewritten.
- `sprint/SKILL.md` — resolve the workflow script path through ToolkitRoot, with `.adlc/workflows/` first as today. Compute `agentNamespace` from the substituted `${CLAUDE_PLUGIN_ROOT}` (non-empty means plugin) and pass it in the Workflow `args`.
- `workflows/adlc-sprint.workflow.js` — a pure `agentTypeFor(name, ns)` inside the PURE sentinels, used at every `agentType:` site. `args.agentNamespace` is read once at the top, and it is validated: `""` or `^[a-z0-9-]+:$`, anything else is `""` plus a log line.
- `workflows/tests/helpers.test.js` — `agentTypeFor` cases.
- `workflows/README.md` — the two-route path resolution and the namespace arg. The "absolute-path symlink" text is reworded.
- `tools/lint-skills/check.py` — new `dispatch-fallback` check. A skill whose text names a dispatched agent ("**<name>** agent", "the <name> agent", or "launch … agents") must carry the canonical sentence.
- `tools/lint-skills/tests/test_check.py` — must-fire and must-not-fire cases.
- `tools/lint-skills/tests/fixtures/dispatch-fallback-*.md` — must-fire and must-not-fire cases.
- `tools/lint-skills/README.md` — new item.
- `.adlc/context/conventions.md` — the canonical dispatch sentence, stated once, as the copy `dispatch-fallback` compares against.

## Acceptance Criteria

- [x] `node --test 'workflows/tests/*.test.js'` passes (the directory form is not portable across Node versions; see `workflows/tests/README.md`). `agentTypeFor('reflector', '')` is `reflector`, and `agentTypeFor('reflector', 'adlc:')` is `adlc:reflector`. An invalid namespace such as `'../'` or `'adlc'` (no colon) yields the bare name.
- [x] Every `agentType:` in the workflow file goes through `agentTypeFor`. A grep for a literal `agentType: '` finds none outside the helper's tests.
- [x] `dispatch-fallback` reports zero findings on the repo. It fires on a fixture that dispatches the reflector with no sentence. It does not fire on a skill that mentions an agent only in a cross-reference, such as "see the reflector's checklist in `/reflect`" (the benign path).
- [x] No `~/.claude/agents` text remains in `*/SKILL.md` or `agents/*.md`.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-9 | test-case | `workflows/tests/helpers.test.js::agentTypeFor` | no |
| BR-9 | test-case | `tools/lint-skills/tests/test_check.py::test_dispatch_fallback_missing_sentence_fires` | no |
| BR-9 | test-case | `tools/lint-skills/tests/test_check.py::test_dispatch_fallback_cross_reference_does_not_fire` | yes |
| BR-4 | test-case | `tools/lint-skills/tests/test_check.py::test_dispatch_fallback_repo_clean` | yes |

## Technical Notes

- The sentence is canonical text, so write it once in conventions.md (TASK-122's section) and have the lint compare against that copy. This avoids a second copy that rots (LESSON-019). Adding the sentence to conventions.md is in this task's diff.
- "Run its checklist inline" means the model reads `$ADLC_TOOLKIT_ROOT/agents/<name>.md` and follows it in its own context. For review and audit agents the run is read-only, matching REQ-666's dispatch paragraph.
- `args.agentNamespace` is untrusted input to the workflow, like any arg. Validate its shape and never splice it unvalidated (LESSON-008).
- The workflow runtime has no `fs`, so the namespace cannot be detected inside the script. `/sprint` is the only place that knows the route.

# /validate results for REQ-655..666 (2026-10-27)

Twelve parallel spec-phase validations of the multi-harness REQs committed in
3563005. **None is ready for `/architect`.** 65 blockers in total, almost all
textual. They fall into three classes; the first is by far the largest and is
the cost of writing twelve specs in parallel before the framework's vocabulary
existed.

| REQ | blockers | verdict | dominant class |
|---|---|---|---|
| REQ-655 Codex adapter | 7 | not ready | framework contradictions; wrong agent count |
| REQ-656 Copilot + Cursor | 5 | not ready | framework contradictions; `tools: *` does not exist |
| REQ-657 framework | 7 | not ready | schema rejects its own fields; capabilities siblings assume |
| REQ-658 Gemini | 11 | not ready | framework contradictions; duplicates 664/665 |
| REQ-659 exec engine | 3 | not ready | **Rule B holes** |
| REQ-660 session sidecar | 3 | not ready | ownership vs 657; harness detection |
| REQ-661 skill splits | 3 | not ready | ordering vs 666 unstated |
| REQ-662 exec adapters | 6 | not ready | re-specifies 664's probes; enums vs 659 |
| REQ-663 migrate-home | 4 | not ready | **lock-before-counter; backup restore re-issues IDs** |
| REQ-664 probes | 8 | not ready | ownership vs 655/662; BR/AC contradictions |
| REQ-665 plugin manifests | 4 | not ready | **one-mount rule impossible**; duplicates 658 |
| REQ-666 skill text | 4 | not ready | **apostrophe quoting**; ordering vs 661; silent BUG-228 reversal |

## Class 1 — cross-spec vocabulary and ownership (fix once, apply everywhere)

Decide each of these once, in the REQ named as authority, then conform the others.

| topic | authority | conform |
|---|---|---|
| Permissions tiers are `routine` and `deny`; there is no "ask tier" in `templates/permissions.yml`. Each adapter declares `deny_tier_render: confirm|deny|unsupported` (657 B-5 fix) | REQ-657 BR-6 | 655 BR-3/OQ-3, 656 BR-6/BR-8 and all "ask-tier" wording, 658 (12 uses), 659/662 "one-way tier" |
| Fence entry (`fence.partial-source`): at project scope the narrowest opening-token prefix or omitted + `inexpressible`; broad entry only at user/exec scope | REQ-657 BR-8 (amended per 657 B-5) | 655 BR-3, 658 BR-5, 656 BR-8, 659 BR-8, 662 BR-3 |
| `accepted_fidelity` block exists on the adapter entity and every adapter declares its `widened`/`inexpressible` losses | REQ-657 (657 B-1 adds the field) | 655 W3, 656 B4, 658 B8 |
| `tier_map` alias→model-id (`unverified` omits `model:`) lives on the adapter; tier config column feeds it | REQ-657 (657 B-3) | 655 BR-2 line 109, 656 BR-4/OQ-4, 658 BR-7/B11 |
| `agent_tool_restriction: enforced|readonly-only|none` drives the restraint line; a missing `tools:` line means all tools (no agent uses `*`); restraint applies to the 17 agents whose `tools:` omits Edit/Write | REQ-657 (657 B-4, I-4) | 655 B2 ("twelve"→17), 656 B5 (`*`), 658 BR-6 |
| CLI spelling `adlc harness install|render|doctor --harness <name>` | REQ-657 BR-3 | 655, 656 (W6), 658 B4 |
| Doctor: `harness:<name>` stays report-only; render-currency is one framework check `render-currency:<name>`; adapters add data rows, not check code | REQ-657 BR-15 (657 W-1) | 655 BR-9 `codex-*`, 656 BR-10, 658 BR-9 `gemini:*` |
| Canonical hook events `session-start`, `session-compact`, `subagent-start`; `HookEntry` gains `timeout_s`; adapter gains `hook_payload` map | REQ-657 (657 W-10) | 656 L75, 658 BR-4/W1, 660 B2 |
| `session-record`: REQ-657 owns the `hooks.yml` entry and every render; REQ-660 owns the partial, sidecar fields (incl. mode 600), pruning, gitignore + lint | REQ-660 OQ-8 resolved as proposed | 657 BR-10/AC-8/L206 (657 B-6), 660 B1 |
| `exec` is an opaque, schema-versioned sub-block owned by REQ-659 (engine) and REQ-662 (adapters); REQ-657 validates map-or-absent; REQ-662 migrates the `claude` block it does not otherwise touch | REQ-659 BR-3 / 662 B2 | 657 W-9, 662 BR-1/L166-167 |
| Trust enum `none|flag|user-config-entry|trusted-folders-file`; working-copy enum `worktree|clone|orchestrator-git` | REQ-657 (trust), REQ-659 (working copy) | 659 L82 (`user-config`), 662 L79 (`git_ops: orchestrator`), 655 L103, 664 L71 |
| Forbidden-flag vocabulary lives in each adapter's `forbidden_flags`, seeded by the engine; `exec-no-bypass` lint reads it | REQ-659 BR-8 | 662 BR-2/AC-2 (662 B5) |
| Probes: ids, `pass|fail|unknown|n/a`, result file `.adlc/research/harness-probes/<harness>.json`; consumers cite, never re-run. `git-write-worktree` on codex gains `root-is-worktree` and `writable-roots-repo` sub-variants | REQ-664 | 662 B1 (Probe entity, ids, path), 655 B6/BR-10, 658 B3/BR-1, 666 AC-1 (§6.10 cites claude.json) |
| `gemini-extension.json`, its version lint and the extension-layout OQ belong to REQ-665 (`manifest-parity`); REQ-658 keeps only `gemini:extension` / `gemini:dual-install` doctor rows | REQ-665 | 658 B2 (BR-10, entity, AC-10, OQ-2) |
| Ordering: REQ-666 lands before REQ-661; REQ-661 drops `harness-skip`, `provenance-safe-fence`, BUG-228 line from BR-5/BR-7/AC-10 and widens its companion walk to REQ-666's four checks + `ethos-line` | both | 661 B1, 666 B2 |
| External Dependencies name ids, not phases: 654, 655, 656, 657, 658, 659, 660, 662, 664, 666 as applicable | all | 655 B6, 658 §7, 659 W1, 660 B3, 662 W1, 664 B-3 |
| `templates/claude-settings-template.json`: REQ-657 deletes it; 655 BR-13, 664 BR-7, 666 BR-15 must re-point | REQ-657 OQ-2 | 657 W-3 |

## Class 2 — design defects (one spec each)

- **REQ-659 Rule B (B1–B3).** The resumed close-out still runs `/wrapup --close-out` item 5, which merges the chore PR from inside the model session; the injected unattended block still says "you own the merge"; and the plain-shell `approve` can be invoked by the harness process itself. Fixes: close-out prompt replaces item 5 (model opens the chore PR and stops, orchestrator merges); unattended block gets the three substitutions; `approve|reject|answer` refuse from inside an exec run (`ADLC_EXEC_RUN` + pid ancestry) and the approve command is in the `claude` deny tier.
- **REQ-663 (B1–B4).** The lock loop (`id-alloc.sh:606-614`) runs before the counter read (`:620`), so a stale allocator never reads through the counter symlink: AC-4/BR-5/BR-15 describe an impossible path. `--back` must move live files back, never restore the backup (which would re-issue IDs). BR-3's backup refusal blocks BR-11's repair and `--back` itself. `<dir>/skills` and `<dir>/agents` are undefined against REQ-654 AC-2.
- **REQ-666 (B3).** Single-quoting the substituted argument breaks on an apostrophe and turns `adlc_intake_detect "$ARGUMENTS"` into a syntax error that silently disables intake; use `'\''` escaping or a quoted here-doc, stated once in conventions. Also B1: BUG-228's 120 s timeout guidance is harness-agnostic and must survive the Teton retirement.
- **REQ-665 (B-1).** "One mount per harness, never both" is unsatisfiable while the plugin still needs `./install.sh` underneath; rewrite BR-8 as coexistence with a documented doubled-catalog cost and per-harness precedence.
- **REQ-657 (B-1, B-2).** The closed schema rejects `accepted_fidelity` and the `fake` adapter; add the field and a fixture-path loading exception.
- **REQ-664 (B-1, B-2, B-8).** `--timeout 5` test is refused by BR-8's 125 s floor; `ask-tier-deny` cannot yield `pass` on a non-zero exit under BR-5; a catchable kill must restore, so AC-4 needs SIGKILL.
- **REQ-660 (B2).** One `.claude/settings.json` entry serves Claude, Copilot and Cursor, so the `harness` field needs a payload-based detection rule and an `unknown` value.
- **REQ-661 (B2, B3).** Companion markers cannot be byte-identical if BR-12 moves phase files; BR-6's "thread the literal" rewrites a fence BR-3 says is byte-identical.

## Class 3 — stale or false repo claims to correct

- `.codex/**`, `.cursor/**`, `.github/**`, `.adlc/partials/**` are already in `lane_check.py` defaults (655 B1/B7, 656 W10, 657 B-7, 666 W9). State "already present, pinned by test".
- No agent uses `tools: *`; `task-implementer` and `pipeline-runner` have no `tools:` line (655 B2, 656 B5, 657 I-4).
- The toolkit has no CI; "toolkit CI" means the lint/pytest/partials gates (657 I-9 posture; 666 W1, 661 OQ-4).
- `proceed/phases-lite.md` has no BUG-228 line (661 W3).
- Copilot's `events.jsonl` `cwd` field is unsourced (660 W9).
- `extract-chat` also exits 1 on an unwritable `-o` (660 W2).
- Several Open Questions are already decided by a BR in the same spec (655 OQ-3, 657 OQ-3/4, 658 OQ-2, 660 OQ-3/4/7, 663 OQ-1/2/3, 664 OQ-1/3/4/5, 665 OQ-5/6, 666 OQ-4/5).

## Suggested fix order

1. REQ-657 first (schema fields, tier map, tool-restriction semantics, deny-tier render, fence scope, session-record hand-off, exec opaque block). It is the vocabulary everyone else conforms to.
2. REQ-664 and REQ-659 next (probe contract; engine enums, Rule B fixes).
3. The adapters 655, 656, 658 and 662, 660 conform to 1–2.
4. REQ-666 then REQ-661 (ordering fixed as 666 → 661).
5. REQ-663 and REQ-665 (independent design fixes).
6. Re-run `/validate` on all twelve.

The full per-spec reports, with exact fix text and line numbers, were produced
by the validation runs in this session; this note is the digest.

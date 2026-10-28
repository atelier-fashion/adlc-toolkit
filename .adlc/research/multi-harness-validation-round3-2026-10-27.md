# /validate round 3 for REQ-655..666 (2026-10-27)

Third pass after two fix rounds. **None is ready for `/architect`.** Blockers
by round: 65 (round 1), 39 (round 2), 45 (round 3). The count has stopped
falling because each round now probes deeper: round-1 findings were
vocabulary disagreements between specs, round-3 findings are design defects
(Rule B holes, unsound probes, irreversible migration). Every round-3 finding
carries exact fix text in the validator's report; this file is the digest.

| REQ | r1 | r2 | r3 | r3 blockers in one line |
|---|---|---|---|---|
| 655 Codex | 7 | 3 | 3 | allow-vs-prompt precedence unverified (Rule B); `working_copy` at wrong level; "TOML written, not parsed" contradicts merge |
| 656 Copilot+Cursor | 5 | 3 | 1 | Copilot `git -C` allow prefix covers every deny-tier git spelling |
| 657 framework | 7 | 6 | 4 | exact-match entries / `defaultMode` / `_comment` not renderable; `accepted_fidelity` not per scope; no `--adapter-path`/`--scope` CLI; dotted `owned_keys` |
| 658 Gemini | 11 | 5 | 4 | `dual-install` ignores installed copies; `render-currency` FAILs when nothing rendered; policy write semantics; `trust` shape |
| 659 engine | 3 | 2 | 4 | close-out prompt inlines wrapup merge/deploy steps; Phase 1 tells model to remove a worktree; orchestrator merges/deploys unreviewed model content; orchestrator runs git hooks/config from a model-writable tree |
| 660 sidecar | 3 | 2 | 4 | lint exception wrong; payload-field seam unowned; session-id regex accepts `..`; missing ACs |
| 661 splits | 3 | 1 | 3 | lesson checks per file break; retrieval-status check silently disarms; moved sections break tests that read them |
| 662 exec adapters | 6 | 6 | 6 | gate "every probe `pass`" contradicts the fallbacks it designs; engine keys missing from schema; `working_copy` ownership; index exclusion fails for tracked files; flag matcher; claude migration not mechanical |
| 663 migrate-home | 4 | 2 | 2 | `--prune-backup` makes migration irreversible; old venv/view lifecycle undefined |
| 664 probes | 8 | 2 | 5 | AC-2 scenarios contradict three-way rule; Gemini deny has no legal location; deny probes pass vacuously (headless ask is already a deny); routine-set pin needs a file that does not exist; AC-3/13 vs left-in-place records |
| 665 manifests | 4 | 2 | 4 | minimum set vs symlink rule; `agents/` read by convention; `dual-install` link vs install; catalog-count/immediacy claims contradict siblings |
| 666 skill text | 4 | 5 | 5 | allowlist inventory incomplete (`git rev-parse` etc.); impossible AC-7 fixture; `/adversary` dispatch unmentioned; `ADLC_HOME` spelling undefined; placeholder token uncommitted |

## Cross-cutting themes (fix each once, then conform)

1. **The shared-base Rule B hole keeps reappearing in new spellings.**
   Cursor `Shell(git)`, Copilot `git push:*`/`git branch:*` and now `git -C`,
   Codex `allow ["git","push"]` vs `prompt [... "--force"]`, Cursor fence
   `if`. Framework rule needed in REQ-657: any routine prefix that is a
   proper prefix of, or can wrap, a deny-tier spelling (including `git -C
   <path> ...`) is omitted and reported `inexpressible` until REQ-664's
   `deny-under-allow` shows the finer rule wins for that spelling shape.
2. **Exec engine must never run or merge model-written content.** Close-out
   prompt built by section (drop wrapup Steps 2/6/7/8); Phase 1 untouched-
   sibling removal rewritten; chore-PR path allowlist and deploy plan frozen
   from the integration branch at the halt; git invoked with hooks/fsmonitor
   disabled and partials resolved from the install only; approval bound to
   head SHA and PR number.
3. **Probe soundness.** A headless ask is already a deny, so `lone-deny` and
   `deny-under-allow` need `baseline` and `allow-only` control launches; match
   a transform of the nonce, not the nonce; define what REQ-662 requires of
   each probe (hard-pass vs declaration-bound) instead of "every probe
   `pass`".
4. **Framework completeness.** `PermissionEntry.match` (exact/prefix),
   `default_mode`/`comment`, per-scope `accepted_fidelity`, `--adapter-path`
   and `--scope`, dotted `owned_keys`, TOML merge ownership, required-vs-
   optional column, `hook_events` matcher (Claude compaction is a `SessionStart`
   matcher).
5. **Doctor semantics for Gemini.** `dual-install` must treat an installed
   extension copy, not only a link, as the extension surface; neither it nor
   `render-currency` may FAIL for a user who never used the harness.
6. **Reversibility of the home migration.** `--back` must not need the
   forward backup; old venv/view/helper are removed only after every check
   passes; tombstone creation is back-to-back with lock release.
7. **Inventory and test-reader fallout of the skill changes.** BR-15's
   allowlist list (`cat`, `grep`, `gcloud`, plus `git rev-parse`,
   `git diff-tree`, `git for-each-ref`), `/adversary` dispatch site, tests
   that read moved sections, `retrieval-status-parity` arming.

## Where this leaves the set

Round 3 found no vocabulary disagreements left between the specs; what
remains are design-level defects that the specs surface precisely because
they are now detailed enough to attack. Two reasonable stopping points:
(a) one more targeted fix round on the seven themes above, then a fourth
validation; (b) accept the specs as drafts, carry these findings into
`/architect` for each REQ as required inputs, and let the architecture
phase resolve them against the code. The Rule B items (themes 1 and 2) should
be fixed in the specs before architecture, not left to it.

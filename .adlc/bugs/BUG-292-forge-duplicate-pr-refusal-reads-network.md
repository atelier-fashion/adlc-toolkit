---
id: BUG-292
title: "A forge's refusal of a second PR for one head and base has no error class, so both backends report it as error_class=network"
status: open
severity: low
created: 2026-11-23
updated: 2026-11-23
component: "adlc/partials/forge"
domain: "adlc"
stack: ["bash", "python"]
concerns: ["correctness", "developer-experience", "unattended"]
tags: ["forge-adapter", "error-classification", "pr-create", "draft-pr", "duplicate-pr", "network", "forge-mock", "misleading-diagnostics", "vendored-partial"]
introduced_by: []
attribution: none
---

## Description

A forge holds one open PR for a head and base and refuses a second. `adlc_forge_pr_create` is the operation that meets that refusal, and `_adlc_forge_classify` (`partials/forge.sh`) has no pattern for it, so the refusal takes the fall-through class:

```
error_class=network
raw=a pull request for branch "feat/REQ-900-thing" into branch "main" already exists:
raw=https://github.com/acme/widgets/pull/101
```

`network` reads as transient and invites a retry (BUG-150, BUG-201, LESSON-581). This refusal is the opposite on both counts. A retry is refused every time, and nothing failed: the PR named is the caller's own.

BUG-291 found the case. Its fix made Step 0's draft-PR fence (`proceed/phase-0-setup.md`, item 8a) read the open PR before creating one, and made the mock forge refuse a duplicate "as `error_class=network`", because that is the class the adapter gives the forges' own words. It weighed a class of its own and left it as a follow-up, as a change to the adapter's contract. This is that follow-up.

A second defect sits beside it and is worse than the first. The refusal quotes the head branch, the base branch and the PR's URL, which are the project's own words, and the classifier matches substrings of the whole message in a fixed order. So the same refusal reads `auth-missing` for a head named `fix/credentials-not-found`, and `merge-blocked-by-policy` for one named `feat/REQ-12-branch-protection-policy` or for a repository named `policy-engine`.

## Reproduction Steps

1. `. partials/forge.sh; _adlc_forge_classify 'a pull request for branch "feat/x" into branch "main" already exists:'`
2. The same with `TF401179: An active pull request for the source and target branch already exists.`
3. The same with the head `fix/credentials-not-found`, and with `feat/REQ-12-branch-protection-policy`.
4. With `ADLC_FORGE_MOCK=1` and a store, `adlc_forge_pr_create --base main --head feat/x --title t --body b` twice.

## Expected Behavior

One class says "a pull request for this head and base already exists", whatever the branches are called, on both backends and on the mock. The contract says what a caller does with it.

## Actual Behavior

1 and 2 print `network`. 3 prints `auth-missing` and `merge-blocked-by-policy`. 4's second call prints `error_class=network`.

## Environment

- Toolkit `main` at `a0eeab8`, macOS, `gh` 2.103.3.
- Evidence: BUG-291's "Weighed and not done", and the classifier run on the strings above.

## Root Cause

Prior lessons consulted:
- LESSON-581 — A classifier's fall-through default is a claim about every input it has never seen — make it 'I don't know', not the most reassuring class in the set (score 14)
- LESSON-572 — A remediation is only real if its audience can execute it. Handing a human-readable instruction into a machine-consumed channel is not a fix — it is a fix-shaped comment. When an operation half-succeeds, give each fact its own normalized field and finish the half you are able to finish. (score 9)
- LESSON-891 — A test double written from the system's side supplies what the real actor cannot: run the whole flow once with the real actor, against a double no kinder than the real service (score 8)
- LESSON-780 — A mock returns the shape its author assumed: run each new forge field once, read-only, against the real CLI (score 8)
- LESSON-617 — `.` is a POSIX special built-in — `. A || . B` exits sh at the first arm, and both it and `[ -f A ] && . A || . B` double-source when A ends non-zero (score 8)

LESSON-581 describes this failure exactly, and its remedy is the one applied: an unmatched signature does not error, it acquires `network`, so the signature is added and pinned in `forge.test.sh`, with negative anchors. Its second half applies too: the documented class set and the emitted one drift apart, so every statement of the set is now held to the classifier's.

1. **No pattern.** `_adlc_forge_classify` is a `case` over substrings of the backend's stderr with `*) echo "network"` last. None of its arms matches "already exists" for a pull request or `TF401179`. The class set was closed at five by REQ-520 and has grown only when a refusal was met in use (`local-git` in BUG-150, the branch-protection arm in BUG-201). No run met a duplicate create until BUG-291, because before that fix the fence never looked first and the mock opened a second PR.
2. **The message carries the project's own words.** Every arm matches anywhere in the message, and the arms for `auth-missing`, `pr-not-found` and `merge-blocked-by-policy` hold ordinary words: `credentials`, `authentication`, `not found`, `policy`, `blocked`. A refusal that quotes a branch name and a URL can therefore be moved to any of those classes by the name of a branch or a repository. A new arm placed in the documented order, most specific first and after those three, would have fixed case 1 and left case 3.

Who reads `error_class`, and what each does with a class it does not name. Found by reading every match of `error_class` and of each class name in the skills, `tools/adlc`, `partials` and `workflows`:

| Reader | Reads | A class it does not name |
|---|---|---|
| `fence_run.pr_verdict` (`tools/adlc/fence_run.py`) | the runner's own `adlc_forge_pr_view`, before a tied fence | `pr-not-found` is 65, a bad value. Any other class that fits `^[a-z][a-z-]{0,39}$` is 75, unverified, and the line names the class. `pr-already-exists` fits |
| `Orchestrator._merge_pinned` (`tools/adlc/sprint_exec.py`) | `adlc_forge_pr_merge` | `merge-blocked-by-policy` re-halts for a fresh approve. Any other ends the run `failed` / `merge-unverified` |
| `adlc_forge_pr_merge` (`partials/forge.sh`) | its own error block, when the PR turns out merged | rewrites `error_class=` to `warn_class=` whatever the class |
| Phase 7's CI read (`proceed/phases-6-8-ship.md`) | `adlc_forge_pr_checks` | any `error_class=` line is "a forge error", and the class goes into `detail` unread |
| Step 0's draft-PR fence, item 8a (`proceed/phase-0-setup.md`) | `adlc_forge_pr_create` | a session reads the block; the text beside the fence keys on the forge's words, not the class |
| `/proceed` Phase 6 fallback, `/wrapup`, `/bugfix`, `workflows/adlc-sprint.workflow.js` | `adlc_forge_pr_create` | none names a class. `/wrapup` and the workflow say to reuse an open PR; the other two create |

So no reader breaks. The two programs that name a class read a `pr_view` and a `pr_merge`, and no forge answers either with this refusal. The one caller that meets it is a session reading a fence's output, and it is the reader the class is for.

Attribution: `git blame` on the classifier (`partials/forge.sh` 272-321 at `a0eeab8`) returns two REQs, REQ-520 and REQ-719. REQ-520 wrote the function, its class set and its `network` default; REQ-719's lines in the range are the missing-CLI arm and one `pr-not-found` pattern, neither of which is this defect. Two candidates, so nothing is written: the operator chooses.

## Resolution

A seventh class, `pr-already-exists`. Not the deny tier: `templates/permissions.yml` and every rendered rule file are untouched.

- **The classifier** (`_adlc_forge_classify`). One arm, for three sentences: `gh pr create`'s own pre-check (`a pull request for branch "<head>" into branch "<base>" already exists:`), GitHub's refusal of the create itself when that pre-check did not see the PR (`A pull request already exists for <owner>:<head>.`, which gh frames as `pull request create failed: GraphQL: … (createPullRequest)`), and Azure DevOps's `TF401179`.
- **It is tried first.** That is against the documented order, and it is the fix for the second defect: the refusal's own signature holds spaces, which no ref can, so a branch name cannot forge it, while every later arm can be reached by a branch name. `forge.md` says so beside "Order is load-bearing".
- **The contract.** The enumeration in `forge.sh`'s header and in `forge.md`, and a passage in `forge.md`: the three sentences and which of them names the PR, what a caller does (use the open PR, the one the `raw=` line names or the one `adlc_forge_pr_list --head … --base … --state open` prints; never open one under another title), and what is not measured.
- **The mock.** `forge_mock.ERROR_CLASSES`, the shell fixture's scenario names, and `op_pr_create`'s refusal, which printed `network`.
- **The text a session reads.** The sentence beside item 8a's fence names `error_class=pr-already-exists`, and says a vendored `forge.sh` older than the class prints `network` for the same words. The fence itself is unchanged, so the census goldens do not move.
- **Records.** `tools/adlc/README.md`, fact 15 of `.adlc/research/harness-probes/codex-exec-manual.md`, and the class list in `.adlc/context/conventions.md`, which had also never gained `local-git`.

Weighed and not done:

- **Printing `url=` and returning 0 when the PR already exists.** LESSON-572 argues for it: give the fact a field and finish the half you can. It would make a create that created nothing read as a success, and the op cannot always name the PR: two of the three sentences do not. Step 0's fence already does the read, and prints `pr_exists=1` for it. Left as it is.
- **An `unclassified` default** in place of `network` (BUG-201's follow-up 2). Still the structural fix, still a change for every caller, still a REQ.
- **Anchoring the other arms** so a branch name cannot reach them. Only this refusal is known to quote one. `no pull requests found for branch "<name>"` does too, and `pr-not-found` is tried before the policy arm, but after `auth-missing`: a branch named for `credentials` would move it. Not met in use; named here.
- **Azure DevOps in a solo run.** `TF401179` names no PR, and the fence's read cannot show one there (the list prints JSON rows whatever `--jq` says), so the text beside the fence ends at "a blocker" on that backend when the session does not read the list itself. BUG-291 left it so and this does not change it.

## Files Changed

- `partials/forge.sh`: the arm, first in `_adlc_forge_classify`; the header's enumeration; the shell fixture's scenario names.
- `partials/forge.md`: the enumeration, the `pr-already-exists` passage, one sentence on the stateful mock.
- `tools/adlc/forge_mock.py`: `ERROR_CLASSES`; `op_pr_create`'s class.
- `proceed/phase-0-setup.md`: the sentence beside item 8a's fence. Prose only.
- `partials/tests/forge.test.sh`: §3's class loop, §4c's `forge.md` guard, §4d's scenario, §4e (new), §12 (new).
- `tools/adlc/tests/test_bug292_forge_pr_already_exists.py`: new.
- `tools/adlc/tests/test_bug291_exec_launch_11_gaps.py`: the two tests that pinned `network`.
- `tools/adlc/README.md`, `CHANGELOG.md`, `.adlc/context/conventions.md`, `.adlc/research/harness-probes/codex-exec-manual.md`.

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`).

Failing-first tests were still written, and run before the fix against `main` at `a0eeab8`.

`partials/tests/forge.test.sh`, under bash, zsh and sh: 15 of the new cases failed and the 438 others passed, the same under each shell. All pass with the fix.

- §3: `pr-already-exists` as a mock scenario under both providers. Before: `error_class=network`, from the fixture's unknown-scenario arm.
- §4c: `forge.md`'s enumeration names every class the classifier prints (new guard; the old one reads `forge.sh`'s header alone), and the classifier prints `pr-already-exists`.
- §4e: the three sentences, `az`'s framing of the third, a cross-repository head, and four refusals whose head, base or repository is named for another class. Before: `network`, and for the four `merge-blocked-by-policy` or `auth-missing`. Four negative anchors passed before and after: a branch that already exists is `local-git`, a label that already exists is the default, and no PR for a branch and `TF401174` are `pr-not-found`.
- §12: `adlc_forge_pr_create` against a stub `gh` and a stub `az` that refuse as the forges do. The op returns the backend's status and the whole block, the URL line included, and asks each backend once.

`tools/adlc/tests/test_bug292_forge_pr_already_exists.py`: 12 of 17 failed, 5 passed; all 17 pass with the fix.

- `test_bug292_every_statement_of_the_class_set_is_the_same_set`: the classifier's set, `forge.sh`'s header, `forge.md`, the shell fixture's scenario names and `forge_mock.ERROR_CLASSES` are one set, with the class in it.
- `test_bug292_each_forges_refusal_has_the_class` (8 cases) and `test_bug292_the_class_takes_nothing_from_another` (4, passing before and after).
- `test_bug292_the_mock_refuses_under_the_class_the_adapter_gives_its_words`: both providers, from `forge_mock.py` and through `adlc_forge_pr_create`; the class of the refusal is the class the classifier gives its `raw=` lines; one PR in the store.
- `test_bug292_the_class_is_a_mock_scenario`: with a store and without.
- `test_bug292_the_runners_pr_read_takes_the_class_for_no_other`: passed before the fix. It holds the new name inside the pattern the fence runner admits for a class, so the read is unverified (75) and never a bad value (65).
- `test_bug292_the_text_a_session_reads_names_the_class`: item 8a, `forge.md` and the operator reference.

`test_bug291_exec_launch_11_gaps.py`'s two tests that pinned `network` now pin `pr-already-exists`, and still hold that the mock's class is the one the classifier gives the same words.

What these cannot show.

- **No sentence was read off a live forge.** That takes opening a second PR for a head and base that have one, which was not done. What each rests on:
  - `gh`'s sentence is the format string the `gh` 2.103.3 binary holds (`a pull request for branch %q into branch %q already exists:`, read with `strings`), and so is the frame `pull request create failed: %w`.
  - GitHub's own sentence, `A pull request already exists for <owner>:<head>.`, is not in that binary: the server says it. It is as third-party code that catches it quotes it (`peter-evans/create-pull-request`, and `github/github-mcp-server` pull 2947, which calls it a 422 forwarded raw), found by a web search on 2026-11-23 whose summary was read, not the pages. GitHub's GraphQL reference does not print it.
  - `TF401179` is confirmed as this refusal only by a community PowerShell module that catches the code (`AzureDevOpsPowerShell`, `New-AzDoPullRequest.ps1`), by the same search. No Microsoft page that defines it was found. The prose after the code is BUG-291's and is unconfirmed, which is why the pattern is the code alone.
  - LESSON-780's remedy, one read-only run against the real CLI, has no read-only form here.
- **A forge that words it differently** still reads `network`, as before: a GitHub Enterprise Server release, a translated Azure DevOps organisation where the prose differs (the `TF401179` code is matched, not the prose), or a later `gh`.
- **What a session does with the class.** The stub CLIs and the mock are scripted. No real `codex` or `claude` launch has run against this, and nothing shows that a model reading `error_class=pr-already-exists` records the PR and goes on.
- **`_merge_pinned`'s row in the table above** is from reading the code. No test drives a merge that answers with this class, since no forge does.

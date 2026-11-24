---
id: BUG-294
title: "The id recheck calls this machine's own reservation a collision once the ref's commit SHA changes: the ledger identifies a reservation by SHA alone"
status: resolved
severity: medium
created: 2026-11-23
updated: 2026-11-24
component: "adlc/partials/id-recheck"
domain: "adlc"
stack: ["shell", "git"]
concerns: ["reliability", "process-compliance", "developer-experience"]
tags: ["id-recheck", "id-alloc", "own-reservation", "ledger", "reservation-ref", "nonce", "history-rewrite", "false-collision", "proceed-step-0"]
introduced_by: []
attribution: none
---

## Description

`adlc_recheck_id` (`partials/id-recheck.sh`) decides whether a reservation ref on the remote is this machine's own by looking for the line `<kind> <num> <sha>` in the own-reservation ledger (`adlc_id_own_ledger`, under `ADLC_HOME`), where `<sha>` is the SHA of the commit the ref points at. `adlc_reserve_id` (`partials/id-alloc.sh`) writes that line when its push wins.

The SHA is the only identity the ledger holds. When the ref's commit is rewritten, its SHA changes and the ledger line no longer matches. The recheck then returns 1, reports `COLLISION`, and prints an `adlc renumber` command for an id this machine reserved.

On 2026-11-01 every commit and every `refs/adlc/ids/*` ref in this repository was rewritten to remove an address from commit metadata. On 2026-11-23 `/proceed REQ-672` halted at Step 0 on its own id, whose spec was already merged under that number (LESSON-905). The owner appended the ref's new SHA to the ledger by hand.

## Reproduction Steps

In a throwaway repo with a local bare `origin`, a throwaway `HOME` and a throwaway `ADLC_HOME`:

1. Seed the counter with 700 and run `adlc_alloc_id req`. It reserves `refs/adlc/ids/req/700` and writes `req 700 <sha>` to the ledger.
2. `adlc_recheck_id req REQ-700` returns 0, with the note `self, not a collision (BUG-145)`.
3. In the bare repo, build a commit with the same tree and the same message and another address in the author and committer lines, and point `refs/adlc/ids/req/700` at it. The subject, `adlc-id-reservation kind=req num=700 nonce=<nonce>`, is unchanged.
4. `adlc_recheck_id req REQ-700` again.

## Expected Behavior

Step 4 returns 0. The reservation is the one this machine pushed: its subject still carries the nonce this machine generated for it.

## Actual Behavior

Step 4 returns 1, under bash, zsh and `/bin/sh` alike, against `main` at `da5b465`:

    COLLISION: REQ-700 already exists on the remote (<repo> (reservation ref)).
    Refusing to push a duplicate id (BR-4). Renumber before continuing:

        adlc renumber REQ-700 REQ-701

## Environment

- macOS (Darwin 27.2.0), git 2.54.0, toolkit `main` at `da5b465`.
- bash, zsh and `/bin/sh`.

## Root Cause

Prior lessons consulted:
- LESSON-905 — An identity recorded as an object SHA dies in a history rewrite: the own-reservation ledger called its own REQ a collision
- LESSON-620 — A guard that degrades only on failure cannot see a narrowed input — when the scan root defines the namespace, resolving it wrongly redefines the question instead of failing to answer it
- LESSON-846 — With git stubbed, the id allocator cannot find the main worktree and walks every repo under `/`: a test that reaches it sets ADLC_REPOS_ROOT
- LESSON-773 — A second copy of a repo walk keeps its old scope when a new kind arrives — a comment saying 'the same set' is not a link
- LESSON-626 — A rule written about one actor does not settle the case for another — bound machine conflict-resolution to a property a machine can check, and write the audit record at the moment of the event

LESSON-905 describes this failure, and the fix applies its first remedy: record something the rewrite does not touch beside the SHA, match on it, and keep the SHA as the fast path.

**The cause.** BUG-145 gave the recheck a way to recognize its own reservation: `adlc_reserve_id` appends `<kind> <num> <sha>` to the ledger, and the reservation probe in `adlc_recheck_id` passes a ref only when `grep -qxF "<kind> <num> <sha-of-the-ref>"` finds that line. The SHA was chosen because it is "precise per allocation EVENT". It is, but it names an object, not an event. A commit's SHA covers its tree, its author and committer lines and its message. Change any of them and it is another object. The 2026-11-01 rewrite changed the author and committer lines of every commit, so every reservation ref now points at a commit the ledger has never seen. The ledger lives under `ADLC_HOME`, outside the repository, and a rewrite of the repository does not reach it.

The reservation does carry an identity that survived: `adlc_reservation_nonce` builds `<epoch>-<pid>-<16 hex from /dev/urandom>` for each attempt, and `adlc_reserve_id` puts it in the commit's subject, `adlc-id-reservation kind=<k> num=<n> nonce=<nonce>`. The rewrite kept every subject. The nonce was written to the remote and nowhere else, so the recheck had nothing to compare it with.

**Attribution.** `git blame` on the probe and on the ledger writer returns two REQ candidates, REQ-546 (the line that lists the reservation ref) and REQ-654 (the line that resolves the ledger path under `ADLC_HOME`). Neither chose the SHA as the identity: the commit that did is `ee64205`, the fix for BUG-145, which is not a REQ. With two candidates `/bugfix` writes none and asks the owner, so `introduced_by` is empty until they choose.

**Fix directions weighed.**

1. *Record the nonce and match on it, SHA first.* Chosen. A ledger holds `<kind> <num> nonce=<nonce>` only on the machine that generated that nonce and won the first-wins push for that ref: the loser of a race records nothing. So a ref whose subject carries a recorded nonce for the same kind and number is this machine's reservation, whatever its SHA is now.
2. *The nonce as a fourth field on the SHA line, or as a line of its own.* A line of its own. The reader shipped since BUG-145 matches the SHA line whole (`grep -qxF "<kind> <num> <sha>"`), and a project that ran `/init` sources its own vendored `.adlc/partials/id-recheck.sh` before the toolkit's. The ledger is one file per machine. With a fourth field, every reservation made by a current allocator would be a false collision in any project whose vendored recheck is older, which is this bug again by another road. `<kind> <num> <sha>` therefore stays as it is, and `<kind> <num> nonce=<nonce>` follows it. `nonce=` is not hex, so the line cannot be taken for a SHA line.
3. *How the recheck learns the subject.* `git ls-remote` returns the ref's SHA and nothing else, so the commit has to be fetched: one root commit on the empty tree. The fetch names the ref and no destination, takes no tags, writes no `FETCH_HEAD`, runs no hook, starts no maintenance and, with `--refmap=`, updates no tracking ref a configured refspec would map the reservation to. It happens only when the SHA did not match and the ledger holds a nonce for that kind and number. A forge API call would avoid the fetch and break the allocator's rule of pure git transport (REQ-546 BR-6).
4. *Accept on kind and number alone.* Rejected. Req, bug and lesson ids are one namespace across every repo on a machine, and each reservation goes to the origin of the repo it was made in. Two machines can both win the same number on two origins, and each then holds a ledger entry for it. The entry says "I reserved this number somewhere", not "that ref is mine".
5. *Old three-field lines.* They keep working exactly as before: the SHA match is tried first and is unchanged. One whose ref was rewritten cannot be proven by the recheck, because the ledger has no nonce for it, and it stays a collision. A rescue was considered: where the commit the ledger names still exists in the working copy's object store, read the nonce from it. On this machine 30 of the 171 affected refs could be proven that way today. It was not built in: those commits are unreachable, so `git gc` removes them, and the same recheck would then pass in one clone and halt in another. The halt instead says what the ledger knows (below).
6. *Healing the ledger.* The recheck could append the ref's new SHA once the nonce has proven it. It does not: the recheck has never written machine state, and the nonce match needs no help on the next run.

**What the nonce does not defend.** The nonce is in a commit subject on the remote, so anyone who can read the repository can read it. Someone with push access could delete this machine's reservation ref and push another commit with the same subject, and the recheck would accept it. The same person could simply delete the ref. The reservation protects against two honest allocators choosing one number, through first-wins ref creation, and that is unchanged.

**Validation.** Re-reading the two paths confirmed the cause and turned up two smaller things in the same block, both handled in the fix:

- The probe tested the ledger for a symlink and then read it in the same `[ ... ] && grep` chain. With a second match to make, the ledger is now read once, into a variable, behind the one symlink test, so the two matches cannot see different files (LESSON-014).
- The halt message needs to know whether the ledger held an entry for the id. That is a global, and a global outlives a call in the same shell (LESSON-773), so it is reset at the top of every call.

**The two shell copies and the other readers.**

- `partials/id-alloc.sh` writes the ledger (`adlc_record_own_reservation`, called by `adlc_reserve_id`) and builds the subject. `partials/id-recheck.sh` reads both. The reader calls nothing new from `id-alloc.sh`, only `adlc_id_own_ledger`, which has existed since BUG-145, so a current recheck beside an older vendored `id-alloc.sh` still loads and falls back to the SHA match. `partials/tests/id-recheck-rewrite.test.sh` runs the writer and the reader together, so a change to the subject or the ledger line on one side fails it.
- `tools/adlc/renumber.py` reserves through `adlc_reserve_id` in a shell, so its reservations get the nonce line with no change of its own. `tools/adlc/tests/test_renumber.py` now asserts both lines.
- `tools/adlc/migrate_home.py` merges two ledgers as a union of whole lines and never parses one, so the new line needs nothing there. `tools/adlc/home_layout.py` only names the file.
- A symlinked ledger: the writer refuses it, the reader refuses it for the SHA match and for the nonce match, and `migrate_home.py` moves the file rather than linking it. Section 5 of the new test pins the first two.

## Resolution

`partials/id-alloc.sh`:

- `adlc_reserve_id` generates the nonce into a variable, puts it in the subject as before, and passes it to `adlc_record_own_reservation`.
- `adlc_record_own_reservation <kind> <num> <sha> [<nonce>]` appends `<kind> <num> <sha>` and, given a nonce, `<kind> <num> nonce=<nonce>`, in one `printf`. Without the fourth argument it writes the one line it always did.

`partials/id-recheck.sh`:

- `_adlc_rc_reservation_nonce <repo> <kind> <num> <sha>` prints the nonce of the reservation commit, or nothing. It passes the SHA to git only when it is a full hex object name, fetches the ref's commit when the working copy lacks it, reads the commit with `git cat-file commit`, and accepts only a message whose first line is exactly `adlc-id-reservation kind=<kind> num=<num> nonce=<nonce>` for the kind and number being rechecked, with a nonce made of digits, `a-f` and `-`.
- The reservation probe reads the ledger's lines for the kind and number once. A whole-line SHA match is self, as before. Otherwise, when the ledger holds a nonce line for the id, the ref's nonce is read and a whole-line match on `<kind> <num> nonce=<nonce>` is self, with a note that names BUG-294. Anything else is a collision.
- When the collision is a reservation ref and the ledger held any line for the id, the halt adds a `NOTE`: the ledger holds an entry for the id, nothing in it proved the ref, and the ref's commit should be read before renumbering. The return code is still 1.

`--no-write-fetch-head` and `--no-auto-maintenance` need git 2.29 (October 2020). With an older git the fetch fails, no nonce is read, and the recheck halts as it did before the fix.

Weighed and not done:

- **The ids already affected.** The fix cannot clear a reservation recorded before it, because the ledger holds no nonce for it. See "Reservations already on the remote" below. No ledger entry was repaired: the only write to the real machine state was the allocation of this bug's own id, which every `/bugfix` run makes.
- **Vendored copies.** A project that ran `/init` keeps its own `.adlc/partials/id-alloc.sh` and `id-recheck.sh` until it is re-synced. Its allocator records no nonce until then, and its recheck ignores the nonce lines a current allocator writes. No consumer project was touched.
- **The frozen fixture** `partials/tests/fixtures/id-alloc-pre-req-654.sh` is a copy of the allocator as it was, and stays as it was.
- **`/proceed` and `/wrapup` text.** No skill text changes: the call sites and the return codes are the same. The exec engine's fence census does change, by one command: the recheck now runs `git cat-file`, so the two census goldens were regenerated.

## Reservations already on the remote

Read on 2026-11-23 with `git ls-remote origin 'refs/adlc/ids/*'` against `atelier-fashion/adlc-toolkit`, and the machine's ledger read-only. The ledger had 1374 lines, all three-field.

| kind | refs | ledger SHA matches | ledger entry, SHA differs | no ledger entry |
|---|---|---|---|---|
| req | 37 | 9 | 28 | 0 |
| bug | 46 | 20 | 26 | 0 |
| lesson | 124 | 33 | 89 | 2 |
| assume | 34 | 6 | 28 | 0 |
| all | 241 | 68 | 171 | 2 |

So 171 reservation refs would be reported as a collision by a recheck of their id, before this fix and after it. The two lesson refs with no entry, 765 and 766, were reserved by something this ledger never recorded, and are a collision by design.

How many of the 171 will be rechecked is smaller. A bug, lesson or assumption id is rechecked once, in the run that allocates it. A REQ id is rechecked again by `/proceed` Step 0. Of the 28 REQs: 20 have a spec marked `complete`, REQ-602 is `cancelled`, REQ-604 has no spec directory on `main`, and six are `in-progress`: REQ-655, 656, 658, 659, 662 and 663. Those six halt at Step 0 if `/proceed` is run on them again.

What the refs themselves say, read with the fix's `_adlc_rc_reservation_nonce` against the real remote:

- All 171 point at a commit whose first message line is a well-formed reservation subject for the ref's own kind and number. The rewrite kept every subject, as LESSON-905 found for REQ-672.
- For 30 of them (2 bug, 16 lesson, 12 assume, no req) the commit the ledger names still exists in this checkout's object store and carries the same nonce as the ref. That is proof the ref is this machine's reservation. Those commits are unreachable, so the proof lasts until the next `git gc` prunes them.
- For the other 141, all 28 REQs among them, the old commit is gone. The ledger line and the ref share the kind and the number and nothing else that can be checked here.

Reading those commits fetched 171 small objects into the checkout's object store. It changed no ref and nothing under the machine's state home.

Clearing an affected id means appending its ref's current SHA to the ledger, as was done for REQ-672. That is the owner's decision, id by id or in one pass, and is not part of this fix.

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`).

A failing-first test was still written, as the task asked: `partials/tests/id-recheck-rewrite.test.sh`, a new harness that cites BUG-294 and is listed in `partials/tests/run.sh`. It was written and run before any of the fix.

- Command run: `env -i PATH=… HOME=<throwaway> USER=… LOGNAME=… TMPDIR=… <shell> partials/tests/id-recheck-rewrite.test.sh`, under bash, zsh and `/bin/sh`. The harness sets its own `ADLC_HOME` and `ADLC_REPOS_ROOT` per machine, under a `mktemp` directory.
- Without the fix: fails, rc 1, 30 cases pass and 12 fail, in each of bash, zsh, `/bin/sh` and dash. The first failing assertion: `FAIL: BUG-294: own reservation rechecks clear after its commit was rewritten (expected '0', got '1')`.
- With the fix: passes, rc 0, 42 of 42 in each of the four shells.

The first run, before any of the fix, was 27 passing and 10 failing with the same first assertion. Five cases were added after an adversarial review of the fix (below), and the final file was run again against the two partials as they are at `da5b465`, which gives the 30 and 12.

The twelve cases that fail without the fix: the rewritten req reservation rechecks clear, is reported as self, and prints no `COLLISION`; it rechecks clear again after a second rewrite; the ledger records the nonce, for req 700 and for req 701; the ledger holds two lines for the id; the two halts that name the ledger entry; the rewritten reservation clears once a symlinked ledger is a regular file again; and a rewritten bug reservation rechecks clear and is reported as self.

The cases that pass before and after pin the fix from the other side. Each of these is rc 1:

- the colleague's machine, with no ledger entry, after the rewrite;
- a colleague's reservation of the same id, with their own nonce, while this machine's ledger holds lines for that kind and number;
- this machine's nonce in a subject for another number, and for another kind;
- a nonce the ledger holds for req 701, in the subject of req 700's ref;
- ledger lines for req 70, req 7000 and bug 700 that carry the ref's SHA and nonce, against req 700;
- a nonce that is a prefix of the recorded one, one that extends it, one followed by more text, and the pattern `.*` in its place;
- this machine's nonce on a later line of the commit message;
- a three-field line whose ref was rewritten;
- a symlinked ledger, by SHA and by nonce.

And: a three-field line still clears its own reservation by SHA; the allocator writes nothing through a symlinked ledger; the recheck creates no ref in the working copy and no `FETCH_HEAD`, also when `remote.origin.fetch` maps every remote ref to a tracking ref.

**Adversarial review.** A read-only adversary agent attacked the diff and the test before the commit. It found no way to get a false "self". Its four findings were all applied:

- with `remote.origin.fetch` set to `+refs/*:refs/remotes/origin/*`, the fetch created a tracking ref for the reservation, in a repo the recheck only walks. `--refmap=` stops that, and a case pins it: with the flag removed, that case fails;
- `gc.auto=0` did not stop the other maintenance tasks a fetch can start. `--no-auto-maintenance` does. No case pins this one;
- no case tied the nonce to its number. The req 701 and the req 70, req 7000 and bug 700 cases above do;
- the halt's `NOTE` said the commit matched no nonce when it might not have been read at all. It now says nothing recorded proved the ref.

The wider runs, all on the final tree, each under a throwaway `HOME` and `ADLC_HOME` built with `env -i`:

- `sh partials/tests/run.sh`: rc 0, 9957 cases pass, 0 fail, 26 harnesses under each of bash, zsh, `/bin/sh` and dash.
- `sh tools/lint-skills/check.sh`: rc 0.
- `python3 -m pytest tools -q`: 5892 passed, 7 skipped, 0 failed. That is all 5899 collected tests, in all 126 files. It was not one command: one process takes over an hour on this machine, so the file list was run as eight parallel processes. One of the eight failed at collection for a reason of the split (with files from several test directories on one command line, `from conftest import TOOLKIT` resolved to another directory's `conftest`), and its 16 files were run again, one directory per process.

An earlier single-process run was stopped at 29% with five failures. All five were the tests that hold the fence census goldens fresh, and all five pass since the goldens were regenerated.

The real ledger and the three counters were hashed before and after these runs. The one change was a `bug 295` line, with the bug counter, from another session's allocation during the runs; that ref is on the remote.

What was not measured:

- **Linux.** Every run was on macOS, with git 2.54.0.
- **A git older than 2.29.** That the fetch fails there and the recheck halts as before was read in the code, not run.
- **`/proceed` Step 0 end to end** against the real remote with a ledger that holds a nonce. No reservation recorded with a nonce has been rewritten there. The nonce reader was run against the real remote and read the nonce of all 171 affected refs.

## Files Changed

- `partials/id-alloc.sh` — `adlc_reserve_id` keeps the nonce and passes it on; `adlc_record_own_reservation` writes the nonce line after the SHA line; the ledger's header comment says why it is two lines.
- `partials/id-recheck.sh` — `_adlc_rc_reservation_nonce`; the reservation probe matches by SHA, then by nonce; the halt's `NOTE`; the header's account of self-identification.
- `partials/tests/id-recheck-rewrite.test.sh` — new harness, 42 cases.
- `partials/tests/run.sh` — runs the new harness, on a line of its own.
- `tools/adlc/tests/test_renumber.py` — `test_reserve_new_id_won_pushes_ref` asserts the SHA line and the nonce line.
- `harness/claude/exec-fence-census.json`, `harness/codex/exec-fence-census.json` — regenerated with `fence_census.py --write`. One line each: the `/wrapup` lesson-recheck fence now reaches `git cat-file`. Its route is still `runner`, and `git fetch` was in its reach already.
- `CHANGELOG.md` — the entry under Unreleased, Fixed.
- `.adlc/bugs/BUG-294-recheck-false-collision-after-ref-rewrite.md` — this report.

## Deployment

- Merged to `main` on 2026-11-23 as `34a0525`, the squash of PR #326. The regression gate reported `off` for this project before the merge.
- No staging or production service: the toolkit is installed from a checkout. A machine has the fix once its toolkit checkout is at `34a0525` or later. A project that vendored `.adlc/partials/` has it once the project is re-synced.
- The lesson from the fix is LESSON-907.

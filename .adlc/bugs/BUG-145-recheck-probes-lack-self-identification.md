---
id: BUG-145
title: "id-recheck probes cannot self-identify — own reservation refs and own merged spec dirs are reported as collisions"
status: open
severity: high
created: 2026-07-23
updated: 2026-07-23
component: "adlc/skills"
domain: "adlc"
stack: ["bash", "git"]
concerns: ["correctness", "concurrency", "multi-user"]
tags: ["id-recheck", "reservation-ref", "self-collision", "false-positive", "renumber-treadmill", "lesson-435"]
---

## Description

`adlc_recheck_id`'s three probes (pushed branch / merged artifact / reservation
ref) are number-keyed presence checks with no way to distinguish a footprint
owned by the current work item or allocator from a colleague's duplicate
(the LESSON-435 class). Two live false-positive instances:

1. **Own reservation ref (all four kinds).** REQ-546 makes every allocation
   push `refs/adlc/ids/<kind>/<NNN>`; the recheck's reservation probe then
   finds the allocator's OWN reservation and reports COLLISION. Every
   `/bugfix` Phase-1 recheck and every `/bugfix`/`/wrapup` lesson recheck now
   false-halts, and the suggested `adlc renumber` to N+1 would itself
   reserve-then-collide — an infinite renumber treadmill.
2. **Own merged spec dir (req kind).** The `/proceed` Step-4 recheck
   (REQ-545) fires after the REQ's spec has merged to the default branch —
   which is the NORMAL flow (spec PR merges before implementation). The
   merged-artifact probe finds the REQ's own `.adlc/specs/REQ-xxx-*/` dir and
   halts. The REQ-545 BR-3 self-exemption covers only the own-branch case.
   Latent in the partial since REQ-518 (no req-kind caller existed); activated
   by REQ-545's wiring.

`tools/adlc/renumber.py` is NOT affected: `remote_collision(new_id)` runs
before `reserve_new_id(new_id)`.

## Reproduction Steps

1. Allocate an id (pushes a reservation): `N=$(adlc_alloc_id lesson)`
2. Recheck it: `adlc_recheck_id lesson "LESSON-$N"` → rc=1,
   `COLLISION ... (reservation ref)` — reproduced live with LESSON-434..439
   and BUG-145 itself on 2026-07-23.
3. For instance 2: with `.adlc/specs/REQ-546-*/` merged on `origin/main` and
   no live `feat/REQ-546-*` branch, `adlc_recheck_id req REQ-546` → rc=1,
   `COLLISION ... (merged artifact)` — reproduced live 2026-07-23.

## Expected Behavior

A recheck hit on a footprint the current work item / this machine's allocator
legitimately owns is self, not a collision: own reservation → proceed; own
merged spec dir (identical full artifact name) → proceed. Hits owned by
anyone else (different reservation object, different artifact name at the
same number) remain collisions.

## Actual Behavior

rc=1 COLLISION with a renumber instruction for the work item's own footprint;
following the instruction produces a fresh reservation that collides again.

## Environment

- Platform: macOS (Darwin 25.5.0), zsh executor; partial is sh/bash/zsh-portable
- Version: toolkit main @ 9f3be94 (post REQ-545/REQ-546 merge)

## Root Cause

Probes key on the numeric id alone. Self-identity requires data the partial
never had: (1) which reservation objects THIS machine pushed — `adlc_alloc_id`
discards the object SHA after a won push; (2) the caller's own artifact name —
`adlc_recheck_id` takes only `<kind> <ID>`, and the artifact scan surface
returns bare numbers, so a same-number hit cannot be compared by name.

## Resolution

Gave the probes the self-identification data they lacked, in the safe
direction (missing data always degrades to the historical collision halt):

1. **Own-reservation ledger.** `adlc_reserve_id` now records every WON push to
   `~/.claude/.adlc-own-reservations` (`<kind> <num> <sha>`, symlink-guarded —
   LESSON-014 parity). The recheck's reservation probe captures the remote
   ref's object SHA and treats an exact whole-line ledger match as self. SHA
   equality is precise per allocation *event* — a colleague's reservation, or
   this user's from another machine, never matches.
2. **Own-artifact name argument.** `adlc_recheck_id` accepts an optional third
   arg — the caller's own full artifact name. On a same-number merged-artifact
   hit, the scan re-lists in a new `names` mode (`adlc_id_artifact_filter`,
   threaded through `adlc_remote_artifact_nums`/`adlc_remote_git_artifact_nums`
   as an optional mode param — one shared surface, REQ-523 BR-6 preserved) and
   the hit is self only when every same-number entry equals the own name
   (awk maximal-munch number filter — prefix-sibling safe). The `/proceed`
   Step-4 call site now derives and passes its spec dir basename; pre-merge
   callers (`/bugfix`, `/wrapup`) are unchanged — their self case is the
   reservation, covered by the ledger with no arg.

Migration note: reservations pushed before this fix have no ledger entries and
would still self-collide; this machine's pre-fix entries (lesson/434–439,
bug/145, req/545–546) were backfilled one-time from `ls-remote` SHAs.

Verified: 6 new matrix cases green under bash + zsh (own-reservation clear,
other-machine still collides, wiped-ledger degrades to collision, own-artifact
clear, different-name still collides, no-arg conservative halt, prefix-sibling
name filter), full `partials/tests/run.sh` green, lint clean, plus live
verification against the real GitHub remote: `adlc_recheck_id req REQ-546
REQ-546-atomic-remote-id-reservation` → self/CLEAR, and LESSON-434 with
own-name → artifact-self then reservation-self → CLEAR.

## Files Changed

- `partials/id-alloc.sh` — own-reservation ledger (`adlc_id_own_ledger`,
  `adlc_record_own_reservation`, recorded on won push); `names` mode on the
  shared artifact scan (`adlc_id_artifact_filter`, mode param threading)
- `partials/id-recheck.sh` — optional own-artifact-name arg; artifact-probe
  full-name self compare; reservation-probe ledger SHA self compare; contract
  header updated
- `proceed/SKILL.md` — Step-4 recheck call site derives `OWN_SPEC_DIR` and
  passes it (closes the merged-spec false halt for the normal flow)
- `partials/tests/id-alloc.test.sh` — BUG-145 cases (self-reservation,
  other-machine, wiped ledger, own/foreign/no-arg artifact, prefix-sibling)

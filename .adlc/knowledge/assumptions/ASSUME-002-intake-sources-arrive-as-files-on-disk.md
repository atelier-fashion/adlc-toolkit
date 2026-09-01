---
id: ASSUME-002
title: "Unstructured intake sources arrive as text files on disk"
status: invalidated
req: REQ-594
created: 2026-08-27
resolved: 2026-08-31
---

## Assumption

From REQ-594's Assumptions section:

> Unstructured sources arrive as text files on disk. Audio, video, and live meeting
> capture are not inputs to this REQ (see Out of Scope).

## Context

The assumption was written to bound scope — to exclude transcription, audio ingestion,
and live-capture connectors. That bounding is correct and still holds.

But the same sentence was read, during architecture and implementation, as a guarantee
about the *shape of the input*: that intake would always be handed a path. Every step
after activation was built file-based on that basis — segmentation, the budget check,
the corpus handed to the delegate, and the direct re-read of any segment the delegate
omitted.

## Resolution

**Invalidated by the REQ's own BR-1.** BR-1 activates intake on any of three conditions,
and the third — `$ARGUMENTS` exceeding 25 lines — is text pasted straight into the
prompt. It has no path. So the spec simultaneously assumed sources are files and defined
a trigger for sources that are not.

Caught in the Phase 5 verify pass, not by spec or architecture validation: both rules
read correctly in isolation, and the defect lived in the seam between them. Trigger (c)
failed one step after firing, with `segment rc=2 "source not readable: <empty>"` — the
entire branch was dead on arrival.

**Resolution taken:** normalize at the boundary rather than teach every downstream step
two shapes. `adlc_intake_detect` now materializes pasted text into a private temp file
named `inline-request.txt`, and exports `ADLC_INTAKE_INLINE=1` so cleanup knows the file
is intake's to delete (a user-supplied source never is). `ADLC_INTAKE_PATH` is therefore
always a real file on the intake path, and the assumption the implementation depends on
is now *made true* by construction instead of merely asserted.

The scope-bounding half of the original assumption is untouched and still correct:
audio, video, and live capture remain out of scope.

Generalized as LESSON-606.

"""REQ-691 TASK-241 — /bugfix's regression-test protocol, held structurally.

The protocol lives in ``bugfix/references/regression-test.md`` (ADR-691-G) and
``bugfix/SKILL.md`` sends the model there from five steps. A live ``/bugfix`` run
is what produces the test, the record and the gate (AC-1 to AC-4, AC-12); this
file pins the text that makes the model produce them: where each pointer sits,
the order the companion gives the steps in, the fields and verdicts it names,
and the mode read at the head of every section (ADR-691-H). The engine's rules
are tested in ``tools/adlc/tests/test_regression_check.py`` and the wrapper's in
``partials/tests/regression-check.test.sh``.

Both files are read by path from the repo root, as ``test_lessons_contract.py``
reads its skills. Markers and fences are found by whole lines outside fenced
blocks, never by a substring a prose mention could also carry (LESSON-404).
"""

import json
import os
import re
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SKILL = "bugfix/SKILL.md"
COMPANION = "bugfix/references/regression-test.md"
SECTIONS = ("Mode", "Write and contrast", "Record", "PR body", "Gate")

SOURCE = ('if [ -f .adlc/partials/regression-check.sh ]; then . .adlc/partials/regression-check.sh; '
          'else . "$ADLC_TOOLKIT_ROOT/partials/regression-check.sh"; fi')
MODE_CALL = 'adlc_regression_check mode; echo "regression_mode_rc=$?"'
UNIT_POINTER = "Read `bugfix/references/regression-test.md` and follow it before you continue."
SECTION_POINTER = "Read the `{}` section of `bugfix/references/regression-test.md` and follow it before you continue."
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as handle:
        return handle.read()


def _section(text, start, end):
    a = text.index(start)
    b = text.index(end, a + len(start))
    return text[a:b]


def _root_line():
    """The canonical root line, taken from conventions.md rather than copied here."""
    for line in _read(".adlc/context/conventions.md").splitlines():
        if line.startswith('ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"'):
            return line
    raise AssertionError("conventions.md carries no root line")


def _fenced_line_numbers(lines):
    """Indices of every line inside a fenced block, the fence lines included."""
    inside, marker, out = False, "", set()
    for i, line in enumerate(lines):
        m = FENCE_RE.match(line)
        if not inside and m:
            inside, marker = True, m.group(1)
            out.add(i)
        elif inside:
            out.add(i)
            if line.strip().startswith(marker[0] * len(marker)) and line.strip().strip(marker[0]) == "":
                inside = False
    return out


def _companion_sections():
    """``## `` headings of the companion, outside fences, mapped to their text."""
    lines = _read(COMPANION).splitlines()
    fenced = _fenced_line_numbers(lines)
    heads = [(i, line[3:].strip()) for i, line in enumerate(lines)
             if i not in fenced and line.startswith("## ")]
    out = {}
    for n, (i, name) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        out[name] = "\n".join(lines[i:end])
    return out


def _sh_fences(text):
    """The bodies of the ```sh fences in ``text``, each a list of its lines."""
    fences, body = [], None
    for line in text.splitlines():
        if body is None:
            if re.match(r"^\s*```(sh|bash|shell)\b", line):
                body = []
        elif line.strip() == "```":
            fences.append(body)
            body = None
        else:
            body.append(line)
    return fences


def _step6(text):
    """``/bugfix`` Step 6 to the next ``## `` heading outside a fence, sliced as
    ``partials/tests/lesson-check.test.sh`` slices it."""
    out, started, inside = [], False, False
    for line in text.splitlines():
        if line.startswith("**Step 6 "):
            started = True
        if not started:
            continue
        if line.lstrip().startswith("```"):
            inside = not inside
        elif not inside and line.startswith("## "):
            break
        out.append(line)
    return "\n".join(out)


def _run_gate_guard(value):
    """Run the Gate fence with the placeholder substituted as conventions.md says
    (one single-quoted literal, each ``'`` written ``'\\''``) and the engine
    replaced by a stub that names its arguments. Returns stdout."""
    fence = _sh_fences(_companion_sections()["Gate"])[0]
    assert fence[0] == _root_line() and fence[1] == SOURCE, fence[:2]
    body = "\n".join(fence[2:])
    assert body.count("'<bug-id>'") == 1, body
    literal = "'" + value.replace("'", "'\\''") + "'"
    stub = 'adlc_regression_check() { echo "STUB-CALLED: $*"; return 0; }\n'
    script = stub + body.replace("'<bug-id>'", literal)
    result = subprocess.run(["/bin/sh", "-c", script], capture_output=True, text=True, timeout=30)
    return result.stdout


def test_mode_read_before_phase_1():
    """BR-1, BR-17, AC-3: the mode is read before Phase 1, an error stops there,
    and an unreadable setting is never off."""
    skill = _read(SKILL)
    prereq = _section(skill, "## Prerequisites", "### Phase 1: Report")
    assert UNIT_POINTER in prereq
    assert "its `Mode` section reads `bugfix.regression_test` now, before Phase 1" in prereq
    assert "a setting it cannot read stops `/bugfix` here" in prereq
    assert skill.index(UNIT_POINTER) < skill.index("### Phase 1: Report")
    context = _section(skill, "## Context", "## Input")
    assert "read .adlc/config.yml before Phase 1" in context
    assert "before Step 1" not in context

    sections = _companion_sections()
    assert list(sections) == list(SECTIONS)
    companion = _read(COMPANION)
    assert "Companion to `bugfix/SKILL.md`" in companion
    assert "| Prerequisites, before Phase 1 | Mode |" in companion
    mode = sections["Mode"]
    assert _sh_fences(mode)[0] == [_root_line(), SOURCE, MODE_CALL]
    fence_end = mode.index("```\n", mode.index("```sh") + 5)
    required = mode.index("- `regression-test: required` (rc 0)")
    off = mode.index("- `regression-test: off` (rc 0)")
    error = mode.index("- `regression-test: error` (rc 2)")
    assert fence_end < required < off < error
    stop = mode[error:]
    assert "stop `/bugfix` here, before Phase 1, and show the second line as printed" in stop
    assert "the allowed values `required` and `off`" in stop
    assert "An error is never `off`" in stop and "do not choose a mode yourself" in stop
    assert "Any other output, or none, is an error as well." in mode


def test_write_and_contrast_section():
    """BR-2, BR-4: Phase 3 sends the model to the test-first protocol before the
    fix, and the protocol says what the test exercises and how it cites the bug."""
    phase3 = _section(_read(SKILL), "### Phase 3: Fix", "### Phase 4: Verify")
    pointer = SECTION_POINTER.format("Write and contrast")
    assert pointer in phase3
    assert phase3.index(pointer) < phase3.index("3. Implement the fix")
    assert "5. Update related test files if the fix changes behavior" in phase3  # BR-8 unchanged

    wc = _companion_sections()["Write and contrast"]
    assert _sh_fences(wc)[0] == [_root_line(), SOURCE, MODE_CALL]
    step1 = _section(wc, "1. **Write the regression test before any of the fix.**", "\n2. **")
    assert "exercises the root cause in the bug report's Root Cause section" in step1
    assert "asserts the expected behavior (BR-2)" in step1
    assert "Updating an existing test counts when the updated case reproduces the bug" in step1
    assert "`BUG-nnn`" in step1
    for where in ("in the test name", "in the describe or suite title", "in a comment next to the case"):
        assert where in step1, where
    # The seam lands first, as its own behaviour-preserving change, and is not the fix.
    assert "land the seam first, on its own" in step1
    assert "behavior-preserving change" in step1 and "The seam is not the fix." in step1
    step2 = _section(wc, "2. **Run the test against the unfixed tree.", "\n3. **")
    assert "**It fails to load**" in step2 and "That is a weak contrast" in step2
    assert "the PR body flags it" in step2


def test_failing_run_recorded_before_fix():
    """BR-3, AC-4 (ADR-691-E): the test is written and its failing run kept before
    the fix is written; a test that passes without the fix is never recorded."""
    wc = _companion_sections()["Write and contrast"]
    anchors = [
        "1. **Write the regression test before any of the fix.**",
        "2. **Run the test against the unfixed tree. It must fail on an assertion.**",
        "keep the exact command and the first failing assertion line",
        "it is never recorded as the regression test (BR-3, AC-4)",
        "3. **Only then write the fix**",
        "4. **Run the regression test(s) again, with the fix in place. They must pass.**",
    ]
    at = [wc.index(a) for a in anchors]
    assert at == sorted(at), list(zip(anchors, at))
    # No step tells the model to write the fix before step 3 does.
    steps = wc[at[0]:]
    assert steps.lower().index("write the fix") == steps.index("3. **Only then write the fix**") + len("3. **Only then ")
    passes = _section(wc, "**It passes.**", "**It fails to load**")
    assert "Rewrite it against the root cause" in passes and "waive the bug instead" in passes


def test_record_section_names_fields():
    """BR-5, BR-7, AC-1: Phase 4 records the tests or a waiver, in the shapes the
    readers need, never both, spelled out in full for an older vendored template."""
    phase4 = _section(_read(SKILL), "### Phase 4: Verify", "### Phase 5:")
    pointer = SECTION_POINTER.format("Record")
    assert phase4.index("3. Update the bug report") < phase4.index(pointer) < phase4.index("4. Present an interim summary")
    assert "1. Run the test suite" in phase4  # BR-8: the suite still runs

    rec = _companion_sections()["Record"]
    assert _sh_fences(rec)[0] == [_root_line(), SOURCE, MODE_CALL]
    assert "LESSON-603" in rec and "whatever the template holds" in rec
    tests_line = re.search(r"`(regression_tests: \[[^`\n]*\])`", rec)
    assert tests_line, "no flow-list regression_tests example"
    value = json.loads(tests_line.group(1).split(": ", 1)[1])
    assert value and all(isinstance(v, str) for v in value)
    assert "Never write a block list" in rec
    assert "`<repo-id>:<path>`" in rec and "(BR-14)" in rec
    waiver_line = re.search(r'`(regression_waiver: "[^"`\n]+")`', rec)
    assert waiver_line, "no double-quoted regression_waiver example"
    assert "double-quoted, because a plain value is cut at the first ` #`" in rec
    body = _section(rec, "fill the body section `## Regression Test`", "**No test can reproduce the bug.**")
    for item in ("- Test path(s):", "- Command run:", "- Without the fix: fails — the first failing assertion line",
                 "- With the fix: passes"):
        assert item in body, item
    assert "never both (BR-7)" in rec
    assert "The regression check fails a bug that has both." in rec


def test_waiver_reaches_pr_body_and_summary():
    """BR-6: a waiver needs a reason, and the waiver and its reason reach the PR
    body and the Phase 6 summary."""
    sections = _companion_sections()
    rec = sections["Record"]
    assert "A waiver needs a reason" in rec
    assert "an empty or whitespace-only `regression_waiver` is no waiver at all (BR-6)" in rec
    assert "write `Waived: <the reason>` in `## Regression Test`" in rec

    pr = sections["PR body"]
    assert _sh_fences(pr)[0] == [_root_line(), SOURCE, MODE_CALL]
    assert "between `## Files Changed (this repo)` and `## Test Plan`" in pr
    assert "- `required`, waived: `Waived:` and the reason from `regression_waiver`, word for word (BR-6)." in pr
    assert "`Weak contrast: without the fix the test failed to load, not on an assertion.`" in pr

    skill = _read(SKILL)
    phase5 = _section(skill, "### Phase 5:", "### Phase 6:")
    pointer = SECTION_POINTER.format("PR body")
    assert phase5.index(pointer) < phase5.index("- **Body**:")
    files = phase5.index("     ## Files Changed (this repo)")
    slot = phase5.index("     ## Regression Test")
    plan = phase5.index("     ## Test Plan")
    assert files < slot < plan
    assert "the waiver and its reason" in phase5[slot:plan]

    step6 = _step6(skill)
    assert "### Regression test" in step6 and "Waived: <reason>" in step6
    assert step6.index("### Regression test") < step6.index("### Lessons captured")
    assert "NO_ENTRY: <reason>" in step6  # lesson-check.test.sh's Step 6 contract
    phase4 = _section(skill, "### Phase 4: Verify", "### Phase 5:")
    assert "- Regression test: the tests and their contrast, the waiver, or off for this project" in phase4


def test_off_mode_at_every_site():
    """BR-8, AC-2: every section reads the mode in its own first fence and says
    what off does there; the summary says off and names the key when it is absent."""
    root_line = _root_line()
    sections = _companion_sections()
    for name in SECTIONS:
        sec = sections[name]
        fences = _sh_fences(sec)
        assert fences, name
        first = fences[0]
        assert first[:2] == [root_line, SOURCE], name
        if name == "Gate":
            assert any("adlc_regression_check check --require-recorded" in line for line in first), name
            off = "- `regression-check: off` (rc 0)"
        else:
            assert first[2] == MODE_CALL, name
            off = "- `regression-test: off`" if name != "PR body" else "- `off`: one line"
        # The mode read heads the section: nothing about off comes before it.
        assert sec.index("```sh") < sec.index(off), name

    mode = sections["Mode"]
    assert "write neither `regression_tests` nor `regression_waiver`" in mode
    assert "Phase 3 still updates related tests when the fix changes behavior" in mode
    assert "Phase 4 still runs the suite (BR-8)" in mode
    assert "When that line says the key is not set, or that there is no `.adlc/config.yml`" in mode
    assert "names the key that turns them on, `bugfix.regression_test: required`" in mode
    assert "- `regression-test: off`: skip this section." in sections["Write and contrast"]
    assert "- `regression-test: off`: write neither field" in sections["Record"]
    assert "- `off`: one line, `Regression tests: off for this project.`" in sections["PR body"]
    assert "there is nothing to gate. Continue to Step 1." in sections["Gate"]

    skill = _read(SKILL)
    assert "`off` skips them all" in _section(skill, "## Prerequisites", "### Phase 1: Report")
    for start, end, name in (("### Phase 3: Fix", "### Phase 4: Verify", "Write and contrast"),
                             ("### Phase 4: Verify", "### Phase 5:", "Record")):
        phase = _section(skill, start, end)
        pointer = phase.index(SECTION_POINTER.format(name))
        line_end = phase.index("\n", pointer)
        assert "skip it when the mode is `off`" in phase[pointer:line_end], name
    step6 = _step6(skill)
    assert "off for this project" in step6
    assert "when the key is not set" in step6
    assert "set bugfix.regression_test: required in .adlc/config.yml to turn them on" in step6


def test_gate_before_merge():
    """BR-13, AC-12 (ADR-691-F): the gate runs before Phase 6 merges, validates
    the id before the check, and stops unmerged and unresolved on anything but
    a pass or off."""
    skill = _read(SKILL)
    phase6 = _section(skill, "### Phase 6:", "## Branch Naming")
    order = [
        "**Step 0 — Regression gate**",
        SECTION_POINTER.format("Gate"),
        "**Step 1 — Merge each PR.**",
        "adlc_forge_pr_merge <prUrl> --squash --delete-branch",
        "- Set status to `resolved`",
    ]
    at = [phase6.index(a) for a in order]
    assert at == sorted(at), list(zip(order, at))
    assert "in the fix worktree" in phase6[at[0]:at[2]]
    assert "stops `/bugfix` here, with nothing merged and the bug unresolved" in phase6[at[0]:at[2]]

    gate = _companion_sections()["Gate"]
    assert "| Phase 6 Step 0, before Step 1 merges | Gate |" in _read(COMPANION)
    assert "Run the fence from the root of the checkout that holds the fix branch" in gate
    text = "\n".join(_sh_fences(gate)[0])
    assert "rgt_bug='<bug-id>'" in text
    assert text.index('case "$rgt_bug" in') < text.index('adlc_regression_check check --require-recorded "$rgt_bug"')
    for outcome in (
        "- `regression-check: pass` (rc 0): continue to Step 1, the merge.",
        "- `regression-check: fail` (rc 1): stop before merging. Merge no PR and do not set the bug `resolved` (AC-12).",
        "Show the engine's `BUG-nnn:` lines as printed",
        "- `regression-check: error`, or `regression_gate_rc=2` from the id refusal: stop exactly as for `fail`.",
    ):
        assert outcome in gate, outcome
    assert "turns a bug that recorded neither tests nor a waiver from legacy into failed (BR-13)" in gate

    # The id guard, run: a valid id reaches the check, anything else never does.
    for good in ("BUG-123", "BUG-1234", "BUG-12345", "BUG-123456"):
        out = _run_gate_guard(good)
        assert f"STUB-CALLED: check --require-recorded {good}" in out, (good, out)
        assert "regression_gate_rc=0" in out, (good, out)
    for bad in ("BUG-12", "BUG-1234567", "bug-123", "BUG-12a", " BUG-123", "BUG-123 ", "",
                "BUG-123\nBUG-456", "BUG-123'; echo INJECTED; '", "BUG-123; echo INJECTED"):
        out = _run_gate_guard(bad)
        assert "STUB-CALLED" not in out, (bad, out)
        assert "INJECTED" not in out.splitlines(), (bad, out)
        assert "regression_gate_rc=2" in out and "is not a bug id" in out, (bad, out)


def test_contrast_sentence_outside_rules_block():
    """BR-16: the recorded pre-fix-fail / post-fix-pass run is named as the
    capture step's contrast and evidence, beside the reproduce-then-fix line and
    outside the capture-rules block, which stays equal to /wrapup's."""
    skill = _read(SKILL)
    lines = skill.splitlines()
    fenced = _fenced_line_numbers(lines)
    opens = [i for i, line in enumerate(lines) if i not in fenced and line.strip() == "<!-- lesson-capture-rules -->"]
    closes = [i for i, line in enumerate(lines) if i not in fenced and line.strip() == "<!-- /lesson-capture-rules -->"]
    assert len(opens) == 1 and len(closes) == 1 and opens[0] < closes[0], (opens, closes)
    block = range(opens[0], closes[0] + 1)
    anchor = [i for i, line in enumerate(lines)
              if line == "A reproduce-then-fix sequence is a contrast (rule 2); name it in `evidence`."]
    sentence = [i for i, line in enumerate(lines)
                if "pre-fix-fail / post-fix-pass run recorded in the bug report's `## Regression Test` section "
                   "is that contrast" in line]
    assert len(anchor) == 1 and len(sentence) == 1, (anchor, sentence)
    assert sentence[0] not in block and sentence[0] not in fenced
    assert closes[0] < anchor[0] and sentence[0] == anchor[0] + 1
    assert "cite it as the lesson's `evidence`" in lines[sentence[0]]
    assert "first failing assertion line" in lines[sentence[0]]
    write_point = [i for i, line in enumerate(lines) if i not in fenced and line.strip() == "<!-- lesson-write-point -->"]
    step4 = [i for i, line in enumerate(lines) if line.startswith("**Step 4 — Capture knowledge**")]
    assert len(write_point) == 1 and len(step4) == 1
    assert step4[0] < sentence[0] < write_point[0]

    wrapup = _read("wrapup/SKILL.md").splitlines()
    w_fenced = _fenced_line_numbers(wrapup)
    w_open = [i for i, line in enumerate(wrapup) if i not in w_fenced and line.strip() == "<!-- lesson-capture-rules -->"]
    w_close = [i for i, line in enumerate(wrapup) if i not in w_fenced and line.strip() == "<!-- /lesson-capture-rules -->"]
    assert len(w_open) == 1 and len(w_close) == 1
    assert lines[opens[0]:closes[0] + 1] == wrapup[w_open[0]:w_close[0] + 1]

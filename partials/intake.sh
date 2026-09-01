#!/bin/sh
# partials/intake.sh — unstructured-source intake helpers for /spec Step 1.4 (REQ-594).
#
# SOURCED, not executed — call sites source this and then call the functions in the
# SAME fenced block, because SKILL.md fenced blocks do not share shell state across
# steps (conventions.md "Bash in skills"; enforced by tools/lint-skills's
# cross-fence-fn check). This is REQ-594 BR-10.
#
# Functions:
#   adlc_intake_detect <args>...  BR-1 trigger check.
#                                 0 = run intake, 1 = ordinary request, skip.
#                                 Exports ADLC_INTAKE_KIND / _PATH / _REASON.
#   adlc_intake_segment <path>    Build the delimited, budget-checked corpus.
#                                 0 = ok, 2 = unreadable, 3 = over budget (refusal).
#                                 Exports ADLC_INTAKE_SEGMENTS / _LINES / _CORPUS.
#   adlc_intake_range <n>         Print "<start> <end>" for segment n, so a segment
#                                 the delegate omitted can be read directly from the
#                                 ORIGINAL source by line offset (BR-12).
#   adlc_intake_redact <path>     Apply the 5-pattern credential chain in place.
#   adlc_intake_sections          Print the gap-checklist section list, derived from
#                                 the requirement template (never hardcoded).
#
# Everything the functions communicate travels through EXPORTED ADLC_INTAKE_* vars,
# never through bare shell variables: tools/lint-skills's cross-fence-var check flags
# a non-exported var assigned in one fence and read in another, and an exported var is
# the sanctioned way to cross that boundary.
#
# POSIX sh only, and must pass under BOTH bash and zsh (partials/tests/run.sh):
#   * no `local` (underscore-prefixed _ai_* globals stand in, as in
#     partials/emit-step-telemetry.sh's _aest_* convention)
#   * no `[[`, no arrays, no `function` keyword, no GNU-only flags
#   * no `\b` in `grep -E` — BSD grep silently fails on it (LESSON-013). Whole-line
#     fixed-string matching uses `grep -vxF` instead.
#   * no variable named `status` — reserved in zsh (LESSON-329)
#   * no unquoted word-splitting for path lists — zsh does not word-split (LESSON-335)
#   * temp files via `mktemp` templates, never a predictable path (LESSON-008)
#
# Sourcing emits nothing on stdout or stderr.

# --- Constants (REQ-594 ADR-3) -------------------------------------------------
# 200 lines/segment mirrors REQ-423's `tail -n 200` bound — the toolkit's established
# unit for "one readable chunk". 40 segments = 8000 lines covers a three-hour meeting
# transcript (roughly 3000-6000 lines, the worst case adversary finding F5 named) while
# still refusing genuinely unbounded input.
#
# Deliberately fixed constants, not env/config knobs: ADR-7 defers configurability
# until real sources have been run through intake, and a hidden env override would be
# exactly the undocumented config surface that decision declined to add.
ADLC_INTAKE_SEGMENT_LINES=200
ADLC_INTAKE_MAX_SEGMENTS=40
# BR-1(c). Hardcoded per ADR-7; the requirement's own Assumptions section argues both
# misclassification directions are tolerable.
ADLC_INTAKE_LINE_TRIGGER=25
export ADLC_INTAKE_SEGMENT_LINES ADLC_INTAKE_MAX_SEGMENTS ADLC_INTAKE_LINE_TRIGGER

# --- Kind classification (internal) --------------------------------------------
# Sets ADLC_INTAKE_KIND to transcript | notes | ticket | prose. Filename signals win
# over content signals: a file someone named "standup-transcript.txt" is a transcript
# even if it does not happen to carry timestamps.
_adlc_intake_kind() {
    _ai_name=""
    if [ -n "$ADLC_INTAKE_PATH" ]; then
        _ai_name=$(basename "$ADLC_INTAKE_PATH" | tr '[:upper:]' '[:lower:]')
    fi

    case "$_ai_name" in
        *transcript*)            ADLC_INTAKE_KIND="transcript"; return 0 ;;
        *ticket*|*issue*|*jira*) ADLC_INTAKE_KIND="ticket";      return 0 ;;
        *notes*|*meeting*)       ADLC_INTAKE_KIND="notes";       return 0 ;;
    esac

    if [ -n "$ADLC_INTAKE_PATH" ] && [ -r "$ADLC_INTAKE_PATH" ]; then
        # Leading clock times ("09:15", "[1:03]") are the strongest transcript tell.
        _ai_ts=$(grep -cE '^[[:space:]]*\[?[0-9]{1,2}:[0-9]{2}' "$ADLC_INTAKE_PATH" 2>/dev/null)
        [ -n "$_ai_ts" ] || _ai_ts=0
        # "Speaker:" turn markers are the second.
        _ai_sp=$(grep -cE '^[[:space:]]*[A-Z][A-Za-z. ]{1,30}:[[:space:]]' "$ADLC_INTAKE_PATH" 2>/dev/null)
        [ -n "$_ai_sp" ] || _ai_sp=0
        if [ "$_ai_ts" -ge 3 ] || [ "$_ai_sp" -ge 5 ]; then
            ADLC_INTAKE_KIND="transcript"
            return 0
        fi
        _ai_bul=$(grep -cE '^[[:space:]]*[-*+][[:space:]]' "$ADLC_INTAKE_PATH" 2>/dev/null)
        [ -n "$_ai_bul" ] || _ai_bul=0
        if [ "$_ai_bul" -ge 5 ]; then
            ADLC_INTAKE_KIND="notes"
            return 0
        fi
    fi

    ADLC_INTAKE_KIND="prose"
    return 0
}

# --- BR-1: trigger detection ----------------------------------------------------
# Intake activates on ANY of: (a) an explicit --intake flag, (b) the argument
# resolving to a readable file path, (c) the argument exceeding 25 lines.
#
# An ordinary one-line feature request trips none of the three, so /spec behaves
# exactly as it does today: no intake step, no gap list, no Provenance section, no
# stderr line (AC-1). That is the whole point of gating here rather than always
# running intake and hoping it no-ops.
adlc_intake_detect() {
    ADLC_INTAKE_KIND=""
    ADLC_INTAKE_PATH=""
    ADLC_INTAKE_REASON=""
    export ADLC_INTAKE_KIND ADLC_INTAKE_PATH ADLC_INTAKE_REASON

    _ai_raw="$*"

    # (a) explicit flag, in either `--intake <path>` or `--intake=<path>` form
    _ai_flag=0
    case " $_ai_raw " in
        *" --intake "*|*" --intake="*) _ai_flag=1 ;;
    esac

    # The source is whatever remains once the flag itself is stripped.
    _ai_body=$(printf '%s\n' "$_ai_raw" \
        | sed -e 's/--intake=/ /g' -e 's/--intake//g' \
        | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')

    _ai_lines=$(printf '%s\n' "$_ai_raw" | wc -l | tr -d ' ')
    [ -n "$_ai_lines" ] || _ai_lines=0

    # (b) a readable file path. Checked even when the flag is absent, since a bare
    # path argument is itself a trigger.
    if [ -n "$_ai_body" ] && [ -f "$_ai_body" ] && [ -r "$_ai_body" ]; then
        ADLC_INTAKE_PATH="$_ai_body"
    fi

    if [ "$_ai_flag" -eq 1 ]; then
        ADLC_INTAKE_REASON="flag"
    elif [ -n "$ADLC_INTAKE_PATH" ]; then
        ADLC_INTAKE_REASON="path"
    elif [ "$_ai_lines" -gt "$ADLC_INTAKE_LINE_TRIGGER" ]; then
        ADLC_INTAKE_REASON="lines"
    else
        return 1
    fi

    _adlc_intake_kind
    return 0
}

# --- BR-12: segmentation, budget enforcement, corpus construction ---------------
# Splits the source into ordered, labelled segments and writes the delimited corpus
# that gets handed to the delegate. Requiring one block per segment in the response,
# and reconciling what comes back against this list, is what makes a partial summary
# detectable — without it a truncated read yields zero gaps precisely because the
# unread remainder is invisible, and BR-11's benign path would certify it.
#
# BR-7: only the BASENAME of the source is embedded in the corpus. Full local paths
# stay on the machine.
adlc_intake_segment() {
    ADLC_INTAKE_SEGMENTS=0
    ADLC_INTAKE_LINES=0
    ADLC_INTAKE_CORPUS=""
    ADLC_INTAKE_SOURCE=""
    export ADLC_INTAKE_SEGMENTS ADLC_INTAKE_LINES ADLC_INTAKE_CORPUS ADLC_INTAKE_SOURCE

    _ai_src="$1"
    if [ -z "$_ai_src" ] || [ ! -f "$_ai_src" ] || [ ! -r "$_ai_src" ]; then
        echo "adlc_intake_segment: source not readable: ${_ai_src:-<empty>}" >&2
        return 2
    fi
    ADLC_INTAKE_SOURCE="$_ai_src"

    _ai_total=$(wc -l < "$_ai_src" | tr -d ' ')
    [ -n "$_ai_total" ] || _ai_total=0
    # wc -l counts newlines, so a final line with no trailing newline is uncounted.
    # Add it back: undercounting here would silently drop the tail of the source,
    # which is the exact class of invisible loss intake exists to prevent.
    if [ -s "$_ai_src" ]; then
        _ai_nl=$(tail -c 1 "$_ai_src" | wc -l | tr -d ' ')
        [ -n "$_ai_nl" ] || _ai_nl=0
        if [ "$_ai_nl" -eq 0 ]; then
            _ai_total=$((_ai_total + 1))
        fi
    fi
    ADLC_INTAKE_LINES="$_ai_total"

    _ai_need=$(( (_ai_total + ADLC_INTAKE_SEGMENT_LINES - 1) / ADLC_INTAKE_SEGMENT_LINES ))
    [ "$_ai_need" -gt 0 ] || _ai_need=1

    # AC-10: refuse, naming the size. Never truncate.
    if [ "$_ai_need" -gt "$ADLC_INTAKE_MAX_SEGMENTS" ]; then
        echo "adlc_intake_segment: REFUSED — source is ${_ai_total} lines (${_ai_need} segments of ${ADLC_INTAKE_SEGMENT_LINES} lines); the budget is ${ADLC_INTAKE_MAX_SEGMENTS} segments / $((ADLC_INTAKE_MAX_SEGMENTS * ADLC_INTAKE_SEGMENT_LINES)) lines. Split the source and run intake on each part. Intake never truncates: a partial read would report zero gaps precisely because the unread remainder is invisible (REQ-594 BR-12)." >&2
        return 3
    fi

    _ai_corpus=$(mktemp -t adlc-intake.XXXXXX) || {
        echo "adlc_intake_segment: could not create a temp corpus file" >&2
        return 2
    }

    _ai_base=$(basename "$_ai_src")
    {
        printf '<source name="%s" kind="%s" lines="%s" segments="%s">\n' \
            "$_ai_base" "${ADLC_INTAKE_KIND:-prose}" "$_ai_total" "$_ai_need"
        _ai_i=1
        while [ "$_ai_i" -le "$_ai_need" ]; do
            _ai_start=$(( (_ai_i - 1) * ADLC_INTAKE_SEGMENT_LINES + 1 ))
            _ai_end=$(( _ai_i * ADLC_INTAKE_SEGMENT_LINES ))
            [ "$_ai_end" -le "$_ai_total" ] || _ai_end="$_ai_total"
            printf '<segment id="S%02d" lines="%s-%s">\n' "$_ai_i" "$_ai_start" "$_ai_end"
            sed -n "${_ai_start},${_ai_end}p" "$_ai_src"
            printf '\n</segment>\n'
            _ai_i=$(( _ai_i + 1 ))
        done
        printf '</source>\n'
    } > "$_ai_corpus"

    ADLC_INTAKE_SEGMENTS="$_ai_need"
    ADLC_INTAKE_CORPUS="$_ai_corpus"
    return 0
}

# --- BR-12: direct-read offsets for an omitted segment --------------------------
# Prints "<start> <end>" for segment n against the ORIGINAL source, so reconciliation
# can read just the segment the delegate skipped rather than re-reading everything.
#
# Deliberately STATELESS — it takes the total line count as an argument rather than
# reading ADLC_INTAKE_LINES. Reconciliation happens in a different SKILL.md fenced
# block than segmentation, and fenced blocks do not share shell state (not even for
# exported vars: each block is a separate shell invocation). A version that read the
# export would silently see an empty value and reject every segment as out of range.
# Pure arithmetic from explicit arguments is the only shape that works at that call
# site. Both arguments are echoed by adlc_intake_segment for the caller to thread
# through as literals, exactly as the telemetry `flag` path is threaded.
#
#   adlc_intake_range <segment-number> <total-lines>
adlc_intake_range() {
    for _ai_v in "$1" "$2"; do
        case "$_ai_v" in
            ''|*[!0-9]*)
                echo "adlc_intake_range: usage: adlc_intake_range <segment-number> <total-lines> (both positive integers)" >&2
                return 2
                ;;
        esac
    done

    # Decimal-normalize BEFORE any arithmetic (LESSON-396). Segment labels are
    # zero-padded (S01..S40), so the natural call after reconciliation spots a
    # missing S08 is `adlc_intake_range 08 <lines>` — and $(( 08 )) is an octal
    # literal. This is shell-divergent, which makes it worse than a plain error:
    # bash fails with "value too great for base", while zsh (the macOS executor
    # shell) silently accepts it. A bug that only appears under bash would sail
    # through local dogfooding. `sed` rather than `10#$n`, which is a bashism.
    _ai_n=$(printf '%s' "$1" | sed -e 's/^0*//' -e 's/^$/0/')
    _ai_tot=$(printf '%s' "$2" | sed -e 's/^0*//' -e 's/^$/0/')

    _ai_max=$(( (_ai_tot + ADLC_INTAKE_SEGMENT_LINES - 1) / ADLC_INTAKE_SEGMENT_LINES ))
    [ "$_ai_max" -gt 0 ] || _ai_max=1
    if [ "$_ai_n" -lt 1 ] || [ "$_ai_n" -gt "$_ai_max" ]; then
        echo "adlc_intake_range: segment ${_ai_n} is outside 1..${_ai_max} for a ${_ai_tot}-line source" >&2
        return 2
    fi

    _ai_s=$(( (_ai_n - 1) * ADLC_INTAKE_SEGMENT_LINES + 1 ))
    _ai_e=$(( _ai_n * ADLC_INTAKE_SEGMENT_LINES ))
    [ "$_ai_e" -le "$_ai_tot" ] || _ai_e="$_ai_tot"
    printf '%s %s\n' "$_ai_s" "$_ai_e"
    return 0
}

# --- Credential redaction -------------------------------------------------------
# The same 5-pattern BSD-sed chain /proceed Phase 5 applies to its verify diff. The
# broader [A-Z_]+_(API_KEY|TOKEN) arm subsumes MOONSHOT_API_KEY, so no separate
# pattern is needed. `-i.bak` (not bare `-i ''`) is the form that works on both BSD
# and GNU sed; the .bak is removed immediately.
adlc_intake_redact() {
    _ai_f="$1"
    if [ -z "$_ai_f" ] || [ ! -f "$_ai_f" ] || [ ! -w "$_ai_f" ]; then
        echo "adlc_intake_redact: file not writable: ${_ai_f:-<empty>}" >&2
        return 2
    fi
    sed -i.bak -E 's/(sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36,}|Bearer [A-Za-z0-9._-]{20,}|[A-Z_]+_(API_KEY|TOKEN)[[:space:]]*[=:][[:space:]]*[^[:space:]]+)/[REDACTED]/g' "$_ai_f" || {
        echo "adlc_intake_redact: sed failed on ${_ai_f}" >&2
        rm -f "$_ai_f.bak"
        return 2
    }
    rm -f "$_ai_f.bak"
    return 0
}

# --- Gap-checklist sections -----------------------------------------------------
# Derived from the requirement template, never hardcoded, so a future template section
# is gap-checked automatically (the requirement's own Assumptions section commits to
# this). Four headings are excluded because they are OUTPUTS of intake rather than
# inputs to it: Description is written from the source, Assumptions and Open Questions
# are where gaps land, Retrieved Context is produced by Step 1.6, and Provenance is the
# intake record itself.
#
# Resolution order is repo-local first (LESSON-441): a worktree must read its own
# template copy, not the global symlink's, or a template change under test is invisible.
adlc_intake_sections() {
    _ai_tpl=""
    for _ai_c in \
        ".adlc/templates/requirement-template.md" \
        "templates/requirement-template.md" \
        "${HOME:-}/.claude/skills/templates/requirement-template.md"
    do
        if [ -r "$_ai_c" ]; then
            _ai_tpl="$_ai_c"
            break
        fi
    done

    if [ -z "$_ai_tpl" ]; then
        echo "adlc_intake_sections: no requirement-template.md found (looked in .adlc/templates, templates, ~/.claude/skills/templates)" >&2
        return 2
    fi

    # grep -vxF: whole-line, fixed-string. NOT `grep -E '\b...'` — BSD grep silently
    # fails on \b in -E and would pass everything through (LESSON-013).
    grep '^## ' "$_ai_tpl" \
        | sed -e 's/^##[[:space:]]*//' -e 's/[[:space:]]*$//' \
        | grep -vxF 'Description' \
        | grep -vxF 'Assumptions' \
        | grep -vxF 'Open Questions' \
        | grep -vxF 'Retrieved Context' \
        | grep -vxF 'Provenance'
}

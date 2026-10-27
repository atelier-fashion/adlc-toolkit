#!/bin/sh
# partials/lesson-check.sh — structural schema check on the lesson file a capture step
# just wrote (REQ-646 BR-3, BR-10, BR-12, BR-13; ADR-1, ADR-2, ADR-3).
#
# SOURCED, not executed. Source it and call adlc_lesson_check WITHIN THE SAME fenced
# block — SKILL.md fences share no shell state (conventions.md "Bash in skills",
# enforced by tools/lint-skills cross-fence-fn; LESSON-020). The path is a threaded
# literal the model substitutes, never a variable carried in from another fence
# (ADR-1: cross-fence-var sanctions no such name):
#   if [ -f .adlc/partials/lesson-check.sh ]; then . .adlc/partials/lesson-check.sh; else . ~/.claude/skills/partials/lesson-check.sh; fi
#   adlc_lesson_check .adlc/knowledge/lessons/LESSON-<id>-<slug>.md
#
# Contract — adlc_lesson_check <lesson-file>:
#   return 0 -> every rule holds. Nothing on stdout, nothing on stderr.
#   return 1 -> one or more violations. One `<field>: <reason>` line per violation on
#               stderr (the field first, so the repair names it); stdout stays empty.
#               The field is a frontmatter key, `frontmatter` for a frontmatter line
#               that sets no key, or a section heading (`## Applies When: section
#               missing`). The caller repairs ONLY the named field(s) — adding a
#               missing or empty required section counts — and runs the fence again: at
#               most two repairs, then it deletes the draft and writes
#               `NO_ENTRY: schema check failed — <field>` to the summary slot. The
#               model counts the repairs, never the fence (ADR-4: a counter would be a
#               cross-fence variable). Not a pipeline halt.
#   return 2 -> usage: missing argument, a symlink, a basename that is not
#               LESSON-<digits>-<slug>.md (3+ digits, digits only, and nothing but
#               A-Z a-z 0-9 . _ - in the whole name), an unreadable file, or no
#               frontmatter block (`lesson-check: ...` on stderr, naming the file by its
#               basename only). A caller bug — never read as a pass.
#
# "New" is defined by who writes the file, not by a date: the capture steps are the
# only writers, so the file they just wrote is new by construction. The function takes
# no cutoff argument and is never run over the historical corpus (BR-2; a date literal
# in a guard is a guard that rots — LESSON-019).
#
# Rules — the table with every regex, and every deliberate departure from the original
# ADR-3, lives in partials/lesson-check.md (one home for the rule set, LESSON-441's
# two-copies class). In brief:
#   * a leading UTF-8 BOM and CR line ends are dropped first. The frontmatter opens at
#     the first line that is neither blank nor inside an HTML comment — that line must
#     be exactly `---` — and closes at the next `---` (ADR-2).
#   * a key is `<key>:` followed by a blank or the end of the line. A validated key —
#     title, kind, evidence, confidence, enforcement, generalizes, supersedes — written
#     any other way (`supersedes:[x]`, `kind:process`, `evidence : x`, `"evidence": x`)
#     is rejected on that key, never silently skipped. Each validated key appears at
#     most once. Unknown keys are ignored.
#   * kind in process|domain; confidence in high|medium|low; both required.
#   * enforcement absent, or none | lint:<id> | test:<path> | script:<path> | hook:<name>,
#     a test:/script: path repo-relative (no leading `/`, no `..` segment).
#   * generalizes/supersedes: a list (never a quoted string) whose every entry is
#     LESSON-nnn, 3-6 digits.
#   * evidence required, not the title repeated, carrying a citation token.
#   * no home-directory path (BR-12) and no credential-shaped string (BR-13) on ANY
#     frontmatter line — validated key, unknown key or comment — as written, trailing
#     comment included: a home path or a token behind a ` #` is committed all the same.
#   * `## Lesson` and `## Applies When` present (the first of each counts), each with a
#     non-blank line under it before the next level-1 or level-2 heading. A `###`-or-
#     deeper heading neither ends a section nor counts as its content, and no line
#     inside a ``` or ~~~ fence is a heading.
# Reject, never redact: the remedy is the repair loop, and a silently rewritten
# `evidence` is a citation nobody wrote.
#
# Value parsing follows YAML closely enough for the template's shape: one layer of
# surrounding "..." or '...' is removed; on an unquoted value a trailing ` # comment`
# is dropped (the template's own lines carry one and a drafter keeps it); a `#` with
# no blank before it is text. A quote never closed on the key's line, a `[` or `{`
# flow collection not closed there, or a value wrapped onto the next line (the next
# line that is neither blank nor a `#` comment does not start a key), is itself a
# violation: a YAML reader would drop or misread the whole lesson silently (/spec Step
# 1.6 discards a document it cannot parse), and a one-line reader never sees the rest.
#
# POSIX sh only; must behave identically under bash, zsh, /bin/sh and dash
# (partials/tests/run.sh, LESSON-405), and under a caller's `set -e`:
#   * no `local` — the `_alc_`-prefixed globals stand in; no double-bracket tests, no
#     arrays, no `function` keyword, no GNU-only flags
#   * `grep -E` only, and no backslash-b word boundary in any regex — BSD grep ignores
#     it (LESSON-013); delimiters are explicit `[^...]` classes instead
#   * bracket expressions that need whitespace open on a literal space before the
#     [:space:] class, so this file never holds a doubled open-bracket
#   * every byte-level tool runs under LC_ALL=C (ranges mean ASCII on every platform)
#   * no variable named `status` or `path` — reserved in zsh (LESSON-329)
#   * every path quoted, no word-splitting of lists (LESSON-335); awk reads the file on
#     stdin, so a path shaped like `name=value` is never taken as an awk assignment
#   * a count from `grep -c` carries `|| true` inside its substitution, and a status is
#     captured with `|| _alc_rc=$?`, so a `set -e` caller never dies on a zero count
#   * `case` guards a value before it reaches arithmetic
#   * no temp files — nothing to clean up, nothing predictable to race (LESSON-008)
#   * definition-only at top level: sourcing defines functions and nothing else, because
#     partials/tests/source-guard.test.sh executes every sourcing line it finds in the
#     corpus (LESSON-619)

# _alc_violation <field> <reason> — one stderr line per violation, counted.
_alc_violation() {
  printf '%s: %s\n' "$1" "$2" >&2
  _alc_bad=$((_alc_bad + 1))
}

# _alc_report <lines> — print `<field>: <reason>` lines built by _alc_scan, count each.
_alc_report() {
  if [ -n "$1" ]; then
    printf '%s\n' "$1" >&2
    _alc_c=$(printf '%s\n' "$1" | LC_ALL=C grep -c . || true)
    case "$_alc_c" in
      ''|*[!0-9]*) _alc_c=1 ;;
    esac
    _alc_bad=$((_alc_bad + _alc_c))
  fi
}

# _alc_scan <ERE> <reason> <enforcement-reason> — one `<field>: <reason>` line per
# field with a frontmatter line, as written, that the ERE matches. The field is the
# key the line starts (one layer of quotes and the blanks before its colon dropped, so
# a misspelt key is still named), or `frontmatter` for a line that starts no key. Every
# line is scanned — unknown keys and `#` comment lines too (BR-12, BR-13): whatever
# sits in the block is committed.
_alc_scan() {
  _alc_hits=$(printf '%s\n' "$_alc_fm" | LC_ALL=C grep -nE -e "$1" \
    | LC_ALL=C sed -e 's/:.*//' | LC_ALL=C tr '\n' ',')
  if [ -z "$_alc_hits" ]; then
    return 0
  fi
  printf '%s\n' "$_alc_fm" | LC_ALL=C awk -v hits=",$_alc_hits" -v q="'" -v r="$2" -v er="$3" '
    index(hits, "," NR ",") {
      k = "frontmatter"
      if (match($0, "^[\"" q "]?[A-Za-z_][A-Za-z0-9_-]*[\"" q "]?[ \t]*:")) {
        k = substr($0, 1, RLENGTH - 1)
        gsub("[\"" q " \t]", "", k)
      }
      if (!(k in seen)) {
        seen[k] = 1
        print k ": " (k == "enforcement" ? er : r)
      }
    }'
}

# _alc_misspelt <key> — 0 when a frontmatter line starts <key> in any spelling but the
# one every reader agrees on: `supersedes:[x]`, `kind:process`, `evidence : x` and
# `"evidence": x` each set the key for one reader and nothing for another.
_alc_misspelt() {
  printf '%s\n' "$_alc_fm" | LC_ALL=C grep -E "^[\"']?$1[\"']?[ [:space:]]*:" \
    | LC_ALL=C grep -qvE "^$1:([ [:space:]]|\$)"
}

# _alc_lines <key> — the text after `<key>:` on every frontmatter line that sets <key>,
# as written (trailing comment kept).
_alc_lines() {
  printf '%s\n' "$_alc_fm" | LC_ALL=C grep -E "^$1:([ [:space:]]|\$)" \
    | LC_ALL=C sed -e 's/^[^:]*://'
}

# _alc_field <key> — read the `<key>:` line of the frontmatter in $_alc_fm. Sets:
#   _alc_n    number of `<key>:` lines (0 = absent)
#   _alc_raw  the text after the colon, leading blanks dropped, comment kept
#   _alc_v    the parsed value (quote layer removed / trailing comment dropped)
#   _alc_err  empty when the value parses, else the reason it does not
_alc_field() {
  _alc_n=$(printf '%s\n' "$_alc_fm" | LC_ALL=C grep -cE "^$1:([ [:space:]]|\$)" || true)
  case "$_alc_n" in
    ''|*[!0-9]*) _alc_n=0 ;;
  esac
  _alc_raw=""
  _alc_v=""
  _alc_err=""
  if [ "$_alc_n" -eq 0 ]; then
    return 0
  fi
  # A second line for the key is a value one reader takes and another drops (YAML
  # parsers disagree on duplicate keys; /review's one-line lookup takes either).
  if [ "$_alc_n" -gt 1 ]; then
    _alc_err="key appears $_alc_n times — keep exactly one $1: line"
    return 0
  fi
  _alc_raw=$(_alc_lines "$1" | LC_ALL=C sed -e 's/^[ [:space:]]*//')
  case "$_alc_raw" in
    \"*)
      if printf '%s\n' "$_alc_raw" | LC_ALL=C grep -qE '^"([^"\\]|\\.)*"'; then
        _alc_v=$(printf '%s\n' "$_alc_raw" | LC_ALL=C sed -E 's/^"(([^"\\]|\\.)*)".*$/\1/')
      else
        _alc_err="opening double quote is never closed on the key's line"
      fi
      ;;
    \'*)
      if printf '%s\n' "$_alc_raw" | LC_ALL=C grep -qE "^'([^']|'')*'"; then
        _alc_v=$(printf '%s\n' "$_alc_raw" \
          | LC_ALL=C sed -E -e "s/^'(([^']|'')*)'.*\$/\\1/" -e "s/''/'/g")
      else
        _alc_err="opening single quote is never closed on the key's line"
      fi
      ;;
    *)
      _alc_v=$(printf '%s\n' "$_alc_raw" \
        | LC_ALL=C sed -E -e 's/(^|[ [:space:]])#.*$//' -e 's/[ [:space:]]+$//')
      ;;
  esac
  # A value wrapped onto the next line (a block list, a folded scalar, a flow
  # collection left open) is invisible to every one-line reader — /review's
  # `^supersedes:[ \t][^#]*<id>([^0-9]|$)` lookup among them (ADR-6). The next line
  # that is neither blank nor a `#` comment (indented or not) must start a key, in any
  # spelling — a misspelt key is named by its own rule, not blamed on the line above.
  case "$_alc_raw" in
    \[*|\{*)
      if printf '%s\n' "$_alc_v" | LC_ALL=C awk '
          {
            d = 0
            for (i = 1; i <= length($0); i++) {
              ch = substr($0, i, 1)
              if (ch == "[" || ch == "{") d++
              else if (ch == "]" || ch == "}") d--
            }
            exit (d > 0 ? 0 : 1)
          }'; then
        _alc_err="value continues onto the next line — keep the whole value on the key's line"
      fi
      ;;
  esac
  if printf '%s\n' "$_alc_fm" | LC_ALL=C awk -v k="$1" -v q="'" '
      p && /^[ \t]*$/ { next }
      p && /^[ \t]*#/ { next }
      p { c = ($0 !~ ("^[\"" q "]?[A-Za-z_][A-Za-z0-9_-]*[\"" q "]?[ \t]*:")); exit }
      $0 ~ ("^" k ":([ \t]|$)") { p = 1 }
      END { exit (c ? 0 : 1) }'; then
    _alc_err="value continues onto the next line — keep the whole value on the key's line"
  fi
  return 0
}

# _alc_present <field> <required:1|0> — report the parse-level violations for the field
# _alc_field just read; return 0 when its value is there to be checked further. A
# required key that is absent only because it is misspelt is not also "missing": the
# spelling rule has named it already.
_alc_present() {
  if [ "$_alc_n" -eq 0 ]; then
    if _alc_misspelt "$1"; then
      return 1
    fi
    if [ "$2" = 1 ]; then
      _alc_violation "$1" "missing — required on every lesson a capture step writes"
    fi
    return 1
  fi
  if [ -n "$_alc_err" ]; then
    _alc_violation "$1" "$_alc_err"
    return 1
  fi
  if [ "$2" = 1 ] && [ -z "$_alc_v" ]; then
    _alc_violation "$1" "empty — required on every lesson a capture step writes"
    return 1
  fi
  return 0
}

# _alc_cites <evidence> — 0 when the value carries at least one citation token (BR-3):
#   id        BUG-/REQ-/LESSON-/TASK- and 3-6 digits, delimited on both sides
#   test name testFoo, TestFoo or test_foo after a non-word character, or `.test.`
#   sha       a maximal hex run, lowercase, 7-40 long, holding at least one digit AND
#             at least one a-f letter: letters alone are English words (effaced,
#             defaced, accede), digits alone are dates and counts (20261026)
#   path:line a `[A-Za-z0-9_./-]+:digits` run that is not a URL authority (does not
#             start `//`), whose part after its last `/` or `.` holds a letter (so
#             127.0.0.1:8080 and 12:30 are not citations), that is not a bare
#             host:port (no `/`, last part com|org|net|io|dev — example.com:8080), and
#             which either has an extension or is extensionless with a `/` in it or a
#             capitalised basename (Makefile:12, tools/run:5)
_alc_cites() {
  if printf '%s\n' "$1" | LC_ALL=C grep -qE '(^|[^A-Za-z0-9])(BUG|REQ|LESSON|TASK)-[0-9]{3,6}([^0-9]|$)|(^|[^A-Za-z0-9_])[Tt]est[A-Z_][A-Za-z0-9_]*|\.test\.'; then
    return 0
  fi
  if printf '%s\n' "$1" | LC_ALL=C tr -c '0-9a-fA-F' '\n' \
       | LC_ALL=C grep -E '^[0-9a-f]{7,40}$' | LC_ALL=C grep '[0-9]' \
       | LC_ALL=C grep -q '[a-f]'; then
    return 0
  fi
  if printf '%s\n' "$1" | LC_ALL=C awk '
      {
        s = $0
        while (match(s, "[A-Za-z0-9_./-]+:[0-9]+")) {
          t = substr(s, RSTART, RLENGTH)
          s = substr(s, RSTART + RLENGTH)
          p = t
          sub(":[0-9]+$", "", p)
          if (substr(p, 1, 2) == "//") continue
          b = p
          sub(".*/", "", b)
          g = p
          sub(".*[/.]", "", g)
          if (g !~ /[A-Za-z]/) continue
          if (!index(p, "/") && tolower(g) ~ /^(com|org|net|io|dev)$/) continue
          if (index(b, ".")) {
            if (g ~ /^[A-Za-z0-9]+$/) { f = 1; exit }
            continue
          }
          if (index(p, "/") || b ~ /^[A-Z]/) { f = 1; exit }
        }
      }
      END { exit (f ? 0 : 1) }'; then
    return 0
  fi
  return 1
}

# _alc_ids_ok <list-value> — 0 when every entry is LESSON-nnn after stripping [ ] " ' ,
_alc_ids_ok() {
  if printf '%s\n' "$1" | LC_ALL=C sed -e "s/[][\"',]/ /g" | LC_ALL=C tr -s ' \t' '\n\n' \
       | LC_ALL=C grep -v '^$' | LC_ALL=C grep -vqE '^LESSON-[0-9]{3,6}$'; then
    return 1
  fi
  return 0
}

adlc_lesson_check() {
  _alc_file=${1-}
  if [ -z "$_alc_file" ]; then
    printf '%s\n' "lesson-check: usage: adlc_lesson_check <lesson-file>" >&2
    return 2
  fi
  # Messages name the file by basename only, every non-printing byte shown as `?`: a
  # crafted name cannot forge a `<field>: <reason>` line, and no home directory in the
  # path reaches a transcript.
  _alc_name=$(printf '%s' "${_alc_file##*/}" | LC_ALL=C tr -c '[:print:]' '?')
  if [ -L "$_alc_file" ]; then
    printf 'lesson-check: refusing a symlink: %s\n' "$_alc_name" >&2
    return 2
  fi
  # The name: LESSON-, an id of 3+ digits and nothing else, -<slug>.md, and no byte
  # outside A-Z a-z 0-9 . _ - anywhere. The byte check runs under LC_ALL=C in `tr` (a
  # shell `case` range follows the caller's locale); the trailing `x` keeps a name that
  # ends in a newline from looking clean once $( ) strips it.
  _alc_base=${_alc_file##*/}
  _alc_id=${_alc_base#LESSON-}
  _alc_id=${_alc_id%%-*}
  _alc_cs=$(printf '%s' "$_alc_base" | LC_ALL=C tr -d 'A-Za-z0-9._-'; printf x)
  _alc_ok=0
  case "$_alc_base" in
    LESSON-[0-9][0-9][0-9]*-*.md) _alc_ok=1 ;;
  esac
  case "$_alc_id" in
    ''|*[!0-9]*) _alc_ok=0 ;;
  esac
  if [ "$_alc_cs" != x ]; then
    _alc_ok=0
  fi
  if [ "$_alc_ok" != 1 ]; then
    printf 'lesson-check: not a lesson file name (want LESSON-<digits>-<slug>.md, A-Z a-z 0-9 . _ - only): %s\n' "$_alc_name" >&2
    return 2
  fi
  if [ ! -f "$_alc_file" ] || [ ! -r "$_alc_file" ]; then
    printf 'lesson-check: cannot read %s\n' "$_alc_name" >&2
    return 2
  fi

  # One pass over the file. Each frontmatter line comes out prefixed `F`; the last line
  # is `S <lesson> <applies-when>`, each 0 (no heading), 1 (heading, nothing under it)
  # or 2 (heading with content). ADR-2: the first line that is not blank and not inside
  # an HTML comment must be `---` — NOT attribution.sh's line-1 assumption, which reads
  # a comment-headed lesson as bare, and not "any `---`", which reads a horizontal rule
  # in a frontmatter-less file as the block.
  # Body: a heading is 1-6 `#` then a blank or the line's end, compared after trailing
  # blanks are stripped. A level-1 or level-2 heading ends the open section; only the
  # FIRST `## Lesson` and the first `## Applies When` open one. A `###`-or-deeper
  # heading neither ends a section nor counts as its content, so a section holding
  # only `### Sub` is empty. A line from an opening ``` or ~~~ fence to its closing
  # fence (same character) is content, never a heading.
  _alc_rc=0
  _alc_out=$(LC_ALL=C awk '
    NR == 1 { sub(/^\357\273\277/, "") }
    { sub(/\r$/, "") }
    s == 0 {
      r = $0
      if (inc) {
        i = index(r, "-->")
        if (i == 0) next
        r = substr(r, i + 3)
        inc = 0
      } else if (r == "---") {
        s = 1
        next
      }
      while (1) {
        sub(/^[ \t]+/, "", r)
        if (substr(r, 1, 4) != "<!--") break
        r = substr(r, 5)
        i = index(r, "-->")
        if (i == 0) { inc = 1; r = ""; break }
        r = substr(r, i + 3)
      }
      if (r != "") exit 3
      next
    }
    s == 1 {
      if ($0 == "---") { s = 2; next }
      print "F" $0
      next
    }
    { h = $0; sub(/[ \t]+$/, "", h); t = h; sub(/^[ \t]+/, "", t); t = substr(t, 1, 3) }
    f != "" {
      if (t == f) f = ""
      if (c == 1) l = 2
      else if (c == 2) a = 2
      next
    }
    h == "" { next }
    t == "```" || t == "~~~" {
      f = t
      if (c == 1) l = 2
      else if (c == 2) a = 2
      next
    }
    match(h, /^#+/) && RLENGTH <= 6 && (RLENGTH == length(h) || substr(h, RLENGTH + 1, 1) ~ /[ \t]/) {
      if (RLENGTH >= 3) next
      c = 0
      if (h == "## Lesson" && l == 0) { l = 1; c = 1 }
      else if (h == "## Applies When" && a == 0) { a = 1; c = 2 }
      next
    }
    {
      if (c == 1) l = 2
      else if (c == 2) a = 2
      c = 0
    }
    END {
      if (s != 2) exit 3
      print "S " (l + 0) " " (a + 0)
    }' < "$_alc_file") || _alc_rc=$?
  if [ "$_alc_rc" -ne 0 ]; then
    printf 'lesson-check: no frontmatter block in %s\n' "$_alc_name" >&2
    return 2
  fi
  _alc_fm=$(printf '%s\n' "$_alc_out" | LC_ALL=C sed -n -e 's/^F//p')
  _alc_sec=$(printf '%s\n' "$_alc_out" | LC_ALL=C sed -n -e 's/^S //p')

  _alc_bad=0
  # Fail closed on spelling: a validated key written any way but `<key>:` + blank is
  # rejected on that key, not read as absent and passed over.
  for _alc_k in title kind evidence confidence enforcement generalizes supersedes; do
    if _alc_misspelt "$_alc_k"; then
      _alc_violation "$_alc_k" "must be written as \"$_alc_k:\" followed by a blank"
    fi
  done

  _alc_field title
  _alc_title=""
  if _alc_present title 0; then
    _alc_title=$_alc_v
  fi

  _alc_field kind
  if _alc_present kind 1; then
    case "$_alc_v" in
      process|domain) ;;
      *) _alc_violation kind "must be process or domain" ;;
    esac
  fi

  _alc_field evidence
  if _alc_present evidence 1; then
    if ! _alc_cites "$_alc_v"; then
      _alc_violation evidence "no citation token — name the moment: a commit sha, a BUG-/REQ-/LESSON-/TASK-nnn id, a path:line, or a test name"
    fi
    if [ -n "$_alc_title" ] && [ "$_alc_v" = "$_alc_title" ]; then
      _alc_violation evidence "repeats the title — cite the moment that proves the lesson"
    fi
  fi

  _alc_field confidence
  if _alc_present confidence 1; then
    case "$_alc_v" in
      high|medium|low) ;;
      *) _alc_violation confidence "must be high, medium or low — decided by the contrast rule" ;;
    esac
  fi

  _alc_field enforcement
  if _alc_present enforcement 0; then
    if ! printf '%s\n' "$_alc_v" | LC_ALL=C grep -qE '^(none|lint:[A-Za-z0-9_.-]+|test:[A-Za-z0-9_./-]+|script:[A-Za-z0-9_./-]+|hook:[A-Za-z0-9_.-]+)$'; then
      _alc_violation enforcement "must be none, lint:<check-id>, test:<path>, script:<path> or hook:<name>"
    elif printf '%s\n' "$_alc_v" | LC_ALL=C grep -qE '^(test|script):(/|(.*/)?\.\.(/|$))'; then
      _alc_violation enforcement "a test:/script: path must be repo-relative — no leading / and no .. segment"
    fi
  fi

  for _alc_k in generalizes supersedes; do
    _alc_field "$_alc_k"
    if _alc_present "$_alc_k" 0; then
      case "$_alc_raw" in
        \"*|\'*)
          _alc_violation "$_alc_k" "a quoted value is one string, not a list — write [LESSON-404]"
          ;;
        *)
          if ! _alc_ids_ok "$_alc_v"; then
            _alc_violation "$_alc_k" "every entry must be a LESSON-nnn id (3-6 digits), e.g. [LESSON-404]"
          fi
          ;;
      esac
    fi
  done

  # BR-12, over every frontmatter line as written — a home path behind a ` #`, on an
  # unknown key or on a comment line is committed all the same:
  #   /Users/   any case, anywhere — no left delimiter, so `/Volumes/Macintosh
  #             HD/Users/bob` and `x.-/Users/bob` are caught (a `/users/` URL path is
  #             a false positive the repair loop absorbs)
  #   /home/, /root/ after anything but a path or word character (so `path=/home/x`,
  #             `[/root/x]`, `a,/root/x` and — fail-closed — `/tmp//home/x` are caught;
  #             `/tmp/home/x` and `https://host/home/x` are not)
  #   /var/root/ anywhere (the macOS root account's home)
  #   $HOME/, ${HOME}/, "$HOME"/ anywhere; C:\Users\ (any drive letter, any case)
  #   ~name/    at a token start. `~/` passes.
  _alc_home_re='/[Uu][Ss][Ee][Rr][Ss]/|(^|[^A-Za-z0-9_.-])(/home/|/root/)|/var/root/|\$[{]?HOME[}]?["'"'"']?/|[A-Za-z]:\\[Uu][Ss][Ee][Rr][Ss]\\|(^|[^A-Za-z0-9_./-])~[A-Za-z0-9_.-]+/'
  _alc_report "$(_alc_scan "$_alc_home_re" \
    'contains a home-directory path (/Users/, /home/, /root/, /var/root/, $HOME/, ~name/ or a drive-letter Users path) — replace the prefix with ~/' \
    'contains a home-directory path (/Users/, /home/, /root/, /var/root/, $HOME/, ~name/ or a drive-letter Users path) — use a repo-relative path')"

  # BR-13, over every frontmatter line as written, likewise. A deliberate sixth copy of
  # the credential chain, wider than REQ-415's on every arm but one
  # (partials/lesson-check.md, "Departures from the original ADR-3", says why). The
  # assignment arm matches its keyword in any case but wants `=` and 8+ characters, so
  # `GITHUB_TOKEN: was unset in CI` — prose about a variable — is not a credential.
  _alc_cred='sk-[A-Za-z0-9_-]{20,}|(sk|rk)_(live|test)_[A-Za-z0-9]{20,}|(AKIA|ASIA|ABIA|ACCA|AIPA|ANPA|AROA)[A-Z0-9]{16}|(github_pat_|gh[opsur]_)[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}|npm_[A-Za-z0-9]{36}|xox[abprs]-[A-Za-z0-9-]{10,}|xapp-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}|eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.|-----BEGIN [A-Z ]*PRIVATE KEY|Bearer [A-Za-z0-9._-]{20,}|://[^/ :@]+:[^/ @]+@|[A-Za-z_]*([Ss][Ee][Cc][Rr][Ee][Tt]|[Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]|[Pp][Aa][Ss][Ss][Ww][Dd]|[Aa][Pp][Ii]_[Kk][Ee][Yy]|[Tt][Oo][Kk][Ee][Nn])[A-Za-z_]*[ [:space:]]*=[ [:space:]]*[^[:space:]]{8,}'
  _alc_cred_why='carries a credential-shaped string (an API key, access token, JWT, private key, URL user:password@ or secret/password/token/api_key assignment) — remove it; the check rejects, it never redacts'
  _alc_report "$(_alc_scan "$_alc_cred" "$_alc_cred_why" "$_alc_cred_why")"

  for _alc_h in '## Lesson' '## Applies When'; do
    case "$_alc_h" in
      '## Lesson') _alc_s=${_alc_sec%% *} ;;
      *) _alc_s=${_alc_sec##* } ;;
    esac
    case "$_alc_s" in
      2) ;;
      1) _alc_violation "$_alc_h" "section is empty — it needs at least one line of text under the heading" ;;
      *) _alc_violation "$_alc_h" "section missing — required on every lesson a capture step writes" ;;
    esac
  done

  if [ "$_alc_bad" -gt 0 ]; then
    return 1
  fi
  return 0
}

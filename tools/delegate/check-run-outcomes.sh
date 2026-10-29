#!/bin/sh
# check-run-outcomes.sh — read the run-outcome log (REQ-648).
#
# Reads $ADLC_RUN_OUTCOMES_LOG (default ~/Library/Logs/adlc-run-outcomes.log),
# the JSON-lines log tools/delegate/emit-run-outcome.sh appends to. Every reader
# keeps only the LATEST line per REQ (the log is append-only, so the last line in
# file order wins): a resumed run that halted, then merged, counts once, as merged.
#
#   --recurrence --reqs REQ-a,REQ-b,...
#       For the listed REQs (the sprint's REQ list is the denominator N, not the
#       line count — a crashed run leaves no line), print one row per finding
#       class:
#           <class>\t<k>\t<N>\t<tier>
#       k = how many listed REQs' latest line carries the class; sorted k
#       descending, then class. tier: `lesson` (LESSON-nnn), `title-slug`
#       (title-slug:...), else `reviewer`. Then one row per listed REQ with no
#       line, in list order:
#           <REQ>\tno-record
#       A missing log makes every listed REQ no-record.
#
#   [--window <N>d]          (default 7d; the /analyze Step 1.10 summary)
#       The latest line per REQ within the window, grouped by toolkit_version:
#           toolkit_version runs merged pr_ready blocked failed
#           mean_validate_retries verify_loop_rate critical major minor nit top_classes
#       Exit contract — distinct signals for distinct empties (LESSON-571):
#         log absent                                   -> rc 0, no output
#         no parsed line inside the window             -> rc 0, `no runs in <N>d window`
#         >0 non-empty lines and none parses           -> rc 1 (corrupt), one stderr line
#         usage error                                  -> rc 2
#       A line that does not parse has no timestamp to place it outside the
#       window, so it counts toward the corrupt rule.
#
# POSIX sh + awk: no jq, no local, no [[, no mktemp. The window cutoff is
# computed once as an ISO-8601 Z string (BSD `date -r`, GNU `date -d @`) and
# compared lexicographically, which ISO-8601 Z permits.

LOG=${ADLC_RUN_OUTCOMES_LOG:-"$HOME/Library/Logs/adlc-run-outcomes.log"}
mode=summary
window_days=7
reqs=""

usage() {
    echo "usage: check-run-outcomes.sh [--window <N>d] | --recurrence --reqs REQ-a,REQ-b,..." >&2
    exit 2
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --window)
            [ "$#" -ge 2 ] || usage
            window_days=${2%d}
            shift 2
            ;;
        --recurrence) mode=recurrence; shift ;;
        --reqs)
            [ "$#" -ge 2 ] || usage
            reqs=$2
            shift 2
            ;;
        *) echo "check-run-outcomes: unknown arg: $1" >&2; usage ;;
    esac
done

case "$window_days" in ''|*[!0-9]*) echo "check-run-outcomes: --window takes <N>d, N digits" >&2; exit 2 ;; esac

TAB=$(printf '\t')

# The shared parser. val() returns the value of a flat "key":"value" pair, or
# the sentinel "\001" when the key is absent; every field read here is
# regex-validated by run_outcome.py and carries no `"`.
PARSE='
function val(line, key,    p, s, e) {
    p = index(line, "\"" key "\":\"")
    if (p == 0) return "\001"
    s = substr(line, p + length(key) + 4)
    e = index(s, "\"")
    if (e == 0) return "\001"
    return substr(s, 1, e - 1)
}
function parsed(line,    ts, req) {
    if (val(line, "skill") != "proceed" || val(line, "step") != "run-outcome") return 0
    ts = val(line, "timestamp")
    if (ts !~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z$/) return 0
    req = val(line, "req")
    if (req !~ /^REQ-[0-9]+$/) return 0
    return 1
}
function num(v) { return (v ~ /^[0-9]+$/) ? v + 0 : 0 }
function tier(c) {
    if (c ~ /^LESSON-[0-9]+$/) return "lesson"
    if (c ~ /^title-slug:/) return "title-slug"
    return "reviewer"
}
'

if [ "$mode" = recurrence ]; then
    [ -n "$reqs" ] || { echo "check-run-outcomes: --recurrence needs --reqs REQ-a,REQ-b,..." >&2; exit 2; }
    bad=$(printf '%s\n' "$reqs" | tr ',' '\n' | command grep -v -E '^REQ-[0-9]+$' | command grep -v '^$' | head -n 1)
    [ -z "$bad" ] || { echo "check-run-outcomes: --reqs holds a value that is not a REQ id: $bad" >&2; exit 2; }
    src=$LOG
    [ -f "$src" ] || src=/dev/null
    # Class rows, sorted k desc then class (C locale, so the order is the same everywhere).
    LC_ALL=C awk -v reqs="$reqs" "$PARSE"'
        BEGIN { n = split(reqs, list, ","); N = 0
                for (i = 1; i <= n; i++) if (list[i] != "" && !(list[i] in want)) { want[list[i]] = 1; N++ } }
        { if (!parsed($0)) next; r = val($0, "req"); if (r in want) latest[r] = val($0, "finding_classes") }
        END {
            for (r in latest) {
                m = split(latest[r], cs, ",")
                for (i = 1; i <= m; i++) {
                    c = cs[i]
                    if (c == "" || c == "\001" || ((r SUBSEP c) in seen)) continue
                    seen[r SUBSEP c] = 1; k[c]++
                }
            }
            for (c in k) printf "%s\t%d\t%d\t%s\n", c, k[c], N, tier(c)
        }' "$src" | LC_ALL=C sort -t "$TAB" -k2,2nr -k1,1
    # no-record rows, in list order.
    LC_ALL=C awk -v reqs="$reqs" "$PARSE"'
        { if (parsed($0)) have[val($0, "req")] = 1 }
        END { n = split(reqs, list, ",")
              for (i = 1; i <= n; i++) { r = list[i]
                  if (r == "" || (r in done)) continue; done[r] = 1
                  if (!(r in have)) printf "%s\tno-record\n", r } }' "$src"
    exit 0
fi

# --- summary mode -------------------------------------------------------------
[ -f "$LOG" ] || exit 0

now_epoch=$(date -u +%s)
cutoff_epoch=$((now_epoch - window_days * 86400))
cutoff=$(date -u -r "$cutoff_epoch" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null) \
    || cutoff=$(date -u -d "@$cutoff_epoch" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null) \
    || cutoff=""

out=$(LC_ALL=C awk -v cutoff="$cutoff" "$PARSE"'
    { if ($0 ~ /^[ \t\r]*$/) next; nonempty++
      if (!parsed($0)) next; ok++
      ts = val($0, "timestamp"); if (cutoff != "" && ts < cutoff) next
      r = val($0, "req"); line[r] = $0 }
    END {
        if (nonempty > 0 && ok == 0) { print "CORRUPT"; exit }
        for (r in line) {
            L = line[r]; v = val(L, "toolkit_version"); if (v == "\001" || v == "") v = "-"
            runs[v]++; vers[v] = 1
            t = val(L, "terminal"); term[v SUBSEP t]++
            vr[v] += num(val(L, "validate_retries"))
            if (num(val(L, "verify_loops")) > 0) looped[v]++
            sc[v] += num(val(L, "findings_critical")); sj[v] += num(val(L, "findings_major"))
            sm[v] += num(val(L, "findings_minor")); sn[v] += num(val(L, "findings_nit"))
            m = split(val(L, "finding_classes"), cs, ",")
            for (i = 1; i <= m; i++) { c = cs[i]
                if (c == "" || c == "\001" || ((r SUBSEP c) in seen)) continue
                seen[r SUBSEP c] = 1; ck[v SUBSEP c]++; cl[v SUBSEP c] = c }
        }
        for (v in vers) {
            top = ""
            for (pick = 1; pick <= 3; pick++) {
                best = ""; bk = 0
                for (key in ck) {
                    split(key, kv, SUBSEP); if (kv[1] != v || (key in used)) continue
                    if (ck[key] > bk || (ck[key] == bk && cl[key] < cl[best])) { best = key; bk = ck[key] }
                }
                if (best == "") break
                used[best] = 1; top = top (top == "" ? "" : ",") cl[best] "=" bk
            }
            printf "%s\t%d\t%d\t%d\t%d\t%d\t%.2f\t%.2f\t%d\t%d\t%d\t%d\t%s\n", v, runs[v],
                term[v SUBSEP "merged"], term[v SUBSEP "pr-ready"], term[v SUBSEP "blocked"],
                term[v SUBSEP "failed"], vr[v] / runs[v], looped[v] / runs[v],
                sc[v], sj[v], sm[v], sn[v], (top == "" ? "-" : top)
        }
    }' "$LOG")
rc=$?
if [ "$rc" -ne 0 ]; then
    echo "check-run-outcomes: awk failed reading $LOG (rc $rc)" >&2
    exit 1
fi

if [ "$out" = CORRUPT ]; then
    echo "check-run-outcomes: $LOG holds no parseable run-outcome line" >&2
    exit 1
fi
if [ -z "$out" ]; then
    echo "no runs in ${window_days}d window"
    exit 0
fi
printf 'toolkit_version\truns\tmerged\tpr_ready\tblocked\tfailed\tmean_validate_retries\tverify_loop_rate\tcritical\tmajor\tminor\tnit\ttop_classes\n'
printf '%s\n' "$out" | LC_ALL=C sort -t "$TAB" -k1,1
exit 0

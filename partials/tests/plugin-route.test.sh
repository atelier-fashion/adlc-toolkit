#!/bin/sh
# partials/tests/plugin-route.test.sh — REQ-669 BR-2, BR-5, BR-6, BR-8, BR-17
# (TASK-123; the /init and /template-drift cases are TASK-125's).
#
# The plugin route, end to end through the partials. HOME is a sandbox with no
# toolkit under ~/.claude/skills and no ~/.claude/agents. ADLC_TOOLKIT_ROOT
# points at a COPY of the toolkit tree at a cache-shaped path, which is what a
# fence's root line exports on a plugin-only machine. Each case is a script FILE
# run by the shell under test, as a fence is: it sources a partial with the fence
# spelling, `"$ADLC_TOOLKIT_ROOT/partials/<name>.sh"` as the fallback, and runs
# the toolkit-owned tool, template or file that partial reads.
#
# "No read under $HOME/.claude/skills" (BR-2) is enforced two ways:
#   - the directory exists with mode 000, so a read, stat or exec under it fails
#     loudly (Permission denied, naming the path) rather than finding nothing;
#   - before the chmod it was filled with DECOY copies (partials, both Python
#     engines, the delegate tools, the template, ETHOS.md) that print DECOY when
#     used, so a read is caught even where mode 000 is not enforced (uid 0).
# Every case asserts its stdout and stderr carry neither DECOY nor the path.
#
# Cases:
#   case_no_skills_symlink_reads (BR-2): lane-check (engine), forge
#       (forge_config.py), delegate-tools-path (skill-flag.sh), emit-step-telemetry
#       (emit-telemetry.sh), ethos-include (ETHOS.md), intake (the requirement
#       template), id-alloc (an allocation) and id-recheck (a recheck, which
#       sources id-alloc.sh itself) each give their expected result.
#   case_lookups_follow_toolkit_root: a ToolkitRoot holding partials only. Every
#       toolkit-owned lookup fails or degrades naming THAT root, and none falls
#       back to HOME. This is what proves the passing runs read the copy.
#   case_vendored_copy_still_first (BR-5): the vendored .adlc/ copies still win
#       on the plugin route, partial-to-partial included, and a branch's own
#       lane_check.py is still ignored (LESSON-718).
#   case_init_copy_fences_same_tree (BR-8): /init's Step 6-9 fences, taken from
#       init/SKILL.md and run on the plugin route, build the same .adlc/ and
#       .claude/ tree as on the symlink route, and the preflight error names both
#       routes.
#   case_template_drift_names_plugin_version (BR-8, AC-8): /template-drift's
#       Step 0a fence, on a released copy, prints `baseline: adlc plugin <version>`
#       from its plugin.json. With the manifest missing or repeating a key it
#       prints `unverified-baseline`, gives the reason, and never says `stale`.
#   case_template_drift_symlink_baseline_unchanged (BR-8, benign path): on the
#       symlink route, Step 0a's output and the BUG-204 values it leaves are
#       byte-identical to the pre-REQ-669 fence, for a clean, current checkout, a
#       dirty one, and one behind origin.
#   case_machine_state_outside_cache (BR-6): the counter lands in ~/.claude, and
#       the copy is byte-identical after every case (bytecode caches aside).
#
# Runs under whatever shell run.sh hands it ($ADLC_TEST_SHELL):
#   ADLC_TEST_SHELL=dash sh partials/tests/plugin-route.test.sh
# or, for bash, zsh, /bin/sh and dash in turn:  sh partials/tests/run.sh
#
# Exits 0 iff every check passes and the executed-case count clears its floor.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PARTIALS=$(CDPATH= cd -- "$HERE/.." && pwd)
TOOLKIT=$(CDPATH= cd -- "$PARTIALS/.." && pwd)
SUT=${ADLC_TEST_SHELL:-/bin/sh}

FAILS=0
CASES=0
pass() { echo "PASS: $1"; CASES=$((CASES + 1)); }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); CASES=$((CASES + 1)); }
check() { # check <desc> <expected> <actual> — compared raw, printed scrubbed
  if [ "$2" = "$3" ]; then pass "$1 (= $(scrub "$3"))"; else fail "$1 (expected '$(scrub "$2")', got '$(scrub "$3")')"; fi
}

# The sandbox path is validated BEFORE any cleanup can derive an `rm -rf` from
# it: non-empty, a directory, and carrying the basename this harness asked for
# (LESSON-619).
SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/adlc-pluginroute.XXXXXX") || { echo "plugin-route.test.sh: mktemp failed" >&2; exit 1; }
[ -n "$SANDBOX" ] && [ -d "$SANDBOX" ] || { echo "plugin-route.test.sh: sandbox path invalid" >&2; exit 1; }
case "$SANDBOX" in
  */adlc-pluginroute.*) ;;
  *) echo "plugin-route.test.sh: sandbox path is not one this harness created" >&2; exit 1 ;;
esac
H="$SANDBOX/home"
GUARD="$H/.claude/skills"
# The mode comes back first: `rm -rf` cannot descend a mode-000 directory, and
# a cleanup that half-ran would leave the sandbox behind.
cleanup() {
  if [ -d "$GUARD" ]; then chmod 700 "$GUARD" 2>/dev/null; fi
  rm -rf "$SANDBOX"
}
trap cleanup EXIT
trap 'cleanup; exit 130' INT TERM

# Absolute sandbox paths never reach a PASS/FAIL line (BUG-054 class).
scrub() { printf '%s' "$1" | sed "s#$SANDBOX#<sandbox>#g"; }

HOME="$H"; export HOME
unset CLAUDE_PLUGIN_ROOT ADLC_TOOLKIT_ROOT GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
GIT_TERMINAL_PROMPT=0; export GIT_TERMINAL_PROMPT
mkdir -p "$SANDBOX/cases" "$SANDBOX/out" "$SANDBOX/work" "$SANDBOX/repos" || exit 1

# ===========================================================================
# 1. ToolkitRoot: a copy of the tree at a cache-shaped path
# ===========================================================================
# The parts a partial reads: partials, templates, ETHOS.md and the two tool
# directories; plus workflows/ and .claude-plugin/, which /init and
# /template-drift read. Test trees and bytecode are dropped, except workflows/tests,
# which a real cache copy carries and /init must not vendor.
mk_root_copy() { # mk_root_copy <dir>
  mkdir -p "$1/tools" \
    && cp -R "$TOOLKIT/partials" "$TOOLKIT/templates" "$TOOLKIT/workflows" "$TOOLKIT/.claude-plugin" "$1/" \
    && cp "$TOOLKIT/ETHOS.md" "$1/" \
    && cp -R "$TOOLKIT/tools/adlc" "$TOOLKIT/tools/delegate" "$1/tools/" \
    && rm -rf "$1/partials/tests" "$1/tools/adlc/tests" "$1/tools/delegate/tests" \
    && find "$1" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null
}
CACHE="$SANDBOX/plugins/cache/adlc-toolkit/adlc/0.0.0-test"
mk_root_copy "$CACHE" || { echo "plugin-route.test.sh: could not build the ToolkitRoot copy" >&2; exit 1; }
# A second root with the partials and nothing else (case_lookups_follow_toolkit_root).
BROKEN="$SANDBOX/broken-root"
mkdir -p "$BROKEN" && cp -R "$TOOLKIT/partials" "$BROKEN/" && rm -rf "$BROKEN/partials/tests" \
  || { echo "plugin-route.test.sh: could not build the partials-only root" >&2; exit 1; }

# Every file in a tree with its checksum, bytecode caches left out.
tree_sum() { # tree_sum <dir>
  find "$1" -name __pycache__ -prune -o -type f -print | sort | while IFS= read -r f; do cksum "$f"; done
}
tree_sum "$CACHE" > "$SANDBOX/cache.before"

# ===========================================================================
# 2. The HOME of a plugin-only machine, with the symlink path booby-trapped
# ===========================================================================
mkdir -p "$GUARD/partials" "$GUARD/tools/adlc" "$GUARD/tools/delegate" "$GUARD/templates" || exit 1
for n in lane-check forge delegate-tools-path emit-step-telemetry ethos-include intake id-alloc id-recheck delegate-gate; do
  printf 'echo "DECOY:partials/%s.sh"; echo "DECOY:partials/%s.sh" >&2\n' "$n" "$n" > "$GUARD/partials/$n.sh"
done
printf 'print("lane_check=pass")\nprint("files_counted=0")\nprint("DECOY:lane_check.py")\n' > "$GUARD/tools/adlc/lane_check.py"
printf 'print("DECOY:forge_config.py")\n' > "$GUARD/tools/adlc/forge_config.py"
for n in emit-telemetry skill-flag; do
  printf '#!/bin/sh\necho "DECOY:%s.sh"\n' "$n" > "$GUARD/tools/delegate/$n.sh" && chmod +x "$GUARD/tools/delegate/$n.sh"
done
printf '# Decoy\n\n## DECOY section\n' > "$GUARD/templates/requirement-template.md"
printf 'DECOY:ETHOS.md\n' > "$GUARD/ETHOS.md"
chmod 000 "$GUARD" || { echo "plugin-route.test.sh: chmod 000 failed" >&2; exit 1; }

if [ "$(id -u)" -eq 0 ]; then
  echo "NOTE: uid 0 ignores mode 000; the DECOY copies alone catch a read under \$HOME/.claude/skills"
elif ls "$GUARD" >/dev/null 2>&1; then
  fail "guard_mode_000: \$HOME/.claude/skills is still readable after chmod 000"
else
  pass "guard_mode_000: a read under \$HOME/.claude/skills fails loudly"
fi
if [ -e "$H/.claude/agents" ]; then
  fail "guard_no_agents: \$HOME/.claude/agents exists in the plugin-only sandbox"
else
  pass "guard_no_agents: no \$HOME/.claude/agents"
fi

# ===========================================================================
# 3. Repos and case scripts
# ===========================================================================
# mkrepo <dir> — one base commit on `main`, left on branch `feat`.
mkrepo() {
  mr_d=$1
  mkdir -p "$mr_d" && git -C "$mr_d" init -q -b main . && git -C "$mr_d" config user.email t@t && git -C "$mr_d" config user.name t
  mkdir -p "$mr_d/src" && printf 'base\n' > "$mr_d/src/a.txt" && git -C "$mr_d" add -A && git -C "$mr_d" commit -qm base
  git -C "$mr_d" checkout -qb feat
  return 0
}
# commit_files <dir> <path>... — write and commit each path on the current branch.
commit_files() {
  cf_d=$1; shift
  for cf_p in "$@"; do
    mkdir -p "$cf_d/$(dirname -- "$cf_p")" && printf 'change\n' > "$cf_d/$cf_p"
  done
  git -C "$cf_d" add -A && git -C "$cf_d" commit -qm change
}

# write_case <name> — the case script is read from stdin (a quoted heredoc).
write_case() { cat > "$SANDBOX/cases/$1.sh"; }

# run_case <name> <cwd> <toolkit-root> [<repo>] — the case script under $SUT, in
# <cwd>, with the environment a plugin-route fence has after its root line:
# ADLC_TOOLKIT_ROOT exported, CLAUDE_PLUGIN_ROOT absent from the environment.
run_case() {
  ( unset CLAUDE_PLUGIN_ROOT
    cd "$2" && ADLC_TOOLKIT_ROOT="$3" CASE_REPO="${4:-}" CASE_SANDBOX="$SANDBOX" \
      ADLC_REPOS_ROOT="$SANDBOX/repos" "$SUT" "$SANDBOX/cases/$1.sh" ) \
    >"$SANDBOX/out/$1.out" 2>"$SANDBOX/out/$1.err"
}
out_of() { cat "$SANDBOX/out/$1.out"; }
err_of() { cat "$SANDBOX/out/$1.err"; }
line_of() { # line_of <case> <prefix> — the first stdout line starting with <prefix>
  command grep -m 1 "^$2" "$SANDBOX/out/$1.out"
}

# no_skills_reads <case> — neither stream carries a DECOY marker, the guard
# path, or `.claude/skills` in any spelling (a permission error names the path).
no_skills_reads() {
  nsr_hits=$(cat "$SANDBOX/out/$1.out" "$SANDBOX/out/$1.err" \
    | command grep -c -F -e 'DECOY' -e "$GUARD" -e '.claude/skills')
  if [ "$nsr_hits" = "0" ]; then
    pass "case_no_skills_symlink_reads: $1 read nothing under \$HOME/.claude/skills"
  else
    fail "case_no_skills_symlink_reads: $1 touched \$HOME/.claude/skills ($nsr_hits line(s)): $(scrub "$(cat "$SANDBOX/out/$1.out" "$SANDBOX/out/$1.err" | command grep -F -e DECOY -e "$GUARD" -e '.claude/skills' | head -3)")"
  fi
}

write_case lane-check <<'EOF'
if [ -f .adlc/partials/lane-check.sh ]; then . .adlc/partials/lane-check.sh; else . "$ADLC_TOOLKIT_ROOT/partials/lane-check.sh"; fi
adlc_lane_check "$CASE_REPO" main; echo "rc=$?"
EOF
write_case forge <<'EOF'
if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . "$ADLC_TOOLKIT_ROOT/partials/forge.sh"; fi
adlc_forge_provider "$CASE_REPO"; echo "rc=$?"
EOF
write_case delegate-tools-path <<'EOF'
if [ -f .adlc/partials/delegate-tools-path.sh ]; then . .adlc/partials/delegate-tools-path.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-tools-path.sh"; fi
echo "DELEGATE_TOOLS=$DELEGATE_TOOLS"
"$DELEGATE_TOOLS"/skill-flag.sh mark "$CASE_SANDBOX/flag-dtp" probe 1
echo "flag=$("$DELEGATE_TOOLS"/skill-flag.sh read "$CASE_SANDBOX/flag-dtp" probe)"
EOF
write_case emit-step-telemetry <<'EOF'
if [ -f .adlc/partials/emit-step-telemetry.sh ]; then . .adlc/partials/emit-step-telemetry.sh; else . "$ADLC_TOOLKIT_ROOT/partials/emit-step-telemetry.sh"; fi
echo "DELEGATE_TOOLS=$DELEGATE_TOOLS"
flag="$CASE_SANDBOX/flag-est"
"$DELEGATE_TOOLS"/skill-flag.sh create "$flag"
_adlc_emit_step_telemetry plugin-route probe-step; echo "rc=$?"
EOF
write_case ethos-include <<'EOF'
if [ -f .adlc/partials/ethos-include.sh ]; then . .adlc/partials/ethos-include.sh; else . "$ADLC_TOOLKIT_ROOT/partials/ethos-include.sh"; fi
EOF
write_case intake <<'EOF'
if [ -f .adlc/partials/intake.sh ]; then . .adlc/partials/intake.sh; else . "$ADLC_TOOLKIT_ROOT/partials/intake.sh"; fi
adlc_intake_sections; echo "rc=$?"
EOF
write_case id-alloc <<'EOF'
if [ -f .adlc/partials/id-alloc.sh ]; then . .adlc/partials/id-alloc.sh; else . "$ADLC_TOOLKIT_ROOT/partials/id-alloc.sh"; fi
N=$(adlc_alloc_id req); echo "rc=$?"; echo "N=$N"
EOF
write_case id-recheck <<'EOF'
if [ -f .adlc/partials/id-recheck.sh ]; then . .adlc/partials/id-recheck.sh; else . "$ADLC_TOOLKIT_ROOT/partials/id-recheck.sh"; fi
adlc_recheck_id req REQ-9001; echo "rc=$?"
if command -v adlc_remote_high >/dev/null 2>&1; then echo "id-alloc=loaded"; fi
EOF
write_case routing <<'EOF'
if [ -f .adlc/partials/lane-check.sh ]; then . .adlc/partials/lane-check.sh; else . "$ADLC_TOOLKIT_ROOT/partials/lane-check.sh"; fi
adlc_lane_check "$CASE_REPO" main >/dev/null; echo "lane_rc=$?"
adlc_forge_provider "$CASE_REPO" >/dev/null; echo "forge_rc=$?"
if [ -f .adlc/partials/delegate-tools-path.sh ]; then . .adlc/partials/delegate-tools-path.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-tools-path.sh"; fi
echo "DELEGATE_TOOLS=$DELEGATE_TOOLS"
if [ -f .adlc/partials/ethos-include.sh ]; then . .adlc/partials/ethos-include.sh; else . "$ADLC_TOOLKIT_ROOT/partials/ethos-include.sh"; fi
if [ -f .adlc/partials/intake.sh ]; then . .adlc/partials/intake.sh; else . "$ADLC_TOOLKIT_ROOT/partials/intake.sh"; fi
adlc_intake_sections >/dev/null; echo "intake_rc=$?"
EOF
write_case vendored <<'EOF'
if [ -f .adlc/partials/lane-check.sh ]; then . .adlc/partials/lane-check.sh; else . "$ADLC_TOOLKIT_ROOT/partials/lane-check.sh"; fi
echo "forge_vendored=${ADLC_ROUTE_VENDORED_FORGE:-0}"
echo "provider=$(adlc_forge_provider .)"
if [ -f .adlc/partials/delegate-tools-path.sh ]; then . .adlc/partials/delegate-tools-path.sh; else . "$ADLC_TOOLKIT_ROOT/partials/delegate-tools-path.sh"; fi
echo "DELEGATE_TOOLS=$DELEGATE_TOOLS"
if [ -f .adlc/partials/ethos-include.sh ]; then . .adlc/partials/ethos-include.sh; else . "$ADLC_TOOLKIT_ROOT/partials/ethos-include.sh"; fi
if [ -f .adlc/partials/intake.sh ]; then . .adlc/partials/intake.sh; else . "$ADLC_TOOLKIT_ROOT/partials/intake.sh"; fi
echo "sections=$(adlc_intake_sections | tr '\n' ',')"
EOF

# ===========================================================================
# 4. case_no_skills_symlink_reads (BR-2)
# ===========================================================================
# --- lane-check: the partial, forge.sh behind it, and the engine ------------
R="$SANDBOX/work/lane"; mkrepo "$R"; commit_files "$R" src/a.txt
run_case lane-check "$R" "$CACHE" "$R"
check "lane-check: verdict from the ToolkitRoot engine" "lane_check=pass" "$(out_of lane-check | sed -n 1p)"
check "lane-check: rc" "rc=0" "$(line_of lane-check rc=)"
no_skills_reads lane-check

# --- forge: the partial and forge_config.py ---------------------------------
# A project config sends provider resolution through forge_config.py; the
# GitHub origin keeps the answer the same with or without PyYAML.
R="$SANDBOX/work/forge"; mkrepo "$R"
git -C "$R" remote add origin https://github.com/example/plugin-route-probe.git
mkdir -p "$R/.adlc" && printf 'forge:\n  provider: github\n' > "$R/.adlc/config.yml"
run_case forge "$R" "$CACHE" "$R"
check "forge: provider resolved through ToolkitRoot's forge_config.py" "github" "$(out_of forge | sed -n 1p)"
check "forge: rc" "rc=0" "$(line_of forge rc=)"
no_skills_reads forge

# --- delegate-tools-path: the partial and skill-flag.sh ---------------------
W="$SANDBOX/work/plain"; mkdir -p "$W"
run_case delegate-tools-path "$W" "$CACHE"
check "delegate-tools-path: DELEGATE_TOOLS is ToolkitRoot's" "DELEGATE_TOOLS=$CACHE/tools/delegate" "$(line_of delegate-tools-path DELEGATE_TOOLS=)"
check "delegate-tools-path: skill-flag.sh ran from it" "flag=1" "$(line_of delegate-tools-path flag=)"
no_skills_reads delegate-tools-path

# --- emit-step-telemetry: its self-source and emit-telemetry.sh -------------
# The self-source inside the partial reads delegate-tools-path.sh through the
# default-expansion operand, and the event lands in the HOME log (BR-6).
run_case emit-step-telemetry "$W" "$CACHE"
check "emit-step-telemetry: self-sourced resolver is ToolkitRoot's" "DELEGATE_TOOLS=$CACHE/tools/delegate" "$(line_of emit-step-telemetry DELEGATE_TOOLS=)"
check "emit-step-telemetry: rc" "rc=0" "$(line_of emit-step-telemetry rc=)"
TLOG="$H/Library/Logs/adlc-skill-telemetry.log"
check "emit-step-telemetry: one event in the HOME telemetry log" "1" \
  "$(command grep -c '"plugin-route"' "$TLOG" 2>/dev/null || echo 0)"
no_skills_reads emit-step-telemetry

# --- ethos-include: ToolkitRoot's ETHOS.md ----------------------------------
run_case ethos-include "$W" "$CACHE"
if cmp -s "$SANDBOX/out/ethos-include.out" "$CACHE/ETHOS.md"; then
  pass "ethos-include: printed ToolkitRoot's ETHOS.md byte for byte"
else
  fail "ethos-include: output differs from ToolkitRoot's ETHOS.md (first line: '$(out_of ethos-include | sed -n 1p)')"
fi
no_skills_reads ethos-include

# --- intake: ToolkitRoot's requirement template ------------------------------
run_case intake "$W" "$CACHE"
check "intake: rc" "rc=0" "$(line_of intake rc=)"
n_sections=$(out_of intake | command grep -vc '^rc=')
if [ "$n_sections" -gt 0 ]; then
  pass "intake: $n_sections gap section(s) derived from ToolkitRoot's template"
else
  fail "intake: no gap sections derived"
fi
no_skills_reads intake

# --- id-alloc: allocation with no install.sh state --------------------------
R="$SANDBOX/work/alloc"
git init -q --bare "$R.git" && git clone -q "$R.git" "$R" 2>/dev/null
git -C "$R" config user.email t@t && git -C "$R" config user.name t \
  && git -C "$R" commit -q --allow-empty -m init && git -C "$R" push -q origin HEAD:main 2>/dev/null
run_case id-alloc "$R" "$CACHE"
check "id-alloc: rc" "rc=0" "$(line_of id-alloc rc=)"
check "id-alloc: first id on a fresh machine" "N=1" "$(line_of id-alloc N=)"
no_skills_reads id-alloc

# --- id-recheck: the recheck and the id-alloc.sh it sources ------------------
# Under dash (no BASH_SOURCE, no %x) the sibling comes from the partial's own
# guarded line, i.e. through the default-expansion operand.
run_case id-recheck "$R" "$CACHE"
check "id-recheck: no collision" "rc=0" "$(line_of id-recheck rc=)"
check "id-recheck: id-alloc.sh loaded from ToolkitRoot" "id-alloc=loaded" "$(line_of id-recheck id-alloc=)"
no_skills_reads id-recheck

# ===========================================================================
# 5. case_lookups_follow_toolkit_root — a root with the partials only
# ===========================================================================
R="$SANDBOX/work/routing"; mkrepo "$R"
git -C "$R" remote add origin https://github.com/example/plugin-route-probe.git
mkdir -p "$R/.adlc" && printf 'forge:\n  provider: github\n' > "$R/.adlc/config.yml"
commit_files "$R" src/a.txt
run_case routing "$R" "$BROKEN" "$R"
check "case_lookups_follow_toolkit_root: lane check errors" "lane_rc=2" "$(line_of routing lane_rc=)"
check "case_lookups_follow_toolkit_root: lane error names ToolkitRoot's tools/adlc" "1" \
  "$(err_of routing | command grep -c -F "lane_check.py not found at $BROKEN/tools/adlc/")"
check "case_lookups_follow_toolkit_root: forge resolution errors" "forge_rc=2" "$(line_of routing forge_rc=)"
check "case_lookups_follow_toolkit_root: forge error names ToolkitRoot's forge_config.py" "1" \
  "$(err_of routing | command grep -c -F "$BROKEN/tools/adlc/forge_config.py")"
check "case_lookups_follow_toolkit_root: delegate tools degrade, not fall back to HOME" "DELEGATE_TOOLS=tools/delegate" "$(line_of routing DELEGATE_TOOLS=)"
check "case_lookups_follow_toolkit_root: no ETHOS.md, no fallback" "No ethos found" "$(line_of routing 'No ethos')"
check "case_lookups_follow_toolkit_root: no template, rc 2" "intake_rc=2" "$(line_of routing intake_rc=)"
no_skills_reads routing

# ===========================================================================
# 6. case_vendored_copy_still_first (BR-5)
# ===========================================================================
# lane-check.sh comes from ToolkitRoot; the forge.sh it sources, and every other
# partial, template and tool here, is vendored and must win.
R="$SANDBOX/work/vendored"; mkrepo "$R"
mkdir -p "$R/.adlc/partials" "$R/.adlc/templates" "$R/.adlc/tools/adlc"
{ cat "$PARTIALS/forge.sh"; printf '\nADLC_ROUTE_VENDORED_FORGE=1\n'; } > "$R/.adlc/partials/forge.sh"
printf 'export DELEGATE_TOOLS=vendored-tools\n' > "$R/.adlc/partials/delegate-tools-path.sh"
printf 'VENDORED ETHOS\n' > "$R/.adlc/ETHOS.md"
printf '# Vendored\n\n## Vendored Section\n' > "$R/.adlc/templates/requirement-template.md"
printf 'print("vendored-provider")\n' > "$R/.adlc/tools/adlc/forge_config.py"
printf 'forge:\n  provider: github\n' > "$R/.adlc/config.yml"
run_case vendored "$R" "$CACHE"
check "case_vendored_copy_still_first: partial-to-partial source takes the vendored forge.sh" "forge_vendored=1" "$(line_of vendored forge_vendored=)"
check "case_vendored_copy_still_first: vendored forge_config.py wins" "provider=vendored-provider" "$(line_of vendored provider=)"
check "case_vendored_copy_still_first: vendored delegate-tools-path.sh wins" "DELEGATE_TOOLS=vendored-tools" "$(line_of vendored DELEGATE_TOOLS=)"
check "case_vendored_copy_still_first: vendored ETHOS.md wins" "VENDORED ETHOS" "$(line_of vendored VENDORED)"
check "case_vendored_copy_still_first: vendored template wins" "sections=Vendored Section," "$(line_of vendored sections=)"
no_skills_reads vendored

# A branch that ships its own engine at both places the old lookup tried is not
# run on the plugin route either: ToolkitRoot's engine sees the blocked path.
R="$SANDBOX/work/ownengine"; mkrepo "$R"
mkdir -p "$R/tools/adlc" "$R/.adlc/tools/adlc"
printf 'import sys\nprint("lane_check=pass")\nprint("files_counted=0")\nsys.exit(0)\n' > "$R/tools/adlc/lane_check.py"
cp "$R/tools/adlc/lane_check.py" "$R/.adlc/tools/adlc/lane_check.py"
commit_files "$R" .github/workflows/ci.yml
run_case lane-check "$R" "$CACHE" "$R"
check "case_vendored_copy_still_first: a branch's own lane_check.py is ignored" "lane_check=escalate" "$(out_of lane-check | sed -n 1p)"
check "case_vendored_copy_still_first: installed engine's rc" "rc=1" "$(line_of lane-check rc=)"
no_skills_reads lane-check

# ===========================================================================
# 6b. Skill fences, taken from the SKILL.md text (TASK-125)
# ===========================================================================
# skill_fence <file> <heading-prefix> — the body of the first sh/bash fence after
# the first line that starts with <heading-prefix>. The fence is the shipped
# text, so the case runs what a model would run, not a copy of it.
skill_fence() {
  awk -v h="$2" '
    !seen { if (index($0, h) == 1) seen = 1; next }
    inside { if ($0 ~ /^```[ \t]*$/) exit; print; next }
    /^```(sh|bash|shell)([ \t]|$)/ { inside = 1 }
  ' "$1"
}
# as_plugin <root> — Claude Code's substitution on the plugin route: the exact
# token ${CLAUDE_PLUGIN_ROOT} becomes the cache path before the shell sees the
# text (verification.md row 1). The symlink route runs the text unchanged.
as_plugin() { sed 's#\${CLAUDE_PLUGIN_ROOT}#'"$1"'#g'; }

# run_fence <name> <cwd> <home> — cases/<name>.sh under $SUT with HOME=<home>,
# no ToolkitRoot and no CLAUDE_PLUGIN_ROOT in the environment (the fence's own
# root line resolves it); the exit status lands in out/<name>.rc.
run_fence() {
  ( unset CLAUDE_PLUGIN_ROOT ADLC_TOOLKIT_ROOT
    HOME="$3"; export HOME
    cd "$2" && "$SUT" "$SANDBOX/cases/$1.sh" ) \
    >"$SANDBOX/out/$1.out" 2>"$SANDBOX/out/$1.err"
  echo "$?" > "$SANDBOX/out/$1.rc"
}
rc_of() { cat "$SANDBOX/out/$1.rc"; }

# rel_tree <dir> — every file under <dir>/.adlc and <dir>/.claude, with its
# checksum, by path relative to <dir>: two projects compare by content.
rel_tree() {
  ( cd "$1" && find .adlc .claude -type f 2>/dev/null | LC_ALL=C sort | while IFS= read -r f; do cksum "$f"; done )
}

# The symlink-route machine for the comparisons: a HOME whose ~/.claude/skills
# is a symlink to a second copy of the same tree.
SYMROOT="$SANDBOX/symlink-clone"
mk_root_copy "$SYMROOT" || { echo "plugin-route.test.sh: could not build the symlink-route copy" >&2; exit 1; }
SYMHOME="$SANDBOX/symhome"
mkdir -p "$SYMHOME/.claude" && ln -s "$SYMROOT" "$SYMHOME/.claude/skills" || exit 1

# ===========================================================================
# 6c. case_init_copy_fences_same_tree (BR-8)
# ===========================================================================
INIT_MD="$TOOLKIT/init/SKILL.md"
for s in 6 7 8 9; do
  skill_fence "$INIT_MD" "### Step $s:" > "$SANDBOX/init-step$s.fence"
  as_plugin "$CACHE" < "$SANDBOX/init-step$s.fence" > "$SANDBOX/cases/init-plugin-$s.sh"
  cp "$SANDBOX/init-step$s.fence" "$SANDBOX/cases/init-symlink-$s.sh"
done
check "case_init_copy_fences_same_tree: Step 6 fence taken from init/SKILL.md" "1" \
  "$(command grep -c '^cp "\$ADLC_TOOLKIT_ROOT/ETHOS.md" .adlc/ETHOS.md$' "$SANDBOX/init-step6.fence")"
check "case_init_copy_fences_same_tree: no fence names ~/.claude/skills outside the root line" "0" \
  "$(cat "$SANDBOX"/init-step6.fence "$SANDBOX"/init-step7.fence "$SANDBOX"/init-step8.fence "$SANDBOX"/init-step9.fence \
      | command grep -v -F 'ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"' | command grep -c '\.claude/skills')"

IP="$SANDBOX/work/init-plugin"; IS="$SANDBOX/work/init-symlink"
mkdir -p "$IP/.adlc" "$IS/.adlc" || exit 1   # Step 3 creates .adlc/ before Step 6 runs
for s in 6 7 8 9; do
  run_fence "init-plugin-$s" "$IP" "$H"
  run_fence "init-symlink-$s" "$IS" "$SYMHOME"
  check "case_init_copy_fences_same_tree: Step $s exits 0 on the plugin route" "0" "$(rc_of "init-plugin-$s")"
  check "case_init_copy_fences_same_tree: Step $s exits 0 on the symlink route" "0" "$(rc_of "init-symlink-$s")"
  no_skills_reads "init-plugin-$s"
done
rel_tree "$IP" > "$SANDBOX/init-plugin.tree"
rel_tree "$IS" > "$SANDBOX/init-symlink.tree"
if [ -s "$SANDBOX/init-plugin.tree" ] && cmp -s "$SANDBOX/init-plugin.tree" "$SANDBOX/init-symlink.tree"; then
  pass "case_init_copy_fences_same_tree: the plugin route builds the symlink route's tree ($(wc -l < "$SANDBOX/init-plugin.tree" | tr -d ' ') files)"
else
  fail "case_init_copy_fences_same_tree: trees differ: $(scrub "$(diff "$SANDBOX/init-plugin.tree" "$SANDBOX/init-symlink.tree" | head -4)")"
fi
for f in .adlc/ETHOS.md .adlc/templates/requirement-template.md .adlc/partials/ethos-include.sh \
         .adlc/workflows/adlc-sprint.workflow.js .adlc/workflows/README.md .adlc/context/taxonomy.md \
         .claude/settings.json .adlc/config.yml; do
  if [ -f "$IP/$f" ]; then pass "case_init_copy_fences_same_tree: plugin route vendored $f"; else fail "case_init_copy_fences_same_tree: plugin route did not vendor $f"; fi
done
if cmp -s "$IP/.adlc/ETHOS.md" "$CACHE/ETHOS.md" && cmp -s "$IP/.adlc/workflows/adlc-sprint.workflow.js" "$CACHE/workflows/adlc-sprint.workflow.js"; then
  pass "case_init_copy_fences_same_tree: the vendored copies are ToolkitRoot's bytes"
else
  fail "case_init_copy_fences_same_tree: a vendored copy differs from ToolkitRoot's"
fi
if [ -e "$IP/.adlc/workflows/tests" ] || [ -n "$(find "$IP/.adlc" -name '*.test.js' 2>/dev/null)" ]; then
  fail "case_init_copy_fences_same_tree: the cache copy's workflows/tests reached .adlc/"
else
  pass "case_init_copy_fences_same_tree: no workflows/tests vendored from the cache copy"
fi

# The preflight guard on a root without the toolkit's files: a loud stop that
# names ToolkitRoot and both ways to install.
as_plugin "$BROKEN" < "$SANDBOX/init-step6.fence" > "$SANDBOX/cases/init-broken-6.sh"
IB="$SANDBOX/work/init-broken"; mkdir -p "$IB/.adlc"
run_fence init-broken-6 "$IB" "$H"
check "case_init_copy_fences_same_tree: preflight stops on a root without ETHOS.md" "1" "$(rc_of init-broken-6)"
check "case_init_copy_fences_same_tree: preflight error names ToolkitRoot and both routes" "1" \
  "$(out_of init-broken-6 | command grep -F "not found at $BROKEN (ToolkitRoot)" | command grep -F 'Plugin route:' | command grep -c -F 'Symlink route:')"
if [ -e "$IB/.adlc/ETHOS.md" ]; then
  fail "case_init_copy_fences_same_tree: preflight copied something before stopping"
else
  pass "case_init_copy_fences_same_tree: preflight stopped before any copy"
fi

# ===========================================================================
# 6d. case_template_drift_names_plugin_version (BR-8, AC-8)
# ===========================================================================
TD_MD="$TOOLKIT/template-drift/SKILL.md"
skill_fence "$TD_MD" "### Step 0a:" > "$SANDBOX/td-step0a.fence"
check "case_template_drift_names_plugin_version: Step 0a fence taken from template-drift/SKILL.md" "1" \
  "$(command grep -c '^TOOLKIT="\$ADLC_TOOLKIT_ROOT"$' "$SANDBOX/td-step0a.fence")"

# A released copy: no .git, and a manifest naming a version no other file has.
TDV="7.7.7-td"
TDROOT="$SANDBOX/plugins/cache/adlc-toolkit/adlc/$TDV"
mk_root_copy "$TDROOT" || { echo "plugin-route.test.sh: could not build the template-drift root" >&2; exit 1; }
python3 -c 'import json,sys; p=sys.argv[1]; m=json.load(open(p)); m["version"]=sys.argv[2]; open(p,"w").write(json.dumps(m, indent=2)+"\n")' \
  "$TDROOT/.claude-plugin/plugin.json" "$TDV" || exit 1
TDW="$SANDBOX/work/td"; mkdir -p "$TDW"

# Arm 1: the substituted token.
as_plugin "$TDROOT" < "$SANDBOX/td-step0a.fence" > "$SANDBOX/cases/td-plugin.sh"
run_fence td-plugin "$TDW" "$H"
check "case_template_drift_names_plugin_version: baseline line names the plugin version" \
  "baseline: adlc plugin $TDV ($TDROOT)" "$(out_of td-plugin)"
check "case_template_drift_names_plugin_version: nothing on stderr, no git run on a released copy" "" "$(err_of td-plugin)"
no_skills_reads td-plugin

# Arm 3: unsubstituted text (a subagent's raw read), the hook's pointer file.
mkdir -p "$H/.claude/adlc" && printf '%s\n' "$TDROOT" > "$H/.claude/adlc/plugin-root"
cp "$SANDBOX/td-step0a.fence" "$SANDBOX/cases/td-pointer.sh"
run_fence td-pointer "$TDW" "$H"
rm -f "$H/.claude/adlc/plugin-root"
check "case_template_drift_names_plugin_version: same baseline through the pointer file" \
  "baseline: adlc plugin $TDV ($TDROOT)" "$(out_of td-pointer)"
no_skills_reads td-pointer

# The Context fence that replaced the `!` line listing the toolkit templates.
skill_fence "$TD_MD" "**Toolkit templates dir" | as_plugin "$TDROOT" > "$SANDBOX/cases/td-context.sh"
run_fence td-context "$TDW" "$H"
check "case_template_drift_names_plugin_version: Context fence names ToolkitRoot" "ToolkitRoot: $TDROOT" "$(line_of td-context ToolkitRoot:)"
check "case_template_drift_names_plugin_version: Context fence lists ToolkitRoot's templates" "requirement-template.md" \
  "$(line_of td-context requirement-template.md)"
no_skills_reads td-context

# No manifest: unverified-baseline with its reason, and never a stale verdict.
TDNOMAN="$SANDBOX/plugins/cache/adlc-toolkit/adlc/7.7.8-noman"
mk_root_copy "$TDNOMAN" && rm -f "$TDNOMAN/.claude-plugin/plugin.json" || exit 1
as_plugin "$TDNOMAN" < "$SANDBOX/td-step0a.fence" > "$SANDBOX/cases/td-noman.sh"
run_fence td-noman "$TDW" "$H"
check "case_template_drift_names_plugin_version: no plugin.json -> unverified-baseline" "1" \
  "$(out_of td-noman | command grep -c '^baseline: unverified-baseline ')"
check "case_template_drift_names_plugin_version: no plugin.json -> the reason is on stderr" "1" \
  "$(err_of td-noman | command grep -c '^plugin.json unreadable: FileNotFoundError')"
check "case_template_drift_names_plugin_version: no plugin.json -> no stale verdict" "0" \
  "$(cat "$SANDBOX/out/td-noman.out" "$SANDBOX/out/td-noman.err" | command grep -ci 'stale')"
check "case_template_drift_names_plugin_version: no plugin.json -> no other baseline substituted" "0" \
  "$(out_of td-noman | command grep -c '^baseline: adlc plugin ')"
no_skills_reads td-noman

# A repeated key: json.loads would keep the last value; the fence keeps neither.
TDDUP="$SANDBOX/plugins/cache/adlc-toolkit/adlc/7.7.9-dup"
mk_root_copy "$TDDUP" || exit 1
printf '{"name": "adlc", "version": "7.7.9", "version": "9.9.9"}\n' > "$TDDUP/.claude-plugin/plugin.json"
as_plugin "$TDDUP" < "$SANDBOX/td-step0a.fence" > "$SANDBOX/cases/td-dup.sh"
run_fence td-dup "$TDW" "$H"
check "case_template_drift_names_plugin_version: repeated key -> unverified-baseline" "1" \
  "$(out_of td-dup | command grep -c '^baseline: unverified-baseline ')"
check "case_template_drift_names_plugin_version: repeated key -> named on stderr (LESSON-716)" "1" \
  "$(err_of td-dup | command grep -c 'repeated JSON key')"
check "case_template_drift_names_plugin_version: repeated key -> no stale verdict" "0" \
  "$(cat "$SANDBOX/out/td-dup.out" "$SANDBOX/out/td-dup.err" | command grep -ci 'stale')"

# ===========================================================================
# 6e. case_template_drift_symlink_baseline_unchanged (BR-8, benign path)
# ===========================================================================
# The Step 0a fence as it shipped before REQ-669 (BUG-204), frozen here. The
# symlink route must print what it printed and leave the values it left.
cat > "$SANDBOX/td-step0a.pre-req-669.fence" <<'EOF'
TOOLKIT=$(readlink ~/.claude/skills)
git -C "$TOOLKIT" fetch --prune origin
TK_BRANCH=$(git -C "$TOOLKIT" branch --show-current)
TK_DEFAULT=$(git -C "$TOOLKIT" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')
TK_DEFAULT=${TK_DEFAULT:-main}
TK_DIRTY=$(git -C "$TOOLKIT" status --porcelain | wc -l | tr -d ' ')
TK_BEHIND=$(git -C "$TOOLKIT" rev-list --count "HEAD..origin/$TK_DEFAULT" 2>/dev/null)
EOF
# What the model reads off the fence: the values it reports in the header.
cat > "$SANDBOX/td-report.suffix" <<'EOF'
echo "head=$(git -C "$TOOLKIT" rev-parse HEAD)"
echo "branch=$TK_BRANCH default=$TK_DEFAULT dirty=$TK_DIRTY behind=$TK_BEHIND"
EOF
cat "$SANDBOX/td-step0a.pre-req-669.fence" "$SANDBOX/td-report.suffix" > "$SANDBOX/cases/td-old.sh"
cat "$SANDBOX/td-step0a.fence" "$SANDBOX/td-report.suffix" > "$SANDBOX/cases/td-new.sh"

# A toolkit checkout with an origin, behind the skills symlink of its own HOME.
TDO="$SANDBOX/td-origin.git"; TDC="$SANDBOX/td-checkout"; TDHOME="$SANDBOX/td-symhome"
git init -q --bare "$TDO" 2>/dev/null \
  && git init -q -b main "$TDC" && git -C "$TDC" config user.email t@t && git -C "$TDC" config user.name t \
  && mkdir -p "$TDC/partials" "$TDC/templates" "$TDC/.claude-plugin" \
  && printf 'x\n' > "$TDC/partials/x.sh" && cp "$TOOLKIT/templates/requirement-template.md" "$TDC/templates/" \
  && cp "$TOOLKIT/.claude-plugin/plugin.json" "$TDC/.claude-plugin/" \
  && git -C "$TDC" add -A && git -C "$TDC" commit -qm base \
  && git -C "$TDC" remote add origin "$TDO" && git -C "$TDC" push -q -u origin main 2>/dev/null \
  && git -C "$TDC" remote set-head origin main \
  && mkdir -p "$TDHOME/.claude" && ln -s "$TDC" "$TDHOME/.claude/skills" \
  || { echo "plugin-route.test.sh: could not build the symlink-route checkout" >&2; exit 1; }

# same_baseline <scenario> <expected values line>
same_baseline() {
  run_fence td-old "$TDW" "$TDHOME"; cp "$SANDBOX/out/td-old.out" "$SANDBOX/out/td-old-$1.out"; cp "$SANDBOX/out/td-old.err" "$SANDBOX/out/td-old-$1.err"
  run_fence td-new "$TDW" "$TDHOME"
  if cmp -s "$SANDBOX/out/td-old-$1.out" "$SANDBOX/out/td-new.out" && cmp -s "$SANDBOX/out/td-old-$1.err" "$SANDBOX/out/td-new.err"; then
    pass "case_template_drift_symlink_baseline_unchanged: $1 — stdout and stderr byte-identical to the pre-REQ-669 fence"
  else
    fail "case_template_drift_symlink_baseline_unchanged: $1 — output differs: $(scrub "$(diff "$SANDBOX/out/td-old-$1.out" "$SANDBOX/out/td-new.out" | head -3) $(diff "$SANDBOX/out/td-old-$1.err" "$SANDBOX/out/td-new.err" | head -3)")"
  fi
  check "case_template_drift_symlink_baseline_unchanged: $1 — the BUG-204 values" "$2" "$(line_of td-new branch=)"
  check "case_template_drift_symlink_baseline_unchanged: $1 — measured the checkout's HEAD" \
    "head=$(git -C "$TDC" rev-parse HEAD)" "$(line_of td-new head=)"
  check "case_template_drift_symlink_baseline_unchanged: $1 — no plugin baseline line on the symlink route" "0" \
    "$(out_of td-new | command grep -c '^baseline:')"
}
same_baseline clean "branch=main default=main dirty=0 behind=0"
printf 'edit\n' >> "$TDC/partials/x.sh"
same_baseline dirty "branch=main default=main dirty=1 behind=0"
git -C "$TDC" checkout -q -- partials/x.sh
TDC2="$SANDBOX/td-checkout-2"
git clone -q "$TDO" "$TDC2" 2>/dev/null && git -C "$TDC2" config user.email t@t && git -C "$TDC2" config user.name t \
  && printf 'y\n' > "$TDC2/partials/y.sh" && git -C "$TDC2" add -A && git -C "$TDC2" commit -qm ahead \
  && git -C "$TDC2" push -q origin HEAD:main 2>/dev/null && git -C "$TDC" fetch -q origin 2>/dev/null \
  || { echo "plugin-route.test.sh: could not move origin ahead" >&2; exit 1; }
same_baseline behind "branch=main default=main dirty=0 behind=1"

# ===========================================================================
# 7. case_machine_state_outside_cache (BR-6)
# ===========================================================================
check "case_machine_state_outside_cache: the req counter is in ~/.claude" "2" "$(cat "$H/.claude/.global-next-req" 2>/dev/null)"
tree_sum "$CACHE" > "$SANDBOX/cache.after"
if cmp -s "$SANDBOX/cache.before" "$SANDBOX/cache.after"; then
  pass "case_machine_state_outside_cache: nothing written into ToolkitRoot"
else
  fail "case_machine_state_outside_cache: ToolkitRoot changed: $(scrub "$(diff "$SANDBOX/cache.before" "$SANDBOX/cache.after" | head -3)")"
fi
if [ "$(id -u)" -ne 0 ]; then
  if ls "$GUARD" >/dev/null 2>&1; then
    fail "guard_mode_000_held: \$HOME/.claude/skills became readable during the run"
  else
    pass "guard_mode_000_held: \$HOME/.claude/skills is still mode 000 after every case"
  fi
fi

# ===========================================================================
# Case-count floor: a harness that ran nothing must not read as a pass.
echo "plugin-route.test.sh: $CASES cases executed"
if [ "$CASES" -lt 103 ]; then
  echo "plugin-route.test.sh: FAIL — expected at least 103 cases, ran $CASES ($SUT)"
  exit 1
fi
if [ "$FAILS" -eq 0 ]; then
  echo "plugin-route.test.sh: ALL CASES PASS ($SUT)"
  exit 0
fi
echo "plugin-route.test.sh: $FAILS FAILURE(S) ($SUT)"
exit 1

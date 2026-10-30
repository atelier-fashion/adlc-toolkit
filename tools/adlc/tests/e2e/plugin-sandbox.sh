#!/bin/sh
# tools/adlc/tests/e2e/plugin-sandbox.sh — end-to-end check of the Claude Code plugin
# route on a machine with no toolkit symlinks and no machine state (REQ-669 TASK-131).
#
# Every install goes into a sandbox HOME under one validated `mktemp -d` directory,
# which is removed on exit (`--keep` keeps it). Your own ~/.claude is never read for
# toolkit files and never written. The plugin is installed from a local-path
# marketplace pointed at a `git archive` snapshot of this checkout (`--ref`, default
# HEAD), so uncommitted edits are not tested.
#
# Cases (the TASK-131 Verification table names them):
#   init_spec_status_doctor              AC-1: the two BR-1 commands, the hook, `adlc doctor`
#                                        on the plugin route, then /adlc:init, /adlc:spec and
#                                        /adlc:status (model)
#   lite_req_end_to_end_with_read_guard  AC-2, BR-2: the mode-000 ~/.claude/skills and
#                                        ~/.claude/agents guard, then a lite REQ through
#                                        /adlc:proceed in a throwaway GitHub repo (model + GitHub)
#   symlink_only_regressions             AC-3, BR-3: a symlink-only sandbox HOME made by
#                                        install.sh, `install.sh --dry-run` with zero actions,
#                                        and the four test suites
#   printed_next_steps_runnable          BR-10, ADR-5: printed `/x` next steps against Claude
#                                        Code's own command names (static), then each printed
#                                        step typed as printed on the plugin-only HOME (model)
#   test_release_update                  AC-8, BR-14: a test version bump, `claude plugin
#                                        update`, and the /adlc:template-drift baseline line
#
# A check that needs a model turn or GitHub and cannot get it is SKIPPED with the
# reason, never PASS: an unrun check is not a pass (LESSON-581). Checks assert outcomes
# on disk, in transcripts and through `gh pr view --json state`, not model wording
# (LESSON-478).
#
# Exit: 0 every check passed; 1 at least one FAIL; 2 nothing failed but at least one
# check was skipped (the run is INCOMPLETE and does not clear a release gate).
#
# POSIX sh, and safe under bash 3.2, zsh and dash (REQ-669 BR-17): no `local`, no
# `[[`, no `case` inside `$( )`, no word splitting of unquoted variables, no globs.
# Usage: sh tools/adlc/tests/e2e/plugin-sandbox.sh --help

E2E_USAGE='usage: sh tools/adlc/tests/e2e/plugin-sandbox.sh [options]

  --case NAME            run only this case (repeatable; default: every case)
  --list                 print the case names and exit
  --ref REF              snapshot this git ref of the checkout (default: HEAD)
  --with-model           allow the checks that make model calls (they cost money)
  --model NAME           model for those calls (default: Claude Code default)
  --max-budget-usd N     per-call budget cap for the short model calls (default: 1)
  --pipeline-budget-usd N  budget cap for the /adlc:proceed run (default: 15)
  --pipeline-timeout-min N  wall-clock cap for the /adlc:proceed run (default: 90)
  --throwaway-repo OWNER/NAME  an existing GitHub repo YOU created for this run; its
                         name must contain "e2e". The script never creates or deletes it.
  --test-version V       version the test release bumps to (default: patch+1 with -e2e)
  --keep                 keep the sandbox directory and print its path
  -h, --help             this text

Environment: ADLC_E2E_TMPROOT (where the sandbox is made; default $TMPDIR, else /tmp),
CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY (passed into the sandbox for model calls),
GH_TOKEN (required for the GitHub case: a fine-grained token scoped to the throwaway
repo, the only GitHub credential the sandbox gets; your gh login and config are never
passed in). The model runs are not filesystem-isolated. See README.md.'

E2E_ALL_CASES='init_spec_status_doctor lite_req_end_to_end_with_read_guard symlink_only_regressions printed_next_steps_runnable test_release_update'
E2E_PLUGIN_ID='adlc@adlc-toolkit'
E2E_MARKETPLACE='adlc-toolkit'

OPT_CASES=''
OPT_REF='HEAD'
OPT_WITH_MODEL=0
OPT_MODEL=''
OPT_BUDGET='1'
OPT_PIPELINE_BUDGET='15'
OPT_PIPELINE_TIMEOUT_MIN='90'
OPT_REPO=''
OPT_TEST_VERSION=''
OPT_KEEP=0

e2e_die() { printf 'plugin-sandbox: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case $1 in
    --case) [ $# -ge 2 ] || e2e_die "--case needs a name"; OPT_CASES="$OPT_CASES $2"; shift ;;
    --list) printf '%s\n' "$E2E_ALL_CASES" | tr ' ' '\n'; exit 0 ;;
    --ref) [ $# -ge 2 ] || e2e_die "--ref needs a ref"; OPT_REF=$2; shift ;;
    --with-model) OPT_WITH_MODEL=1 ;;
    --model) [ $# -ge 2 ] || e2e_die "--model needs a name"; OPT_MODEL=$2; shift ;;
    --max-budget-usd) [ $# -ge 2 ] || e2e_die "--max-budget-usd needs a number"; OPT_BUDGET=$2; shift ;;
    --pipeline-budget-usd) [ $# -ge 2 ] || e2e_die "--pipeline-budget-usd needs a number"; OPT_PIPELINE_BUDGET=$2; shift ;;
    --pipeline-timeout-min) [ $# -ge 2 ] || e2e_die "--pipeline-timeout-min needs a number"; OPT_PIPELINE_TIMEOUT_MIN=$2; shift ;;
    --throwaway-repo) [ $# -ge 2 ] || e2e_die "--throwaway-repo needs OWNER/NAME"; OPT_REPO=$2; shift ;;
    --test-version) [ $# -ge 2 ] || e2e_die "--test-version needs a version"; OPT_TEST_VERSION=$2; shift ;;
    --keep) OPT_KEEP=1 ;;
    -h|--help) printf '%s\n' "$E2E_USAGE"; exit 0 ;;
    *) e2e_die "unknown option '$1' (try --help)" ;;
  esac
  shift
done
[ -n "$OPT_CASES" ] || OPT_CASES=" $E2E_ALL_CASES"
OPT_CASES="$OPT_CASES "
e2e_selected() { case $OPT_CASES in *" $1 "*) return 0 ;; esac; return 1; }
for e2e_c in $(printf '%s\n' "$OPT_CASES" | tr ' ' '\n'); do
  case " $E2E_ALL_CASES " in *" $e2e_c "*) ;; *) e2e_die "unknown case '$e2e_c' (try --list)" ;; esac
done

# --- the checkout under test and the caller's tools ---------------------------------
E2E_HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) || e2e_die "cannot locate the script directory"
E2E_REPO=$(git -C "$E2E_HERE" rev-parse --show-toplevel 2>/dev/null) || e2e_die "not inside a git checkout of the toolkit"
E2E_SHA=$(git -C "$E2E_REPO" rev-parse --verify "$OPT_REF^{commit}" 2>/dev/null) || e2e_die "no commit for --ref '$OPT_REF'"
E2E_PY=$(command -v python3) || e2e_die "python3 is required"
E2E_CLAUDE=$(command -v claude 2>/dev/null) || E2E_CLAUDE=''
E2E_GH=$(command -v gh 2>/dev/null) || E2E_GH=''
E2E_NODE=$(command -v node 2>/dev/null) || E2E_NODE=''
E2E_USER=${USER:-$(id -un)}
E2E_REAL_HOME=$HOME

# --- the sandbox: one validated mktemp directory -----------------------------------
E2E_TMPROOT=${ADLC_E2E_TMPROOT:-${TMPDIR:-/tmp}}
while [ "${E2E_TMPROOT%/}" != "$E2E_TMPROOT" ]; do E2E_TMPROOT=${E2E_TMPROOT%/}; done
case $E2E_TMPROOT in /?*) ;; *) e2e_die "sandbox root '$E2E_TMPROOT' is not an absolute path" ;; esac
[ -d "$E2E_TMPROOT" ] || e2e_die "sandbox root '$E2E_TMPROOT' is not a directory"
E2E_TMPROOT_REAL=$(CDPATH= cd -- "$E2E_TMPROOT" && pwd -P) || e2e_die "cannot resolve '$E2E_TMPROOT'"

# e2e_valid_sbx <path> — true only for the directory this run made. Checked before the
# first write into it and again before `rm -rf` (LESSON-017).
e2e_valid_sbx() {
  evs_p=$1
  case $evs_p in
    ''|*'
'*|*/../*|*/..|*/./*) return 1 ;;
  esac
  case $evs_p in "$E2E_TMPROOT_REAL"/adlc-e2e.??????) ;; *) return 1 ;; esac
  [ -d "$evs_p" ] && [ ! -L "$evs_p" ] && [ -O "$evs_p" ] || return 1
  evs_r=$(CDPATH= cd -- "$evs_p" 2>/dev/null && pwd -P) || return 1
  [ "$evs_r" = "$evs_p" ] || return 1
  case $evs_r in /|"$E2E_REAL_HOME"|"$E2E_REAL_HOME"/.claude|"$E2E_REAL_HOME"/.claude/*) return 1 ;; esac
  return 0
}

E2E_SBX=$(mktemp -d "$E2E_TMPROOT_REAL/adlc-e2e.XXXXXX") || e2e_die "mktemp -d failed under $E2E_TMPROOT_REAL"
e2e_valid_sbx "$E2E_SBX" || e2e_die "mktemp gave '$E2E_SBX', which failed validation; not using it"
if git -C "$E2E_SBX" rev-parse --git-dir >/dev/null 2>&1; then
  # adlc doctor's `reservations` check pushes a probe ref to the cwd repo's origin.
  rmdir "$E2E_SBX"
  e2e_die "the sandbox root is inside a git work tree; set ADLC_E2E_TMPROOT to a directory outside any repo"
fi

e2e_cleanup() {
  if [ "$OPT_KEEP" = 1 ]; then
    printf 'sandbox kept: %s\n' "$E2E_SBX"
    printf 'remove it with: chmod -R u+rwx %s && rm -rf %s\n' "$E2E_SBX" "$E2E_SBX"
    return 0
  fi
  if e2e_valid_sbx "$E2E_SBX"; then
    chmod -R u+rwx "$E2E_SBX" 2>/dev/null
    rm -rf -- "$E2E_SBX"
  else
    printf 'plugin-sandbox: refusing to remove %s: it failed validation\n' "$E2E_SBX" >&2
  fi
}
trap e2e_cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

E2E_BIN=$E2E_SBX/bin
E2E_TMP=$E2E_SBX/tmp
E2E_LOGS=$E2E_SBX/logs
E2E_WORK=$E2E_SBX/work
E2E_RESULTS=$E2E_SBX/results.tsv
mkdir -p "$E2E_BIN" "$E2E_TMP" "$E2E_LOGS" "$E2E_WORK" "$E2E_SBX/toolbin" || e2e_die "cannot populate $E2E_SBX"
: > "$E2E_RESULTS"
export E2E_TMP

# --- helpers written into the sandbox ----------------------------------------------
# The launcher builds each sandbox command's environment from an allowlist. Secrets
# (model and GitHub credentials) reach the child through its environment, never argv,
# and only for the calls that need them (E2E_PASS_AUTH, E2E_PASS_GH).
cat > "$E2E_BIN/launch.py" <<'PY'
import os, subprocess, sys
home, path, userbase = sys.argv[1], sys.argv[2], sys.argv[3]
cmd = sys.argv[4:]
src = os.environ
env = {"HOME": home, "PATH": path, "USER": src.get("E2E_USER", ""),
       "LOGNAME": src.get("E2E_USER", ""), "SHELL": "/bin/sh", "TERM": "dumb",
       "TMPDIR": src["E2E_TMP"]}
# The caller's locale and bytecode settings, from copies the shell made. Python's own
# os.environ cannot be used for these: in the C locale it coerces LC_CTYPE to UTF-8
# (PEP 538), which changes what awk and grep do in the child.
for k in src.get("E2E_KEEP_KEYS", "").split():
    env[k] = src.get("E2E_KEEP_" + k, "")
if userbase:
    env["PYTHONUSERBASE"] = userbase
if src.get("E2E_PASS_AUTH") == "1":
    for k in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
        if src.get(k):
            env[k] = src[k]
# GitHub: GH_TOKEN alone, which the README asks to be a fine-grained token scoped to
# the throwaway repo. Never the caller's gh config directory or GITHUB_TOKEN: a model
# run can reach the caller's whole filesystem (a sandbox HOME is not a boundary), so
# what it is handed must be no broader than the repo it is meant to touch.
if src.get("E2E_PASS_GH") == "1" and src.get("GH_TOKEN"):
    env["GH_TOKEN"] = src["GH_TOKEN"]
for k in ("CLAUDE_PLUGIN_ROOT", "CLAUDE_ENV_FILE"):
    if src.get("E2E_SET_" + k):
        env[k] = src["E2E_SET_" + k]
timeout = int(src.get("E2E_TIMEOUT") or "900")
try:
    proc = subprocess.Popen(cmd, env=env)
except OSError as exc:
    sys.stderr.write("e2e-launch: cannot run %s: %s\n" % (cmd[0], exc))
    sys.exit(127)
try:
    sys.exit(proc.wait(timeout=timeout))
except subprocess.TimeoutExpired:
    proc.kill()
    proc.wait()
    sys.stderr.write("e2e-launch: %s timed out after %ds\n" % (cmd[0], timeout))
    sys.exit(124)
PY

cat > "$E2E_BIN/helpers.py" <<'PY'
"""plugin-sandbox.sh helpers. Stdlib only, Python 3.6+."""
import collections, glob, json, os, re, sys, uuid

ROOT_LINE_HEAD = 'ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}";'


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def install_record(home, plugin_id):
    data = load(os.path.join(home, ".claude", "plugins", "installed_plugins.json"))
    recs = (data.get("plugins") or {}).get(plugin_id) or []
    if not recs or not isinstance(recs[0], dict):
        sys.exit("no install record for %s" % plugin_id)
    return recs[0]


def cmd_record(home, plugin_id):
    rec = install_record(home, plugin_id)
    print("%s\t%s" % (rec.get("version", ""), rec.get("installPath", "")))


def cmd_list_entry(listjson, plugin_id):
    for entry in load(listjson):
        if entry.get("id") == plugin_id:
            print("%s\t%s\t%s" % (entry.get("version", ""), str(entry.get("enabled")).lower(),
                                  entry.get("installPath", "")))
            return
    sys.exit("%s is not in `claude plugin list --json`" % plugin_id)


def cmd_load_root(home, plugin_id):
    # The directory Claude Code loads the plugin from: a local-path (directory)
    # marketplace runs its source directory, every other source the recorded
    # installPath (REQ-669 verification.md row 12, E4).
    name, market = plugin_id.split("@", 1)
    rec = install_record(home, plugin_id)
    known = load(os.path.join(home, ".claude", "plugins", "known_marketplaces.json"))
    entry = known.get(market) or {}
    source = entry.get("source") or {}
    if source.get("source") == "directory":
        base = entry.get("installLocation") or source.get("path")
        manifest = load(os.path.join(base, ".claude-plugin", "marketplace.json"))
        for plugin in manifest.get("plugins") or []:
            if plugin.get("name") == name and isinstance(plugin.get("source"), str):
                print(os.path.realpath(os.path.join(base, plugin["source"])))
                return
    print(rec.get("installPath", ""))


def cmd_version(root):
    print(load(os.path.join(root, ".claude-plugin", "plugin.json")).get("version", ""))


def cmd_bump(version):
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if not m:
        sys.exit("cannot bump version %r" % version)
    print("%s.%s.%d-e2e" % (m.group(1), m.group(2), int(m.group(3)) + 1))


def cmd_set_version(root, version):
    path = os.path.join(root, ".claude-plugin", "plugin.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh, object_pairs_hook=collections.OrderedDict)
    data["version"] = version
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, indent=2) + "\n")
    with open(os.path.join(root, "VERSION"), "w", encoding="utf-8") as fh:
        fh.write(version + "\n")


def fences(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return re.findall(r"^```(?:bash|sh)[^\n]*\n(.*?)^```[ \t]*$", text, re.M | re.S)


def subst(text, root):
    # The loader rewrites the exact braced token and nothing else (verification.md row 1).
    return text if root == "-" else text.replace("${CLAUDE_PLUGIN_ROOT}", root)


def cmd_fence(skill, needle, root):
    hits = [b for b in fences(skill) if needle in b]
    if len(hits) != 1:
        sys.exit("%s: %d fences contain %r, expected exactly 1" % (skill, len(hits), needle))
    sys.stdout.write(subst(hits[0], root))


def cmd_root_line(skill, root):
    with open(skill, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith(ROOT_LINE_HEAD):
                sys.stdout.write(subst(line, root))
                return
    sys.exit("%s has no canonical root line" % skill)


def records(paths):
    """Yield (role, block) for every content block in transcripts or stream logs."""
    for path in paths:
        try:
            fh = open(path, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(obj, dict):
                    continue
                msg = obj.get("message")
                if isinstance(msg, dict):
                    role = msg.get("role") or obj.get("type")
                    content = msg.get("content")
                    if isinstance(content, str):
                        yield role, {"type": "text", "text": content}
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict):
                                yield role, block
                if obj.get("type") == "result" and isinstance(obj.get("result"), str):
                    yield "result", {"type": "text", "text": obj["result"]}


def block_text(block):
    content = block.get("content", block.get("text", ""))
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
    return content if isinstance(content, str) else json.dumps(content)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            for s in strings(v):
                yield s
    elif isinstance(value, list):
        for v in value:
            for s in strings(v):
                yield s


GUARDED = re.compile(r"(?:~|\$HOME|\$\{HOME\}|/)[^\s\"']*?/?\.claude/(?:skills|agents)\b")
DENIED = re.compile(r"(?i)(permission denied|eacces|operation not permitted)")
# The arms of the canonical root line and the ADR-2 default spelling name
# ~/.claude/skills by design: an existence test that the guard makes false.
ALLOWED = [
    '[ ! -d "$HOME/.claude/skills/partials" ]',
    'ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"',
    '${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}',
]


# Tool calls that reach the filesystem. A prompt handed to the Agent or Skill tool may
# quote skill prose that names ~/.claude/skills without reading it.
FS_TOOLS = {"Bash", "Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "Glob", "Grep", "LS"}


def cmd_scan(*paths):
    findings = []
    for role, block in records(paths):
        kind = block.get("type")
        if kind == "tool_use":
            name = block.get("name", "")
            if name not in FS_TOOLS:
                continue
            text = "\n".join(strings(block.get("input")))
            if name == "Bash":
                for allowed in ALLOWED:
                    text = text.replace(allowed, "")
            if GUARDED.search(text):
                findings.append("%s tool_use names a guarded path: %s" % (name, text.strip()[:200]))
        elif kind == "tool_result":
            text = block_text(block)
            for line in text.splitlines():
                if DENIED.search(line) and ".claude/" in line and GUARDED.search(line):
                    findings.append("tool_result was refused under the guard: %s" % line.strip()[:200])
    for f in findings:
        print(f)
    sys.exit(1 if findings else 0)


def cmd_command_names(*paths):
    for role, block in records(paths):
        if block.get("type") == "text":
            for m in re.finditer(r"<command-name>([^<]*)</command-name>", block.get("text", "")):
                print(m.group(1).strip())


def cmd_printed(names_csv, *paths):
    names = "|".join(re.escape(n) for n in names_csv.split(",") if n)
    pat = re.compile(r"(?<![A-Za-z0-9_./:$~-])/((?:adlc:)?(?:%s))(?![A-Za-z0-9_/-])" % names)
    seen = []
    for role, block in records(paths):
        if role in ("assistant", "result") and block.get("type") == "text":
            for m in pat.finditer(block.get("text", "")):
                if m.group(1) not in seen:
                    seen.append(m.group(1))
    for token in seen:
        print("/" + token)


def cmd_tool_output_has(needle, *paths):
    for role, block in records(paths):
        if block.get("type") == "tool_result" and needle in block_text(block):
            sys.exit(0)
    sys.exit(1)


def cmd_result_text(path):
    out = []
    for role, block in records([path]):
        if role == "result":
            out.append(block.get("text", ""))
    sys.stdout.write("\n".join(out))


def cmd_logged_in(path):
    try:
        print("true" if load(path).get("loggedIn") is True else "false")
    except (OSError, ValueError, AttributeError):
        print("false")


def cmd_lane(reqfile):
    with open(reqfile, encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    lane = re.search(r'^lane:[ \t]*"?([a-z]+)"?', m.group(1), re.M) if m else None
    print(lane.group(1) if lane else "")


# --- BR-10 static audit -------------------------------------------------------------
# INSTR_VERB and INSTR_TAIL are BUILTIN_COLLISION_VERB_RE and BUILTIN_COLLISION_TAIL_RE
# in tools/lint-skills/check.py, character for character (a lint test compares them).
# A line that also carries /adlc:<name> prints both spellings (TASK-133), so it is
# counted as dual-spelled, not as a bare instruction.
# "*/references/*.md": the skills' companions (REQ-661), which the lint reads too.
SHIPPED = ["*/SKILL.md", "*/references/*.md", "proceed/*.md", "agents/*.md", "partials/*.sh", "partials/*.md",
           "scripts/*", "hooks/*", "workflows/*.js", "workflows/*.md", "templates/*",
           "presets/*", "ETHOS.md", "tools/adlc/*.py", "tools/delegate/*"]
INSTR_VERB = (r"(?i)\b(?:run|re-run|rerun|re-runs|reruns|running|re-running|invoke|type|"
              r"recommend(?:s|ing)?(?: running)?|proceed to|ready for|before|note for|use|try)"
              r"\s+[`\"']?/(%s)(?![A-Za-z0-9_/-])")
INSTR_TAIL = (r"(?<![A-Za-z0-9_./:$~-])/(%s)[`\"']?\s+(?:first|there too|to vendor|to refresh|"
              r"to scaffold|to set up|if missing|to copy)\b")


def builtin_kinds(data, name):
    q = re.escape(name)
    kinds = []

    def has(pat):
        return re.search(pat.encode(), data) is not None

    if (has(r'type:"(?:prompt|local|local-jsx)",name:"%s"' % q) or has(r'\(\{name:"%s",' % q)
            or has(r'name:"%s",(?:get )?description[^{}]{0,600}source:"builtin"' % q)):
        kinds.append("command")
    else:
        for m in re.finditer((r'\b([A-Za-z_$][\w$]{0,6})="%s"' % q).encode(), data):
            if re.search(rb"\(\{name:" + re.escape(m.group(1)) + rb"[,}]", data):
                kinds.append("command")
                break
    if has(r'aliases:\[[^\]]{0,200}"%s"' % q):
        kinds.append("alias")
    return kinds


def cmd_audit(root, binary):
    skills = sorted(d for d in os.listdir(root) if os.path.isfile(os.path.join(root, d, "SKILL.md")))
    with open(binary, "rb") as fh:
        data = fh.read()
    anchors = [a for a in ("help", "clear", "compact", "model")
               if re.search(('type:"(?:prompt|local|local-jsx)",name:"%s"' % a).encode(), data)]
    print("builtin-table: %s (anchors found: %s)" % (binary, ",".join(anchors) or "none"))
    if len(anchors) < 3:
        print("VERDICT unreadable")
        return
    files = sorted({f for p in SHIPPED for f in glob.glob(os.path.join(root, p)) if os.path.isfile(f)})
    names = "|".join(re.escape(s) for s in skills)
    ref = re.compile(r"(?<![A-Za-z0-9_./:$~-])/(%s)(?![A-Za-z0-9_/-])" % names)
    pre, post = re.compile(INSTR_VERB % names), re.compile(INSTR_TAIL % names)
    total = collections.Counter()
    dual = collections.Counter()
    instr = collections.defaultdict(list)
    for path in files:
        rel = os.path.relpath(path, root)
        with open(path, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh, 1):
                for m in ref.finditer(line):
                    total[m.group(1)] += 1
                hit = {m.group(1) for m in pre.finditer(line)} | {m.group(1) for m in post.finditer(line)}
                for n in hit:
                    if "/adlc:%s" % n in line:
                        dual[n] += 1
                    else:
                        instr[n].append("%s:%d" % (rel, i))
    used = sorted(set(instr) | set(dual))
    print("shipped files scanned: %d; skill names in printed run-/x instructions: %s"
          % (len(files), ",".join(used)))
    fail, warn = [], []
    for name in skills:
        kinds = builtin_kinds(data, name)
        if not kinds:
            continue
        locs = instr.get(name, [])
        nfiles = len({loc.rsplit(":", 1)[0] for loc in locs})
        what = "built-in command of the same name" if "command" in kinds else "alias of a built-in command"
        print("collision /%s: %s; %d references, %d bare instruction lines in %d files, "
              "%d dual-spelled" % (name, what, total[name], len(locs), nfiles, dual[name]))
        byfile = collections.OrderedDict()
        for loc in locs:
            path, line = loc.rsplit(":", 1)
            byfile.setdefault(path, []).append(line)
        for path, lines in byfile.items():
            print("    %s:%s" % (path, ",".join(lines)))
        if "command" in kinds and locs:
            fail.append(name)
        else:
            warn.append(name)
    print("VERDICT %s fail=%s warn=%s" % ("fail" if fail else ("warn" if warn else "pass"),
                                         ",".join(fail) or "-", ",".join(warn) or "-"))


def cmd_skill_names(root):
    print(",".join(sorted(d for d in os.listdir(root)
                          if os.path.isfile(os.path.join(root, d, "SKILL.md")))))


def cmd_uuid():
    print(uuid.uuid4())


def cmd_realpath(path):
    print(os.path.realpath(path))


def cmd_filter_path(path, home):
    home = home.rstrip("/")
    keep = []
    for entry in path.split(":"):
        if not entry or not entry.startswith("/"):
            continue
        if entry == home or entry.startswith(home + "/"):
            continue
        if entry not in keep:
            keep.append(entry)
    print(":".join(keep))


if __name__ == "__main__":
    fn = globals().get("cmd_" + sys.argv[1].replace("-", "_"))
    if fn is None:
        sys.exit("helpers.py: unknown command %s" % sys.argv[1])
    fn(*sys.argv[2:])
PY

e2e_py() { "$E2E_PY" -I "$E2E_BIN/helpers.py" "$@"; }

# The sandbox PATH: the caller's PATH without any entry under the real HOME (so no
# ~/bin/adlc or other personal shim answers), behind a toolbin that keeps claude, gh
# and node reachable wherever they are installed.
for e2e_t in claude gh node; do
  e2e_tp=$(command -v "$e2e_t" 2>/dev/null) || continue
  case $e2e_tp in /*) ln -s "$e2e_tp" "$E2E_SBX/toolbin/$e2e_t" ;; esac
done
E2E_PATH="$E2E_SBX/toolbin:$(e2e_py filter-path "$PATH" "$E2E_REAL_HOME")"
# Python packages installed with --user (PyYAML, pytest) live under the real HOME's
# user base. The sandbox reads them from there so it has this machine's packages,
# while seeing none of its ~/.claude.
E2E_USERBASE=$("$E2E_PY" -I -c 'import site; print(site.getuserbase())' 2>/dev/null) || E2E_USERBASE=''
[ -d "$E2E_USERBASE" ] || E2E_USERBASE=''
export E2E_USER
# The caller's locale, timezone and bytecode settings pass through unchanged, and only
# those that are set (see launch.py for why they travel as copies).
E2E_KEEP_KEYS=''
for e2e_k in LANG LC_ALL LC_CTYPE LC_MESSAGES TZ PYTHONDONTWRITEBYTECODE; do
  eval "e2e_isset=\${$e2e_k+x}"
  if [ -n "$e2e_isset" ]; then
    eval "E2E_KEEP_$e2e_k=\$$e2e_k; export E2E_KEEP_$e2e_k"
    E2E_KEEP_KEYS="$E2E_KEEP_KEYS $e2e_k"
  fi
done
export E2E_KEEP_KEYS

# e2e_run_in <home> <cmd> [args...] — run in the current directory with the sandbox
# environment and HOME=<home>.
e2e_run_in() {
  eri_home=$1; shift
  "$E2E_PY" -I "$E2E_BIN/launch.py" "$eri_home" "$E2E_PATH" "$E2E_USERBASE" "$@"
}
# e2e_git <home> <git args...> — git for the sandbox's own repos, under the sandbox
# HOME, so its .gitconfig (identity, no personal hooks) applies.
e2e_git() {
  eg_home=$1; shift
  e2e_run_in "$eg_home" git "$@"
}

# --- results -----------------------------------------------------------------------
# e2e_check <case> <check> <PASS|FAIL|SKIPPED> <detail>
e2e_check() {
  ec_detail=$(printf '%s' "$4" | tr '\t\n' '  ')
  printf '%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$ec_detail" >> "$E2E_RESULTS"
  printf '  [%s] %s.%s — %s\n' "$3" "$1" "$2" "$ec_detail"
}

# e2e_excerpt <file> — the lines a reader needs from a failed command's log.
e2e_excerpt() {
  [ -s "$1" ] || return 0
  { command grep -n -E '^(FAIL|\[FAIL\])|FAILED|Error|error:|ERROR' "$1" | head -n 12
    printf -- '--- last lines of %s ---\n' "$(basename "$1")"
    tail -n 8 "$1"; } | sed 's/^/      /'
}

# --- machine prerequisites ---------------------------------------------------------
E2E_GIT_NAME=$(git config --global --get user.name 2>/dev/null) || E2E_GIT_NAME=''
E2E_GIT_EMAIL=$(git config --global --get user.email 2>/dev/null) || E2E_GIT_EMAIL=''
[ -n "$E2E_GIT_NAME" ] || E2E_GIT_NAME='ADLC e2e'
[ -n "$E2E_GIT_EMAIL" ] || E2E_GIT_EMAIL='adlc-e2e@example.invalid'

# e2e_new_home <dir> [guard] — a fresh HOME with only a git identity, the machine fact
# every user has. With `guard`, ~/.claude/skills and ~/.claude/agents are mode-000
# directories, so any read under them fails (BR-2, AC-2).
# The empty credential.helper resets the helper list. Xcode's git ships
# `helper = osxkeychain` in its own gitconfig, and after every authenticated push git
# asks it to store the credential: under a sandbox HOME there is no login keychain, so
# macOS raises a modal "Keychain Not Found" dialog and the push waits on it.
e2e_new_home() {
  mkdir -p "$1/.claude" || return 1
  printf '[user]\n\tname = %s\n\temail = %s\n[credential]\n\thelper =\n' \
    "$E2E_GIT_NAME" "$E2E_GIT_EMAIL" > "$1/.gitconfig"
  if [ "${2:-}" = guard ]; then
    mkdir -p "$1/.claude/skills" "$1/.claude/agents" && chmod 000 "$1/.claude/skills" "$1/.claude/agents"
  fi
}

E2E_MODEL_READY=''
E2E_MODEL_REASON=''
e2e_model_ready() {
  if [ -n "$E2E_MODEL_READY" ]; then [ "$E2E_MODEL_READY" = yes ]; return; fi
  E2E_MODEL_READY=no
  if [ -z "$E2E_CLAUDE" ]; then E2E_MODEL_REASON='claude is not on PATH'; return 1; fi
  mkdir -p "$E2E_SBX/auth-home"
  (cd "$E2E_WORK" && E2E_PASS_AUTH=1 && export E2E_PASS_AUTH && E2E_TIMEOUT=60 && export E2E_TIMEOUT \
    && e2e_run_in "$E2E_SBX/auth-home" claude auth status --json) > "$E2E_LOGS/auth-status.json" 2>&1
  emr_in=$(e2e_py logged-in "$E2E_LOGS/auth-status.json")
  emr_auth=''
  if [ "$emr_in" = true ]; then emr_auth='claude auth status in a sandbox HOME: loggedIn true'
  elif [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then emr_auth='CLAUDE_CODE_OAUTH_TOKEN is set'
  elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then emr_auth='ANTHROPIC_API_KEY is set'
  fi
  if [ -z "$emr_auth" ]; then
    E2E_MODEL_REASON='no model access: claude auth status in a sandbox HOME reports loggedIn false, and neither CLAUDE_CODE_OAUTH_TOKEN nor ANTHROPIC_API_KEY is set'
    [ "$OPT_WITH_MODEL" = 1 ] || E2E_MODEL_REASON="$E2E_MODEL_REASON; --with-model was not given either"
    return 1
  fi
  if [ "$OPT_WITH_MODEL" != 1 ]; then
    E2E_MODEL_REASON="model calls cost money and need --with-model ($emr_auth)"
    return 1
  fi
  E2E_MODEL_REASON=$emr_auth
  E2E_MODEL_READY=yes
  return 0
}

E2E_GH_READY=''
E2E_GH_REASON=''
e2e_github_ready() {
  if [ -n "$E2E_GH_READY" ]; then [ "$E2E_GH_READY" = yes ]; return; fi
  E2E_GH_READY=no
  if [ -z "$OPT_REPO" ]; then
    E2E_GH_REASON='no throwaway GitHub repo: create one yourself (gh repo create OWNER/adlc-e2e-YYYYMMDD --private) and pass --throwaway-repo OWNER/NAME'
    return 1
  fi
  case $OPT_REPO in
    */*/*|*[!A-Za-z0-9._/-]*|/*|*/) E2E_GH_REASON="--throwaway-repo '$OPT_REPO' is not OWNER/NAME"; return 1 ;;
    */*e2e*) ;;
    *) E2E_GH_REASON="--throwaway-repo '$OPT_REPO': the name must contain 'e2e', so a real repo is never driven by mistake"; return 1 ;;
  esac
  if [ -z "$E2E_GH" ]; then E2E_GH_REASON='gh is not on PATH'; return 1; fi
  if [ -z "${GH_TOKEN:-}" ]; then
    E2E_GH_REASON='GH_TOKEN is not set: the GitHub case runs only with a fine-grained token scoped to the throwaway repo (README.md, "What it needs"); your gh login and config are never passed into the sandbox'
    return 1
  fi
  # Probed the way the sandbox will use it: an empty HOME and GH_TOKEN alone.
  mkdir -p "$E2E_SBX/gh-home"
  if ! (cd "$E2E_WORK" && E2E_PASS_GH=1 && export E2E_PASS_GH && E2E_TIMEOUT=60 && export E2E_TIMEOUT \
        && e2e_run_in "$E2E_SBX/gh-home" gh repo view "$OPT_REPO" --json name) >/dev/null 2>&1; then
    E2E_GH_REASON="gh repo view $OPT_REPO with GH_TOKEN alone fails: the repo does not exist or the token cannot read it"
    return 1
  fi
  E2E_GH_READY=yes
  return 0
}

# --- the snapshot and the plugin install -------------------------------------------
e2e_snapshot() {
  [ -f "$E2E_SBX/src/.claude-plugin/plugin.json" ] && return 0
  mkdir -p "$E2E_SBX/src" || return 1
  git -C "$E2E_REPO" archive "$E2E_SHA" > "$E2E_SBX/src.tar" && tar -x -f "$E2E_SBX/src.tar" -C "$E2E_SBX/src" \
    && rm -f "$E2E_SBX/src.tar" && [ -f "$E2E_SBX/src/.claude-plugin/plugin.json" ]
}

# e2e_install <case> <home> <marketplace dir> — the two BR-1 commands, with the local
# snapshot standing in for atelier-fashion/adlc-toolkit. Records one check.
e2e_install() {
  ei_case=$1 ei_home=$2 ei_src=$3
  ei_log=$E2E_LOGS/$ei_case-install.log
  ei_want=$(tr -d ' \n' < "$ei_src/VERSION")
  (cd "$E2E_WORK" && e2e_run_in "$ei_home" claude plugin marketplace add "$ei_src" \
    && e2e_run_in "$ei_home" claude plugin install "$E2E_PLUGIN_ID" \
    && e2e_run_in "$ei_home" claude plugin list --json > "$E2E_LOGS/$ei_case-list.json") \
    < /dev/null > "$ei_log" 2>&1
  ei_rc=$?
  if [ "$ei_rc" -ne 0 ]; then
    e2e_check "$ei_case" bri1_install FAIL "marketplace add / plugin install exited $ei_rc"
    e2e_excerpt "$ei_log"
    return 1
  fi
  ei_entry=$(e2e_py list-entry "$E2E_LOGS/$ei_case-list.json" "$E2E_PLUGIN_ID" 2>&1)
  ei_ver=$(printf '%s' "$ei_entry" | cut -f1)
  ei_on=$(printf '%s' "$ei_entry" | cut -f2)
  ei_path=$(printf '%s' "$ei_entry" | cut -f3)
  if [ "$ei_ver" = "$ei_want" ] && [ "$ei_on" = true ] && [ -f "$ei_path/.claude-plugin/plugin.json" ]; then
    e2e_check "$ei_case" bri1_install PASS "claude plugin list: $E2E_PLUGIN_ID $ei_ver enabled, cache copy at $ei_path"
    return 0
  fi
  e2e_check "$ei_case" bri1_install FAIL "claude plugin list gave '$ei_entry', expected version $ei_want enabled"
  return 1
}

# e2e_hook <case> <home> <root> <envfile> <check> — the plugin's SessionStart hook, run
# with the environment Claude Code gives it (verification.md row 9). Starting a real
# session needs a model turn, so the hook is run directly. The hook records the pointer
# only for a plugin-cache copy (LESSON-718): a root that resolves under <home>'s plugin
# cache must end up in the pointer, resolved; any other root, such as the source
# directory a local-path marketplace runs, must leave the pointer as it was.
e2e_hook() {
  eh_case=$1 eh_home=$2 eh_root=$3 eh_env=$4 eh_check=$5
  : > "$eh_env"
  eh_before=$(cat "$eh_home/.claude/adlc/plugin-root" 2>/dev/null)
  (cd "$E2E_WORK" && E2E_SET_CLAUDE_PLUGIN_ROOT=$eh_root && E2E_SET_CLAUDE_ENV_FILE=$eh_env \
    && export E2E_SET_CLAUDE_PLUGIN_ROOT E2E_SET_CLAUDE_ENV_FILE \
    && e2e_run_in "$eh_home" sh "$eh_root/scripts/session-start.sh") > "$E2E_LOGS/$eh_case-$eh_check.log" 2>&1
  eh_rc=$?
  eh_ptr=$(cat "$eh_home/.claude/adlc/plugin-root" 2>/dev/null)
  eh_real=$(CDPATH= cd -P -- "$eh_root" 2>/dev/null && pwd -P)
  eh_cache=$(CDPATH= cd -P -- "$eh_home/.claude/plugins/cache" 2>/dev/null && pwd -P)
  eh_want=$eh_before
  eh_what="a local-path source root, so the pointer is left as it was ('$eh_before')"
  if [ -n "$eh_cache" ] && [ -n "$eh_real" ]; then
    case $eh_real in
      "$eh_cache"/?*) eh_want=$eh_real; eh_what="a plugin-cache copy, so the pointer names $eh_real" ;;
    esac
  fi
  if [ "$eh_rc" -eq 0 ] && [ "$eh_ptr" = "$eh_want" ] \
     && command grep -q 'enabled: false' "$eh_home/.claude/adlc/config.yml" 2>/dev/null \
     && command grep -qF "$eh_root/scripts\" # adlc-plugin-path" "$eh_env" \
     && [ "$(command grep -c -v '^adlc: ' "$E2E_LOGS/$eh_case-$eh_check.log")" = 0 ]; then
    e2e_check "$eh_case" "$eh_check" PASS "root is $eh_what; config.yml scaffolded with delegation off, PATH line appended (hook run directly with CLAUDE_PLUGIN_ROOT and CLAUDE_ENV_FILE)"
    return 0
  fi
  e2e_check "$eh_case" "$eh_check" FAIL "hook rc=$eh_rc, pointer='$eh_ptr' (want '$eh_want': root is $eh_what), or config.yml / PATH line missing, or output other than one adlc: line"
  e2e_excerpt "$E2E_LOGS/$eh_case-$eh_check.log"
  return 1
}

# e2e_doctor <case> <check> <home> <cwd> <envfile> — `adlc doctor` through the PATH line
# the hook wrote, and the plugin-route assertions (AC-1, REQ-669 ADR-7).
e2e_doctor() {
  ed_case=$1 ed_check=$2 ed_home=$3 ed_cwd=$4 ed_env=$5
  ed_log=$E2E_LOGS/$ed_case-$ed_check.log
  (cd "$ed_cwd" && E2E_TIMEOUT=300 && export E2E_TIMEOUT \
    && e2e_run_in "$ed_home" sh -c '. "$1" && exec adlc doctor' sh "$ed_env") > "$ed_log" 2>&1
  ed_bad=''
  command grep -q 'route=plugin' "$ed_log" || ed_bad="$ed_bad route is not plugin;"
  command grep -q '^\[PASS\] plugin-route' "$ed_log" || ed_bad="$ed_bad plugin-route did not PASS;"
  command grep -q '^\[PASS\] doubled-install' "$ed_log" || ed_bad="$ed_bad doubled-install did not PASS;"
  for ed_c in skills-symlink agents-symlink toolkit-clean path-shims; do
    command grep -q "^\[SKIP\] $ed_c — plugin route" "$ed_log" || ed_bad="$ed_bad $ed_c did not SKIP;"
  done
  ed_fails=$(command grep '^\[FAIL\]' "$ed_log" | cut -c1-160 | tr '\n' ';')
  [ -z "$ed_fails" ] || ed_bad="$ed_bad $ed_fails"
  if [ -z "$ed_bad" ]; then
    e2e_check "$ed_case" "$ed_check" PASS "$(command grep '^verdict:' "$ed_log"); route=plugin, plugin-route and doubled-install PASS, the 4 symlink checks SKIP"
    return 0
  fi
  e2e_check "$ed_case" "$ed_check" FAIL "$ed_bad"
  e2e_excerpt "$ed_log"
  return 1
}

E2E_PH=$E2E_SBX/plugin-home
E2E_PH_ENV=$E2E_SBX/plugin-home.env
E2E_PH_ROOT=''
E2E_PH_PTR=''
E2E_PH_STATE=''
# e2e_plugin_home <case> — the shared plugin-only HOME (with the guard), installed once.
e2e_plugin_home() {
  if [ -n "$E2E_PH_STATE" ]; then [ "$E2E_PH_STATE" = ok ]; return; fi
  E2E_PH_STATE=failed
  if [ -z "$E2E_CLAUDE" ]; then e2e_check "$1" bri1_install SKIPPED 'claude is not on PATH'; return 1; fi
  e2e_new_home "$E2E_PH" guard || { e2e_check "$1" bri1_install FAIL "cannot create $E2E_PH"; return 1; }
  e2e_install "$1" "$E2E_PH" "$E2E_SBX/src" || return 1
  E2E_PH_ROOT=$(e2e_py load-root "$E2E_PH" "$E2E_PLUGIN_ID") || return 1
  # The root this local-path install's sessions get: its source directory, which the
  # hook does not record.
  e2e_hook "$1" "$E2E_PH" "$E2E_PH_ROOT" "$E2E_PH_ENV" session_hook || return 1
  # The root a GitHub-route session gets: the cache copy, which it does record. That
  # pointer is what the guard's raw root-line check reads (ADR-1 arm 3).
  ehc_cache=$(e2e_py record "$E2E_PH" "$E2E_PLUGIN_ID" | cut -f2)
  e2e_hook "$1" "$E2E_PH" "$ehc_cache" "$E2E_SBX/plugin-home-cache.env" session_hook_cache_copy || return 1
  E2E_PH_PTR=$(cat "$E2E_PH/.claude/adlc/plugin-root" 2>/dev/null)
  E2E_PH_STATE=ok
}

# e2e_claude <home> <cwd> <tag> <budget> <timeout-s> <prompt> [extra claude args...] —
# one `claude -p` run with stream-json output; sets E2E_SID and E2E_TRANSCRIPT.
E2E_UNATTENDED='This is an unattended end-to-end test in a throwaway sandbox. Do not ask questions. Take the documented default at every choice and finish the task.'
e2e_claude() {
  ec_home=$1 ec_cwd=$2 ec_tag=$3 ec_budget=$4 ec_timeout=$5 ec_prompt=$6
  shift 6
  E2E_SID=$(e2e_py uuid)
  set -- -p "$ec_prompt" --session-id "$E2E_SID" --output-format stream-json --verbose \
    --max-budget-usd "$ec_budget" --append-system-prompt "$E2E_UNATTENDED" "$@"
  [ -z "$OPT_MODEL" ] || set -- "$@" --model "$OPT_MODEL"
  (cd "$ec_cwd" && E2E_PASS_AUTH=1 && E2E_PASS_GH=${E2E_CLAUDE_GH:-0} && E2E_TIMEOUT=$ec_timeout \
    && export E2E_PASS_AUTH E2E_PASS_GH E2E_TIMEOUT && e2e_run_in "$ec_home" claude "$@") \
    < /dev/null > "$E2E_LOGS/$ec_tag.jsonl" 2> "$E2E_LOGS/$ec_tag.err"
  ec_rc=$?
  E2E_TRANSCRIPT=$(find "$ec_home/.claude/projects" -name "$E2E_SID.jsonl" 2>/dev/null | head -n 1)
  return "$ec_rc"
}
E2E_TOOLS_WORK='Bash Read Write Edit Glob Grep Skill Agent Task Workflow TodoWrite'

# e2e_guard_scan <case> <check> <home> — no transcript or stream log of the case shows
# a read under the guard (AC-2).
e2e_guard_scan() {
  egs_files=$E2E_SBX/scan-files.txt
  { find "$3/.claude/projects" -name '*.jsonl' 2>/dev/null; find "$E2E_LOGS" -name "$1*.jsonl" 2>/dev/null; } > "$egs_files"
  if [ ! -s "$egs_files" ]; then e2e_check "$1" "$2" FAIL 'no transcript to scan'; return 1; fi
  egs_out=$(tr '\n' '\0' < "$egs_files" | xargs -0 "$E2E_PY" -I "$E2E_BIN/helpers.py" scan)
  if [ $? -eq 0 ]; then
    e2e_check "$1" "$2" PASS "$(wc -l < "$egs_files" | tr -d ' ') transcripts: no tool call names ~/.claude/skills or ~/.claude/agents, and none was refused under the guard"
    return 0
  fi
  e2e_check "$1" "$2" FAIL "$(printf '%s' "$egs_out" | head -n 3)"
  return 1
}

# ===================================================================================
# case: init_spec_status_doctor (AC-1)
# ===================================================================================
case_init_spec_status_doctor() {
  c=init_spec_status_doctor
  if ! e2e_plugin_home "$c"; then
    e2e_check "$c" doctor_plugin_route SKIPPED 'the plugin install or hook failed above'
    e2e_check "$c" init_spec_status SKIPPED 'the plugin install or hook failed above'
    return
  fi
  e2e_doctor "$c" doctor_plugin_route "$E2E_PH" "$E2E_WORK" "$E2E_PH_ENV"
  if ! e2e_model_ready; then
    e2e_check "$c" init_spec_status SKIPPED "$E2E_MODEL_REASON"
    e2e_check "$c" doctor_in_project SKIPPED 'needs the project /adlc:init scaffolds'
    e2e_check "$c" guard_transcripts SKIPPED 'no model run, so no transcript to scan'
    return
  fi
  p=$E2E_SBX/proj
  mkdir -p "$p" && (cd "$p" && e2e_git "$E2E_PH" init -q -b main && printf '# e2e project\n' > README.md \
    && e2e_git "$E2E_PH" add README.md && e2e_git "$E2E_PH" commit -q -m 'initial commit') > /dev/null 2>&1
  # AC-1 runs in a repo with no remote, so nothing leaves the machine except model calls.
  bad=''
  e2e_claude "$E2E_PH" "$p" "$c-init" "$OPT_BUDGET" 1800 '/adlc:init' --permission-mode acceptEdits --allowedTools "$E2E_TOOLS_WORK"
  for f in .adlc/context/project-overview.md .adlc/context/architecture.md .adlc/context/conventions.md .adlc/templates/requirement-template.md; do
    [ -f "$p/$f" ] || bad="$bad /adlc:init did not write $f;"
  done
  e2e_py command-names "$E2E_TRANSCRIPT" | command grep -qx '/adlc:init' || bad="$bad /adlc:init did not resolve to the plugin skill;"
  e2e_claude "$E2E_PH" "$p" "$c-spec" "$OPT_BUDGET" 1800 '/adlc:spec Add a scripts/hello.sh that prints hello, and one README line that names it' \
    --permission-mode acceptEdits --allowedTools "$E2E_TOOLS_WORK"
  req=$(find "$p/.adlc/specs" -name requirement.md 2>/dev/null | head -n 1)
  reqid=''
  if [ -n "$req" ]; then reqid=$(basename "$(dirname "$req")" | sed 's/^\(REQ-[0-9]*\).*/\1/'); else bad="$bad /adlc:spec wrote no .adlc/specs/REQ-*/requirement.md;"; fi
  if [ -n "$reqid" ]; then
    e2e_claude "$E2E_PH" "$p" "$c-status" "$OPT_BUDGET" 900 '/adlc:status' --permission-mode default --allowedTools 'Bash Read Glob Grep Skill'
    e2e_py result-text "$E2E_LOGS/$c-status.jsonl" | command grep -q "$reqid" || bad="$bad /adlc:status output does not list $reqid;"
  fi
  if [ -z "$bad" ]; then
    e2e_check "$c" init_spec_status PASS "/adlc:init scaffolded .adlc/, /adlc:spec wrote $reqid, /adlc:status listed it"
  else
    e2e_check "$c" init_spec_status FAIL "$bad"
  fi
  e2e_doctor "$c" doctor_in_project "$E2E_PH" "$p" "$E2E_PH_ENV"
  e2e_guard_scan "$c" guard_transcripts "$E2E_PH"
}

# ===================================================================================
# case: lite_req_end_to_end_with_read_guard (AC-2, BR-2)
# ===================================================================================
case_lite_req_end_to_end_with_read_guard() {
  c=lite_req_end_to_end_with_read_guard
  if ! e2e_plugin_home "$c"; then
    e2e_check "$c" read_guard SKIPPED 'the plugin install or hook failed above'
    e2e_check "$c" lite_pipeline SKIPPED 'the plugin install or hook failed above'
    return
  fi
  # 1. The guard is armed: an unarmed guard would pass every check below by accident.
  bad=''
  for d in skills agents; do
    [ "$(ls -ld "$E2E_PH/.claude/$d" | cut -c1-10)" = 'd---------' ] || bad="$bad ~/.claude/$d is not mode 000;"
    (cd "$E2E_WORK" && e2e_run_in "$E2E_PH" ls "$E2E_PH/.claude/$d") > "$E2E_LOGS/$c-probe-$d.log" 2>&1 \
      && bad="$bad listing ~/.claude/$d succeeded;"
    command grep -q 'Permission denied' "$E2E_LOGS/$c-probe-$d.log" || bad="$bad listing ~/.claude/$d was not refused;"
  done
  if [ -z "$bad" ]; then
    e2e_check "$c" guard_armed PASS '~/.claude/skills and ~/.claude/agents are mode-000 directories; listing either is refused'
  else
    e2e_check "$c" guard_armed FAIL "$bad"
  fi
  # 2. The canonical root line resolves to the plugin under the guard, both as the
  # loader substitutes it and as raw text a subagent reads (arm 3, the pointer, which
  # names the cache copy: the hook records no other root).
  sk=$E2E_PH_ROOT/template-drift/SKILL.md
  bad=''
  for form in substituted raw; do
    if [ "$form" = substituted ]; then e2e_py root-line "$sk" "$E2E_PH_ROOT" > "$E2E_SBX/root-line.sh"; want=$E2E_PH_ROOT
    else e2e_py root-line "$sk" - > "$E2E_SBX/root-line.sh"; want=$E2E_PH_PTR; fi
    printf 'printf "%%s\\n" "$ADLC_TOOLKIT_ROOT"\n' >> "$E2E_SBX/root-line.sh"
    for sh in sh bash zsh dash; do
      command -v "$sh" > /dev/null 2>&1 || continue
      got=$(cd "$E2E_WORK" && e2e_run_in "$E2E_PH" "$sh" "$E2E_SBX/root-line.sh" 2> "$E2E_LOGS/$c-root-$form-$sh.err")
      [ -n "$want" ] && [ "$got" = "$want" ] || bad="$bad $form root line under $sh gave '$got', want '$want';"
      [ ! -s "$E2E_LOGS/$c-root-$form-$sh.err" ] || bad="$bad $form root line under $sh wrote to stderr;"
    done
  done
  if [ -z "$bad" ]; then
    e2e_check "$c" guard_root_line PASS "the canonical root line gives $E2E_PH_ROOT substituted and $E2E_PH_PTR raw (the pointer) under sh, bash, zsh and dash"
  else
    e2e_check "$c" guard_root_line FAIL "$bad"
  fi
  # 3. Every partial sources from ToolkitRoot under the guard, with no refused read,
  # and the two that read toolkit files return the plugin's copies.
  bad=''
  n=0
  e2e_py root-line "$sk" "$E2E_PH_ROOT" > "$E2E_SBX/root-line.sh"
  for part in $(cd "$E2E_PH_ROOT/partials" && ls | command grep '\.sh$'); do
    n=$((n + 1))
    { cat "$E2E_SBX/root-line.sh"
      printf 'if [ -f .adlc/partials/%s ]; then . .adlc/partials/%s; else . "$ADLC_TOOLKIT_ROOT/partials/%s"; fi\n' "$part" "$part" "$part"
      printf 'printf "DELEGATE_TOOLS=%%s\\n" "${DELEGATE_TOOLS:-}"\n'; } > "$E2E_SBX/source-$part"
    mkdir -p "$E2E_SBX/empty-$n"
    (cd "$E2E_SBX/empty-$n" && E2E_TIMEOUT=60 && export E2E_TIMEOUT && e2e_run_in "$E2E_PH" sh "$E2E_SBX/source-$part") \
      > "$E2E_LOGS/$c-source-$part.out" 2> "$E2E_LOGS/$c-source-$part.err"
    prc=$?
    if command grep -q -i 'permission denied' "$E2E_LOGS/$c-source-$part.err" "$E2E_LOGS/$c-source-$part.out" \
       || command grep -q -E '\.claude/(skills|agents)' "$E2E_LOGS/$c-source-$part.err"; then
      bad="$bad $part touched the guard;"
    elif [ "$prc" -ne 0 ] || [ -s "$E2E_LOGS/$c-source-$part.err" ]; then
      bad="$bad sourcing $part exited $prc or wrote to stderr: $(head -n 1 "$E2E_LOGS/$c-source-$part.err");"
    fi
  done
  ethos_head=$(head -n 1 "$E2E_PH_ROOT/ETHOS.md")
  command grep -qxF "$ethos_head" "$E2E_LOGS/$c-source-ethos-include.sh.out" 2>/dev/null || bad="$bad ethos-include.sh did not print the plugin's ETHOS.md;"
  command grep -qxF "DELEGATE_TOOLS=$E2E_PH_ROOT/tools/delegate" "$E2E_LOGS/$c-source-delegate-tools-path.sh.out" 2>/dev/null \
    || bad="$bad delegate-tools-path.sh did not resolve to the plugin's tools/delegate;"
  if [ -z "$bad" ] && [ "$n" -gt 0 ]; then
    e2e_check "$c" guard_partials PASS "$n partials sourced from ToolkitRoot with no refused read; ethos-include and delegate-tools-path read the plugin's copies"
  else
    e2e_check "$c" guard_partials FAIL "${bad:- no partials found}"
  fi
  # 4. The pipeline itself: model turns and a throwaway GitHub repo.
  if ! e2e_model_ready; then e2e_check "$c" lite_pipeline SKIPPED "$E2E_MODEL_REASON"; return; fi
  if ! e2e_github_ready; then e2e_check "$c" lite_pipeline SKIPPED "$E2E_GH_REASON"; return; fi
  lite_pipeline "$c"
  E2E_CLAUDE_GH=0   # every later case's sessions run without GitHub credentials
}

lite_pipeline() {
  c=$1
  r=$E2E_SBX/lite
  E2E_CLAUDE_GH=1   # the sessions of this case, and only these, get the gh credentials
  printf '[credential "https://github.com"]\n\thelper = !gh auth git-credential\n' >> "$E2E_PH/.gitconfig"
  start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  (E2E_PASS_GH=1 && export E2E_PASS_GH && cd "$E2E_WORK" \
    && e2e_run_in "$E2E_PH" git clone -q "https://github.com/$OPT_REPO.git" "$r") > "$E2E_LOGS/$c-clone.log" 2>&1 \
    || { e2e_check "$c" lite_pipeline FAIL "git clone of $OPT_REPO failed"; e2e_excerpt "$E2E_LOGS/$c-clone.log"; return; }
  if ! git -C "$r" rev-parse --verify -q HEAD > /dev/null; then
    (cd "$r" && e2e_git "$E2E_PH" checkout -q -b main \
      && printf '# %s\n\nThrowaway repo for the ADLC plugin end-to-end check.\n' "$OPT_REPO" > README.md \
      && e2e_git "$E2E_PH" add README.md && e2e_git "$E2E_PH" commit -q -m 'initial commit' \
      && E2E_PASS_GH=1 && export E2E_PASS_GH && e2e_git "$E2E_PH" push -q origin main) > "$E2E_LOGS/$c-seed.log" 2>&1 \
      || { e2e_check "$c" lite_pipeline FAIL 'seeding the empty throwaway repo failed'; e2e_excerpt "$E2E_LOGS/$c-seed.log"; return; }
  fi
  e2e_claude "$E2E_PH" "$r" "$c-init" "$OPT_BUDGET" 1800 '/adlc:init' --permission-mode acceptEdits --allowedTools "$E2E_TOOLS_WORK"
  (cd "$r" && e2e_git "$E2E_PH" add -A && e2e_git "$E2E_PH" commit -q -m 'chore: adlc init' \
    && E2E_PASS_GH=1 && export E2E_PASS_GH && e2e_git "$E2E_PH" push -q origin HEAD) > "$E2E_LOGS/$c-init-push.log" 2>&1 \
    || { e2e_check "$c" lite_pipeline FAIL 'committing and pushing the /adlc:init scaffold failed'; e2e_excerpt "$E2E_LOGS/$c-init-push.log"; return; }
  e2e_claude "$E2E_PH" "$r" "$c-spec" "$OPT_BUDGET" 1800 '/adlc:spec --lite Add scripts/hello.sh, a POSIX sh script that prints hello, and one README line that names it' \
    --permission-mode acceptEdits --allowedTools "$E2E_TOOLS_WORK"
  req=$(find "$r/.adlc/specs" -name requirement.md 2>/dev/null | head -n 1)
  [ -n "$req" ] || { e2e_check "$c" lite_pipeline FAIL '/adlc:spec --lite wrote no requirement.md'; return; }
  reqid=$(basename "$(dirname "$req")" | sed 's/^\(REQ-[0-9]*\).*/\1/')
  lane=$(e2e_py lane "$req")
  [ "$lane" = lite ] || { e2e_check "$c" lite_pipeline FAIL "$reqid has lane '$lane', not lite"; return; }
  e2e_claude "$E2E_PH" "$r" "$c-proceed" "$OPT_PIPELINE_BUDGET" "$((OPT_PIPELINE_TIMEOUT_MIN * 60))" "/adlc:proceed $reqid" \
    --permission-mode acceptEdits --allowedTools "$E2E_TOOLS_WORK"
  bad=''
  pr=$(E2E_PASS_GH=1 && export E2E_PASS_GH && cd "$E2E_WORK" && e2e_run_in "$E2E_PH" gh pr list --repo "$OPT_REPO" --state all \
    --search "$reqid in:title,body" --json number --jq '.[0].number' 2>/dev/null)
  if [ -z "$pr" ] || [ "$pr" = null ]; then
    pr=''
    bad="$bad no PR for $reqid in $OPT_REPO;"
  else
    state=$(E2E_PASS_GH=1 && export E2E_PASS_GH && cd "$E2E_WORK" && e2e_run_in "$E2E_PH" gh pr view "$pr" --repo "$OPT_REPO" --json state --jq .state 2>/dev/null)
    [ "$state" = MERGED ] || bad="$bad PR #$pr is $state, not MERGED;"
  fi
  (E2E_PASS_GH=1 && export E2E_PASS_GH && cd "$r" && e2e_run_in "$E2E_PH" git fetch -q origin) > /dev/null 2>&1
  lesson=$(git -C "$r" log --since="$start" --name-only --format= origin/main -- .adlc/knowledge/lessons 2>/dev/null | command grep 'LESSON-' | head -n 1)
  if [ -z "$lesson" ] && ! command grep -q 'NO_ENTRY:' "$E2E_LOGS/$c-proceed.jsonl" ${E2E_TRANSCRIPT:+"$E2E_TRANSCRIPT"}; then
    bad="$bad neither a new lesson on main nor the wrapup NO_ENTRY line;"
  fi
  if [ -z "$bad" ]; then
    e2e_check "$c" lite_pipeline PASS "$reqid lane lite, PR #$pr MERGED, ${lesson:-NO_ENTRY line in the wrapup}"
  else
    e2e_check "$c" lite_pipeline FAIL "$bad"
  fi
  e2e_guard_scan "$c" guard_transcripts "$E2E_PH"
  printf '    The throwaway repo is yours to delete. This script never deletes it:\n'
  printf '      gh repo delete %s --yes\n' "$OPT_REPO"
}

# ===================================================================================
# case: symlink_only_regressions (AC-3, BR-3)
# ===================================================================================
case_symlink_only_regressions() {
  c=symlink_only_regressions
  sh_home=$E2E_SBX/symlink-home
  clone=$E2E_SBX/clone
  # A clone of the snapshot, on main and clean, the shape the doctor expects of the
  # maintainer's checkout.
  e2e_new_home "$sh_home"
  mkdir -p "$clone" && tar -C "$E2E_SBX/src" -c -f - . | tar -C "$clone" -x -f - \
    && (cd "$clone" && e2e_git "$sh_home" init -q -b main && e2e_git "$sh_home" add -A \
        && e2e_git "$sh_home" commit -q -m "snapshot of $E2E_SHA") > /dev/null 2>&1 \
    || { e2e_check "$c" install_symlink_route FAIL "cannot build the clone at $clone"; return; }
  (cd "$E2E_WORK" && e2e_run_in "$sh_home" bash "$clone/install.sh") > "$E2E_LOGS/$c-install.log" 2>&1
  irc=$?
  if [ "$irc" -eq 0 ] && [ "$(readlink "$sh_home/.claude/skills")" = "$clone" ] && [ "$(readlink "$sh_home/.claude/agents")" = "$clone/agents" ]; then
    e2e_check "$c" install_symlink_route PASS "install.sh linked ~/.claude/skills and ~/.claude/agents to the clone ($(command grep '^Install summary' "$E2E_LOGS/$c-install.log"))"
  else
    e2e_check "$c" install_symlink_route FAIL "install.sh exited $irc, or the two links do not point at $clone"
    e2e_excerpt "$E2E_LOGS/$c-install.log"
  fi
  (cd "$E2E_WORK" && e2e_run_in "$sh_home" bash "$clone/install.sh" --dry-run) > "$E2E_LOGS/$c-dry-run.log" 2>&1
  drc=$?
  nwould=$(command grep -c '^  would:' "$E2E_LOGS/$c-dry-run.log")
  if [ "$drc" -eq 0 ] && [ "$nwould" -eq 0 ] && command grep -q '^Dry run: no changes made' "$E2E_LOGS/$c-dry-run.log"; then
    e2e_check "$c" install_dry_run_zero_actions PASS 'install.sh --dry-run on the symlink-only HOME plans no action (0 "would:" lines)'
  else
    e2e_check "$c" install_dry_run_zero_actions FAIL "install.sh --dry-run exited $drc with $nwould planned actions"
    e2e_excerpt "$E2E_LOGS/$c-dry-run.log"
  fi
  # The doctor as a new shell runs it: install.sh's rc block puts ~/bin first on PATH.
  (cd "$E2E_WORK" && E2E_TIMEOUT=300 && export E2E_TIMEOUT \
    && e2e_run_in "$sh_home" sh -c 'PATH="$HOME/bin:$PATH"; export PATH; exec adlc doctor') > "$E2E_LOGS/$c-doctor.log" 2>&1
  dfails=$(command grep '^\[FAIL\]' "$E2E_LOGS/$c-doctor.log" | cut -c1-120 | tr '\n' ';')
  if command grep -q 'route=symlink' "$E2E_LOGS/$c-doctor.log" && command grep -q '^\[PASS\] doubled-install' "$E2E_LOGS/$c-doctor.log" \
     && [ -z "$dfails" ]; then
    e2e_check "$c" doctor_symlink_route PASS "route=symlink, doubled-install PASS, no FAIL ($(command grep '^verdict:' "$E2E_LOGS/$c-doctor.log"))"
  else
    e2e_check "$c" doctor_symlink_route FAIL "the doctor did not report route=symlink, doubled-install PASS and no FAIL: ${dfails:-see log}"
    e2e_excerpt "$E2E_LOGS/$c-doctor.log"
  fi
  # The four suites, run in the clone with the symlink-only HOME.
  for suite in partials pytest node lint; do
    case $suite in
      partials) set -- sh partials/tests/run.sh; label='sh partials/tests/run.sh' ;;
      pytest) set -- python3 -m pytest tools -q -p no:cacheprovider; label='python3 -m pytest tools -q' ;;
      node) set -- node --test 'workflows/tests/*.test.js'; label="node --test 'workflows/tests/*.test.js'" ;;
      lint) set -- ./tools/lint-skills/check.sh; label='tools/lint-skills/check.sh' ;;
    esac
    if [ "$suite" = node ] && [ -z "$E2E_NODE" ]; then e2e_check "$c" "suite_$suite" SKIPPED 'node is not on PATH'; continue; fi
    (cd "$clone" && E2E_TIMEOUT=1800 && export E2E_TIMEOUT && e2e_run_in "$sh_home" "$@") > "$E2E_LOGS/$c-$suite.log" 2>&1
    src=$?
    uncounted=$(command grep -c '^FAIL' "$E2E_LOGS/$c-$suite.log")
    if [ "$src" -eq 0 ] && [ "$uncounted" -gt 0 ]; then
      # Exit 0, but the log shows failures the harness did not count. A failure the
      # exit code lost is still a failure, never a pass.
      e2e_check "$c" "suite_$suite" FAIL "$label: exit 0, but the log has $uncounted 'FAIL' line(s) the harness did not count, first: $(command grep -m 1 '^FAIL' "$E2E_LOGS/$c-$suite.log" | cut -c1-110)"
      e2e_excerpt "$E2E_LOGS/$c-$suite.log"
    elif [ "$src" -eq 0 ]; then
      e2e_check "$c" "suite_$suite" PASS "$label: exit 0 ($(tail -n 1 "$E2E_LOGS/$c-$suite.log" | cut -c1-100))"
    else
      e2e_check "$c" "suite_$suite" FAIL "$label: exit $src"
      e2e_excerpt "$E2E_LOGS/$c-$suite.log"
    fi
  done
}

# ===================================================================================
# case: printed_next_steps_runnable (BR-10, ADR-5)
# ===================================================================================
case_printed_next_steps_runnable() {
  c=printed_next_steps_runnable
  # 1. Static: the skill names in printed "run /x" instructions, against the command
  # names and aliases compiled into the installed Claude Code.
  if [ -z "$E2E_CLAUDE" ]; then
    e2e_check "$c" builtin_collision_static SKIPPED 'claude is not on PATH'
  else
    bin=$(e2e_py realpath "$E2E_CLAUDE")
    e2e_py audit "$E2E_SBX/src" "$bin" > "$E2E_LOGS/$c-audit.txt" 2>&1
    verdict=$(command grep '^VERDICT ' "$E2E_LOGS/$c-audit.txt")
    command grep -v '^VERDICT ' "$E2E_LOGS/$c-audit.txt" | sed 's/^/      /'
    case $verdict in
      'VERDICT pass'*) e2e_check "$c" builtin_collision_static PASS 'no adlc skill name is a Claude Code command name or alias' ;;
      'VERDICT warn'*) e2e_check "$c" builtin_collision_static PASS "only alias collisions, or names no printed instruction leaves bare (${verdict#VERDICT warn }); see the collision lines" ;;
      'VERDICT fail'*) e2e_check "$c" builtin_collision_static FAIL "printed bare next steps name a built-in Claude Code command (${verdict#VERDICT fail }); on the plugin route a typed bare name reaches the built-in, not /adlc:<skill>. Print both spellings on the line (conventions.md, \"Skill names Claude Code also owns\")" ;;
      *) e2e_check "$c" builtin_collision_static SKIPPED "could not read the command table from $bin" ;;
    esac
  fi
  # 2. Dynamic: each printed step typed on the plugin HOME; the transcript must show it
  # resolved to /adlc:<skill>. A name Claude Code also owns is printed in both
  # spellings (TASK-133, conventions.md "Skill names Claude Code also owns"), and the
  # text tells a plugin user to type /adlc:<name>, so that is the step typed. Where
  # the bare name goes is then typed once per colliding name and reported, not
  # failed: the dual spelling is right whichever way it resolves.
  if ! e2e_model_ready; then e2e_check "$c" printed_steps_typed SKIPPED "$E2E_MODEL_REASON"; return; fi
  if ! e2e_plugin_home "$c"; then e2e_check "$c" printed_steps_typed SKIPPED 'the plugin install or hook failed above'; return; fi
  names=$(e2e_py skill-names "$E2E_SBX/src")
  collide=$(command grep '^collision ' "$E2E_LOGS/$c-audit.txt" 2>/dev/null | sed 's/^collision \/\([a-z-]*\):.*/\1/' | tr '\n' ' ')
  find "$E2E_PH/.claude/projects" -name '*.jsonl' > "$E2E_SBX/printed-files.txt" 2>/dev/null
  { tr '\n' '\0' < "$E2E_SBX/printed-files.txt" | xargs -0 "$E2E_PY" -I "$E2E_BIN/helpers.py" printed "$names"
    for nm in $collide; do echo "/$nm"; done; } \
    | while IFS= read -r step; do
        case " $collide" in *" ${step#/} "*) echo "/adlc:${step#/}" ;; *) echo "$step" ;; esac
      done | sort -u > "$E2E_SBX/printed-steps.txt"
  bad=''
  n=0
  mkdir -p "$E2E_SBX/typed"
  while IFS= read -r step; do
    [ -n "$step" ] || continue
    n=$((n + 1))
    case $step in /adlc:*) want=$step ;; *) want="/adlc:${step#/}" ;; esac
    e2e_claude "$E2E_PH" "$E2E_SBX/typed" "$c-typed-$n" 0.25 300 "$step" --tools ''
    got=$(e2e_py command-names "$E2E_TRANSCRIPT" | head -n 1)
    [ "$got" = "$want" ] || bad="$bad typed $step resolved to '${got:-nothing}', not $want;"
  done < "$E2E_SBX/printed-steps.txt"
  bare=''
  for nm in $collide; do
    e2e_claude "$E2E_PH" "$E2E_SBX/typed" "$c-bare-$nm" 0.25 300 "/$nm" --tools ''
    got=$(e2e_py command-names "$E2E_TRANSCRIPT" | head -n 1)
    bare="$bare bare /$nm reached '${got:-nothing}';"
  done
  if [ "$n" -eq 0 ]; then
    e2e_check "$c" printed_steps_typed SKIPPED 'no printed next step was found in the transcripts and no name collides'
  elif [ -z "$bad" ]; then
    e2e_check "$c" printed_steps_typed PASS "$n printed steps, each typed as printed for the plugin install, reached /adlc:<skill>.${bare:+ For the record:$bare}"
  else
    e2e_check "$c" printed_steps_typed FAIL "$bad${bare:+ For the record:$bare}"
  fi
}

# ===================================================================================
# case: test_release_update (AC-8, BR-14)
# ===================================================================================
case_test_release_update() {
  c=test_release_update
  if [ -z "$E2E_CLAUDE" ]; then
    e2e_check "$c" plugin_update SKIPPED 'claude is not on PATH'
    e2e_check "$c" template_drift_baseline_fence SKIPPED 'claude is not on PATH'
    e2e_check "$c" template_drift_skill_run SKIPPED 'claude is not on PATH'
    return
  fi
  rh=$E2E_SBX/release-home
  rsrc=$E2E_SBX/release-src
  mkdir -p "$rsrc" && tar -C "$E2E_SBX/src" -c -f - . | tar -C "$rsrc" -x -f - || { e2e_check "$c" plugin_update FAIL "cannot copy the snapshot to $rsrc"; return; }
  e2e_new_home "$rh" guard
  if ! e2e_install "$c" "$rh" "$rsrc"; then
    for chk in plugin_update template_drift_baseline_fence template_drift_skill_run; do
      e2e_check "$c" "$chk" SKIPPED 'the first install failed'
    done
    return
  fi
  v0=$(e2e_py version "$rsrc")
  tv=${OPT_TEST_VERSION:-$(e2e_py bump "$v0")}
  v0_path=$(e2e_py record "$rh" "$E2E_PLUGIN_ID" | cut -f2)
  # The release bump, made in the sandbox copy only: VERSION and plugin.json together,
  # the way RELEASING.md steps 2 and 3 make it.
  e2e_py set-version "$rsrc" "$tv"
  (cd "$E2E_WORK" && e2e_run_in "$rh" claude plugin marketplace update "$E2E_MARKETPLACE" \
    && e2e_run_in "$rh" claude plugin update "$E2E_PLUGIN_ID" \
    && e2e_run_in "$rh" claude plugin list --json > "$E2E_LOGS/$c-list-after.json") < /dev/null > "$E2E_LOGS/$c-update.log" 2>&1
  urc=$?
  entry=$(e2e_py list-entry "$E2E_LOGS/$c-list-after.json" "$E2E_PLUGIN_ID" 2>&1)
  ipath=$(printf '%s' "$entry" | cut -f3)
  if [ "$urc" -eq 0 ] && [ "$(printf '%s' "$entry" | cut -f1)" = "$tv" ] && [ "$(e2e_py version "$ipath" 2>/dev/null)" = "$tv" ]; then
    e2e_check "$c" plugin_update PASS "marketplace update + plugin update moved $E2E_PLUGIN_ID from $v0 to $tv; claude plugin list shows $tv at $ipath"
  else
    e2e_check "$c" plugin_update FAIL "update exited $urc; claude plugin list gave '$entry', expected $tv"
    e2e_excerpt "$E2E_LOGS/$c-update.log"
    e2e_check "$c" template_drift_baseline_fence SKIPPED 'the update failed'
    e2e_check "$c" template_drift_skill_run SKIPPED 'the update failed'
    return
  fi
  # /adlc:template-drift's Step 0a baseline fence, with ${CLAUDE_PLUGIN_ROOT} rewritten
  # to the root the loader would substitute, run in sh under the guarded HOME. The old
  # cache copy is the control: it must still name the old version.
  lroot=$(e2e_py load-root "$rh" "$E2E_PLUGIN_ID")
  bad=''
  ok=''
  for pair in "$ipath=$tv" "$lroot=$tv" "$v0_path=$v0"; do
    froot=${pair%=*}
    fver=${pair##*=}
    e2e_py fence "$froot/template-drift/SKILL.md" 'baseline: adlc plugin' "$froot" > "$E2E_SBX/drift-fence.sh" 2> "$E2E_LOGS/$c-fence-extract.err" \
      || { bad="$bad cannot extract the baseline fence from $froot: $(cat "$E2E_LOGS/$c-fence-extract.err");"; continue; }
    got=$(cd "$E2E_WORK" && e2e_run_in "$rh" sh "$E2E_SBX/drift-fence.sh" 2> "$E2E_LOGS/$c-fence.err" | command grep '^baseline:')
    if [ "$got" = "baseline: adlc plugin $fver ($froot)" ]; then ok="$ok '$got'"; else bad="$bad fence on $froot printed '$got', want 'baseline: adlc plugin $fver ($froot)';"; fi
  done
  if [ -z "$bad" ]; then
    e2e_check "$c" template_drift_baseline_fence PASS "the Step 0a fence, substituted as the loader does, printed:$ok"
  else
    e2e_check "$c" template_drift_baseline_fence FAIL "$bad"
  fi
  if ! e2e_model_ready; then e2e_check "$c" template_drift_skill_run SKIPPED "$E2E_MODEL_REASON"; return; fi
  p=$E2E_SBX/drift-proj
  mkdir -p "$p/.adlc" && cp -R "$ipath/templates" "$p/.adlc/templates" && (cd "$p" && e2e_git "$rh" init -q -b main) > /dev/null 2>&1
  e2e_claude "$rh" "$p" "$c-drift" "$OPT_BUDGET" 900 '/adlc:template-drift' --permission-mode default --allowedTools 'Bash Read Glob Grep Skill'
  if e2e_py tool-output-has "baseline: adlc plugin $tv" "$E2E_LOGS/$c-drift.jsonl" ${E2E_TRANSCRIPT:+"$E2E_TRANSCRIPT"}; then
    e2e_check "$c" template_drift_skill_run PASS "a Bash tool result in the /adlc:template-drift run printed 'baseline: adlc plugin $tv'"
  else
    e2e_check "$c" template_drift_skill_run FAIL "no tool result in the /adlc:template-drift run printed 'baseline: adlc plugin $tv'"
  fi
}

# ===================================================================================
# run
# ===================================================================================
printf 'plugin-sandbox: REQ-669 end-to-end check of the plugin route\n'
printf '  checkout: %s at %s (%s)\n' "$E2E_REPO" "$OPT_REF" "$E2E_SHA"
mkdir -p "$E2E_SBX/version-home"
E2E_CC_VERSION=$( [ -n "$E2E_CLAUDE" ] && cd "$E2E_WORK" && e2e_run_in "$E2E_SBX/version-home" claude --version 2>/dev/null) || E2E_CC_VERSION='not on PATH'
printf '  claude:   %s\n' "$E2E_CC_VERSION"
printf '  sandbox:  %s\n' "$E2E_SBX"
e2e_snapshot || e2e_die "git archive of $E2E_SHA into $E2E_SBX/src failed"
printf '  snapshot: plugin.json version %s\n' "$(e2e_py version "$E2E_SBX/src")"

for e2e_c in $(printf '%s\n' "$E2E_ALL_CASES" | tr ' ' '\n'); do
  e2e_selected "$e2e_c" || continue
  printf '\n== %s\n' "$e2e_c"
  "case_$e2e_c"
done

printf '\n== summary\n'
E2E_FAILS=0
E2E_SKIPS=0
E2E_INCOMPLETE_CASES=0
for e2e_c in $(printf '%s\n' "$E2E_ALL_CASES" | tr ' ' '\n'); do
  e2e_selected "$e2e_c" || continue
  e2e_np=$(awk -F '\t' -v c="$e2e_c" '$1==c && $3=="PASS"' "$E2E_RESULTS" | wc -l | tr -d ' ')
  e2e_nf=$(awk -F '\t' -v c="$e2e_c" '$1==c && $3=="FAIL"' "$E2E_RESULTS" | wc -l | tr -d ' ')
  e2e_ns=$(awk -F '\t' -v c="$e2e_c" '$1==c && $3=="SKIPPED"' "$E2E_RESULTS" | wc -l | tr -d ' ')
  if [ "$e2e_nf" -gt 0 ]; then e2e_st=FAIL
  elif [ "$e2e_ns" -gt 0 ] && [ "$e2e_np" -gt 0 ]; then e2e_st=PARTIAL
  elif [ "$e2e_ns" -gt 0 ] || [ "$e2e_np" -eq 0 ]; then e2e_st=SKIPPED
  else e2e_st=PASS; fi
  [ "$e2e_ns" -eq 0 ] || E2E_INCOMPLETE_CASES=$((E2E_INCOMPLETE_CASES + 1))
  E2E_FAILS=$((E2E_FAILS + e2e_nf))
  E2E_SKIPS=$((E2E_SKIPS + e2e_ns))
  printf '  %-8s %s (%s pass, %s fail, %s skipped)\n' "$e2e_st" "$e2e_c" "$e2e_np" "$e2e_nf" "$e2e_ns"
done
if [ "$E2E_SKIPS" -gt 0 ]; then
  printf '\nINCOMPLETE: %s cases skipped (wholly or in part; %s checks did not run). An unrun check is not a pass (LESSON-581).\n' \
    "$E2E_INCOMPLETE_CASES" "$E2E_SKIPS"
  awk -F '\t' '$3=="SKIPPED" {printf "  skipped %s.%s: %s\n", $1, $2, $4}' "$E2E_RESULTS"
fi
if [ "$E2E_FAILS" -gt 0 ]; then
  printf '\nRESULT: FAIL (%s checks failed)\n' "$E2E_FAILS"
  exit 1
fi
if [ "$E2E_SKIPS" -gt 0 ]; then
  printf '\nRESULT: INCOMPLETE (no check failed)\n'
  exit 2
fi
printf '\nRESULT: PASS\n'
exit 0

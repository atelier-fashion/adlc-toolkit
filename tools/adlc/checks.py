#!/usr/bin/env python3
"""adlc doctor checks (REQ-519 BR-4).

Each check is a function ``(profile) -> (Result, detail, remediation)`` and is
registered in ``REGISTRY`` in report order. Every FAIL carries a copy-pasteable
remediation — a literal command or exact file edit, never "see docs" (BR-5).

The ``delegate-gate`` check **reuses REQ-515's shipped surface** rather than
reinventing config resolution (REQ-519 ADR-4): it sources
``partials/delegate-gate.sh`` for the 0/1/2 gate verdict and reads
``tools/delegate/_common.parse_delegate_config`` (via a subprocess probe) to
distinguish "not opted in" (SKIP) from "config says enabled but the binary is
missing" (FAIL — misconfigured).

Pure standard library: doctor must run before/without the delegation venv. That
holds transitively (LESSON-395) — nothing YAML-related is imported here or in
anything imported here, because the `pyyaml` check below exists precisely to
report on a machine where PyYAML is missing, and a check that cannot load
without the thing it diagnoses cannot report it.
"""

import os
import shutil
import subprocess
import sys
import time

from doctor import Check, Profile, Result

# A counter lock dir older than this (seconds) with no live holder is treated as
# stale (BR-4 "lock-dir not stale"). 15 minutes is generous for any real
# increment, which holds the lock for milliseconds.
_STALE_LOCK_SECONDS = 15 * 60

_COUNTERS = (".global-next-req", ".global-next-bug", ".global-next-lesson")


# --- helpers ---------------------------------------------------------------

def _claude_home() -> str:
    return os.path.join(os.path.expanduser("~"), ".claude")


def _resolves_into_checkout(link_path: str) -> bool:
    """True if link_path is a symlink whose real target is inside a git checkout."""
    if not os.path.islink(link_path):
        return False
    target = os.path.realpath(link_path)
    if not os.path.isdir(target):
        return False
    # The target (or, for agents, its parent) must be a git working tree.
    probe = target
    return subprocess.run(
        ["git", "-C", probe, "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True,
    ).returncode == 0


def _delegate_interpreter() -> str:
    """The interpreter ``adlc`` runs under (REQ-609 BR-8, ADR-2).

    The delegate venv's ``python3`` when it exists and is executable, else the
    interpreter running us. This is exactly the selection the ``adlc`` shim
    written by the root ``install.sh`` makes, and it is one helper on purpose:
    the doctor's ``pyyaml`` check must report on the SAME interpreter the config
    probes below run in, or it reports on a machine nobody is using (LESSON-392).

    Not unconditional: the venv only exists after ``install.sh
    --with-delegation``, and a probe that `exec`s a missing interpreter breaks
    doctor on exactly the machine that most needs it (LESSON-395).
    """
    venv = os.path.join(_claude_home(), "delegate-venv", "bin", "python3")
    if os.path.isfile(venv) and os.access(venv, os.X_OK):
        return venv
    return sys.executable


def _partial_path(profile: Profile, name: str) -> str:
    """Resolve a partial with the two-level fallback (project, then toolkit)."""
    local = os.path.join(profile.repo_root, "partials", name)
    if os.path.isfile(local):
        return local
    return os.path.join(_claude_home(), "skills", "partials", name)


# --- symlink checks --------------------------------------------------------

def check_skills_symlink(profile: Profile):
    link = os.path.join(_claude_home(), "skills")
    if _resolves_into_checkout(link):
        return Result.PASS, f"{link} -> {os.path.realpath(link)}", ""
    return (
        Result.FAIL,
        f"{link} is missing, dangling, or not a symlink into a git checkout",
        f"ln -sfn '{profile.repo_root}' '{link}'",
    )


def check_agents_symlink(profile: Profile):
    link = os.path.join(_claude_home(), "agents")
    target = os.path.join(profile.repo_root, "agents")
    if os.path.islink(link) and os.path.realpath(link) == os.path.realpath(target):
        return Result.PASS, f"{link} -> {os.path.realpath(link)}", ""
    return (
        Result.FAIL,
        f"{link} does not resolve to {target}",
        f"ln -sfn '{target}' '{link}'",
    )


# --- toolkit clone health --------------------------------------------------

def check_toolkit_clean(profile: Profile):
    root = profile.repo_root
    head = subprocess.run(
        ["git", "-C", root, "symbolic-ref", "--quiet", "HEAD"],
        capture_output=True, text=True,
    )
    if head.returncode != 0:
        return (
            Result.FAIL,
            "toolkit clone is in detached HEAD state",
            f"git -C '{root}' checkout main",
        )
    dirty = subprocess.run(
        ["git", "-C", root, "status", "--porcelain"],
        capture_output=True, text=True,
    ).stdout.strip()
    if dirty:
        return (
            Result.FAIL,
            "toolkit clone has uncommitted changes",
            f"git -C '{root}' status   # review, then commit or stash",
        )
    return Result.PASS, f"on {head.stdout.strip()}, clean", ""


# --- PATH / shims ----------------------------------------------------------

def check_path_shims(profile: Profile):
    adlc = shutil.which("adlc")
    if not adlc:
        return (
            Result.FAIL,
            "adlc is not on PATH",
            "./install.sh --repair   # then restart your shell (or: source ~/.zshrc)",
        )
    probe = subprocess.run([adlc, "--version"], capture_output=True, text=True)
    if probe.returncode != 0:
        return (
            Result.FAIL,
            f"adlc on PATH ({adlc}) but `adlc --version` failed",
            "./install.sh --repair   # regenerates the shim",
        )
    return Result.PASS, f"adlc -> {adlc} (v{probe.stdout.strip()})", ""


# --- gh --------------------------------------------------------------------

def check_gh_present(profile: Profile):
    gh = shutil.which("gh")
    if gh:
        return Result.PASS, f"gh -> {gh}", ""
    install_line = (
        "brew install gh" if profile.os == "Darwin"
        else "see https://github.com/cli/cli#installation"
    )
    return Result.FAIL, "gh (GitHub CLI) is not on PATH", install_line


def check_gh_auth(profile: Profile):
    # Retained as a helper reused by check_forge on the github branch (REQ-520
    # ADR-4). It is NO LONGER in REGISTRY — the `forge` check is the single
    # forge-auth mechanism and folds this probe in for provider github.
    if not shutil.which("gh"):
        return Result.SKIP, "gh not installed (see gh-present)", ""
    status = subprocess.run(
        ["gh", "auth", "status"], capture_output=True, text=True,
    )
    if status.returncode == 0:
        return Result.PASS, "gh is authenticated", ""
    return Result.FAIL, "gh is not authenticated", "gh auth login"


# --- forge adapter (REQ-520 BR-7) — supersedes the standalone gh-auth check --

def _forge_provider_verdict(profile: Profile):
    """Resolve the forge provider by sourcing partials/forge.sh under bash.

    Returns (provider, detail) on success, or (None, reason) when resolution
    failed. ``no-remote`` is a distinguished reason -> the check SKIPs (BR-7).
    Mirrors ``_gate_verdict``'s source-a-partial-under-bash pattern.
    """
    partial = _partial_path(profile, "forge.sh")
    if not os.path.isfile(partial):
        return None, "forge-partial-missing"
    # Resolve against the current working dir (the repo doctor was invoked in),
    # not the toolkit root — provider is a property of the consumer repo's remote.
    # No temp-file redirect: subprocess capture_output collects stderr into
    # proc.stderr, so there is no predictable-path junk file / TOCTOU foothold
    # (LESSON-008). The function's fail-loud message lands in proc.stderr if needed.
    script = (
        f". '{partial}'; "
        "adlc_forge_provider \"$PWD\"; rc=$?; "
        'printf "%s\\n" "$rc"'
    )
    proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    out = proc.stdout.splitlines()
    # The script prints the provider (from adlc_forge_provider) then the rc line.
    # Parse defensively: provider is the recognized non-rc line.
    provider = ""
    for line in out:
        s = line.strip()
        if s in ("github", "azure-devops"):
            provider = s
    if provider:
        return provider, "resolved"
    # No remote at all is the documented SKIP case.
    if not _has_remote(profile):
        return None, "no-remote"
    return None, "unresolved"


def _has_remote(profile: Profile) -> bool:
    out = subprocess.run(
        ["git", "remote"], capture_output=True, text=True,
    )
    return out.returncode == 0 and bool(out.stdout.strip())


def check_forge(profile: Profile):
    """Resolved provider, backend CLI present, auth valid, read-only probe (BR-7).

    SKIP-with-reason when the repo has no remote. Supersedes the standalone
    gh-auth check: for provider github it performs the gh auth probe; for
    azure-devops it checks `az`/PAT.
    """
    if not _has_remote(profile):
        return Result.SKIP, "no git remote — forge provider not applicable", ""

    provider, reason = _forge_provider_verdict(profile)
    if provider is None:
        if reason == "no-remote":
            return Result.SKIP, "no git remote — forge provider not applicable", ""
        if reason == "forge-partial-missing":
            return (
                Result.FAIL,
                "partials/forge.sh not found — forge adapter is not installed",
                "re-run /init to vendor partials, or check the toolkit checkout",
            )
        # Unrecognized host / unresolved: fail loud (BR-2) with config remediation.
        return (
            Result.FAIL,
            "could not resolve a forge provider (unrecognized origin host?)",
            "set forge.provider in .adlc/config.yml to one of: github, azure-devops",
        )

    if provider == "github":
        if not shutil.which("gh"):
            install = ("brew install gh" if profile.os == "Darwin"
                       else "see https://github.com/cli/cli#installation")
            return Result.FAIL, "forge=github but gh (GitHub CLI) is not on PATH", install
        # Fold in the gh auth probe (the superseded gh-auth check).
        auth = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
        if auth.returncode != 0:
            return Result.FAIL, "forge=github: gh is not authenticated", "gh auth login"
        return Result.PASS, "forge=github: gh present and authenticated", ""

    if provider == "azure-devops":
        if not shutil.which("az"):
            return (
                Result.FAIL,
                "forge=azure-devops but az (Azure CLI) is not on PATH",
                "brew install azure-cli && az extension add --name azure-devops"
                if profile.os == "Darwin"
                else "install the Azure CLI + azure-devops extension "
                     "(https://learn.microsoft.com/cli/azure/install-azure-cli)",
            )
        # Either an az login session OR a PAT env var named in config satisfies auth.
        acct = subprocess.run(["az", "account", "show"], capture_output=True, text=True)
        pat_var, pat_set = _forge_pat_status(profile)
        if acct.returncode == 0 or pat_set:
            how = "az login session" if acct.returncode == 0 else f"PAT env var {pat_var}"
            return Result.PASS, f"forge=azure-devops: authenticated via {how}", ""
        remediation = "az login"
        if pat_var:
            remediation = f"az login   # or set the PAT env var {pat_var}"
        return (
            Result.FAIL,
            "forge=azure-devops: no az login session and PAT env var not set",
            remediation,
        )

    return Result.FAIL, f"unknown forge provider '{provider}'", \
        "set forge.provider to github or azure-devops in .adlc/config.yml"


def _forge_pat_status(profile: Profile):
    """Return (pat_var_name, is_set). Reads forge.auth from config (a var NAME).

    Reuses tools/adlc/forge_config.parse_forge_config via subprocess probe so
    checks keeps no hard import of the forge module at registry-build time.
    The probe runs in ``_delegate_interpreter()`` — the interpreter that has
    PyYAML where delegation is installed — so the probe reads the config the
    same way the real call does (REQ-609 BR-8, LESSON-392). A malformed config
    makes the reader exit non-zero, which lands here as "no PAT var", and the
    `pyyaml`/`forge` checks report the real cause.
    """
    reader = os.path.join(profile.repo_root, "tools", "adlc", "forge_config.py")
    if not os.path.isfile(reader):
        return "", False
    cfg_proj = os.path.join(os.getcwd(), ".adlc", "config.yml")
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import forge_config as fc; "
        "d = fc.parse_forge_config(sys.argv[2]); print(d.get('auth', ''))"
    )
    out = subprocess.run(
        [_delegate_interpreter(), "-c", code, os.path.dirname(reader), cfg_proj],
        capture_output=True, text=True,
    )
    auth = out.stdout.strip() if out.returncode == 0 else ""
    # 'gh'/'az' are CLI-login sources, not PAT var names.
    if not auth or auth in ("gh", "az"):
        return "", False
    return auth, bool(os.environ.get(auth))


# --- reservation namespace pushability (REQ-546 BR-13) ---------------------

def _classify_git_failure(stderr: str) -> str:
    """Name the failing layer from a git push/ls-remote stderr (BR-13).

    Ordered most-specific first. Auth and server-policy declines are distinct
    failure modes a machine operator must fix differently; transport is the
    catch-all connectivity bucket.
    """
    s = (stderr or "").lower()
    if ("authentication failed" in s or "permission denied" in s or "403" in s
            or "could not read username" in s or "invalid username or password" in s):
        return "auth"
    if ("pre-receive hook declined" in s or "[remote rejected]" in s
            or "protected branch" in s or "denied" in s):
        return "server policy"
    if ("could not read from remote" in s or "does not appear to be a git repository" in s
            or "could not resolve host" in s or "unable to access" in s
            or "connection" in s or "timed out" in s or "network" in s):
        return "transport"
    return "unknown"


def check_reservations(profile: Profile):
    """Reservation ref namespace is readable AND writable on origin (BR-13).

    A machine that silently cannot push reservations allocates permanently
    degraded — the one remaining duplicate source REQ-546 leaves open by design —
    so doctor catches it. Probes: (1) ls-remote the namespace (read + transport +
    read-auth); (2) push an EPHEMERAL probe ref that is actually pushed and deleted
    (`refs/adlc/ids/_probe/<nonce>` — `_probe` is not a real kind, so it reserves
    nothing; the delete is the ONE sanctioned deletion). A `git push --dry-run` is
    NOT a substitute — it never exercises server-side pre-receive policy, exactly the
    layer this check exists to catch. Pure subprocess, no dependency on the mechanism
    it diagnoses (LESSON-395). SKIP-with-reason on a remote-less repo.
    """
    if not _has_remote(profile):
        return Result.SKIP, "no git remote — reservation namespace not applicable", ""

    # GIT_TERMINAL_PROMPT=0 so an auth-required remote fails fast (reported as a layer)
    # instead of hanging the whole doctor run on a credential prompt.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    # 1. Readability (also exercises transport + read auth).
    read = subprocess.run(
        ["git", "ls-remote", "origin", "refs/adlc/ids/*"],
        capture_output=True, text=True, env=env,
    )
    if read.returncode != 0:
        layer = _classify_git_failure(read.stderr)
        return (
            Result.FAIL,
            f"reservation namespace not readable ({layer})",
            "verify `git ls-remote origin` works — reservations live under refs/adlc/ids/*",
        )

    # 2. Writability via a real ephemeral probe ref. Probe object: a tiny throwaway
    #    commit over the empty tree (git commit-tree needs a configured identity — if
    #    unset, SKIP and defer to the git-identity check rather than false-passing).
    tree = subprocess.run(
        ["git", "hash-object", "-w", "-t", "tree", os.devnull],
        capture_output=True, text=True,
    ).stdout.strip() or "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    ct = subprocess.run(
        ["git", "commit-tree", tree],
        input="adlc-doctor-reservation-probe\n", capture_output=True, text=True,
    )
    obj = ct.stdout.strip()
    if not obj:
        return (
            Result.SKIP,
            "cannot build a probe object (git identity unset — see git-identity check)",
            "",
        )

    proberef = "refs/adlc/ids/_probe/" + os.urandom(8).hex()
    push = subprocess.run(
        ["git", "push", "origin", f"{obj}:{proberef}"],
        capture_output=True, text=True, env=env,
    )
    if push.returncode != 0:
        layer = _classify_git_failure(push.stderr)
        return (
            Result.FAIL,
            f"reservation namespace not writable ({layer})",
            "grant push access to refs/adlc/ids/* on origin — otherwise id allocation "
            "runs permanently degraded (ids get verified late by the REQ-545 recheck)",
        )
    # Cleanup: delete the probe ref (the ONE sanctioned deletion — it reserves nothing).
    subprocess.run(
        ["git", "push", "origin", "--delete", proberef],
        capture_output=True, text=True, env=env,
    )
    return Result.PASS, "reservation namespace readable and writable on origin", ""


# --- git identity ----------------------------------------------------------

def check_git_identity(profile: Profile):
    def _cfg(key):
        return subprocess.run(
            ["git", "config", "--get", key], capture_output=True, text=True,
        ).stdout.strip()

    name, email = _cfg("user.name"), _cfg("user.email")
    if name and email:
        return Result.PASS, f"git identity: {name} <{email}>", ""
    missing = []
    if not name:
        missing.append('git config --global user.name "Your Name"')
    if not email:
        missing.append('git config --global user.email "you@example.com"')
    return (
        Result.FAIL,
        "git identity is not fully set ("
        + ", ".join(k for k, v in (("user.name", name), ("user.email", email)) if not v)
        + " missing)",
        " && ".join(missing),
    )


# --- delegation gate (REUSES REQ-515, ADR-4) -------------------------------

def _gate_verdict(profile: Profile):
    """Return (rc, reason) from sourcing partials/delegate-gate.sh under bash.

    Captures the function's own rc into a var BEFORE echoing (the partial's
    documented protocol) so the echo does not clobber $?.
    """
    partial = _partial_path(profile, "delegate-gate.sh")
    if not os.path.isfile(partial):
        return None, "gate-partial-missing"
    script = (
        f". '{partial}'; adlc_delegate_gate_check; rc=$?; "
        'printf "%s\\n%s\\n" "$rc" "$ADLC_DELEGATE_GATE_REASON"'
    )
    out = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True,
    ).stdout.splitlines()
    if len(out) < 2:
        return None, "gate-probe-failed"
    try:
        return int(out[0].strip()), out[1].strip()
    except ValueError:
        return None, "gate-probe-unparsable"


def _config_enabled(profile: Profile):
    """True iff delegate.enabled is true in the REQ-515 config.

    Reuses tools/delegate/_common.parse_delegate_config via a subprocess probe so
    adlc keeps no hard import dependency on the delegate module (it may be absent
    on a skills-only checkout). Returns False on any failure (treated as
    not-opted-in). (REQ-522 renamed tools/kimi -> tools/delegate.)

    The probe runs in ``_delegate_interpreter()``: the config is parsed with
    PyYAML since REQ-609, and the venv is where ``install.sh`` pins it — probing
    with a bare ``python3`` from ``$PATH`` would answer for an interpreter the
    real call never uses (BR-8, LESSON-392).
    """
    common_dir = os.path.join(profile.repo_root, "tools", "delegate")
    if not os.path.isfile(os.path.join(common_dir, "_common.py")):
        return False
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import _common; "
        "print('1' if _common.parse_delegate_config().get('enabled') else '0')"
    )
    out = subprocess.run(
        [_delegate_interpreter(), "-c", code, common_dir],
        capture_output=True, text=True,
    )
    return out.returncode == 0 and out.stdout.strip() == "1"


# --- PyYAML in the interpreter adlc runs under (REQ-609 BR-8, ADR-2) -------

def check_pyyaml(profile: Profile):
    """Is PyYAML importable in the interpreter that parses the ADLC config?

    Since REQ-609 the machine config is parsed by ``yaml.safe_load`` behind a
    strict schema, and a missing PyYAML is not a silent degradation: the
    delegate consumer refuses outright, and the forge consumer proceeds
    unconfigured after a stderr line. Either way the operator's config is not
    being read, so doctor says so with the fix.

    There is no SKIP: the check is meaningful on every machine, delegation
    opted into or not. The probe is a subprocess, never an import here — this
    module must load on a machine that has no PyYAML at all (LESSON-395).
    """
    interp = _delegate_interpreter()
    fix = (
        f"{os.path.join(profile.repo_root, 'install.sh')} --with-delegation"
        "   # or: python3 -m pip install --user 'pyyaml>=6.0'"
    )
    try:
        probe = subprocess.run(
            [interp, "-c", "import yaml; print(yaml.__version__)"],
            capture_output=True, text=True,
        )
    except OSError as exc:
        # The selected interpreter could not be executed at all. Still a FAIL
        # with the same fix — doctor reports, it never crashes.
        return (
            Result.FAIL,
            f"could not run {interp} to check PyYAML ({exc.strerror or exc})",
            fix,
        )
    version = probe.stdout.strip()
    if probe.returncode == 0 and version:
        return Result.PASS, f"PyYAML {version} in {interp}", ""
    return (
        Result.FAIL,
        f"PyYAML is not importable in {interp} — the ADLC config "
        f"(~/.claude/adlc/config.yml) cannot be parsed there",
        fix,
    )


def check_delegate_gate(profile: Profile):
    rc, reason = _gate_verdict(profile)
    if rc == 0:
        return Result.PASS, "delegation enabled and reachable", ""
    if rc == 1:
        # opt-in off, or explicitly disabled — not a failure (BR-9 default).
        return Result.SKIP, f"delegation not active ({reason})", ""
    if rc == 2:
        # adlc-read not on PATH. Only a FAIL if config asked for delegation
        # (misconfigured); otherwise it is the expected not-opted-in posture.
        if _config_enabled(profile):
            return (
                Result.FAIL,
                "delegation config sets enabled: true but adlc-read is not on PATH",
                "./install.sh --with-delegation   # installs the delegate shims, "
                "or set delegate.enabled: false in ~/.claude/adlc/config.yml",
            )
        return Result.SKIP, "delegation not enabled (adlc-read not installed)", ""
    # rc is None — the gate probe itself failed.
    return (
        Result.FAIL,
        f"could not evaluate the delegation gate ({reason})",
        "verify partials/delegate-gate.sh is present and bash is on PATH",
    )


# --- counters --------------------------------------------------------------

def _lock_is_stale(lock_dir: str) -> bool:
    try:
        age = time.time() - os.path.getmtime(lock_dir)
    except OSError:
        return False
    return age > _STALE_LOCK_SECONDS


def check_counters(profile: Profile):
    base = _claude_home()
    problems = []
    fixes = []
    for name in _COUNTERS:
        path = os.path.join(base, name)
        lock = path + ".lock.d"
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    raw = fh.read().strip()
            except OSError as exc:
                # Use strerror, not str(exc): OSError.__str__ embeds the absolute
                # filename, which leaks into the report/CI logs (LESSON-021).
                problems.append(f"{name} unreadable ({exc.strerror or 'I/O error'})")
                fixes.append(f"ls -l '{path}'")
                continue
            if not raw.isdigit():
                problems.append(f"{name} is not numeric ('{raw}')")
                fixes.append(f"printf '<correct-next-number>' > '{path}'")
        # A counter that does not exist yet is fine (first run) — not flagged.
        if os.path.isdir(lock) and _lock_is_stale(lock):
            problems.append(f"{name} has a stale lock dir")
            fixes.append(f"rmdir '{lock}'")
    if problems:
        return Result.FAIL, "; ".join(problems), " && ".join(fixes)
    return Result.PASS, "global counters present, numeric, no stale locks", ""


# --- launchctl (macOS-only, opt-in) ----------------------------------------

def check_launchctl(profile: Profile):
    # applies_to already gates this off on non-Darwin (BR-6). Reaching here means
    # macOS. The LaunchAgent only matters when delegation is opted in.
    rc, _reason = _gate_verdict(profile)
    if rc != 0:
        return Result.SKIP, "delegation not active — launchctl setenv not required", ""
    # REQ-522 renamed the LaunchAgent label; the installer migrates the old one.
    label = "com.adlc-toolkit.delegate-setenv"
    listed = subprocess.run(
        ["launchctl", "list", label], capture_output=True, text=True,
    )
    if listed.returncode == 0:
        return Result.PASS, f"LaunchAgent {label} is loaded", ""
    plist = os.path.join(
        os.path.expanduser("~"), "Library", "LaunchAgents", label + ".plist",
    )
    return (
        Result.FAIL,
        f"LaunchAgent {label} is not loaded",
        f"launchctl bootstrap gui/$(id -u) '{plist}'",
    )


# --- template version (consumer-project staleness pointer) -----------------

def check_template_version(profile: Profile):
    # Only meaningful inside a consumer project that vendored templates.
    project_templates = os.path.join(os.getcwd(), ".adlc", "templates")
    if not os.path.isdir(project_templates):
        return Result.SKIP, "not inside a consumer project with vendored templates", ""
    return (
        Result.PASS,
        "project .adlc/templates present — run /template-drift to compare with toolkit",
        "",
    )


# --- claude-code (report-only, never fails the verdict) --------------------

def check_claude_code(profile: Profile):
    cc = shutil.which("claude")
    if not cc:
        return Result.SKIP, "claude CLI not detected on PATH (report-only)", ""
    return Result.PASS, f"claude -> {cc} (report-only; not gated)", ""


# --- registry (report order) ----------------------------------------------

REGISTRY = [
    Check("skills-symlink", check_skills_symlink),
    Check("agents-symlink", check_agents_symlink),
    Check("toolkit-clean", check_toolkit_clean),
    Check("path-shims", check_path_shims),
    Check("gh-present", check_gh_present),
    # `forge` supersedes the standalone gh-auth check (REQ-520 ADR-4): it folds the
    # gh auth probe in for provider github and handles azure-devops auth too.
    Check("forge", check_forge),
    Check("reservations", check_reservations),
    Check("git-identity", check_git_identity),
    Check("delegate-gate", check_delegate_gate),
    # Reads on the interpreter BOTH config consumers use, so it is registered
    # next to the delegation check it explains (REQ-609 ADR-2).
    Check("pyyaml", check_pyyaml),
    Check("counters", check_counters),
    Check(
        "launchctl",
        check_launchctl,
        applies_to=lambda p: p.os == "Darwin",
        skip_notice="launchctl is macOS-only",
    ),
    Check("template-version", check_template_version),
    Check("claude-code", check_claude_code),
]

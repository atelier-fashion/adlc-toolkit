#!/usr/bin/env python3
"""exec_safety — what the orchestrator will and will not execute (REQ-659 BR-17, BR-23).

Everything read from the model's side is data, so it is validated here before any path
or shell use. Everything the orchestrator runs goes through :class:`Toolbox`, which
resolves its binaries once, verifies a sha256 manifest of them and of the install before
each source or exec, re-checks the common gitdir, and runs under an environment that
neutralizes git. That is environment and not ``-c`` flags, because a trial merge, the
lane check and the id allocator spawn git themselves, where a flag cannot reach.

Standard library only.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import time

VALID_REQ = re.compile(r"^REQ-[0-9]{3,6}$")
VALID_REPO_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
VALID_BRANCH = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
VALID_OID = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
VALID_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,120}$")
PR_URL = re.compile(r"^https://([A-Za-z0-9.-]+)/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)"
                    r"/pull/([0-9]{1,10})$")
#: `git` and `sh` are needed for anything at all; the rest are resolved when present.
REQUIRED_TOOLS = ("git", "python3", "sh")
OPTIONAL_TOOLS = ("gh", "az", "ssh")
#: Top-level toolkit paths the manifest walks.
INSTALL_TREES = ("partials", "tools/adlc", "proceed", "wrapup")
INSTALL_FILES = ("sprint/SKILL.md", "tools/delegate/emit-run-outcome.sh",
                 "tools/delegate/run_outcome.py")
#: Operator settings a snapshot may carry; a filter driver or pager never is one.
GITCONFIG_KEEP = re.compile(r"^(user\.|credential\.|url\.|http\.|init\.defaultbranch$|"
                            r"safe\.directory$)")
#: Environment the orchestrator's own tools inherit; everything else is dropped.
BASE_ENV = ("HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TERM",
            "SSH_AUTH_SOCK", "GH_TOKEN", "GITHUB_TOKEN", "GH_HOST", "ADLC_HOME", "ADLC_CONFIG",
            "ADLC_DISABLE_DELEGATE", "ADLC_RUN_OUTCOMES_LOG", "XDG_STATE_HOME", "XDG_CONFIG_HOME")
BASE_ENV_PREFIXES = ("ADLC_FORGE_MOCK",)
SYSTEM_PATH = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")


class RuleBViolation(Exception):
    """A protocol violation: surfaced, recorded, and nothing further runs in that tree."""


class SafetyError(ValueError):
    """A value from the model's side failed validation (BR-17)."""


def require(pattern, value, field):
    if not isinstance(value, str) or not pattern.match(value):
        raise SafetyError("%s failed validation: %r" % (field, value))
    return value


def valid_req(value, field="req"):
    return require(VALID_REQ, value, field)


def valid_branch(value, field="branch"):
    require(VALID_BRANCH, value, field)
    if ".." in value or value.startswith(("-", "/")) or value.endswith("/"):
        raise SafetyError("%s failed validation: %r" % (field, value))
    return value


def parse_pr_url(url, host, field="prUrl"):
    """``(owner, name, number)`` of a PR URL on ``host``, or :class:`SafetyError`."""
    match = PR_URL.match(url) if isinstance(url, str) else None
    if match is None:
        raise SafetyError("%s failed validation: %r" % (field, url))
    if match.group(1) != host:
        raise SafetyError("%s is on host %s, not the configured forge host %s"
                          % (field, match.group(1), host))
    return match.group(2), match.group(3), int(match.group(4))


def origin_parts(url):
    """``(host, owner, name)`` of an origin URL, any of its spellings."""
    text = url.strip()
    if text.startswith(("/", "file://")):
        path = text[len("file://"):] if text.startswith("file://") else text
        host = ""
    elif "://" in text:
        rest = text.split("://", 1)[1]
        host, _, path = rest.partition("/")
        host = host.rsplit("@", 1)[-1].split(":")[0]
    else:
        left, _, path = text.partition(":")
        host = left.rsplit("@", 1)[-1]
    parts = [p for p in path.split("/") if p]
    name = parts[-1] if parts else ""
    name = name[:-4] if name.endswith(".git") else name
    return host, parts[-2] if len(parts) > 1 else "", name


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strip_branch_sections(text):
    """A git config without its ``[branch "..."]`` sections.

    A legitimate ``git push -u`` writes one, so the checksum must not see them.
    """
    out = []
    skipping = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            skipping = stripped.startswith('[branch "')
        if not skipping:
            out.append(line)
    return "\n".join(out)


def gitdir_digest(common):
    """The launch-time checksum set of a common gitdir (BR-23 b)."""
    items = {}
    config = os.path.join(common, "config")
    if os.path.isfile(config):
        with open(config, encoding="utf-8", errors="replace") as fh:
            items["config"] = hashlib.sha256(strip_branch_sections(fh.read())
                                             .encode("utf-8")).hexdigest()
    for rel in ("config.worktree", os.path.join("info", "attributes")):
        path = os.path.join(common, rel)
        items[rel] = sha256_file(path) if os.path.isfile(path) else None
    hooks = os.path.join(common, "hooks")
    if os.path.isdir(hooks):
        for base, dirs, files in os.walk(hooks):
            dirs.sort()
            for name in sorted(files):
                path = os.path.join(base, name)
                rel = os.path.relpath(path, common)
                mode = os.lstat(path).st_mode & 0o777
                body = os.readlink(path) if os.path.islink(path) else sha256_file(path)
                items[rel] = "%o:%s" % (mode, body)
    worktrees = os.path.join(common, "worktrees")
    if os.path.isdir(worktrees):
        for name in sorted(os.listdir(worktrees)):
            path = os.path.join(worktrees, name, "config.worktree")
            if os.path.isfile(path):
                items[os.path.join("worktrees", name, "config.worktree")] = sha256_file(path)
    return items


def install_files(toolkit):
    """Every file the manifest covers, relative to the toolkit root."""
    out = []
    for tree in INSTALL_TREES:
        top = os.path.join(toolkit, tree)
        for base, dirs, files in os.walk(top):
            dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", "tests", ".pytest_cache"))
            for name in sorted(files):
                if not name.endswith((".pyc", ".pyo")):
                    out.append(os.path.relpath(os.path.join(base, name), toolkit))
    out += [rel for rel in INSTALL_FILES if os.path.isfile(os.path.join(toolkit, rel))]
    return out


def resolve_tools(path_env):
    """Absolute paths of the orchestrator's tools, once (BR-23 b). Raises on a missing one."""
    found = {}
    for name in REQUIRED_TOOLS + OPTIONAL_TOOLS:
        hit = shutil.which(name, path=path_env)
        if hit:
            found[name] = os.path.abspath(hit)
        elif name in REQUIRED_TOOLS:
            raise SafetyError("%s is not on PATH" % name)
    return found


def git_version(git):
    out = subprocess.run([git, "--version"], stdout=subprocess.PIPE, universal_newlines=True,
                         env={"PATH": "/usr/bin:/bin"}).stdout
    match = re.search(r"(\d+)\.(\d+)", out)
    return (int(match.group(1)), int(match.group(2))) if match else (0, 0)


class Toolbox(object):
    """One run's resolved tools, snapshots, manifest, checksums and action log."""

    def __init__(self, run_dir, toolkit, environ=None):
        self.run_dir = run_dir
        self.toolkit = toolkit
        self.environ = dict(os.environ if environ is None else environ)
        self.record_path = os.path.join(run_dir, "toolbox.json")
        self.log_path = os.path.join(run_dir, "orchestrator.log")
        self.tools = {}
        self.manifest = {}
        self.trees = {}
        self.helpers = []
        self.provider = None
        self.halted = False

    # -- launch-time preparation ------------------------------------------------
    def prepare(self, provider=None):
        self.provider = provider
        self.tools = resolve_tools(self.environ.get("PATH", ""))
        if git_version(self.tools["git"]) < (2, 31):
            raise SafetyError("git 2.31 or newer is required (GIT_CONFIG_COUNT)")
        bindir = os.path.join(self.run_dir, "bin")
        os.makedirs(bindir, exist_ok=True)
        for name, path in self.tools.items():
            link = os.path.join(bindir, name)
            if not os.path.lexists(link):
                os.symlink(path, link)
        os.makedirs(os.path.join(self.run_dir, "hooks-empty"), exist_ok=True)
        with open(os.path.join(self.run_dir, "attributes-empty"), "w", encoding="utf-8"):
            pass
        self._snapshot_gitconfig()
        self._snapshot_ssh()
        self._snapshot_gh()
        self.manifest = self._compute_manifest()
        self.save()

    def _snapshot_gitconfig(self):
        res = subprocess.run([self.tools["git"], "config", "--global", "--includes", "--list",
                              "-z"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             env={"HOME": self.environ.get("HOME", ""),
                                  "XDG_CONFIG_HOME": self.environ.get("XDG_CONFIG_HOME", ""),
                                  "PATH": "/usr/bin:/bin"})
        target = os.path.join(self.run_dir, "gitconfig")
        with open(target, "w", encoding="utf-8"):
            pass
        for item in res.stdout.split(b"\0"):
            if not item:
                continue
            key, _, value = item.decode("utf-8", "replace").partition("\n")
            if not GITCONFIG_KEEP.match(key.lower()):
                continue
            if key.lower() == "credential.helper":
                self.helpers.append(value)
                continue
            subprocess.run([self.tools["git"], "config", "--file", target, "--add", key, value],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           env={"PATH": "/usr/bin:/bin"})

    def _snapshot_ssh(self):
        target = os.path.join(self.run_dir, "ssh_config")
        source = os.path.join(self.environ.get("HOME", ""), ".ssh", "config")
        if os.path.isfile(source):
            shutil.copyfile(source, target)
        else:
            with open(target, "w", encoding="utf-8"):
                pass

    def _snapshot_gh(self):
        target = os.path.join(self.run_dir, "gh")
        os.makedirs(target, exist_ok=True)
        base = self.environ.get("GH_CONFIG_DIR") or os.path.join(
            self.environ.get("XDG_CONFIG_HOME") or os.path.join(self.environ.get("HOME", ""),
                                                                ".config"), "gh")
        for name in ("hosts.yml", "config.yml"):
            source = os.path.join(base, name)
            if os.path.isfile(source):
                shutil.copyfile(source, os.path.join(target, name))

    def _compute_manifest(self):
        files = {}
        for rel in install_files(self.toolkit):
            files[rel] = sha256_file(os.path.join(self.toolkit, rel))
        binaries = {name: sha256_file(os.path.realpath(path)) for name, path in self.tools.items()}
        return {"files": files, "binaries": binaries}

    def register_tree(self, repo):
        """Record the checksum set of the common gitdir a repo's working copies share."""
        common = self.common_dir(repo)
        self.trees[repo] = {"common": common, "digest": gitdir_digest(common)}
        self.save()

    def common_dir(self, repo):
        res = subprocess.run([self.tools["git"], "-C", repo, "rev-parse",
                              "--path-format=absolute", "--git-common-dir"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             universal_newlines=True, env=self.env())
        if res.returncode != 0:
            raise SafetyError("%s is not a git repository: %s" % (repo, res.stderr.strip()))
        return res.stdout.strip()

    def save(self):
        doc = {"tools": self.tools, "manifest": self.manifest, "trees": self.trees,
               "helpers": self.helpers, "provider": self.provider, "halted": self.halted}
        tmp = self.record_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1, sort_keys=True)
        os.replace(tmp, self.record_path)

    @classmethod
    def load(cls, run_dir, toolkit, environ=None):
        box = cls(run_dir, toolkit, environ)
        with open(box.record_path, encoding="utf-8") as fh:
            doc = json.load(fh)
        box.tools = doc["tools"]
        box.manifest = doc["manifest"]
        box.trees = doc["trees"]
        box.helpers = doc["helpers"]
        box.provider = doc.get("provider")
        box.halted = doc.get("halted", False)
        return box

    # -- the environment --------------------------------------------------------
    def git_config_pairs(self):
        ssh = self.tools.get("ssh", "ssh")
        pairs = [("core.hooksPath", os.path.join(self.run_dir, "hooks-empty")),
                 ("core.fsmonitor", "false"),
                 ("core.sshCommand", "%s -F %s" % (ssh, os.path.join(self.run_dir, "ssh_config"))),
                 ("credential.helper", "")]
        pairs += [("credential.helper", h) for h in self.helpers]
        pairs += [("core.attributesFile", os.path.join(self.run_dir, "attributes-empty")),
                  ("commit.gpgsign", "false"), ("log.showSignature", "false"),
                  ("protocol.ext.allow", "never")]
        return pairs

    def env(self, extra=None):
        env = {k: self.environ[k] for k in BASE_ENV if k in self.environ}
        for key, value in self.environ.items():
            if key.startswith(BASE_ENV_PREFIXES):
                env[key] = value
        env["PATH"] = os.pathsep.join((os.path.join(self.run_dir, "bin"),) + SYSTEM_PATH)
        env["ADLC_TOOLKIT_ROOT"] = self.toolkit
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["GIT_CONFIG_GLOBAL"] = os.path.join(self.run_dir, "gitconfig")
        pairs = self.git_config_pairs()
        env["GIT_CONFIG_COUNT"] = str(len(pairs))
        for i, (key, value) in enumerate(pairs):
            env["GIT_CONFIG_KEY_%d" % i] = key
            env["GIT_CONFIG_VALUE_%d" % i] = value
        if self.provider:
            env["ADLC_FORGE_PROVIDER_OVERRIDE"] = self.provider
        gh_dir = os.path.join(self.run_dir, "gh")
        env["GH_CONFIG_DIR"] = gh_dir
        env.update(extra or {})
        return env

    # -- verification -----------------------------------------------------------
    def verify_manifest(self):
        if not self.manifest:
            raise RuleBViolation("no manifest was recorded for this run")
        current = {name: sha256_file(os.path.realpath(path)) for name, path in self.tools.items()}
        for name, digest in self.manifest["binaries"].items():
            if current.get(name) != digest:
                self.violate("sha256 manifest mismatch: resolved binary %s (%s)"
                             % (name, self.tools.get(name)))
        for rel, digest in self.manifest["files"].items():
            path = os.path.join(self.toolkit, rel)
            actual = sha256_file(path) if os.path.isfile(path) else None
            if actual != digest:
                self.violate("sha256 manifest mismatch: install file %s" % rel)
        known = set(self.manifest["files"])
        for rel in install_files(self.toolkit):
            if rel not in known:
                self.violate("sha256 manifest mismatch: new install file %s" % rel)

    def check_gitdir(self, repo):
        """Whether the common gitdir still matches. Stubbed by the fixtures that need to."""
        tree = self.trees.get(repo)
        if tree is None:
            return True
        return gitdir_digest(tree["common"]) == tree["digest"]

    def verify_gitdir(self, repo):
        if not self.check_gitdir(repo):
            tree = self.trees[repo]
            now = gitdir_digest(tree["common"])
            changed = sorted(k for k in set(now) | set(tree["digest"])
                             if now.get(k) != tree["digest"].get(k))
            self.violate("common gitdir checksum mismatch in %s: %s" % (repo, ", ".join(changed)))

    def violate(self, message):
        self.halted = True
        self.save()
        self.log("protocol_violation", [message], "", None)
        raise RuleBViolation(message)

    # -- running things ---------------------------------------------------------
    def log(self, kind, argv, cwd, rc, env=None):
        record = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "kind": kind,
                  "argv": list(argv), "cwd": cwd, "rc": rc}
        if env is not None:
            record["env"] = {k: v for k, v in env.items() if k.startswith("GIT_CONFIG")}
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")

    def git(self, repo, args, cwd=None, extra_env=None, tree=None, stdin_text=None):
        """Run git in ``cwd`` (default ``repo``) after every BR-23 check."""
        if self.halted:
            raise RuleBViolation("a protocol violation stopped this run's tree")
        if args[0] in ("push", "fetch"):
            positional = [a for a in args[1:] if not a.startswith("-")]
            if len(positional) < 2:
                raise ValueError("every push and fetch names the remote and a refspec: %r"
                                 % (args,))
        self.verify_manifest()
        self.verify_gitdir(tree or repo)
        where = cwd or repo
        env = self.env(extra_env)
        argv = [self.tools["git"], "-C", where] + list(args)
        res = subprocess.run(argv, input=stdin_text, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, universal_newlines=True, env=env)
        self.log("git", argv, where, res.returncode, env)
        return res

    def partial(self, partial, func, args, cwd, extra_env=None, tree=None):
        """Source a partial from the install, by absolute path, and call one function.

        ``adlc-home.sh`` is loaded first, so ``forge.sh`` never falls to its cwd-relative
        load, and the forge provider was resolved once, so ``forge_config.py`` is never
        looked for in the repo.
        """
        if tree and self.halted:
            raise RuleBViolation("a protocol violation stopped this run's tree")
        self.verify_manifest()
        if tree:
            self.verify_gitdir(tree)
        script = '. "$1"; . "$2"; [ "$3" = "-" ] || . "$3"; f=$4; shift 4; "$f" "$@"'
        partials = os.path.join(self.toolkit, "partials")
        forge = os.path.join(partials, "forge.sh")
        target = os.path.join(partials, partial)
        argv = [self.tools["sh"], "-c", script, "sh", os.path.join(partials, "adlc-home.sh"),
                forge, "-" if target == forge else target, func] + list(args)
        env = self.env(extra_env)
        res = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             universal_newlines=True, env=env, cwd=cwd)
        self.log("partial", [partial, func] + list(args), cwd, res.returncode, env)
        return res

    def forge(self, func, args, repo, extra_env=None):
        """A forge op, from the parent repo path (BR-11)."""
        env = dict(extra_env or {})
        env["ADLC_FORGE_REPO"] = repo
        return self.partial("forge.sh", func, args, repo, env, tree=repo)

    def tool(self, argv, cwd):
        """Run an install-resident tool under the same environment."""
        self.verify_manifest()
        env = self.env()
        res = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             universal_newlines=True, env=env, cwd=cwd)
        self.log("tool", argv, cwd, res.returncode, env)
        return res


def kv(text):
    """``key=value`` lines of a forge op's output, as a dict."""
    out = {}
    for line in (text or "").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            out[key] = value
    return out

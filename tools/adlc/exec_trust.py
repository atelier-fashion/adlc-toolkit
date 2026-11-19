#!/usr/bin/env python3
"""exec_trust — the per-run trust grant in the adapter's user config (REQ-662 BR-5, ADR-5).

For ``trust_grant: user-config-entry`` the engine appends one block to the user config the
adapter names (``paths.config.user``) before a launch, and removes exactly that block when
the run ends, on success, on failure and on the crash path::

    <blank line>
    # adlc exec trust (REQ-662) — removed when the run ends
    [projects."<the working copy, resolved>"]
    trust_level = "trusted"
    <blank line>

* **The path.** Absolute, resolved, an existing directory under the run's working-copy
  root, with no ``"``, ``\\`` or control character (a TOML key cannot carry one
  unescaped). Anything else is refused before any byte is written (:func:`check_path`).
* **Additive.** The block is appended; every other byte of the file is unchanged, so no
  write reaches ``hooks.state`` or any other hook-review key. A path the file already
  trusts is recorded ``pre_existing``, nothing is written, and revoke leaves it.
* **Surgical revoke.** Revoke removes the block's exact bytes and nothing else. A block
  that is gone is a warning; a block the operator edited (a key added to its table) is
  left as the operator has it, with a warning. The block is the same for a given path, so
  a block a killed run left behind is found by the next grant (``adopted``) and by a
  revoke built from the path alone.
* **The lock.** One ``mkdir`` directory beside the trust file, refused when it is a
  symlink, as the id allocator's is (LESSON-014). Every write to the trust file takes it.
  It is ``exec_ledger.mkdir_lock``, the implementation the user policy file's lock (BR-4)
  shares.
* **The probe.** While REQ-664's recovery marker exists for the harness, a probe run is
  editing, or died editing, the same file and restores it whole: the grant refuses,
  naming the marker.

The table is spelled as the probe's own trust edit spells it (``harness_probe``), and a
test holds the two equal. This module does not import the probe: that module is pinned
to the standard library alone, and its whole-file restore is wrong for a file two runs
may edit at once. Every harness difference is adapter data passed in (the user config
path, the mechanism); no harness is named here.

Standard library only.
"""

import os
import stat

import exec_ledger as el
import toml_merge as tm

#: The mechanism this module writes a file for (REQ-657 ``TRUST_MECHANISMS``).
USER_CONFIG_ENTRY = "user-config-entry"
#: Mechanisms that need no file: nothing is written and revoke is a no-op (REQ-659 BR-5).
NO_FILE = ("none", "flag")

#: Mirrors ``harness_probe.STATE_SUBDIR`` and its marker name; a test holds them equal.
PROBE_STATE_SUBDIR = ("adlc", "harness-probe")
PROBE_MARKER = "%s.marker.json"

#: The lock directory, beside the trust file.
LOCK_SUFFIX = ".adlc-trust.lock.d"
LOCK_TIMEOUT_S = 10.0

#: The one line that tells this module's block from an operator's own entry.
BLOCK_COMMENT = "# adlc exec trust (REQ-662) — removed when the run ends\n"

#: What :func:`revoke` found.
REVOKED = "revoked"           # the block was there and is gone
PRE_EXISTING = "pre-existing"  # the grant wrote nothing; the entry is the operator's
GONE = "gone"                 # the block was already gone: a warning
EDITED = "edited"             # the block was edited since the grant; left as it is
NO_FILE_STATUS = "no-file"    # the mechanism writes no file


class TrustRefused(ValueError):
    """A grant, revoke or pre-flight that must not go on; the message says why."""


# ---------------------------------------------------------------------------
# Adapter data and the probe's marker
# ---------------------------------------------------------------------------


def user_config_path(adapter, environ=None):
    """The adapter's user config file (``paths.config.user``), ``$HOME`` expanded: from
    ``environ`` when given (the run's environment, the one the harness is handed, so the file
    written is the file the harness reads; LESSON-777), else from this process's."""
    import harness_adapter as ha
    spec = ((adapter.get("paths") or {}).get("config") or {})
    user = spec.get("user")
    if not isinstance(user, str) or not user:
        raise TrustRefused("harness/%s.yml declares no paths.config.user, so trust_grant %s "
                           "has no file to write" % (adapter.get("name"), USER_CONFIG_ENTRY))
    if environ is None:
        return ha.expand_user_path(user)
    import exec_surfaces as esf
    try:
        return esf.user_path(user, environ)
    except esf.SurfaceRefused as exc:
        raise TrustRefused(str(exc))


def probe_marker(adlc_home, harness):
    """Where REQ-664's recovery marker for ``harness`` lives (``harness_probe.marker_path``)."""
    return os.path.join(adlc_home, *(PROBE_STATE_SUBDIR + (PROBE_MARKER % harness,)))


def refuse_while_probe_recovers(marker):
    """Refuse, naming ``marker``, while REQ-664's recovery marker exists."""
    if os.path.lexists(marker):
        name = os.path.basename(marker)[:-len(PROBE_MARKER % "")] or "<name>"
        raise TrustRefused("REQ-664's recovery marker %s exists: a probe run is editing the "
                           "same user files, or died before restoring them. Let it finish, "
                           "or run `adlc harness probe %s --recover`, then launch"
                           % (marker, name))


# ---------------------------------------------------------------------------
# The path and the block
# ---------------------------------------------------------------------------


def _key_problem(text):
    for ch in text:
        if ch in '"\\':
            return "holds %r, which a TOML key cannot carry unescaped" % ch
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            return "holds a control character"
    return None


def check_path(path, root):
    """The resolved working copy to trust, or :class:`TrustRefused`.

    ``path`` must be absolute and must resolve, symlinks followed, to an existing
    directory at or under the resolved ``root``.
    """
    for label, value in (("working-copy root", root), ("trust path", path)):
        if not isinstance(value, str) or not value:
            raise TrustRefused("the %s is empty" % label)
        if not os.path.isabs(value):
            raise TrustRefused("the %s %r is relative" % (label, value))
        problem = _key_problem(value)
        if problem:
            raise TrustRefused("the %s %r %s" % (label, value, problem))
    real_root = os.path.realpath(root)
    if real_root == os.path.dirname(real_root):
        raise TrustRefused("the working-copy root %r is the filesystem root" % root)
    resolved = os.path.realpath(path)
    if resolved != real_root and not resolved.startswith(real_root + os.sep):
        raise TrustRefused("the trust path %r resolves to %s, outside the working-copy root "
                           "%s" % (path, resolved, real_root))
    problem = _key_problem(resolved)
    if problem:
        raise TrustRefused("the trust path %r resolves to %r, which %s"
                           % (path, resolved, problem))
    if not os.path.isdir(resolved):
        raise TrustRefused("the trust path %r is not a directory" % path)
    return resolved


def trust_table(path):
    """The table, spelled as the probe's trust edit spells it."""
    return '[projects."%s"]\ntrust_level = "trusted"\n' % path


def trust_block(path):
    """Exactly the bytes a grant appends, and a revoke removes."""
    return "\n" + BLOCK_COMMENT + trust_table(path) + "\n"


# ---------------------------------------------------------------------------
# The lock
# ---------------------------------------------------------------------------


class TrustLock(object):
    """``with lock(trust_file):`` — the ``mkdir`` lock beside ``trust_file``, which is
    ``exec_ledger.mkdir_lock``, the one lock implementation the engine has.

    The directory that holds ``trust_file`` must exist. A symlink where the lock goes is
    refused, before taking it and before releasing it (LESSON-014). A lock not taken in
    ``timeout`` seconds is refused, naming the directory: an adlc run is editing the file,
    or one died holding it. The release never masks an exception the body raised.
    """

    def __init__(self, trust_file, timeout=LOCK_TIMEOUT_S):
        self.path = trust_file + LOCK_SUFFIX
        self.timeout = timeout
        self.held = False
        self._lock = None

    def __enter__(self):
        lock = el.mkdir_lock(self.path, self.timeout, TrustRefused,
                             holder="another adlc run is editing the file")
        lock.__enter__()
        self._lock, self.held = lock, True
        return self

    def __exit__(self, *exc):
        lock, self._lock, self.held = self._lock, None, False
        if lock is not None:
            lock.__exit__(*exc)
        return False


def lock(trust_file, timeout=LOCK_TIMEOUT_S):
    """The lock every write to ``trust_file`` takes, the user policy file's included."""
    return TrustLock(trust_file, timeout)


# ---------------------------------------------------------------------------
# Reading the trust file
# ---------------------------------------------------------------------------


def _lstat_file(path):
    """``os.lstat`` of a regular, singly linked ``path``; ``None`` when it is absent."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(st.st_mode):
        raise TrustRefused("%s is a symlink: the trust grant replaces a regular file "
                           "atomically and would break the link" % path)
    if not stat.S_ISREG(st.st_mode):
        raise TrustRefused("%s is not a regular file" % path)
    if st.st_nlink > 1:
        raise TrustRefused("%s has %d hard links: an atomic replace would split them"
                           % (path, st.st_nlink))
    return st


def _read(path):
    with open(path, "rb") as fh:
        data = fh.read()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TrustRefused("%s is not UTF-8 (%s); not editing it" % (path, exc))


def _scan(path, text):
    """``toml_merge.scan`` of ``text``; a file with no final newline reads as if it had one."""
    if text and not text.endswith("\n"):
        text += "\n"
    try:
        return tm.scan(text)
    except tm.TomlConstructError as exc:
        raise TrustRefused("%s holds a construct the trust grant will not edit around: %s"
                           % (path, exc))


def _entry(found, path):
    """What the file already says about ``path``: ``None`` (nothing), ``"trusted"``, or
    another word naming why the grant must not add a table for it."""
    name = "projects." + path
    if name in found.table_keys:
        raw = found.table_keys[name].get("trust_level")
        if raw is None:
            return "a table with no trust_level"
        return "trusted" if tm.plain_string(raw[0]) == "trusted" else "trust_level = %s" % raw[0]
    for key, (raw, _begin, _end) in (found.table_keys.get("projects") or {}).items():
        if key == path + ".trust_level":
            return "trusted" if tm.plain_string(raw) == "trusted" else "trust_level = %s" % raw
        if key.startswith(path + "."):
            return "dotted keys under [projects]"
    return None


def _replace(path, text, st):
    el.atomic_write(path, text.encode("utf-8"))
    if st is not None:
        os.chmod(path, stat.S_IMODE(st.st_mode))


# ---------------------------------------------------------------------------
# Grant, revoke, pre-flight
# ---------------------------------------------------------------------------


class Grant(object):
    """One grant: what revoke needs, and what the engine logs and records.

    ``config`` is the trust file (``None`` for a mechanism that writes none); ``path``
    the resolved working copy; ``pre_existing`` the file trusted it before the grant
    (nothing written); ``adopted`` the block a killed run left was taken over;
    ``newline_added`` the file had no final newline; ``created`` the file did not exist;
    ``marker`` REQ-664's recovery marker; ``granted_at`` the moment, for
    ``exec.trustGrantedAt``.
    """

    FIELDS = ("mechanism", "config", "path", "pre_existing", "adopted", "newline_added",
              "created", "marker", "granted_at")
    _BOOLS = ("pre_existing", "adopted", "newline_added", "created")

    def __init__(self, mechanism, config, path, pre_existing=False, adopted=False,
                 newline_added=False, created=False, marker=None, granted_at=None):
        self.mechanism = mechanism
        self.config = config
        self.path = path
        self.pre_existing = pre_existing
        self.adopted = adopted
        self.newline_added = newline_added
        self.created = created
        self.marker = marker
        self.granted_at = granted_at or el.now()

    @property
    def written(self):
        """True when this grant put a block in the file that revoke must take out."""
        return self.config is not None and not self.pre_existing

    def to_doc(self):
        return {k: getattr(self, k) for k in self.FIELDS}

    @classmethod
    def from_doc(cls, doc):
        """A grant read back from a run record, checked field by field."""
        if not isinstance(doc, dict) or set(doc) != set(cls.FIELDS):
            raise TrustRefused("a trust grant record holds exactly %s" % ", ".join(cls.FIELDS))
        for key in cls._BOOLS:
            if not isinstance(doc[key], bool):
                raise TrustRefused("trust grant %s is not a boolean" % key)
        for key in ("mechanism", "path", "granted_at"):
            if not isinstance(doc[key], str) or not doc[key]:
                raise TrustRefused("trust grant %s is not a string" % key)
        for key in ("config", "marker"):
            value = doc[key]
            if value is not None and not (isinstance(value, str) and os.path.isabs(value)):
                raise TrustRefused("trust grant %s is not an absolute path" % key)
        if not os.path.isabs(doc["path"]) or _key_problem(doc["path"]):
            raise TrustRefused("trust grant path %r is not one a grant writes" % doc["path"])
        return cls(**doc)


class Revoked(object):
    """What a revoke did: ``status`` (one of the module's status words), ``warning`` (empty
    when there is nothing to say), ``revoked_at`` (for ``exec.trustRevokedAt``)."""

    def __init__(self, status, warning=""):
        self.status = status
        self.warning = warning
        self.revoked_at = el.now()


def _mechanism(mechanism, config):
    """``True`` when ``mechanism`` writes ``config``; refuses a mechanism with no arm."""
    if mechanism in NO_FILE:
        return False
    if mechanism != USER_CONFIG_ENTRY:
        raise TrustRefused("trust_grant %r has no engine arm yet (REQ-662 stage 1 writes %s "
                           "only)" % (mechanism, USER_CONFIG_ENTRY))
    if not isinstance(config, str) or not os.path.isabs(config):
        raise TrustRefused("trust_grant %s needs the user config as an absolute path, not %r"
                           % (USER_CONFIG_ENTRY, config))
    return True


def preflight(mechanism, config, marker):
    """Refuse before any working copy is made: the marker, the mechanism, and a trust
    file the grant could not edit (a symlink, a hard link, not UTF-8, or a construct
    ``toml_merge.scan`` will not classify). Writes nothing."""
    refuse_while_probe_recovers(marker)
    if not _mechanism(mechanism, config):
        return
    if _lstat_file(config) is not None:
        _scan(config, _read(config))


def grant(mechanism, config, path, root, marker, timeout=LOCK_TIMEOUT_S):
    """Trust ``path`` for one run, and return the :class:`Grant` revoke needs.

    ``config`` is :func:`user_config_path`'s answer, ``root`` the run's working-copy
    root, ``marker`` :func:`probe_marker`'s answer. A mechanism in :data:`NO_FILE`
    writes nothing. Raises :class:`TrustRefused`, having written nothing, on a bad path,
    a recovery marker, a lock it cannot take, or a trust file it will not edit.
    """
    refuse_while_probe_recovers(marker)
    writes = _mechanism(mechanism, config)
    resolved = check_path(path, root)
    if not writes:
        return Grant(mechanism, None, resolved, marker=marker)
    os.makedirs(os.path.dirname(config), mode=0o700, exist_ok=True)
    with lock(config, timeout):
        refuse_while_probe_recovers(marker)
        st = _lstat_file(config)
        text = _read(config) if st is not None else ""
        block = trust_block(resolved)
        state = _entry(_scan(config, text), resolved)
        if state == "trusted":
            # The same bytes a grant writes: a killed run's block, which this run removes.
            adopted = text.count(block) == 1
            return Grant(mechanism, config, resolved, pre_existing=not adopted,
                         adopted=adopted, marker=marker)
        if state is not None:
            raise TrustRefused("%s already holds %s for %s: the grant does not edit an "
                               "operator's entry" % (config, state, resolved))
        newline_added = bool(text) and not text.endswith("\n")
        new = text + ("\n" if newline_added else "") + block
        if _entry(_scan(config, new), resolved) != "trusted":
            raise TrustRefused("the grant's own output for %s does not read back as trusted"
                               % config)
        _replace(config, new, st)
    return Grant(mechanism, config, resolved, newline_added=newline_added,
                 created=st is None, marker=marker)


def _ends_table(rest):
    """True when the block's table ends where its bytes end: what follows opens another
    table, or is only blank and comment lines. A key there would belong to the block's
    table, and removing the header would move it into the table above."""
    for line in rest.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped.startswith("[")
    return True


def revoke(grant, timeout=LOCK_TIMEOUT_S):
    """Remove exactly the block ``grant`` wrote; safe to call again, and after a kill.

    Returns :class:`Revoked`. A block already gone, or edited since the grant, leaves
    the file as it is and says so in ``warning``. Raises :class:`TrustRefused` only when
    the file cannot be edited safely (the lock, a symlink, not UTF-8).
    """
    if grant.config is None:
        return Revoked(NO_FILE_STATUS)
    if grant.pre_existing:
        return Revoked(PRE_EXISTING)
    config = grant.config
    note = ""
    if grant.marker and os.path.lexists(grant.marker):
        note = (" REQ-664's recovery marker %s appeared during the run: its whole-file "
                "restore may bring the block back" % grant.marker)
    block = trust_block(grant.path)
    if not os.path.isdir(os.path.dirname(config)):
        return Revoked(GONE, "%s is gone, and the trust block for %s with it.%s"
                       % (config, grant.path, note))
    with lock(config, timeout):
        st = _lstat_file(config)
        if st is None:
            return Revoked(GONE, "%s is gone, and the trust block for %s with it.%s"
                           % (config, grant.path, note))
        text = _read(config)
        count = text.count(block)
        at = text.find(block)
        end = at + len(block)
        if count == 1 and _ends_table(text[end:]):
            if grant.newline_added and end == len(text) and text[at - 1:at] == "\n":
                at -= 1
            new = text[:at] + text[end:]
            if new == "" and grant.created:
                os.remove(config)
            else:
                _replace(config, new, st)
            return Revoked(REVOKED, note.strip())
    header = '[projects."%s"]' % grant.path
    if count or (BLOCK_COMMENT in text and header in text):
        return Revoked(EDITED, "the trust block for %s in %s was edited since the grant and "
                       "is left as it is, so the path may still be trusted; remove %s by "
                       "hand if it should not be.%s" % (grant.path, config, header, note))
    return Revoked(GONE, "the trust block for %s was already gone from %s.%s"
                   % (grant.path, config, note))

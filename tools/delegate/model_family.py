"""The closed ``ModelFamily`` enum (REQ-722 BR-2, BR-3, ADR-2).

A model family is **declared**, never inferred. The toolkit compares two declared
values for equality and nothing else: it does not read a family out of a model
name, an endpoint URL or a harness name, because a harness can run more than one
family (Copilot CLI and Cursor serve both Anthropic and OpenAI models) and a
model name is whatever a provider chose to call it this month.

``unknown`` is the value for "cannot be established". It is a member, so a
config or an adapter can say it out loud, and it never counts as differing from
anything: a wrong ``unknown`` costs one cross-family review, while a wrong family
claim would label a single-family review cross-family, which is the failure
REQ-722 exists to prevent.

Defined once, here. The delegate config loader (``_machine_config``) and the
harness adapter loader both read it. Standard library only, and no PyYAML
import, so the system ``python3`` can load it (REQ-722 ASSUME-003).
"""

#: The closed enum. Adding a member is a schema change: the README's
#: ``delegate:`` table, the differential oracle and the harness adapters all
#: read this set.
MODEL_FAMILIES = (
    "anthropic", "openai", "moonshot", "google", "meta", "other", "unknown",
)

#: The member meaning "cannot be established" (REQ-722 BR-3).
UNKNOWN = "unknown"


def parse_family(value):
    """Return ``value`` when it is exactly a member of :data:`MODEL_FAMILIES`.

    Raises ``ValueError`` for anything else: a non-string, a case variant
    (``Anthropic``), a padded string, a model name (``kimi-k2.6``), or a string
    that merely contains a member (``openai-compatible``). There is no case
    folding and no substring match, because either would be inference (BR-2).

    The message names the allowed values and never the rejected one: a caller
    may be reading a governance file whose reasons carry no file content
    (``_machine_config``'s contract).
    """
    if not isinstance(value, str) or value not in MODEL_FAMILIES:
        raise ValueError("not a model family: expected exactly one of %s"
                         % ", ".join(MODEL_FAMILIES))
    return value


def families_differ(a, b):
    """True only when ``a`` and ``b`` are two different known families.

    ``False`` whenever either side is ``unknown`` (BR-3), so an unestablished
    family can never make a review count as cross-family. Both sides go through
    :func:`parse_family` first, so a value outside the enum raises
    ``ValueError`` rather than comparing unequal to everything and reading as a
    difference.
    """
    a = parse_family(a)
    b = parse_family(b)
    if a == UNKNOWN or b == UNKNOWN:
        return False
    return a != b

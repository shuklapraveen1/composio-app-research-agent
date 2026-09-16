"""Deterministic identifier generation.

An app's id is a function of its name alone, so the same source list always
yields the same ids regardless of row order, and a re-export of the list with
rows shuffled does not invalidate previously published data.

Where two different names slugify to the same value, both ids are disambiguated
with a short stable digest of the original name. Identical names are not
disambiguated: they are a duplicate, and duplicates are reported rather than
papered over.
"""

import re
import unicodedata
from typing import Dict, Iterable, List, Sequence, Tuple

from ..determinism import fingerprint

#: Length of the digest appended when two distinct names collide.
DISAMBIGUATOR_LENGTH = 6

_SEPARATORS = re.compile(r"[\s_/\\.,:;|+]+")
_INVALID = re.compile(r"[^a-z0-9-]+")
_DASHES = re.compile(r"-{2,}")

#: Expansions applied before slugging so "Notes & Tasks" and "Notes and Tasks"
#: do not produce different ids.
_REPLACEMENTS = (
    ("&", " and "),
    ("@", " at "),
    ("#", " sharp "),
)

#: Dropped before Unicode normalization, which would otherwise expand them into
#: letters and turn "Qualtrics XM™" into "qualtrics-xmtm".
_DROPPED_MARKS = "\u2122\u00ae\u00a9\u2120"


def _strip_marks(text: str) -> str:
    return "".join(char for char in text if char not in _DROPPED_MARKS)


def slugify(text: str) -> str:
    """Convert arbitrary text into a stable lowercase slug.

    Accents are folded rather than dropped, so "Qualtrics XM" and "Qualtrícs XM"
    do not silently become different apps.
    """
    if not text or not text.strip():
        raise ValueError("cannot slugify empty text")

    value = unicodedata.normalize("NFKD", _strip_marks(text.strip()))
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower()
    for needle, replacement in _REPLACEMENTS:
        value = value.replace(needle, replacement)
    value = _SEPARATORS.sub("-", value)
    value = _INVALID.sub("-", value)
    value = _DASHES.sub("-", value).strip("-")

    if not value:
        raise ValueError("text has no slug-safe characters: {!r}".format(text))
    return value


def normalize_name(text: str) -> str:
    """Casefold a name for comparison. Used for duplicate detection only."""
    value = unicodedata.normalize("NFKD", _strip_marks(text.strip()))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value).casefold()


def generate_ids(names: Sequence[str]) -> Dict[int, str]:
    """Assign an id to each name, keyed by its position in ``names``.

    Position is used only to key the result; the id itself never depends on it.
    """
    slugs: List[Tuple[int, str, str]] = []
    for index, name in enumerate(names):
        slugs.append((index, name, slugify(name)))

    by_slug: Dict[str, List[Tuple[int, str]]] = {}
    for index, name, slug in slugs:
        by_slug.setdefault(slug, []).append((index, name))

    assigned: Dict[int, str] = {}
    for slug, entries in by_slug.items():
        distinct_names = {normalize_name(name) for _, name in entries}
        if len(entries) == 1 or len(distinct_names) == 1:
            # A single app, or genuine duplicates that the caller will report.
            for index, _ in entries:
                assigned[index] = slug
        else:
            for index, name in entries:
                assigned[index] = "{}-{}".format(
                    slug, fingerprint(normalize_name(name), DISAMBIGUATOR_LENGTH)
                )
    return assigned


def generate_category_ids(categories: Iterable[str]) -> Dict[str, str]:
    """Map each supplied category name to a stable id."""
    mapping: Dict[str, str] = {}
    seen: Dict[str, str] = {}
    for category in categories:
        if category in mapping:
            continue
        slug = slugify(category)
        if slug in seen and seen[slug] != category:
            slug = "{}-{}".format(
                slug, fingerprint(normalize_name(category), DISAMBIGUATOR_LENGTH)
            )
        seen[slug] = category
        mapping[category] = slug
    return mapping

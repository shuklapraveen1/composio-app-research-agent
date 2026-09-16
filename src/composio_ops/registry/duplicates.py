"""Duplicate detection over the supplied app list.

Duplicates are reported, never merged or silently renamed: two rows for the
same product is a defect in the input that a human should see and resolve.
"""

from typing import Dict, List, Sequence
from urllib.parse import urlsplit

from ..schemas.registry import DuplicateGroup, RawAppRecord
from .ids import normalize_name, slugify


def _canonical_url(url: str) -> str:
    """Reduce a URL to host plus path, so trivial variants compare equal."""
    parsed = urlsplit(url.strip().lower())
    host = parsed.netloc or parsed.path
    host = host.split("@")[-1]
    if host.startswith("www."):
        host = host[4:]
    host = host.rstrip("/")
    path = (parsed.path if parsed.netloc else "").rstrip("/")
    return host + path


def find_duplicates(
    records: Sequence[RawAppRecord], urls: Dict[int, str] = None
) -> List[DuplicateGroup]:
    """Return every group of source rows that look like the same application.

    Three independent signals are checked: an identical normalized name, an
    identical slug (which catches punctuation-only differences), and an
    identical homepage URL.
    """
    urls = urls or {}
    groups: List[DuplicateGroup] = []

    by_name: Dict[str, List[int]] = {}
    by_slug: Dict[str, List[int]] = {}
    by_url: Dict[str, List[int]] = {}

    for record in records:
        by_name.setdefault(normalize_name(record.name), []).append(record.source_index)
        try:
            by_slug.setdefault(slugify(record.name), []).append(record.source_index)
        except ValueError:
            pass
        raw_url = urls.get(record.source_index)
        if raw_url and raw_url.strip():
            by_url.setdefault(_canonical_url(raw_url), []).append(record.source_index)

    name_duplicates = {
        key: indexes for key, indexes in by_name.items() if len(indexes) > 1
    }
    for key in sorted(name_duplicates):
        groups.append(
            DuplicateGroup(
                reason="identical_name", key=key, source_indexes=name_duplicates[key]
            )
        )

    already = {tuple(sorted(indexes)) for indexes in name_duplicates.values()}

    for key in sorted(by_slug):
        indexes = by_slug[key]
        if len(indexes) > 1 and tuple(sorted(indexes)) not in already:
            groups.append(
                DuplicateGroup(reason="identical_slug", key=key, source_indexes=indexes)
            )
            already.add(tuple(sorted(indexes)))

    for key in sorted(by_url):
        indexes = by_url[key]
        if len(indexes) > 1 and tuple(sorted(indexes)) not in already:
            groups.append(
                DuplicateGroup(
                    reason="identical_homepage_url", key=key, source_indexes=indexes
                )
            )
            already.add(tuple(sorted(indexes)))

    return groups


def describe(groups: Sequence[DuplicateGroup]) -> str:
    """One-line human summary of a duplicate report."""
    return "; ".join(
        "{} rows {} ({})".format(group.reason, group.source_indexes, group.key)
        for group in groups
    )

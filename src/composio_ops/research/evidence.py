"""Turning corpus sources into evidence items, and indexing them by field.

Evidence ids are derived from the app id and the source id rather than
generated, so the same corpus always produces the same ids and a classified
value can be traced to its source across runs.
"""

from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence

from .. import constants as C
from ..schemas.corpus import CorpusEntry, CorpusSource
from ..schemas.evidence import EvidenceItem, domain_of
from ..taxonomy import FIRST_PARTY_SOURCE_TYPES, ResearchFieldName, SourceType

#: Fields that are concluded from other fields rather than read off a page. They
#: cite the evidence behind the fields they were derived from.
DERIVED_FIELDS = (
    ResearchFieldName.BUILDABILITY,
    ResearchFieldName.BLOCKER,
)


def evidence_id_for(app_id: str, source_id: str) -> str:
    """Stable evidence id: ``<app_id>::<source_id>``."""
    return "{}::{}".format(app_id, source_id)


def build_evidence(
    entry: CorpusEntry,
    captured_at: datetime,
    retrieval: C.EvidenceRetrieval = C.EvidenceRetrieval.CITED,
    channel: C.Channel = C.Channel.CHANNEL_A,
) -> List[EvidenceItem]:
    """One evidence item per corpus source, sorted by evidence id."""
    items = [
        EvidenceItem(
            evidence_id=evidence_id_for(entry.app_id, source.id),
            app_id=entry.app_id,
            url=source.url,
            title=source.title,
            domain=domain_of(source.url),
            source_type=source.type,
            claim=source.claim,
            excerpt=source.excerpt,
            retrieval=retrieval,
            supports=list(source.supports),
            channel=channel,
            captured_at=captured_at,
            notes=None if source.current else "Source currency could not be established.",
        )
        for source in entry.sources
    ]
    return sorted(items, key=lambda item: item.evidence_id)


class EvidenceIndex:
    """Lookup from a researched field to the evidence that backs it."""

    def __init__(self, items: Sequence[EvidenceItem]) -> None:
        self._items = list(items)
        self._by_field: Dict[ResearchFieldName, List[str]] = {}
        for item in self._items:
            for field in item.supports:
                self._by_field.setdefault(field, []).append(item.evidence_id)
        for ids in self._by_field.values():
            ids.sort()

    @classmethod
    def from_entry(
        cls, entry: CorpusEntry, captured_at: datetime
    ) -> "EvidenceIndex":
        return cls(build_evidence(entry, captured_at=captured_at))

    @property
    def items(self) -> List[EvidenceItem]:
        return list(self._items)

    def for_field(self, field: ResearchFieldName) -> List[str]:
        """Evidence ids whose source declares support for ``field``."""
        return list(self._by_field.get(field, []))

    def for_fields(self, fields: Iterable[ResearchFieldName]) -> List[str]:
        """Union of the evidence behind several fields, for derived conclusions."""
        collected: set = set()
        for field in fields:
            collected.update(self._by_field.get(field, []))
        return sorted(collected)

    def primary(self) -> Optional[str]:
        """The most authoritative single source: first-party docs if there is one."""
        for preferred in (
            SourceType.FIRST_PARTY_DOCS,
            SourceType.FIRST_PARTY_SITE,
            SourceType.FIRST_PARTY_PRICING,
            SourceType.FIRST_PARTY_CHANGELOG,
            SourceType.REPOSITORY,
            SourceType.REGISTRY_LISTING,
            SourceType.THIRD_PARTY,
        ):
            matches = sorted(
                item.evidence_id for item in self._items if item.source_type is preferred
            )
            if matches:
                return matches[0]
        return None

    def with_fallback(self, field: ResearchFieldName) -> List[str]:
        """Evidence for ``field``, falling back to the primary source.

        The fallback exists for fields every source implicitly speaks to, such as
        identity: a vendor's own API reference establishes which product is being
        described even when it does not carry an explicit ``identity`` support tag.
        """
        direct = self.for_field(field)
        if direct:
            return direct
        primary = self.primary()
        return [primary] if primary else []

    def first_party_ids(self) -> List[str]:
        return sorted(
            item.evidence_id
            for item in self._items
            if item.source_type in FIRST_PARTY_SOURCE_TYPES
        )

    def has_source_type(self, source_type: SourceType) -> bool:
        return any(item.source_type is source_type for item in self._items)

    def has_current_source(self) -> bool:
        """True when at least one source was recorded as current."""
        return any(
            (item.notes or "") != "Source currency could not be established."
            for item in self._items
        )

    def has_page_level_evidence(self) -> bool:
        return any(item.is_page_level for item in self._items)

    def __len__(self) -> int:
        return len(self._items)

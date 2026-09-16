"""Evidence schemas.

Evidence is the unit that makes "evidence before conclusions" enforceable: a
classified value may only exist if it points at evidence items recorded here,
each with a retrievable source, the fields it supports, and the time it was
captured.

Implements architecture section 5.2. ``supports`` is the link that lets a
reviewer walk from a final classification back to the documentation page that
produced it.
"""

from typing import List, Optional
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from .. import constants as C
from ..taxonomy import (
    FIRST_PARTY_SOURCE_TYPES,
    ResearchFieldName,
    SourceType,
)
from .base import AppId, ArtifactMetadata, NonEmptyStr, StrictModel, UtcDatetime


def domain_of(url: str) -> str:
    """Registered host of a URL, lowercased and stripped of ``www.``."""
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


class EvidenceItem(StrictModel):
    """A single supporting observation, tied to the fields it supports."""

    evidence_id: NonEmptyStr
    app_id: AppId
    url: NonEmptyStr
    title: NonEmptyStr
    domain: NonEmptyStr
    source_type: SourceType
    #: What the source says, in the source's own terms.
    claim: NonEmptyStr
    #: Verbatim text from the page. Absent when the page was not fetched in this
    #: run; ``retrieval`` records which of the two happened.
    excerpt: Optional[str] = None
    retrieval: C.EvidenceRetrieval
    supports: List[ResearchFieldName] = Field(min_length=1)
    channel: C.Channel = C.Channel.CHANNEL_A
    captured_at: UtcDatetime
    notes: Optional[str] = None

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("evidence url must be an http(s) URL")
        return value

    @field_validator("supports")
    @classmethod
    def _dedupe_supports(cls, value: List[ResearchFieldName]) -> List[ResearchFieldName]:
        return sorted(set(value), key=lambda item: item.value)

    @model_validator(mode="after")
    def _check_domain(self) -> "EvidenceItem":
        actual = domain_of(self.url)
        if not actual:
            raise ValueError("evidence url has no host")
        if self.domain != actual:
            raise ValueError(
                "domain '{}' does not match the url host '{}'".format(
                    self.domain, actual
                )
            )
        if self.retrieval is C.EvidenceRetrieval.FETCHED and not (self.excerpt or "").strip():
            raise ValueError("a fetched evidence item must carry the excerpt it fetched")
        return self

    @property
    def is_first_party(self) -> bool:
        return self.source_type in FIRST_PARTY_SOURCE_TYPES

    @property
    def is_page_level(self) -> bool:
        """True when the page itself was read, rather than cited from a corpus."""
        return self.retrieval is C.EvidenceRetrieval.FETCHED


class EvidenceSet(StrictModel):
    """All evidence gathered for the registry, keyed by evidence id."""

    metadata: ArtifactMetadata
    items: List[EvidenceItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_items(self) -> "EvidenceSet":
        if self.metadata.record_count != len(self.items):
            raise ValueError("metadata.record_count does not match the number of items")
        ids = [item.evidence_id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("evidence_id values must be unique")
        if ids != sorted(ids):
            raise ValueError("items must be sorted by evidence_id for canonical output")
        return self

    def ids(self) -> set:
        return {item.evidence_id for item in self.items}

    def for_app(self, app_id: str) -> List[EvidenceItem]:
        return [item for item in self.items if item.app_id == app_id]

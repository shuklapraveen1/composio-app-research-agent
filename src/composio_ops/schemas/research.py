"""The per-application research record. Architecture section 5.1.

Each researched field is wrapped rather than stored bare, so a value can never
appear without its status and its evidence. That wrapper is what makes the
architecture's rules mechanical instead of aspirational:

* a conclusion must cite evidence,
* "not found" is never silently rendered as ``false`` or ``none``, and
* "not applicable" must justify itself in prose.

Confidence sits on the record, not on the field, and is computed by
:mod:`composio_ops.research.confidence` from the inputs recorded here. A model
never gets to declare its own confidence.

Nothing here encodes a finding about any application.
"""

from typing import Generic, List, Optional, Sequence, Tuple, TypeVar, Union

from pydantic import Field, field_validator, model_validator

from .. import constants as C
from ..taxonomy import (
    EVIDENCE_BEARING_STATUSES,
    RATIONALE_REQUIRED_STATUSES,
    AccessRestriction,
    ApiBreadth,
    ApiCapability,
    ApiType,
    ApplicationType,
    AuthMethod,
    Blocker,
    Buildability,
    CredentialAccess,
    Dimension,
    McpMaintenance,
    McpStatus,
    RateLimitInfo,
    ResearchFieldName,
    ResolutionStatus,
    WebhookSupport,
)
from .base import AppId, ArtifactMetadata, NonEmptyStr, StrictModel, UtcDatetime

T = TypeVar("T")

#: Canonical comparable form of a field's value: ``None`` for an unresolved
#: field, a string for a single value, a tuple of strings for a multi-valued one.
FieldKey = Union[None, str, Tuple[str, ...]]


def _value_token(value: object) -> str:
    """Stable string for an enum member, a bool, or plain text."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(getattr(value, "value", value))


class _FieldBase(StrictModel):
    """Status, evidence, and rationale shared by single- and multi-valued fields."""

    status: ResolutionStatus
    evidence_ids: List[str] = Field(default_factory=list)
    rationale: Optional[str] = None

    @field_validator("evidence_ids")
    @classmethod
    def _clean_evidence_ids(cls, value: List[str]) -> List[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("evidence_ids must be unique")
        return sorted(cleaned)

    def _check_common(self) -> None:
        if self.status in EVIDENCE_BEARING_STATUSES and not self.evidence_ids:
            raise ValueError(
                "status '{}' asserts a finding and must cite evidence".format(
                    self.status.value
                )
            )
        if self.status in RATIONALE_REQUIRED_STATUSES and not (self.rationale or "").strip():
            raise ValueError("status '{}' requires a rationale".format(self.status.value))

    @property
    def is_resolved(self) -> bool:
        return self.status is ResolutionStatus.RESOLVED

    @property
    def is_known(self) -> bool:
        """True when the field asserts something, including a definite absence."""
        return self.status in EVIDENCE_BEARING_STATUSES

    def key(self) -> FieldKey:
        raise NotImplementedError


class ResearchField(_FieldBase, Generic[T]):
    """A single-valued researched field."""

    value: Optional[T] = None

    @model_validator(mode="after")
    def _check_value(self) -> "ResearchField":
        self._check_common()
        if self.status is ResolutionStatus.RESOLVED:
            if self.value is None:
                raise ValueError("a resolved field must carry a value")
        elif self.value is not None:
            raise ValueError(
                "status '{}' must not carry a value".format(self.status.value)
            )
        return self

    def key(self) -> FieldKey:
        if self.status is not ResolutionStatus.RESOLVED or self.value is None:
            return None
        return _value_token(self.value)

    @classmethod
    def resolved(
        cls,
        value: T,
        evidence_ids: Sequence[str],
        rationale: Optional[str] = None,
    ) -> "ResearchField":
        return cls(
            status=ResolutionStatus.RESOLVED,
            value=value,
            evidence_ids=list(evidence_ids),
            rationale=rationale,
        )

    @classmethod
    def unavailable(
        cls, evidence_ids: Sequence[str], rationale: str
    ) -> "ResearchField":
        """The capability was established not to exist."""
        return cls(
            status=ResolutionStatus.UNAVAILABLE,
            evidence_ids=list(evidence_ids),
            rationale=rationale,
        )

    @classmethod
    def not_found(cls, rationale: str) -> "ResearchField":
        """Searched, nothing found. Record where you looked."""
        return cls(status=ResolutionStatus.NOT_FOUND, rationale=rationale)

    @classmethod
    def unclear(
        cls, rationale: str, evidence_ids: Sequence[str] = ()
    ) -> "ResearchField":
        """Sources conflict or are too vague to conclude."""
        return cls(
            status=ResolutionStatus.UNCLEAR,
            evidence_ids=list(evidence_ids),
            rationale=rationale,
        )

    @classmethod
    def not_applicable(cls, rationale: str) -> "ResearchField":
        """The question does not apply. Must say why."""
        return cls(status=ResolutionStatus.NOT_APPLICABLE, rationale=rationale)


class MultiResearchField(_FieldBase, Generic[T]):
    """A multi-valued researched field: a deduplicated, ordered set of values."""

    values: List[T] = Field(default_factory=list)

    @field_validator("values")
    @classmethod
    def _dedupe_and_sort(cls, value: List[T]) -> List[T]:
        seen: List[T] = []
        for item in value:
            if item not in seen:
                seen.append(item)
        return sorted(seen, key=_value_token)

    @model_validator(mode="after")
    def _check_values(self) -> "MultiResearchField":
        self._check_common()
        if self.status is ResolutionStatus.RESOLVED:
            if not self.values:
                raise ValueError("a resolved multi-valued field must carry values")
        elif self.values:
            raise ValueError(
                "status '{}' must not carry values".format(self.status.value)
            )
        return self

    def key(self) -> FieldKey:
        if self.status is not ResolutionStatus.RESOLVED:
            return None
        return tuple(_value_token(item) for item in self.values)

    @classmethod
    def resolved(
        cls,
        values: Sequence[T],
        evidence_ids: Sequence[str],
        rationale: Optional[str] = None,
    ) -> "MultiResearchField":
        return cls(
            status=ResolutionStatus.RESOLVED,
            values=list(values),
            evidence_ids=list(evidence_ids),
            rationale=rationale,
        )

    @classmethod
    def unavailable(
        cls, evidence_ids: Sequence[str], rationale: str
    ) -> "MultiResearchField":
        return cls(
            status=ResolutionStatus.UNAVAILABLE,
            evidence_ids=list(evidence_ids),
            rationale=rationale,
        )

    @classmethod
    def not_found(cls, rationale: str) -> "MultiResearchField":
        return cls(status=ResolutionStatus.NOT_FOUND, rationale=rationale)

    @classmethod
    def unclear(
        cls, rationale: str, evidence_ids: Sequence[str] = ()
    ) -> "MultiResearchField":
        return cls(
            status=ResolutionStatus.UNCLEAR,
            evidence_ids=list(evidence_ids),
            rationale=rationale,
        )

    @classmethod
    def not_applicable(cls, rationale: str) -> "MultiResearchField":
        return cls(status=ResolutionStatus.NOT_APPLICABLE, rationale=rationale)


class AppIdentity(StrictModel):
    """Which real product the supplied name refers to."""

    canonical_name: NonEmptyStr
    vendor: Optional[str] = None
    homepage_url: Optional[str] = None
    docs_url: Optional[str] = None

    @field_validator("homepage_url", "docs_url")
    @classmethod
    def _check_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if not cleaned.startswith(("http://", "https://")):
            raise ValueError("url must be an http(s) URL")
        return cleaned

    def __str__(self) -> str:
        return self.canonical_name


class McpDetails(StrictModel):
    """Provenance and upkeep of the MCP server, when one exists. Section 6.6."""

    official: bool
    maintained: McpMaintenance
    source_url: Optional[str] = None

    @field_validator("source_url")
    @classmethod
    def _check_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        if not value.startswith(("http://", "https://")):
            raise ValueError("source_url must be an http(s) URL")
        return value.strip()


class BuildabilityAssessment(StrictModel):
    """The three legs of the buildability decision tree. Section 8."""

    technical_feasibility: Dimension
    credential_accessibility: Dimension
    commercial_accessibility: Dimension
    reason: NonEmptyStr


class Contradiction(StrictModel):
    """A conflict the pipeline detected, either between sources or within a record."""

    kind: NonEmptyStr
    fields: List[ResearchFieldName] = Field(min_length=1)
    detail: NonEmptyStr

    @field_validator("fields")
    @classmethod
    def _sorted(cls, value: List[ResearchFieldName]) -> List[ResearchFieldName]:
        return sorted(set(value), key=lambda item: item.value)


class ConfidenceInputs(StrictModel):
    """The deterministic inputs to the confidence function. Section 7.

    The research layer supplies facts; :func:`composio_ops.research.confidence.
    calculate` turns them into a level. The model never writes ``confidence``.
    """

    identity_resolved: bool
    has_first_party_source: bool
    has_critical_field_evidence: bool
    has_contradiction: bool
    source_count: int = Field(ge=0)
    has_page_level_evidence: bool
    has_current_source: bool
    has_explicit_documentation: bool
    has_unresolved_ambiguity: bool


class VerificationState(StrictModel):
    """What verification, if any, this record has been through. Section 5.1."""

    status: C.VerificationStatus = C.VerificationStatus.NOT_SELECTED
    channels: List[C.Channel] = Field(default_factory=list)
    sample: Optional[C.SampleGroup] = None
    discrepancies: List[ResearchFieldName] = Field(default_factory=list)
    corrected: bool = False
    triggers: List[C.ReviewTrigger] = Field(default_factory=list)
    notes: Optional[str] = None

    @field_validator("channels")
    @classmethod
    def _dedupe_channels(cls, value: List[C.Channel]) -> List[C.Channel]:
        return sorted(set(value), key=lambda item: item.value)

    @field_validator("discrepancies")
    @classmethod
    def _dedupe_fields(cls, value: List[ResearchFieldName]) -> List[ResearchFieldName]:
        return sorted(set(value), key=lambda item: item.value)

    @field_validator("triggers")
    @classmethod
    def _dedupe_triggers(cls, value: List[C.ReviewTrigger]) -> List[C.ReviewTrigger]:
        return sorted(set(value), key=lambda item: item.value)

    @model_validator(mode="after")
    def _check_consistency(self) -> "VerificationState":
        sampled = [channel for channel in self.channels if channel in C.SAMPLED_CHANNELS]
        if sampled and self.sample is None and not self.triggers:
            raise ValueError(
                "verification channels run over sampled or trigger-reviewed records only"
            )
        if self.corrected and self.status is not C.VerificationStatus.CORRECTED:
            raise ValueError("a corrected record must carry the 'corrected' status")
        if self.discrepancies and not self.channels:
            raise ValueError("a discrepancy requires the channel that found it")
        return self

    @property
    def was_verified(self) -> bool:
        return bool(self.channels)


class AppResearchRecord(StrictModel):
    """Everything Channel A concluded about one app, field by field.

    ``category_id`` is carried over from the registry rather than researched:
    the category is supplied input data.
    """

    app_id: AppId
    app: NonEmptyStr
    category_id: NonEmptyStr
    channel: C.Channel = C.Channel.CHANNEL_A
    provider: C.ResearchProvider
    classifier_version: NonEmptyStr
    generated_at: UtcDatetime

    identity: ResearchField[AppIdentity]
    description: ResearchField[str]
    application_type: ResearchField[ApplicationType]
    authentication: MultiResearchField[AuthMethod]
    credential_access: ResearchField[CredentialAccess]
    access_restrictions: MultiResearchField[AccessRestriction]
    api_exists: ResearchField[bool]
    api_types: MultiResearchField[ApiType]
    api_breadth: ResearchField[ApiBreadth]
    api_capabilities: MultiResearchField[ApiCapability]
    mcp: ResearchField[McpStatus]
    webhook_support: ResearchField[WebhookSupport]
    rate_limit_info: ResearchField[RateLimitInfo]
    buildability: ResearchField[Buildability]
    blocker: MultiResearchField[Blocker]

    mcp_details: Optional[McpDetails] = None
    buildability_assessment: BuildabilityAssessment
    api_notes: Optional[str] = None
    access_notes: Optional[str] = None

    confidence: C.Confidence
    confidence_inputs: ConfidenceInputs
    contradictions: List[Contradiction] = Field(default_factory=list)

    verification: VerificationState = Field(default_factory=VerificationState)
    notes: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_cross_field(self) -> "AppResearchRecord":
        if self.mcp_details is not None and not self.mcp.is_resolved:
            raise ValueError("mcp_details requires a resolved mcp status")
        if self.mcp.is_resolved and self.mcp_details is None:
            raise ValueError("a resolved mcp status must record its provenance")
        if self.mcp_details is not None:
            official_statuses = (McpStatus.OFFICIAL, McpStatus.MULTIPLE)
            if self.mcp_details.official and self.mcp.value not in official_statuses:
                raise ValueError(
                    "mcp_details.official contradicts mcp status '{}'".format(
                        _value_token(self.mcp.value)
                    )
                )
            if not self.mcp_details.official and self.mcp.value is McpStatus.OFFICIAL:
                raise ValueError("an official mcp status must be marked official")
        if self.confidence_inputs.has_contradiction != bool(self.contradictions):
            raise ValueError(
                "confidence_inputs.has_contradiction must match the recorded contradictions"
            )
        return self

    def field(self, name: ResearchFieldName) -> _FieldBase:
        """Return one researched field by its taxonomy name."""
        return getattr(self, name.value)

    def fields(self) -> List[Tuple[ResearchFieldName, _FieldBase]]:
        """All researched fields as ``(name, field)`` pairs, in taxonomy order."""
        return [(name, self.field(name)) for name in ResearchFieldName]

    def evidence_ids(self) -> set:
        ids = set()
        for _, field in self.fields():
            ids.update(field.evidence_ids)
        return ids

    def status_counts(self) -> dict:
        counts = {status.value: 0 for status in ResolutionStatus}
        for _, field in self.fields():
            counts[field.status.value] += 1
        return counts


class ResearchSet(StrictModel):
    """Channel A output for the whole registry, one record per app."""

    metadata: ArtifactMetadata
    records: List[AppResearchRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_records(self) -> "ResearchSet":
        if self.metadata.record_count != len(self.records):
            raise ValueError("metadata.record_count does not match the number of records")
        app_ids = [record.app_id for record in self.records]
        if len(set(app_ids)) != len(app_ids):
            raise ValueError("app_id values must be unique")
        if app_ids != sorted(app_ids):
            raise ValueError("records must be sorted by app_id for canonical output")
        return self

    def record_for(self, app_id: str) -> Optional[AppResearchRecord]:
        for record in self.records:
            if record.app_id == app_id:
                return record
        return None

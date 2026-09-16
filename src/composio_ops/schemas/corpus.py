"""The research corpus: what the sources say, before anything is concluded.

A corpus entry records observations, not classifications. It says "the docs list
these authentication mechanisms" and "the developer portal is reachable after a
free signup"; it does not say ``credential_access = self_serve_free``. Turning
observations into taxonomy values is the classifier's job, which is what makes
the classifier's rules auditable and improvable between Sample A and Sample B.

The corpus is also the seam at which the pipeline goes offline: with a research
provider configured, Channel A writes these entries from live tool calls; with
the ``corpus`` provider it replays the reviewed entries committed here. Either
way, everything downstream sees the same shape.
"""

from typing import Dict, List, Optional

from pydantic import Field, field_validator, model_validator

from ..taxonomy import (
    AccessRestriction,
    ApiCapability,
    ApiType,
    ApplicationType,
    AuthMethod,
    McpMaintenance,
    McpStatus,
    RateLimitInfo,
    ResearchFieldName,
    SourceType,
    WebhookSupport,
)
from .base import AppId, ArtifactMetadata, NonEmptyStr, StrictModel


class CorpusSource(StrictModel):
    """One documentation page, and what it was consulted for."""

    id: NonEmptyStr
    url: NonEmptyStr
    title: NonEmptyStr
    type: SourceType
    supports: List[ResearchFieldName] = Field(min_length=1)
    claim: NonEmptyStr
    excerpt: Optional[str] = None
    #: True when the page was published or last updated within the window the
    #: confidence function treats as current. Recorded by whoever captured it.
    current: bool = True

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("source url must be an http(s) URL")
        return value

    @field_validator("supports")
    @classmethod
    def _sorted(cls, value: List[ResearchFieldName]) -> List[ResearchFieldName]:
        return sorted(set(value), key=lambda item: item.value)


#: How an account is obtained, and which plan unlocks API access. Free text in
#: the corpus, closed here so a typo fails the load.
ACCOUNT_VALUES = ("free", "trial", "paid", "invite", "contact_sales")
API_PLAN_VALUES = ("free", "trial", "paid", "enterprise", "partner", "none")

#: Share of the documented product surface an API covers.
COVERAGE_VALUES = ("most", "major", "subset", "slice")


class AccessObservations(StrictModel):
    """How a developer would actually obtain credentials, as documented."""

    #: How an account is obtained: free, trial, paid, invite, contact_sales.
    account: NonEmptyStr = "free"
    #: Which plan unlocks API access: free, trial, paid, enterprise, partner,
    #: none. ``none`` means no plan grants it.
    api_plan: NonEmptyStr = "free"
    #: The vendor reviews or approves developer access before issuing credentials.
    approval_required: bool = False
    #: Credentials are only issued to members of a partner programme.
    partner_only: bool = False
    #: Only an account administrator can create the credential.
    admin_only: bool = False
    #: Credentials come from an instance the developer deploys themselves.
    self_hosted: bool = False
    restrictions: List[AccessRestriction] = Field(default_factory=list)

    @field_validator("account")
    @classmethod
    def _check_account(cls, value: str) -> str:
        if value not in ACCOUNT_VALUES:
            raise ValueError(
                "account must be one of {}".format(", ".join(ACCOUNT_VALUES))
            )
        return value

    @field_validator("api_plan")
    @classmethod
    def _check_plan(cls, value: str) -> str:
        if value not in API_PLAN_VALUES:
            raise ValueError(
                "api_plan must be one of {}".format(", ".join(API_PLAN_VALUES))
            )
        return value

    @field_validator("restrictions")
    @classmethod
    def _sorted(cls, value: List[AccessRestriction]) -> List[AccessRestriction]:
        return sorted(set(value), key=lambda item: item.value)


class ApiObservations(StrictModel):
    """What the developer documentation shows about the programmatic interface."""

    #: ``None`` when the corpus could not establish either way.
    exists: Optional[bool] = None
    documented: bool = True
    types: List[ApiType] = Field(default_factory=list)
    #: Top-level resource groups the reference documents, verbatim from its
    #: navigation. Drives the breadth classification; never invented.
    resource_groups: List[str] = Field(default_factory=list)
    #: True when the reference enumerates its resources well enough to count
    #: them. False means breadth cannot be read off the documentation.
    enumerated: bool = True
    capabilities: List[ApiCapability] = Field(default_factory=list)
    #: Share of the documented product surface the API covers, as judged from
    #: the reference: ``most``, ``major``, ``subset``, ``slice``.
    coverage: NonEmptyStr = "major"
    notes: Optional[str] = None

    @field_validator("coverage")
    @classmethod
    def _check_coverage(cls, value: str) -> str:
        if value not in COVERAGE_VALUES:
            raise ValueError(
                "coverage must be one of {}".format(", ".join(COVERAGE_VALUES))
            )
        return value

    @field_validator("types")
    @classmethod
    def _sorted_types(cls, value: List[ApiType]) -> List[ApiType]:
        return sorted(set(value), key=lambda item: item.value)

    @field_validator("capabilities")
    @classmethod
    def _sorted_caps(cls, value: List[ApiCapability]) -> List[ApiCapability]:
        return sorted(set(value), key=lambda item: item.value)

    @field_validator("resource_groups")
    @classmethod
    def _clean_groups(cls, value: List[str]) -> List[str]:
        return sorted({item.strip() for item in value if item.strip()})

    @model_validator(mode="after")
    def _check_consistency(self) -> "ApiObservations":
        if self.exists is False and (self.types or self.resource_groups):
            raise ValueError("an absent API cannot document types or resources")
        if self.exists and not self.types:
            raise ValueError("an API that exists must record at least one type")
        return self


class McpObservations(StrictModel):
    """What was found when looking for a Model Context Protocol server."""

    #: ``None`` when nothing was found. Distinct from "found nothing official".
    status: Optional[McpStatus] = None
    official: bool = False
    maintained: McpMaintenance = McpMaintenance.UNCLEAR
    source_url: Optional[str] = None
    #: The corpus looked and found nothing, as opposed to not having looked.
    searched: bool = True

    @model_validator(mode="after")
    def _check(self) -> "McpObservations":
        if self.status is None and self.source_url:
            raise ValueError("a source url implies a server was found")
        if self.status is McpStatus.OFFICIAL and not self.official:
            raise ValueError("an official server must be marked official")
        if self.status is McpStatus.THIRD_PARTY and self.official:
            raise ValueError("a third-party server is not official")
        return self


class CorpusEntry(StrictModel):
    """Everything the corpus records about one application."""

    app_id: AppId
    canonical_name: NonEmptyStr
    vendor: Optional[str] = None
    homepage_url: Optional[str] = None
    docs_url: Optional[str] = None
    description: NonEmptyStr
    application_type: ApplicationType
    #: False for tools with nothing to integrate against: no hosted service, no
    #: credentials, no API. Routes to "Not applicable" in the decision tree.
    integration_model: bool = True
    #: True when the supplied name does not resolve to a single product.
    identity_ambiguous: bool = False

    auth_methods: List[AuthMethod] = Field(default_factory=list)
    auth_notes: Optional[str] = None
    access: AccessObservations = Field(default_factory=AccessObservations)
    api: ApiObservations = Field(default_factory=ApiObservations)
    mcp: McpObservations = Field(default_factory=McpObservations)
    webhooks: Optional[WebhookSupport] = None
    rate_limits: Optional[RateLimitInfo] = None
    #: Observations that conflict with each other, recorded rather than resolved.
    conflicts: List[str] = Field(default_factory=list)
    sources: List[CorpusSource] = Field(min_length=1)
    notes: Optional[str] = None

    @field_validator("auth_methods")
    @classmethod
    def _sorted_auth(cls, value: List[AuthMethod]) -> List[AuthMethod]:
        return sorted(set(value), key=lambda item: item.value)

    @field_validator("homepage_url", "docs_url")
    @classmethod
    def _check_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        if not value.startswith(("http://", "https://")):
            raise ValueError("url must be an http(s) URL")
        return value.strip()

    @model_validator(mode="after")
    def _check_sources(self) -> "CorpusEntry":
        ids = [source.id for source in self.sources]
        if len(set(ids)) != len(ids):
            raise ValueError("source ids must be unique within an entry")
        if self.identity_ambiguous and self.application_type is not (
            ApplicationType.AMBIGUOUS_IDENTITY
        ):
            raise ValueError(
                "an ambiguous identity must carry the ambiguous_identity type"
            )
        return self

    def sources_for(self, field: ResearchFieldName) -> List[CorpusSource]:
        return [source for source in self.sources if field in source.supports]


class Corpus(StrictModel):
    """The whole corpus, assembled from the per-category files on disk."""

    metadata: ArtifactMetadata
    entries: List[CorpusEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_entries(self) -> "Corpus":
        if self.metadata.record_count != len(self.entries):
            raise ValueError("metadata.record_count does not match the number of entries")
        app_ids = [entry.app_id for entry in self.entries]
        if len(set(app_ids)) != len(app_ids):
            raise ValueError("app_id values must be unique across the corpus")
        if app_ids != sorted(app_ids):
            raise ValueError("entries must be sorted by app_id")
        return self

    def by_app(self) -> Dict[str, CorpusEntry]:
        return {entry.app_id: entry for entry in self.entries}

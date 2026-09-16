"""Controlled vocabularies for the research data model.

Every researched field draws from a closed set defined here, so a value is
either in the taxonomy or the record fails validation.

The vocabularies implement architecture section 6 verbatim, with one structural
difference that is a superset rather than a deviation. The architecture lists
``unknown`` / ``unclear`` / ``none_found`` / ``unavailable`` alongside real
values inside several taxonomies. Here those live on :class:`ResolutionStatus`,
which every field carries next to its value, because a single ``unknown`` member
cannot distinguish "we did not find it" from "it provably does not exist".
:data:`ARCHITECTURE_STATUS_ALIASES` records that mapping so an architecture value
can always be traced to its implementation.

Nothing in this module encodes a finding about any application.
"""

from enum import Enum
from typing import Dict


class ResolutionStatus(str, Enum):
    """Why a field has, or does not have, a value.

    The four non-resolved states are deliberately distinct; collapsing them
    would destroy the difference between "we could not find out", "the thing
    does not exist", and "the question does not apply".
    """

    #: Researched and established, with evidence.
    RESOLVED = "resolved"
    #: Searched, but no supporting information was found. Absence of evidence.
    NOT_FOUND = "not_found"
    #: Established with evidence that the capability does not exist or is not
    #: offered. A positive finding, not a gap.
    UNAVAILABLE = "unavailable"
    #: Sources exist but conflict, or are too vague to support a conclusion.
    UNCLEAR = "unclear"
    #: The question is meaningless for this application. Requires a rationale,
    #: so it cannot be used as a catch-all for non-SaaS apps.
    NOT_APPLICABLE = "not_applicable"


#: Architecture taxonomy values that this implementation represents as a status
#: rather than as a member of the value enum. Keyed by the architecture's
#: spelling, valued by the status that carries it.
ARCHITECTURE_STATUS_ALIASES: Dict[str, ResolutionStatus] = {
    "unknown": ResolutionStatus.NOT_FOUND,
    "none_found": ResolutionStatus.NOT_FOUND,
    "unavailable": ResolutionStatus.UNAVAILABLE,
    "unclear": ResolutionStatus.UNCLEAR,
    "not_applicable": ResolutionStatus.NOT_APPLICABLE,
}


#: Statuses that assert something about the world and therefore need evidence.
EVIDENCE_BEARING_STATUSES = frozenset(
    {ResolutionStatus.RESOLVED, ResolutionStatus.UNAVAILABLE}
)

#: Statuses that must explain themselves in prose.
RATIONALE_REQUIRED_STATUSES = frozenset(
    {
        ResolutionStatus.NOT_FOUND,
        ResolutionStatus.UNCLEAR,
        ResolutionStatus.NOT_APPLICABLE,
        ResolutionStatus.UNAVAILABLE,
    }
)


class ResearchFieldName(str, Enum):
    """The researched fields, named so verification can reference them safely."""

    IDENTITY = "identity"
    DESCRIPTION = "description"
    APPLICATION_TYPE = "application_type"
    AUTHENTICATION = "authentication"
    CREDENTIAL_ACCESS = "credential_access"
    ACCESS_RESTRICTIONS = "access_restrictions"
    API_EXISTS = "api_exists"
    API_TYPES = "api_types"
    API_BREADTH = "api_breadth"
    API_CAPABILITIES = "api_capabilities"
    MCP = "mcp"
    WEBHOOK_SUPPORT = "webhook_support"
    RATE_LIMIT_INFO = "rate_limit_info"
    BUILDABILITY = "buildability"
    BLOCKER = "blocker"


#: Fields that hold a list of values rather than a single one. Reconciliation
#: treats these differently: several values can legitimately coexist, whereas a
#: single-valued field must resolve to exactly one.
MULTI_VALUED_FIELDS = frozenset(
    {
        ResearchFieldName.AUTHENTICATION,
        ResearchFieldName.ACCESS_RESTRICTIONS,
        ResearchFieldName.API_TYPES,
        ResearchFieldName.API_CAPABILITIES,
        ResearchFieldName.BLOCKER,
    }
)

#: Fields that hold exactly one value.
SINGLE_VALUED_FIELDS = frozenset(ResearchFieldName) - MULTI_VALUED_FIELDS

#: The verification protocol: the fields counted by the field-level accuracy
#: metric. Fixed here, before any result is known, so the headline metric cannot
#: be redefined after the fact. Prose fields are excluded because they have no
#: objective right answer; identity is excluded because it gates the others and
#: is reported separately as an identity-resolution rate.
VERIFIED_FIELDS = (
    ResearchFieldName.APPLICATION_TYPE,
    ResearchFieldName.AUTHENTICATION,
    ResearchFieldName.CREDENTIAL_ACCESS,
    ResearchFieldName.API_EXISTS,
    ResearchFieldName.API_TYPES,
    ResearchFieldName.API_BREADTH,
    ResearchFieldName.MCP,
    ResearchFieldName.WEBHOOK_SUPPORT,
    ResearchFieldName.RATE_LIMIT_INFO,
    ResearchFieldName.BUILDABILITY,
    ResearchFieldName.BLOCKER,
)

#: Fields whose absence makes the record unusable. Used by the confidence
#: function and the trigger-review rules.
CRITICAL_FIELDS = (
    ResearchFieldName.APPLICATION_TYPE,
    ResearchFieldName.AUTHENTICATION,
    ResearchFieldName.CREDENTIAL_ACCESS,
    ResearchFieldName.API_EXISTS,
    ResearchFieldName.BUILDABILITY,
)


class ApplicationType(str, Enum):
    """What kind of thing the application is. Architecture section 6.1."""

    SAAS_APPLICATION = "saas_application"
    API_PLATFORM = "api_platform"
    OPEN_SOURCE_SELF_HOSTED = "open_source_self_hosted"
    CLI_TOOL = "cli_tool"
    THIRD_PARTY_WRAPPER = "third_party_wrapper"
    OTHER_TOOL = "other_tool"
    #: The supplied name maps to more than one real product, or to none.
    AMBIGUOUS_IDENTITY = "ambiguous_identity"


class AuthMethod(str, Enum):
    """How to authenticate against the API. Multi-valued. Section 6.2."""

    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    PAT = "pat"
    BASIC_AUTH = "basic_auth"
    SERVICE_ACCOUNT = "service_account"
    TOKEN = "token"
    OTHER = "other"


class CredentialAccess(str, Enum):
    """How a developer obtains working credentials. Single-valued. Section 6.3."""

    SELF_SERVE_FREE = "self_serve_free"
    SELF_SERVE_TRIAL = "self_serve_trial"
    SELF_SERVE_PAID = "self_serve_paid"
    ADMIN_APPROVAL = "admin_approval"
    ENTERPRISE = "enterprise"
    PARTNER_REQUIRED = "partner_required"
    CONTACT_SALES = "contact_sales"
    INVITE_ONLY = "invite_only"
    #: Valid for open-source/self-hosted products: credentials exist, but only
    #: once the reviewer has deployed an instance.
    SELF_HOSTED_DEPLOYMENT_DEPENDENT = "self_hosted_deployment_dependent"


class AccessRestriction(str, Enum):
    """Conditions gating API access. Multi-valued."""

    NONE = "none"
    PAID_PLAN_REQUIRED = "paid_plan_required"
    ENTERPRISE_PLAN_REQUIRED = "enterprise_plan_required"
    WAITLIST = "waitlist"
    REGION_RESTRICTED = "region_restricted"
    APPROVAL_REQUIRED = "approval_required"
    PARTNER_ONLY = "partner_only"
    INVITE_ONLY = "invite_only"
    IP_ALLOWLIST_REQUIRED = "ip_allowlist_required"
    IDENTITY_VERIFICATION_REQUIRED = "identity_verification_required"
    DEPLOYMENT_REQUIRED = "deployment_required"
    OTHER = "other"


class ApiType(str, Enum):
    """Shape of the programmatic interface. Multi-valued. Section 6.4."""

    REST = "rest"
    GRAPHQL = "graphql"
    SDK = "sdk"
    CLI = "cli"
    WEBHOOKS = "webhooks"
    OTHER = "other"


class ApiBreadth(str, Enum):
    """How much of the product the API covers. Ordinal. Section 6.5.

    Anchors, quoted from the architecture:

    * ``narrow`` - small set of resources or capabilities.
    * ``moderate`` - meaningful coverage, limited to a subset of the product.
    * ``broad`` - many important resources with meaningful action/CRUD coverage
      across major product surfaces.
    * ``very_broad`` - extensive coverage across most major product capabilities.
    """

    NARROW = "narrow"
    MODERATE = "moderate"
    BROAD = "broad"
    VERY_BROAD = "very_broad"


#: Ordering for ordinal comparisons and for presenting breadth in analytics.
API_BREADTH_ORDER = (
    ApiBreadth.NARROW,
    ApiBreadth.MODERATE,
    ApiBreadth.BROAD,
    ApiBreadth.VERY_BROAD,
)

#: Human-readable anchor for each breadth level, rendered into the case study so
#: the classification is auditable rather than asserted.
API_BREADTH_ANCHORS = {
    ApiBreadth.NARROW: "Small set of resources or capabilities.",
    ApiBreadth.MODERATE: (
        "Meaningful API coverage but limited to a subset of the product."
    ),
    ApiBreadth.BROAD: (
        "Many important resources with meaningful action/CRUD coverage across "
        "major product surfaces."
    ),
    ApiBreadth.VERY_BROAD: (
        "Extensive coverage across most major product capabilities."
    ),
}


class ApiCapability(str, Enum):
    """Kinds of operation the API exposes. Multi-valued."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    SEARCH = "search"
    ADMIN = "admin"
    USER_MANAGEMENT = "user_management"
    FILE_TRANSFER = "file_transfer"
    MESSAGING = "messaging"
    EVENT_SUBSCRIPTIONS = "event_subscriptions"
    BULK_OR_BATCH = "bulk_or_batch"
    STREAMING = "streaming"
    SCHEDULING = "scheduling"
    REPORTING_ANALYTICS = "reporting_analytics"
    OTHER = "other"


class McpStatus(str, Enum):
    """Availability of a Model Context Protocol server. Section 6.6."""

    OFFICIAL = "official"
    THIRD_PARTY = "third_party"
    #: Several servers exist, at least one of which is not the vendor's.
    MULTIPLE = "multiple"


class McpMaintenance(str, Enum):
    """Whether the MCP server is being kept up. Section 6.6."""

    MAINTAINED = "maintained"
    UNMAINTAINED = "unmaintained"
    UNCLEAR = "unclear"


class WebhookSupport(str, Enum):
    """How the product pushes events out. First of the two added fields."""

    NATIVE_WEBHOOKS = "native_webhooks"
    EVENT_STREAMING = "event_streaming"
    POLLING_ONLY = "polling_only"
    NO_EVENTS = "no_events"


class RateLimitInfo(str, Enum):
    """What the vendor publishes about rate limits. Second added field."""

    DOCUMENTED_QUANTITATIVE = "documented_quantitative"
    DOCUMENTED_QUALITATIVE = "documented_qualitative"
    ENFORCED_BUT_UNDISCLOSED = "enforced_but_undisclosed"
    NO_PUBLISHED_LIMITS = "no_published_limits"


class Buildability(str, Enum):
    """Whether a Composio-style toolkit could be built today. Section 6.7.

    ``Unclear`` and ``Not applicable`` from the architecture are carried by the
    field's status, not by a member here.
    """

    BUILDABLE = "buildable"
    BUILDABLE_WITH_FRICTION = "buildable_with_friction"
    BLOCKED = "blocked"


class Dimension(str, Enum):
    """Outcome of one leg of the buildability decision tree. Section 8."""

    PASS = "pass"
    FRICTION = "friction"
    FAIL = "fail"
    UNCLEAR = "unclear"
    NOT_APPLICABLE = "not_applicable"


class Blocker(str, Enum):
    """What stands in the way of building. Multi-valued. Section 6.8."""

    NONE = "none"
    NO_PUBLIC_API = "no_public_api"
    CREDENTIALS_UNAVAILABLE = "credentials_unavailable"
    ADMIN_APPROVAL = "admin_approval"
    PAID_ACCESS = "paid_access"
    ENTERPRISE_ONLY = "enterprise_only"
    PARTNER_REQUIRED = "partner_required"
    INSUFFICIENT_API_SURFACE = "insufficient_api_surface"
    INSUFFICIENT_DOCUMENTATION = "insufficient_documentation"
    AUTHENTICATION_COMPLEXITY = "authentication_complexity"
    UNCLEAR_ACCESS = "unclear_access"
    UNCLEAR_API = "unclear_api"
    NON_SAAS_TOOL = "non_saas_tool"
    AMBIGUOUS_IDENTITY = "ambiguous_identity"
    OTHER = "other"


class SourceType(str, Enum):
    """Where an evidence item came from.

    First-party sources are what the confidence function rewards: a vendor's own
    documentation is the only place an authentication model can be settled.
    """

    #: Vendor's own API/developer documentation.
    FIRST_PARTY_DOCS = "first_party_docs"
    #: Vendor's marketing site, product pages, or help centre.
    FIRST_PARTY_SITE = "first_party_site"
    #: Vendor's pricing or plan-comparison page.
    FIRST_PARTY_PRICING = "first_party_pricing"
    #: Vendor's changelog, status page, or developer blog.
    FIRST_PARTY_CHANGELOG = "first_party_changelog"
    #: Source repository, whether the vendor's or a community fork.
    REPOSITORY = "repository"
    #: Package or server registry listing.
    REGISTRY_LISTING = "registry_listing"
    #: Anything else: press, aggregators, community write-ups.
    THIRD_PARTY = "third_party"


#: Source types published by the vendor itself.
FIRST_PARTY_SOURCE_TYPES = frozenset(
    {
        SourceType.FIRST_PARTY_DOCS,
        SourceType.FIRST_PARTY_SITE,
        SourceType.FIRST_PARTY_PRICING,
        SourceType.FIRST_PARTY_CHANGELOG,
    }
)


#: Which taxonomy backs each researched field, for validation and reporting.
#: ``identity``, ``description`` and ``api_exists`` are absent on purpose: they
#: are free text, free text, and a boolean respectively.
FIELD_TAXONOMY = {
    ResearchFieldName.APPLICATION_TYPE: ApplicationType,
    ResearchFieldName.AUTHENTICATION: AuthMethod,
    ResearchFieldName.CREDENTIAL_ACCESS: CredentialAccess,
    ResearchFieldName.ACCESS_RESTRICTIONS: AccessRestriction,
    ResearchFieldName.API_TYPES: ApiType,
    ResearchFieldName.API_BREADTH: ApiBreadth,
    ResearchFieldName.API_CAPABILITIES: ApiCapability,
    ResearchFieldName.MCP: McpStatus,
    ResearchFieldName.WEBHOOK_SUPPORT: WebhookSupport,
    ResearchFieldName.RATE_LIMIT_INFO: RateLimitInfo,
    ResearchFieldName.BUILDABILITY: Buildability,
    ResearchFieldName.BLOCKER: Blocker,
}

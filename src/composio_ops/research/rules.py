"""The classifier: corpus observations in, taxonomy values out.

The corpus records what sources say; this module decides what that means. The
separation is deliberate. Because every rule here is explicit, ordered and
version-tagged, a wrong answer can be traced to the rule that produced it and
fixed for every app at once, which is exactly what the improvement phase
between Sample A and Sample B does.

Two rule sets live side by side:

* ``v1`` is the first pass, warts included. Sample A measures it.
* ``v2`` is what the Sample A failures taught us. Sample B measures it.

The differences are listed in :data:`IMPROVEMENTS` and are the only places the
two versions diverge.
"""

from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from .. import constants as C
from ..errors import ClassificationError
from ..schemas.corpus import CorpusEntry
from ..schemas.registry import NormalizedAppRecord
from ..schemas.research import (
    AppIdentity,
    AppResearchRecord,
    BuildabilityAssessment,
    ConfidenceInputs,
    Contradiction,
    McpDetails,
    MultiResearchField,
    ResearchField,
)
from ..taxonomy import (
    CRITICAL_FIELDS,
    AccessRestriction,
    ApiBreadth,
    ApiCapability,
    ApiType,
    ApplicationType,
    AuthMethod,
    Blocker,
    Buildability,
    CredentialAccess,
    McpStatus,
    RateLimitInfo,
    ResearchFieldName,
    ResolutionStatus,
    SourceType,
    WebhookSupport,
)
from . import buildability as bd
from . import confidence as conf
from .evidence import EvidenceIndex

F = ResearchFieldName

#: What changed between the two classifier versions, and why. Consumed by the
#: improvement report so the write-up cannot drift from the code.
IMPROVEMENTS: Tuple[Dict[str, object], ...] = (
    {
        "key": "credential-access-plan-gating",
        "failure_mode": (
            "Credential access was read off the signup tier alone, so a product "
            "with a free account but a paid-only API was recorded as "
            "self_serve_free."
        ),
        "fields": [F.CREDENTIAL_ACCESS, F.ACCESS_RESTRICTIONS],
        "change": (
            "v2 resolves credential access from the plan that actually unlocks "
            "the API, together with partner, approval and self-hosting gates, "
            "and derives the matching access restrictions rather than copying "
            "only those the source spelled out."
        ),
    },
    {
        "key": "api-breadth-coverage-anchor",
        "failure_mode": (
            "API breadth was a count of documented resource groups, so a large "
            "reference covering one corner of a product scored very_broad."
        ),
        "fields": [F.API_BREADTH],
        "change": (
            "v2 caps the count-derived breadth by the documented share of the "
            "product the API actually covers."
        ),
    },
    {
        "key": "event-mechanism-distinction",
        "failure_mode": (
            "Anything event-like was recorded as native_webhooks, which erased "
            "the difference between a callback, a gateway stream and polling."
        ),
        "fields": [F.WEBHOOK_SUPPORT],
        "change": "v2 keeps the observed event mechanism as the source states it.",
    },
    {
        "key": "derived-restriction-provenance",
        "failure_mode": (
            "Access restrictions were cited to the credential page without "
            "saying so, so the citation audit read them as claims the page "
            "never made."
        ),
        "fields": [F.ACCESS_RESTRICTIONS],
        "change": (
            "v2 records restrictions as derived from the documented access "
            "conditions and says so in the rationale, so the audit judges the "
            "citation as support for a conclusion rather than as a quotation."
        ),
    },
    {
        "key": "blocker-completeness",
        "failure_mode": (
            "Blockers were only named when an app was blocked outright, so "
            "'buildable with friction' records were silent about the friction, "
            "and unblocked apps read as though nothing had been established."
        ),
        "fields": [F.BLOCKER],
        "change": (
            "v2 names friction blockers explicitly and records 'none' when the "
            "decision tree found nothing in the way."
        ),
    },
)


class ClassifierVersion:
    """Feature switches for one rule set. Everything else is shared."""

    def __init__(self, version: str) -> None:
        if version not in C.CLASSIFIER_VERSIONS:
            raise ClassificationError(
                "Unknown classifier version",
                version=version,
                known=list(C.CLASSIFIER_VERSIONS),
            )
        self.version = version

    @property
    def plan_gated_credentials(self) -> bool:
        return self.version != C.CLASSIFIER_V1

    @property
    def coverage_anchored_breadth(self) -> bool:
        return self.version != C.CLASSIFIER_V1

    @property
    def distinguishes_event_mechanisms(self) -> bool:
        return self.version != C.CLASSIFIER_V1

    @property
    def complete_blockers(self) -> bool:
        return self.version != C.CLASSIFIER_V1

    @property
    def derives_restrictions(self) -> bool:
        """v2 states that restrictions are concluded, not quoted."""
        return self.version != C.CLASSIFIER_V1


def derives_restrictions(version: str) -> bool:
    """Whether this classifier version treats access restrictions as derived.

    The citation audit needs to know: a derived field is supported by the pages
    behind its inputs, whereas a quoted field must be supported by a page that
    says it.
    """
    return ClassifierVersion(version).derives_restrictions


# --- individual field rules -------------------------------------------------

#: Resource-group counts that separate the breadth levels. Ordinal thresholds,
#: applied from the top down.
BREADTH_THRESHOLDS: Tuple[Tuple[int, ApiBreadth], ...] = (
    (10, ApiBreadth.VERY_BROAD),
    (6, ApiBreadth.BROAD),
    (3, ApiBreadth.MODERATE),
    (1, ApiBreadth.NARROW),
)

#: The highest breadth each documented coverage judgement can support.
COVERAGE_CAPS: Dict[str, ApiBreadth] = {
    "most": ApiBreadth.VERY_BROAD,
    "major": ApiBreadth.BROAD,
    "subset": ApiBreadth.MODERATE,
    "slice": ApiBreadth.NARROW,
}

_BREADTH_RANK = {
    ApiBreadth.NARROW: 0,
    ApiBreadth.MODERATE: 1,
    ApiBreadth.BROAD: 2,
    ApiBreadth.VERY_BROAD: 3,
}

#: Keywords that map a recorded conflict onto the fields it casts doubt on.
_CONFLICT_KEYWORDS: Tuple[Tuple[Tuple[str, ...], Tuple[ResearchFieldName, ...]], ...] = (
    (("mcp",), (F.MCP,)),
    (("webhook", "event"), (F.WEBHOOK_SUPPORT,)),
    (("rate limit", "quota"), (F.RATE_LIMIT_INFO,)),
    (
        ("self-hosted", "self hosted", "open source", "open-source"),
        (F.APPLICATION_TYPE, F.CREDENTIAL_ACCESS),
    ),
    (
        ("plan", "pricing", "tier", "paid", "free", "trial", "sandbox", "credential"),
        (F.CREDENTIAL_ACCESS, F.ACCESS_RESTRICTIONS),
    ),
    (("name", "identity", "referent", "unique"), (F.IDENTITY,)),
    (("api", "endpoint"), (F.API_EXISTS, F.API_BREADTH)),
)


def breadth_from_counts(resource_groups: Sequence[str]) -> Optional[ApiBreadth]:
    """The v1 rule: breadth is how many resource groups the reference lists."""
    count = len(resource_groups)
    for threshold, breadth in BREADTH_THRESHOLDS:
        if count >= threshold:
            return breadth
    return None


def cap_breadth(breadth: ApiBreadth, coverage: str) -> ApiBreadth:
    """The v2 rule: a count cannot outrank the documented coverage judgement."""
    cap = COVERAGE_CAPS.get(coverage, ApiBreadth.VERY_BROAD)
    return breadth if _BREADTH_RANK[breadth] <= _BREADTH_RANK[cap] else cap


def credential_access_v1(entry: CorpusEntry) -> Optional[CredentialAccess]:
    """Signup tier only. Kept verbatim because Sample A measures this rule."""
    return {
        "free": CredentialAccess.SELF_SERVE_FREE,
        "trial": CredentialAccess.SELF_SERVE_TRIAL,
        "paid": CredentialAccess.SELF_SERVE_PAID,
        "invite": CredentialAccess.INVITE_ONLY,
        "contact_sales": CredentialAccess.CONTACT_SALES,
    }.get(entry.access.account)


def credential_access_v2(entry: CorpusEntry) -> Optional[CredentialAccess]:
    """Ordered gates: the first one a developer actually hits wins."""
    access = entry.access
    if access.partner_only or access.api_plan == "partner":
        return CredentialAccess.PARTNER_REQUIRED
    if access.api_plan == "enterprise":
        return CredentialAccess.ENTERPRISE
    if access.account == "contact_sales":
        return CredentialAccess.CONTACT_SALES
    if access.self_hosted:
        return CredentialAccess.SELF_HOSTED_DEPLOYMENT_DEPENDENT
    if access.admin_only or access.approval_required:
        return CredentialAccess.ADMIN_APPROVAL
    if access.api_plan == "paid":
        return CredentialAccess.SELF_SERVE_PAID
    if access.api_plan == "trial" or access.account == "trial":
        return CredentialAccess.SELF_SERVE_TRIAL
    if access.account == "invite":
        return CredentialAccess.INVITE_ONLY
    if access.api_plan == "free":
        return CredentialAccess.SELF_SERVE_FREE
    return None


def restrictions_v1(entry: CorpusEntry) -> List[AccessRestriction]:
    """Whatever the source spelled out, verbatim."""
    return list(entry.access.restrictions) or [AccessRestriction.NONE]


def restrictions_v2(entry: CorpusEntry) -> List[AccessRestriction]:
    """The spelled-out restrictions plus the ones the access facts imply."""
    values = set(entry.access.restrictions)
    access = entry.access
    if access.partner_only:
        values.add(AccessRestriction.PARTNER_ONLY)
    if access.approval_required or access.admin_only:
        values.add(AccessRestriction.APPROVAL_REQUIRED)
    if access.self_hosted:
        values.add(AccessRestriction.DEPLOYMENT_REQUIRED)
    if access.api_plan == "paid":
        values.add(AccessRestriction.PAID_PLAN_REQUIRED)
    if access.api_plan == "enterprise":
        values.add(AccessRestriction.ENTERPRISE_PLAN_REQUIRED)
    if access.account == "invite":
        values.add(AccessRestriction.INVITE_ONLY)
    values.discard(AccessRestriction.NONE)
    if not values:
        return [AccessRestriction.NONE]
    return sorted(values, key=lambda item: item.value)


def webhook_support(
    entry: CorpusEntry, distinguishes: bool
) -> Optional[WebhookSupport]:
    """v1 collapsed every event mechanism into native webhooks; v2 does not."""
    observed = entry.webhooks
    if observed is None:
        return None
    if distinguishes:
        return observed
    if observed in (WebhookSupport.NATIVE_WEBHOOKS, WebhookSupport.EVENT_STREAMING):
        return WebhookSupport.NATIVE_WEBHOOKS
    return observed


def contradictions_for(entry: CorpusEntry) -> List[Contradiction]:
    """Turn recorded conflicts into typed contradictions over specific fields."""
    contradictions: List[Contradiction] = []
    for detail in entry.conflicts:
        lowered = detail.lower()
        fields: List[ResearchFieldName] = []
        for keywords, mapped in _CONFLICT_KEYWORDS:
            if any(keyword in lowered for keyword in keywords):
                fields.extend(mapped)
        if not fields:
            fields = [F.APPLICATION_TYPE]
        contradictions.append(
            Contradiction(
                kind="source_conflict",
                fields=sorted(set(fields), key=lambda item: item.value),
                detail=detail,
            )
        )
    return contradictions


# --- the classifier ---------------------------------------------------------


def classify(
    entry: CorpusEntry,
    app: NormalizedAppRecord,
    index: EvidenceIndex,
    version: str,
    provider: C.ResearchProvider,
    generated_at: datetime,
) -> AppResearchRecord:
    """Produce one complete research record from one corpus entry."""
    rules = ClassifierVersion(version)

    def cites(field: ResearchFieldName) -> List[str]:
        return index.for_field(field)

    # --- identity -----------------------------------------------------------
    identity_ids = index.with_fallback(F.IDENTITY)
    if entry.identity_ambiguous or not identity_ids:
        identity = ResearchField[AppIdentity].unclear(
            rationale=(
                "The supplied name does not resolve to a single product."
                if entry.identity_ambiguous
                else "No source could be tied to a single product."
            ),
            evidence_ids=identity_ids,
        )
    else:
        identity = ResearchField[AppIdentity].resolved(
            value=AppIdentity(
                canonical_name=entry.canonical_name,
                vendor=entry.vendor,
                homepage_url=entry.homepage_url,
                docs_url=entry.docs_url,
            ),
            evidence_ids=identity_ids,
            rationale=None,
        )

    description_ids = index.with_fallback(F.DESCRIPTION)
    description = (
        ResearchField[str].resolved(value=entry.description, evidence_ids=description_ids)
        if description_ids
        else ResearchField[str].not_found("No source describes the product.")
    )

    # --- application type ---------------------------------------------------
    type_ids = index.with_fallback(F.APPLICATION_TYPE)
    application_type = (
        ResearchField[ApplicationType].resolved(
            value=entry.application_type, evidence_ids=type_ids
        )
        if type_ids
        else ResearchField[ApplicationType].not_found(
            "No source establishes what kind of product this is."
        )
    )

    # --- authentication -----------------------------------------------------
    auth_ids = cites(F.AUTHENTICATION)
    if entry.auth_methods and auth_ids:
        authentication = MultiResearchField[AuthMethod].resolved(
            values=entry.auth_methods, evidence_ids=auth_ids
        )
    elif entry.api.exists is False or not entry.integration_model:
        authentication = MultiResearchField[AuthMethod].not_applicable(
            "There is no credentialed interface to authenticate against."
        )
    else:
        authentication = MultiResearchField[AuthMethod].not_found(
            "No source documents an authentication mechanism."
        )

    # --- credential access --------------------------------------------------
    access_ids = cites(F.CREDENTIAL_ACCESS)
    access_value = (
        credential_access_v2(entry)
        if rules.plan_gated_credentials
        else credential_access_v1(entry)
    )
    if access_value is not None and access_ids:
        credential_access = ResearchField[CredentialAccess].resolved(
            value=access_value, evidence_ids=access_ids
        )
    else:
        credential_access = ResearchField[CredentialAccess].not_found(
            "No source documents how a developer obtains credentials."
        )

    restriction_ids = cites(F.ACCESS_RESTRICTIONS) or access_ids
    restriction_values = (
        restrictions_v2(entry) if rules.plan_gated_credentials else restrictions_v1(entry)
    )
    if restriction_ids:
        access_restrictions = MultiResearchField[AccessRestriction].resolved(
            values=restriction_values,
            evidence_ids=restriction_ids,
            rationale=(
                "Concluded from the documented access conditions: account tier "
                "'{}', API plan '{}'.".format(
                    entry.access.account, entry.access.api_plan
                )
                if rules.derives_restrictions
                else None
            ),
        )
    else:
        access_restrictions = MultiResearchField[AccessRestriction].not_found(
            "No source documents the conditions on API access."
        )

    # --- the API ------------------------------------------------------------
    api_ids = cites(F.API_EXISTS)
    if entry.api.exists is True and api_ids:
        api_exists = ResearchField[bool].resolved(value=True, evidence_ids=api_ids)
    elif entry.api.exists is False and api_ids:
        api_exists = ResearchField[bool].unavailable(
            evidence_ids=api_ids,
            rationale="The vendor documents no public programmatic interface.",
        )
    else:
        api_exists = ResearchField[bool].not_found(
            "No source establishes whether a public API exists."
        )

    type_evidence = cites(F.API_TYPES) or api_ids
    if api_exists.is_resolved and entry.api.types and type_evidence:
        api_types = MultiResearchField[ApiType].resolved(
            values=entry.api.types, evidence_ids=type_evidence
        )
    elif api_exists.status is ResolutionStatus.UNAVAILABLE:
        api_types = MultiResearchField[ApiType].not_applicable(
            "There is no API whose shape could be described."
        )
    else:
        api_types = MultiResearchField[ApiType].not_found(
            "No source documents the shape of the interface."
        )

    breadth_ids = cites(F.API_BREADTH) or api_ids
    breadth_value: Optional[ApiBreadth] = None
    if api_exists.is_resolved:
        counted = breadth_from_counts(entry.api.resource_groups)
        if counted is not None and rules.coverage_anchored_breadth:
            counted = cap_breadth(counted, entry.api.coverage)
        breadth_value = counted
    if breadth_value is not None and breadth_ids and entry.api.enumerated:
        api_breadth = ResearchField[ApiBreadth].resolved(
            value=breadth_value,
            evidence_ids=breadth_ids,
            rationale="{} documented resource groups; coverage judged '{}'.".format(
                len(entry.api.resource_groups), entry.api.coverage
            ),
        )
    elif api_exists.status is ResolutionStatus.UNAVAILABLE:
        api_breadth = ResearchField[ApiBreadth].not_applicable(
            "There is no API whose breadth could be measured."
        )
    elif api_exists.is_resolved and not entry.api.enumerated:
        api_breadth = ResearchField[ApiBreadth].unclear(
            rationale="The reference does not enumerate its resources.",
            evidence_ids=breadth_ids,
        )
    else:
        api_breadth = ResearchField[ApiBreadth].not_found(
            "The documented surface could not be measured."
        )

    capability_ids = cites(F.API_CAPABILITIES) or api_ids
    if api_exists.is_resolved and entry.api.capabilities and capability_ids:
        api_capabilities = MultiResearchField[ApiCapability].resolved(
            values=entry.api.capabilities, evidence_ids=capability_ids
        )
    elif api_exists.status is ResolutionStatus.UNAVAILABLE:
        api_capabilities = MultiResearchField[ApiCapability].not_applicable(
            "There is no API whose capabilities could be listed."
        )
    else:
        api_capabilities = MultiResearchField[ApiCapability].not_found(
            "No source enumerates what the interface can do."
        )

    # --- MCP ----------------------------------------------------------------
    mcp_ids = cites(F.MCP)
    mcp_details: Optional[McpDetails] = None
    if entry.mcp.status is not None and mcp_ids:
        mcp = ResearchField[McpStatus].resolved(
            value=entry.mcp.status, evidence_ids=mcp_ids
        )
        mcp_details = McpDetails(
            official=entry.mcp.official,
            maintained=entry.mcp.maintained,
            source_url=entry.mcp.source_url,
        )
    elif mcp_ids:
        # A source that speaks to MCP while recording no server is evidence of
        # absence, which is a finding; having looked and found nothing is not.
        mcp = ResearchField[McpStatus].unavailable(
            evidence_ids=mcp_ids,
            rationale="A source addressing MCP coverage records no server for "
            "this product.",
        )
    elif entry.mcp.searched:
        mcp = ResearchField[McpStatus].not_found(
            "Searched the vendor's documentation and the public registries; no "
            "MCP server was found."
        )
    else:
        mcp = ResearchField[McpStatus].not_found("No search for an MCP server was made.")

    # --- events and limits --------------------------------------------------
    webhook_ids = cites(F.WEBHOOK_SUPPORT)
    webhook_value = webhook_support(entry, rules.distinguishes_event_mechanisms)
    if webhook_value is not None and webhook_ids:
        webhook_support_field = ResearchField[WebhookSupport].resolved(
            value=webhook_value, evidence_ids=webhook_ids
        )
    else:
        webhook_support_field = ResearchField[WebhookSupport].not_found(
            "No source documents how the product emits events."
        )

    limit_ids = cites(F.RATE_LIMIT_INFO)
    if entry.rate_limits is not None and limit_ids:
        rate_limit_info = ResearchField[RateLimitInfo].resolved(
            value=entry.rate_limits, evidence_ids=limit_ids
        )
    else:
        rate_limit_info = ResearchField[RateLimitInfo].not_found(
            "No source documents rate limiting."
        )

    # --- buildability -------------------------------------------------------
    technical = bd.technical_feasibility(
        api_status=api_exists.status,
        api_exists=api_exists.value,
        breadth=api_breadth.value,
        capabilities=list(api_capabilities.values),
        integration_model=entry.integration_model,
    )
    credential = bd.credential_accessibility(
        access_status=credential_access.status, access=credential_access.value
    )
    commercial = bd.commercial_accessibility(
        restriction_status=access_restrictions.status,
        restrictions=list(access_restrictions.values),
    )
    assessment = BuildabilityAssessment(
        technical_feasibility=technical[0],
        credential_accessibility=credential[0],
        commercial_accessibility=commercial[0],
        reason=bd.describe(technical, credential, commercial),
    )

    build_status, build_value = bd.combine(technical[0], credential[0], commercial[0])
    build_ids = index.for_fields(
        (F.API_EXISTS, F.API_BREADTH, F.CREDENTIAL_ACCESS, F.ACCESS_RESTRICTIONS)
    ) or index.with_fallback(F.BUILDABILITY)
    if build_status is ResolutionStatus.RESOLVED and build_ids:
        buildability = ResearchField[Buildability].resolved(
            value=build_value, evidence_ids=build_ids, rationale=assessment.reason
        )
    elif build_status is ResolutionStatus.NOT_APPLICABLE:
        buildability = ResearchField[Buildability].not_applicable(
            "The tool has no hosted integration surface, so buildability does "
            "not arise: {}".format(assessment.reason)
        )
    else:
        buildability = ResearchField[Buildability].unclear(
            rationale=assessment.reason, evidence_ids=build_ids
        )

    blocker_values = bd.blockers_for(
        technical=technical[0],
        credential=credential[0],
        commercial=commercial[0],
        access=credential_access.value,
        restrictions=list(access_restrictions.values),
        breadth=api_breadth.value,
        integration_model=entry.integration_model,
        identity_ambiguous=entry.identity_ambiguous,
        include_friction=rules.complete_blockers,
    )
    if blocker_values and build_ids:
        blocker = MultiResearchField[Blocker].resolved(
            values=blocker_values, evidence_ids=build_ids, rationale=assessment.reason
        )
    elif rules.complete_blockers and build_ids and build_status is (
        ResolutionStatus.RESOLVED
    ):
        blocker = MultiResearchField[Blocker].resolved(
            values=[Blocker.NONE],
            evidence_ids=build_ids,
            rationale="The decision tree found nothing in the way.",
        )
    else:
        blocker = MultiResearchField[Blocker].not_found(
            "No blocker was established from the documented access and API facts."
        )

    # --- confidence ---------------------------------------------------------
    contradictions = contradictions_for(entry)
    record_fields = {
        F.APPLICATION_TYPE: application_type,
        F.AUTHENTICATION: authentication,
        F.CREDENTIAL_ACCESS: credential_access,
        F.API_EXISTS: api_exists,
        F.BUILDABILITY: buildability,
    }
    has_critical_evidence = all(
        record_fields[name].is_known and bool(record_fields[name].evidence_ids)
        for name in CRITICAL_FIELDS
    )
    inputs = ConfidenceInputs(
        identity_resolved=identity.is_resolved,
        has_first_party_source=bool(index.first_party_ids()),
        has_critical_field_evidence=has_critical_evidence,
        has_contradiction=bool(contradictions),
        source_count=len(index),
        has_page_level_evidence=index.has_page_level_evidence(),
        has_current_source=index.has_current_source(),
        has_explicit_documentation=entry.api.documented
        and index.has_source_type(SourceType.FIRST_PARTY_DOCS),
        has_unresolved_ambiguity=entry.identity_ambiguous,
    )

    notes = [entry.notes] if entry.notes else []
    if not index.has_page_level_evidence():
        notes.append(
            "Evidence is cited from the reviewed corpus rather than fetched in "
            "this run; see the case study's limitations."
        )

    return AppResearchRecord(
        app_id=app.app_id,
        app=app.name,
        category_id=app.category_id,
        channel=C.Channel.CHANNEL_A,
        provider=provider,
        classifier_version=version,
        generated_at=generated_at,
        identity=identity,
        description=description,
        application_type=application_type,
        authentication=authentication,
        credential_access=credential_access,
        access_restrictions=access_restrictions,
        api_exists=api_exists,
        api_types=api_types,
        api_breadth=api_breadth,
        api_capabilities=api_capabilities,
        mcp=mcp,
        webhook_support=webhook_support_field,
        rate_limit_info=rate_limit_info,
        buildability=buildability,
        blocker=blocker,
        mcp_details=mcp_details,
        buildability_assessment=assessment,
        api_notes=entry.api.notes,
        access_notes=entry.auth_notes,
        confidence=conf.calculate(inputs),
        confidence_inputs=inputs,
        contradictions=contradictions,
        notes=notes,
    )

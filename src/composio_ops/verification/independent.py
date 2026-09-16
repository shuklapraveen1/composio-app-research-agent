"""Channel B: an independent second reading of the same sources.

Channel B is only worth running if it can disagree, so it never sees Channel A's
answer and it does not share Channel A's rules. It reads the same corpus entry
and reaches its own conclusion by a different, equally defensible route:
credential access from the documented conditions rather than the plan table,
breadth from the documented coverage judgement rather than a resource count.

Where the two routes agree, the value is corroborated. Where they diverge, the
divergence is the finding: it locates a rule that is doing the work, rather than
a fact that is in doubt.
"""

from typing import Dict, List, Optional, Tuple

from ..research import buildability as bd
from ..schemas.corpus import CorpusEntry
from ..schemas.verification import FieldValue
from ..taxonomy import (
    VERIFIED_FIELDS,
    AccessRestriction,
    ApiBreadth,
    Blocker,
    CredentialAccess,
    ResearchFieldName,
    ResolutionStatus,
)

F = ResearchFieldName

#: Channel B reads breadth straight off the documented coverage judgement.
_COVERAGE_TO_BREADTH: Dict[str, ApiBreadth] = {
    "most": ApiBreadth.VERY_BROAD,
    "major": ApiBreadth.BROAD,
    "subset": ApiBreadth.MODERATE,
    "slice": ApiBreadth.NARROW,
}


def _value(field: F, status: ResolutionStatus, tokens: Optional[List[str]] = None) -> FieldValue:
    return FieldValue(field=field, status=status, value=tokens)


def _resolved(field: F, *tokens: str) -> FieldValue:
    """A resolved observation, with tokens in canonical order."""
    return FieldValue(
        field=field, status=ResolutionStatus.RESOLVED, value=sorted(set(tokens))
    )


def _credential_access(entry: CorpusEntry) -> Optional[CredentialAccess]:
    """Conditions first: what would actually stop a developer getting a key?"""
    access = entry.access
    restrictions = set(access.restrictions)
    if access.partner_only or AccessRestriction.PARTNER_ONLY in restrictions:
        return CredentialAccess.PARTNER_REQUIRED
    if AccessRestriction.ENTERPRISE_PLAN_REQUIRED in restrictions:
        return CredentialAccess.ENTERPRISE
    if AccessRestriction.INVITE_ONLY in restrictions or access.account == "invite":
        return CredentialAccess.INVITE_ONLY
    if access.self_hosted:
        return CredentialAccess.SELF_HOSTED_DEPLOYMENT_DEPENDENT
    if access.account == "contact_sales":
        return CredentialAccess.CONTACT_SALES
    if AccessRestriction.APPROVAL_REQUIRED in restrictions or access.approval_required:
        return CredentialAccess.ADMIN_APPROVAL
    if access.admin_only:
        return CredentialAccess.ADMIN_APPROVAL
    if AccessRestriction.PAID_PLAN_REQUIRED in restrictions or access.api_plan == "paid":
        return CredentialAccess.SELF_SERVE_PAID
    if access.api_plan == "trial" or access.account == "trial":
        return CredentialAccess.SELF_SERVE_TRIAL
    if access.api_plan in ("free",):
        return CredentialAccess.SELF_SERVE_FREE
    return None


def _restrictions(entry: CorpusEntry) -> List[AccessRestriction]:
    values = set(entry.access.restrictions)
    values.discard(AccessRestriction.NONE)
    if entry.access.approval_required or entry.access.admin_only:
        values.add(AccessRestriction.APPROVAL_REQUIRED)
    if entry.access.partner_only:
        values.add(AccessRestriction.PARTNER_ONLY)
    if entry.access.self_hosted:
        values.add(AccessRestriction.DEPLOYMENT_REQUIRED)
    if entry.access.api_plan == "paid":
        values.add(AccessRestriction.PAID_PLAN_REQUIRED)
    if entry.access.api_plan == "enterprise":
        values.add(AccessRestriction.ENTERPRISE_PLAN_REQUIRED)
    if not values:
        return [AccessRestriction.NONE]
    return sorted(values, key=lambda item: item.value)


def observe(entry: CorpusEntry) -> Dict[F, FieldValue]:
    """Channel B's own reading of every verified field."""
    observations: Dict[F, FieldValue] = {}

    observations[F.APPLICATION_TYPE] = _resolved(
        F.APPLICATION_TYPE, entry.application_type.value
    )

    if entry.auth_methods:
        observations[F.AUTHENTICATION] = _resolved(
            F.AUTHENTICATION, *[item.value for item in entry.auth_methods]
        )
    elif entry.api.exists is False or not entry.integration_model:
        observations[F.AUTHENTICATION] = _value(
            F.AUTHENTICATION, ResolutionStatus.NOT_APPLICABLE
        )
    else:
        observations[F.AUTHENTICATION] = _value(
            F.AUTHENTICATION, ResolutionStatus.NOT_FOUND
        )

    access = _credential_access(entry)
    observations[F.CREDENTIAL_ACCESS] = (
        _resolved(F.CREDENTIAL_ACCESS, access.value)
        if access is not None
        else _value(F.CREDENTIAL_ACCESS, ResolutionStatus.UNCLEAR)
    )

    if entry.api.exists is True:
        observations[F.API_EXISTS] = _resolved(F.API_EXISTS, "true")
    elif entry.api.exists is False:
        observations[F.API_EXISTS] = _value(F.API_EXISTS, ResolutionStatus.UNAVAILABLE)
    else:
        observations[F.API_EXISTS] = _value(F.API_EXISTS, ResolutionStatus.NOT_FOUND)

    if entry.api.exists is True and entry.api.types:
        observations[F.API_TYPES] = _resolved(
            F.API_TYPES, *[item.value for item in entry.api.types]
        )
    elif entry.api.exists is False:
        observations[F.API_TYPES] = _value(F.API_TYPES, ResolutionStatus.NOT_APPLICABLE)
    else:
        observations[F.API_TYPES] = _value(F.API_TYPES, ResolutionStatus.NOT_FOUND)

    if entry.api.exists is True and entry.api.enumerated:
        breadth = _COVERAGE_TO_BREADTH.get(entry.api.coverage)
        observations[F.API_BREADTH] = (
            _resolved(F.API_BREADTH, breadth.value)
            if breadth
            else _value(F.API_BREADTH, ResolutionStatus.UNCLEAR)
        )
    elif entry.api.exists is False:
        observations[F.API_BREADTH] = _value(
            F.API_BREADTH, ResolutionStatus.NOT_APPLICABLE
        )
    else:
        observations[F.API_BREADTH] = _value(F.API_BREADTH, ResolutionStatus.UNCLEAR)

    if entry.mcp.status is not None:
        observations[F.MCP] = _resolved(F.MCP, entry.mcp.status.value)
    elif entry.sources_for(F.MCP):
        observations[F.MCP] = _value(F.MCP, ResolutionStatus.UNAVAILABLE)
    else:
        observations[F.MCP] = _value(F.MCP, ResolutionStatus.NOT_FOUND)

    observations[F.WEBHOOK_SUPPORT] = (
        _resolved(F.WEBHOOK_SUPPORT, entry.webhooks.value)
        if entry.webhooks is not None
        else _value(F.WEBHOOK_SUPPORT, ResolutionStatus.NOT_FOUND)
    )
    observations[F.RATE_LIMIT_INFO] = (
        _resolved(F.RATE_LIMIT_INFO, entry.rate_limits.value)
        if entry.rate_limits is not None
        else _value(F.RATE_LIMIT_INFO, ResolutionStatus.NOT_FOUND)
    )

    buildability, blockers = _decide(entry, observations)
    observations[F.BUILDABILITY] = buildability
    observations[F.BLOCKER] = blockers
    return {field: observations[field] for field in VERIFIED_FIELDS}


def _decide(
    entry: CorpusEntry, observations: Dict[F, FieldValue]
) -> Tuple[FieldValue, FieldValue]:
    """Run the shared decision tree over Channel B's own field values.

    The tree is the architecture's, not the classifier's, so both channels are
    entitled to use it; what differs is the inputs each one derived.
    """
    api = observations[F.API_EXISTS]
    breadth_value = observations[F.API_BREADTH].value
    breadth = ApiBreadth(breadth_value[0]) if breadth_value else None
    access_value = observations[F.CREDENTIAL_ACCESS].value
    access = CredentialAccess(access_value[0]) if access_value else None
    restrictions = _restrictions(entry)

    technical = bd.technical_feasibility(
        api_status=api.status,
        api_exists=True if api.status is ResolutionStatus.RESOLVED else None,
        breadth=breadth,
        capabilities=list(entry.api.capabilities),
        integration_model=entry.integration_model,
    )
    credential = bd.credential_accessibility(
        access_status=observations[F.CREDENTIAL_ACCESS].status, access=access
    )
    commercial = bd.commercial_accessibility(
        restriction_status=ResolutionStatus.RESOLVED, restrictions=restrictions
    )
    status, value = bd.combine(technical[0], credential[0], commercial[0])

    if status is ResolutionStatus.RESOLVED and value is not None:
        buildability = _resolved(F.BUILDABILITY, value.value)
    else:
        buildability = _value(F.BUILDABILITY, status)

    blocker_values = bd.blockers_for(
        technical=technical[0],
        credential=credential[0],
        commercial=commercial[0],
        access=access,
        restrictions=restrictions,
        breadth=breadth,
        integration_model=entry.integration_model,
        identity_ambiguous=entry.identity_ambiguous,
        include_friction=True,
    ) or [Blocker.NONE]

    if status is ResolutionStatus.NOT_APPLICABLE:
        blockers = _resolved(F.BLOCKER, *[item.value for item in blocker_values])
    elif status is ResolutionStatus.UNCLEAR:
        blockers = _value(F.BLOCKER, ResolutionStatus.UNCLEAR)
    else:
        blockers = _resolved(F.BLOCKER, *[item.value for item in blocker_values])
    return buildability, blockers

"""The buildability decision tree. Architecture section 8.

Buildability is not a vibe about an API: it is the conjunction of three
independent questions, each answered from fields that were classified first.

* *technical feasibility* - is there enough programmable surface to build against?
* *credential accessibility* - can a developer obtain working credentials?
* *commercial accessibility* - does a plan, contract or programme gate the above?

Each leg answers pass, friction, fail, unclear, or not applicable, and the
combination rule below is total: the worst leg wins, with ``fail`` beating
``unclear`` because a known blocker is a stronger statement than a gap.
"""

from typing import List, Optional, Tuple

from ..taxonomy import (
    AccessRestriction,
    ApiBreadth,
    ApiCapability,
    Blocker,
    Buildability,
    CredentialAccess,
    Dimension,
    ResolutionStatus,
)

#: Credential access values that make credentials obtainable without a deal.
_CREDENTIAL_DIMENSION = {
    CredentialAccess.SELF_SERVE_FREE: Dimension.PASS,
    CredentialAccess.SELF_SERVE_TRIAL: Dimension.PASS,
    CredentialAccess.SELF_SERVE_PAID: Dimension.FRICTION,
    CredentialAccess.ADMIN_APPROVAL: Dimension.FRICTION,
    CredentialAccess.SELF_HOSTED_DEPLOYMENT_DEPENDENT: Dimension.FRICTION,
    CredentialAccess.ENTERPRISE: Dimension.FAIL,
    CredentialAccess.CONTACT_SALES: Dimension.FAIL,
    CredentialAccess.PARTNER_REQUIRED: Dimension.FAIL,
    CredentialAccess.INVITE_ONLY: Dimension.FAIL,
}

#: Restrictions that end the conversation, versus those that merely slow it down.
_BLOCKING_RESTRICTIONS = frozenset(
    {
        AccessRestriction.ENTERPRISE_PLAN_REQUIRED,
        AccessRestriction.PARTNER_ONLY,
        AccessRestriction.INVITE_ONLY,
    }
)

_FRICTION_RESTRICTIONS = frozenset(
    {
        AccessRestriction.PAID_PLAN_REQUIRED,
        AccessRestriction.APPROVAL_REQUIRED,
        AccessRestriction.WAITLIST,
        AccessRestriction.REGION_RESTRICTED,
        AccessRestriction.IP_ALLOWLIST_REQUIRED,
        AccessRestriction.IDENTITY_VERIFICATION_REQUIRED,
        AccessRestriction.DEPLOYMENT_REQUIRED,
        AccessRestriction.OTHER,
    }
)

#: Capabilities that let a toolkit do something rather than only observe.
_ACTION_CAPABILITIES = frozenset(
    {
        ApiCapability.WRITE,
        ApiCapability.DELETE,
        ApiCapability.ADMIN,
        ApiCapability.USER_MANAGEMENT,
        ApiCapability.MESSAGING,
        ApiCapability.FILE_TRANSFER,
        ApiCapability.SCHEDULING,
        ApiCapability.BULK_OR_BATCH,
    }
)


def technical_feasibility(
    api_status: ResolutionStatus,
    api_exists: Optional[bool],
    breadth: Optional[ApiBreadth],
    capabilities: List[ApiCapability],
    integration_model: bool,
) -> Tuple[Dimension, str]:
    """Is there enough documented surface to build a toolkit against?"""
    if not integration_model:
        return (
            Dimension.NOT_APPLICABLE,
            "the tool is not a hosted product with an integration surface",
        )
    if api_status is ResolutionStatus.UNAVAILABLE or api_exists is False:
        return Dimension.FAIL, "no public API is offered"
    if api_status is not ResolutionStatus.RESOLVED or not api_exists:
        return Dimension.UNCLEAR, "the existence of a public API could not be established"
    if breadth is None:
        return Dimension.UNCLEAR, "the API exists but its breadth could not be judged"
    if breadth is ApiBreadth.NARROW and not (set(capabilities) & _ACTION_CAPABILITIES):
        return (
            Dimension.FRICTION,
            "the API is narrow and exposes little beyond reads",
        )
    if breadth is ApiBreadth.NARROW:
        return Dimension.FRICTION, "the API covers a small slice of the product"
    return Dimension.PASS, "the API covers a meaningful part of the product"


def credential_accessibility(
    access_status: ResolutionStatus, access: Optional[CredentialAccess]
) -> Tuple[Dimension, str]:
    """Can a developer get working credentials, and at what cost?"""
    if access_status is not ResolutionStatus.RESOLVED or access is None:
        return Dimension.UNCLEAR, "how to obtain credentials could not be established"
    dimension = _CREDENTIAL_DIMENSION[access]
    return dimension, "credentials are obtained via {}".format(
        access.value.replace("_", " ")
    )


def commercial_accessibility(
    restriction_status: ResolutionStatus, restrictions: List[AccessRestriction]
) -> Tuple[Dimension, str]:
    """Does a plan, contract, or programme gate access?"""
    if restriction_status is not ResolutionStatus.RESOLVED:
        return Dimension.UNCLEAR, "access conditions could not be established"
    blocking = sorted(
        item.value for item in set(restrictions) & _BLOCKING_RESTRICTIONS
    )
    if blocking:
        return Dimension.FAIL, "access requires {}".format(", ".join(blocking))
    frictional = sorted(
        item.value for item in set(restrictions) & _FRICTION_RESTRICTIONS
    )
    if frictional:
        return Dimension.FRICTION, "access is conditioned on {}".format(
            ", ".join(frictional)
        )
    return Dimension.PASS, "no access conditions are documented"


def combine(
    technical: Dimension, credential: Dimension, commercial: Dimension
) -> Tuple[ResolutionStatus, Optional[Buildability]]:
    """Fold the three legs into one status and value.

    Ordered so that a definite finding always beats a gap: ``not applicable``
    first (the question does not arise), then ``fail``, then ``unclear``, then
    ``friction``.
    """
    legs = (technical, credential, commercial)
    if Dimension.NOT_APPLICABLE in legs:
        return ResolutionStatus.NOT_APPLICABLE, None
    if Dimension.FAIL in legs:
        return ResolutionStatus.RESOLVED, Buildability.BLOCKED
    if Dimension.UNCLEAR in legs:
        return ResolutionStatus.UNCLEAR, None
    if Dimension.FRICTION in legs:
        return ResolutionStatus.RESOLVED, Buildability.BUILDABLE_WITH_FRICTION
    return ResolutionStatus.RESOLVED, Buildability.BUILDABLE


def blockers_for(
    technical: Dimension,
    credential: Dimension,
    commercial: Dimension,
    access: Optional[CredentialAccess],
    restrictions: List[AccessRestriction],
    breadth: Optional[ApiBreadth],
    integration_model: bool,
    identity_ambiguous: bool,
    include_friction: bool,
) -> List[Blocker]:
    """Name what stands in the way, in taxonomy terms.

    ``include_friction`` is what separates classifier v1 from v2: v1 named only
    hard blockers, which left "buildable with friction" records silent about the
    very friction that produced the classification.
    """
    blockers: List[Blocker] = []
    if identity_ambiguous:
        blockers.append(Blocker.AMBIGUOUS_IDENTITY)
    if not integration_model:
        blockers.append(Blocker.NON_SAAS_TOOL)

    if technical is Dimension.FAIL:
        blockers.append(Blocker.NO_PUBLIC_API)
    elif technical is Dimension.UNCLEAR:
        blockers.append(Blocker.UNCLEAR_API)
    elif technical is Dimension.FRICTION and include_friction:
        if breadth is ApiBreadth.NARROW:
            blockers.append(Blocker.INSUFFICIENT_API_SURFACE)

    if credential is Dimension.FAIL:
        if access is CredentialAccess.PARTNER_REQUIRED:
            blockers.append(Blocker.PARTNER_REQUIRED)
        elif access in (CredentialAccess.ENTERPRISE, CredentialAccess.CONTACT_SALES):
            blockers.append(Blocker.ENTERPRISE_ONLY)
        elif access is CredentialAccess.INVITE_ONLY:
            blockers.append(Blocker.CREDENTIALS_UNAVAILABLE)
    elif credential is Dimension.UNCLEAR:
        blockers.append(Blocker.UNCLEAR_ACCESS)
    elif credential is Dimension.FRICTION and include_friction:
        if access is CredentialAccess.SELF_SERVE_PAID:
            blockers.append(Blocker.PAID_ACCESS)
        elif access is CredentialAccess.ADMIN_APPROVAL:
            blockers.append(Blocker.ADMIN_APPROVAL)

    if commercial is Dimension.FAIL:
        if AccessRestriction.PARTNER_ONLY in restrictions:
            blockers.append(Blocker.PARTNER_REQUIRED)
        if AccessRestriction.ENTERPRISE_PLAN_REQUIRED in restrictions:
            blockers.append(Blocker.ENTERPRISE_ONLY)
        if AccessRestriction.INVITE_ONLY in restrictions:
            blockers.append(Blocker.CREDENTIALS_UNAVAILABLE)
    elif commercial is Dimension.UNCLEAR:
        blockers.append(Blocker.UNCLEAR_ACCESS)
    elif commercial is Dimension.FRICTION and include_friction:
        if AccessRestriction.PAID_PLAN_REQUIRED in restrictions:
            blockers.append(Blocker.PAID_ACCESS)
        if AccessRestriction.APPROVAL_REQUIRED in restrictions:
            blockers.append(Blocker.ADMIN_APPROVAL)

    ordered: List[Blocker] = []
    for blocker in blockers:
        if blocker not in ordered:
            ordered.append(blocker)
    return ordered


def describe(
    technical: Tuple[Dimension, str],
    credential: Tuple[Dimension, str],
    commercial: Tuple[Dimension, str],
) -> str:
    """One sentence naming each leg's verdict, for the assessment's ``reason``."""
    return (
        "technical: {} ({}); credentials: {} ({}); commercial: {} ({})".format(
            technical[0].value,
            technical[1],
            credential[0].value,
            credential[1],
            commercial[0].value,
            commercial[1],
        )
    )

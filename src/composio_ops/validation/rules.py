"""Deterministic validation of a research pass.

Every check here is a pure function of the artifacts: no model, no network, no
clock. The point is to catch the failures that a fluent-sounding research pass
hides - a conclusion citing evidence that does not exist, a buildability verdict
that does not follow from its own dimensions, a confidence level that was not
computed from the recorded inputs.

Errors block the pipeline; warnings are reported and carried forward, because
"we could not establish this" is a finding rather than a fault.
"""

from typing import Dict, List, Optional, Sequence

from .. import constants as C
from ..research import buildability as bd
from ..research import confidence as conf
from ..schemas.evidence import EvidenceItem, EvidenceSet, domain_of
from ..schemas.registry import NormalizedRegistry
from ..schemas.research import AppResearchRecord, ResearchSet
from ..schemas.validation import ValidationIssue
from ..taxonomy import (
    CRITICAL_FIELDS,
    EVIDENCE_BEARING_STATUSES,
    VERIFIED_FIELDS,
    ApiBreadth,
    Blocker,
    Buildability,
    ResearchFieldName,
    ResolutionStatus,
)

#: Fields that are read off another field's page rather than their own. A single
#: API reference establishes that an API exists, what shape it has, how broad it
#: is and what it can do, so citing it for all four is correct, not sloppy.
_COMPANION_EVIDENCE: Dict[ResearchFieldName, frozenset] = {
    ResearchFieldName.API_TYPES: frozenset({ResearchFieldName.API_EXISTS}),
    ResearchFieldName.API_BREADTH: frozenset({ResearchFieldName.API_EXISTS}),
    ResearchFieldName.API_CAPABILITIES: frozenset({ResearchFieldName.API_EXISTS}),
    ResearchFieldName.ACCESS_RESTRICTIONS: frozenset(
        {ResearchFieldName.CREDENTIAL_ACCESS}
    ),
}

#: Fields that are concluded rather than read, and therefore cite the evidence
#: behind the fields they were concluded from.
_DERIVED_OR_NARRATIVE = frozenset(
    {
        ResearchFieldName.BUILDABILITY,
        ResearchFieldName.BLOCKER,
        ResearchFieldName.IDENTITY,
        ResearchFieldName.DESCRIPTION,
        ResearchFieldName.APPLICATION_TYPE,
    }
)

#: Blockers that contradict a "buildable" verdict if they appear alongside it.
_HARD_BLOCKERS = frozenset(
    {
        Blocker.NO_PUBLIC_API,
        Blocker.CREDENTIALS_UNAVAILABLE,
        Blocker.ENTERPRISE_ONLY,
        Blocker.PARTNER_REQUIRED,
    }
)


def _issue(
    code: str,
    severity: C.Severity,
    message: str,
    app_id: Optional[str] = None,
    attribute: Optional[str] = None,
    location: Optional[str] = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=severity,
        message=message,
        app_id=app_id,
        attribute=attribute,
        location=location,
    )


def check_coverage(
    registry: NormalizedRegistry, research: ResearchSet
) -> List[ValidationIssue]:
    """Every registered app must have exactly one research record, and no others."""
    issues: List[ValidationIssue] = []
    registered = set(registry.app_ids())
    researched = {record.app_id for record in research.records}
    for app_id in sorted(registered - researched):
        issues.append(
            _issue(
                "record_missing",
                C.Severity.ERROR,
                "The registry lists this app but Channel A produced no record.",
                app_id=app_id,
            )
        )
    for app_id in sorted(researched - registered):
        issues.append(
            _issue(
                "record_unregistered",
                C.Severity.ERROR,
                "A research record exists for an app that is not in the registry.",
                app_id=app_id,
            )
        )
    by_id = {record.app_id: record for record in registry.records}
    for record in research.records:
        app = by_id.get(record.app_id)
        if app is None:
            continue
        if app.category_id != record.category_id:
            issues.append(
                _issue(
                    "category_mismatch",
                    C.Severity.ERROR,
                    "The record's category does not match the supplied registry: "
                    "'{}' vs '{}'.".format(record.category_id, app.category_id),
                    app_id=record.app_id,
                )
            )
    return issues


def check_evidence(
    record: AppResearchRecord, evidence: Dict[str, EvidenceItem]
) -> List[ValidationIssue]:
    """Cited evidence must exist, belong to the app, and support what it is cited for."""
    issues: List[ValidationIssue] = []
    for name, field in record.fields():
        for evidence_id in field.evidence_ids:
            item = evidence.get(evidence_id)
            if item is None:
                issues.append(
                    _issue(
                        "evidence_missing",
                        C.Severity.ERROR,
                        "Cites evidence '{}', which does not exist.".format(evidence_id),
                        app_id=record.app_id,
                        attribute=name.value,
                    )
                )
                continue
            if item.app_id != record.app_id:
                issues.append(
                    _issue(
                        "evidence_foreign",
                        C.Severity.ERROR,
                        "Cites evidence '{}', which belongs to '{}'.".format(
                            evidence_id, item.app_id
                        ),
                        app_id=record.app_id,
                        attribute=name.value,
                    )
                )
            elif (
                name not in item.supports
                and name not in _DERIVED_OR_NARRATIVE
                and not (set(item.supports) & _COMPANION_EVIDENCE.get(name, frozenset()))
            ):
                issues.append(
                    _issue(
                        "evidence_unrelated",
                        C.Severity.WARNING,
                        "Evidence '{}' does not declare support for this field.".format(
                            evidence_id
                        ),
                        app_id=record.app_id,
                        attribute=name.value,
                    )
                )
        if field.status in EVIDENCE_BEARING_STATUSES and not field.evidence_ids:
            issues.append(
                _issue(
                    "conclusion_without_evidence",
                    C.Severity.ERROR,
                    "Status '{}' asserts a finding but cites no evidence.".format(
                        field.status.value
                    ),
                    app_id=record.app_id,
                    attribute=name.value,
                )
            )
    return issues


def check_first_party(
    record: AppResearchRecord, evidence: Dict[str, EvidenceItem]
) -> List[ValidationIssue]:
    """Critical fields resting solely on third-party pages are worth flagging."""
    issues: List[ValidationIssue] = []
    for name in CRITICAL_FIELDS:
        field = record.field(name)
        if field.status is not ResolutionStatus.RESOLVED or not field.evidence_ids:
            continue
        items = [evidence[eid] for eid in field.evidence_ids if eid in evidence]
        if items and not any(item.is_first_party for item in items):
            issues.append(
                _issue(
                    "no_first_party_evidence",
                    C.Severity.WARNING,
                    "A critical field rests only on sources the vendor did not publish.",
                    app_id=record.app_id,
                    attribute=name.value,
                )
            )
    return issues


def check_internal_consistency(record: AppResearchRecord) -> List[ValidationIssue]:
    """Recompute the derived values and insist the record agrees with itself."""
    issues: List[ValidationIssue] = []

    expected = conf.calculate(record.confidence_inputs)
    if expected is not record.confidence:
        issues.append(
            _issue(
                "confidence_not_derived",
                C.Severity.ERROR,
                "Confidence is '{}' but the recorded inputs compute '{}'.".format(
                    record.confidence.value, expected.value
                ),
                app_id=record.app_id,
                attribute="confidence",
            )
        )

    assessment = record.buildability_assessment
    status, value = bd.combine(
        assessment.technical_feasibility,
        assessment.credential_accessibility,
        assessment.commercial_accessibility,
    )
    if status is not record.buildability.status or value is not record.buildability.value:
        issues.append(
            _issue(
                "buildability_not_derived",
                C.Severity.ERROR,
                "Buildability does not follow from its own dimensions: "
                "expected {}/{}, found {}/{}.".format(
                    status.value,
                    value.value if value else "-",
                    record.buildability.status.value,
                    record.buildability.value.value if record.buildability.value else "-",
                ),
                app_id=record.app_id,
                attribute="buildability",
            )
        )

    if record.buildability.value is Buildability.BLOCKED and not record.blocker.values:
        issues.append(
            _issue(
                "blocked_without_blocker",
                C.Severity.ERROR,
                "The app is blocked but no blocker is named.",
                app_id=record.app_id,
                attribute="blocker",
            )
        )
    if record.buildability.value is Buildability.BUILDABLE:
        hard = sorted(
            item.value for item in set(record.blocker.values) & _HARD_BLOCKERS
        )
        if hard:
            issues.append(
                _issue(
                    "buildable_with_hard_blocker",
                    C.Severity.ERROR,
                    "Classified buildable while naming blocking conditions: {}.".format(
                        ", ".join(hard)
                    ),
                    app_id=record.app_id,
                    attribute="blocker",
                )
            )

    if record.api_exists.is_resolved and record.api_exists.value:
        if not record.api_types.values and record.api_types.is_resolved:
            issues.append(
                _issue(
                    "api_without_type",
                    C.Severity.ERROR,
                    "An API that exists must record at least one interface type.",
                    app_id=record.app_id,
                    attribute="api_types",
                )
            )
        if record.api_breadth.status is ResolutionStatus.NOT_APPLICABLE:
            issues.append(
                _issue(
                    "breadth_not_applicable",
                    C.Severity.ERROR,
                    "Breadth cannot be 'not applicable' for an API that exists.",
                    app_id=record.app_id,
                    attribute="api_breadth",
                )
            )
    if record.api_exists.status is ResolutionStatus.UNAVAILABLE:
        if record.api_types.is_resolved or record.api_breadth.is_resolved:
            issues.append(
                _issue(
                    "api_absent_but_described",
                    C.Severity.ERROR,
                    "No API exists, yet its shape or breadth is recorded.",
                    app_id=record.app_id,
                    attribute="api_exists",
                )
            )
    if (
        record.api_breadth.value is ApiBreadth.VERY_BROAD
        and record.api_capabilities.is_resolved
        and len(record.api_capabilities.values) < 3
    ):
        issues.append(
            _issue(
                "breadth_capability_mismatch",
                C.Severity.WARNING,
                "Very broad coverage is claimed on fewer than three capabilities.",
                app_id=record.app_id,
                attribute="api_breadth",
            )
        )
    return issues


def check_completeness(record: AppResearchRecord) -> List[ValidationIssue]:
    """Report, without blocking, the fields the pass could not establish."""
    issues: List[ValidationIssue] = []
    for name in VERIFIED_FIELDS:
        field = record.field(name)
        if field.status in (ResolutionStatus.NOT_FOUND, ResolutionStatus.UNCLEAR):
            issues.append(
                _issue(
                    "field_unresolved",
                    C.Severity.WARNING,
                    "Field is '{}': {}".format(
                        field.status.value, field.rationale or "no rationale recorded"
                    ),
                    app_id=record.app_id,
                    attribute=name.value,
                )
            )
    if not record.identity.is_resolved:
        issues.append(
            _issue(
                "identity_unresolved",
                C.Severity.WARNING,
                "The supplied name was not resolved to a single product.",
                app_id=record.app_id,
                attribute="identity",
            )
        )
    return issues


#: Two-label suffixes where the registrable name is the third label from the end.
_COMPOUND_SUFFIXES = frozenset(
    {"co.uk", "com.au", "co.nz", "co.jp", "com.br", "co.in", "com.sg"}
)


def registrable_domain(host: str) -> str:
    """The part of a host that identifies the organisation behind it.

    ``developers.google.com`` and ``workspace.google.com`` are the same vendor;
    comparing full hosts would flag every documentation subdomain as off-domain
    and drown the real finding, which is a claim resting on somebody else's site.
    """
    labels = [label for label in host.split(".") if label]
    if len(labels) <= 2:
        return ".".join(labels)
    if ".".join(labels[-2:]) in _COMPOUND_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def check_evidence_hygiene(
    record: AppResearchRecord,
    evidence: Dict[str, EvidenceItem],
    homepage_url: Optional[str],
) -> List[ValidationIssue]:
    """Flag identity claims that rest on a domain the vendor does not own."""
    issues: List[ValidationIssue] = []
    if not homepage_url:
        return issues
    expected = registrable_domain(domain_of(homepage_url))
    if not expected:
        return issues
    for evidence_id in sorted(record.identity.evidence_ids):
        item = evidence.get(evidence_id)
        if item is None:
            continue
        if item.is_first_party and registrable_domain(item.domain) != expected:
            issues.append(
                _issue(
                    "identity_evidence_offdomain",
                    C.Severity.WARNING,
                    "Identity evidence '{}' is on '{}', not the registry's '{}'.".format(
                        evidence_id, item.domain, expected
                    ),
                    app_id=record.app_id,
                    attribute="identity",
                )
            )
    return issues


def validate(
    registry: NormalizedRegistry,
    research: ResearchSet,
    evidence: EvidenceSet,
) -> List[ValidationIssue]:
    """Run every check and return the issues, sorted for a byte-stable report."""
    index = {item.evidence_id: item for item in evidence.items}
    homepages = {
        record.app_id: record.homepage_url for record in registry.records
    }

    issues: List[ValidationIssue] = list(check_coverage(registry, research))
    for record in research.records:
        issues.extend(check_evidence(record, index))
        issues.extend(check_first_party(record, index))
        issues.extend(check_internal_consistency(record))
        issues.extend(check_completeness(record))
        issues.extend(
            check_evidence_hygiene(record, index, homepages.get(record.app_id))
        )

    orphaned = sorted(
        {item.evidence_id for item in evidence.items}
        - {
            evidence_id
            for record in research.records
            for evidence_id in record.evidence_ids()
        }
    )
    for evidence_id in orphaned:
        issues.append(
            _issue(
                "evidence_uncited",
                C.Severity.WARNING,
                "Evidence was gathered but no field cites it.",
                app_id=index[evidence_id].app_id,
                location=evidence_id,
            )
        )

    return sorted(issues, key=lambda issue: issue.sort_key())


def summarize(issues: Sequence[ValidationIssue]) -> Dict[str, int]:
    """Counts by code, for logs and for the case study's validation section."""
    counts: Dict[str, int] = {}
    for issue in issues:
        counts[issue.code] = counts.get(issue.code, 0) + 1
    return dict(sorted(counts.items()))

"""Risk-based review triggers. Architecture section 4.4.

Human attention is the scarcest thing in this pipeline, so it is spent where
being wrong is both likely and consequential, not on a random slice. Each rule
below names a specific way a record can be quietly wrong; a record that trips
any of them enters the queue with the reason attached, so the reviewer starts
from a question rather than from a blank page.

The queue is uncapped on purpose. If half the registry qualifies, that is a
finding about the research pass and is reported as one.
"""

from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .. import constants as C
from ..config import Settings
from ..determinism import fingerprint
from ..schemas.base import ArtifactMetadata
from ..schemas.research import AppResearchRecord
from ..schemas.review import ReviewQueue, ReviewQueueEntry
from ..schemas.verification import VerificationResult
from ..taxonomy import (
    CRITICAL_FIELDS,
    ApiBreadth,
    ApplicationType,
    AuthMethod,
    Blocker,
    Buildability,
    ResearchFieldName,
    ResolutionStatus,
)

F = ResearchFieldName

#: Application types that the taxonomy handles well. Anything else is worth a look.
_STANDARD_TYPES = frozenset(
    {ApplicationType.SAAS_APPLICATION, ApplicationType.API_PLATFORM}
)

#: Blockers that contradict a clean "buildable" verdict.
_HARD_BLOCKERS = frozenset(
    {
        Blocker.NO_PUBLIC_API,
        Blocker.CREDENTIALS_UNAVAILABLE,
        Blocker.ENTERPRISE_ONLY,
        Blocker.PARTNER_REQUIRED,
    }
)

TriggerRule = Callable[[AppResearchRecord], Optional[Tuple[str, List[F]]]]


def _unresolved_identity(record: AppResearchRecord):
    if not record.identity.is_resolved:
        return (
            "The supplied name did not resolve to a single product, so every "
            "other field is conditional on the wrong subject.",
            [F.IDENTITY],
        )
    return None


def _low_confidence(record: AppResearchRecord):
    if record.confidence is C.Confidence.LOW:
        return (
            "The confidence function returned low from the recorded evidence "
            "properties.",
            [],
        )
    return None


def _missing_critical_evidence(record: AppResearchRecord):
    missing = [
        name
        for name in CRITICAL_FIELDS
        if not record.field(name).is_known or not record.field(name).evidence_ids
    ]
    if missing:
        return (
            "Critical fields carry no established, evidenced value: {}.".format(
                ", ".join(name.value for name in missing)
            ),
            missing,
        )
    return None


def _source_contradiction(record: AppResearchRecord):
    if record.contradictions:
        fields: List[F] = []
        for contradiction in record.contradictions:
            fields.extend(contradiction.fields)
        return (
            "Sources conflict: {}".format(record.contradictions[0].detail),
            sorted(set(fields), key=lambda item: item.value),
        )
    return None


def _internal_contradiction(record: AppResearchRecord):
    problems: List[str] = []
    fields: List[F] = []
    if record.buildability.value is Buildability.BUILDABLE and (
        set(record.blocker.values) & _HARD_BLOCKERS
    ):
        problems.append("classified buildable while naming a blocking condition")
        fields.extend([F.BUILDABILITY, F.BLOCKER])
    if (
        record.api_breadth.value is ApiBreadth.VERY_BROAD
        and record.api_capabilities.is_resolved
        and len(record.api_capabilities.values) < 3
    ):
        problems.append("very broad coverage claimed on fewer than three capabilities")
        fields.extend([F.API_BREADTH, F.API_CAPABILITIES])
    if record.mcp_details is not None and record.mcp_details.official and (
        record.mcp.value is not None and record.mcp.value.value == "third_party"
    ):
        problems.append("an official MCP server recorded as third party")
        fields.append(F.MCP)
    if problems:
        return (
            "The record disagrees with itself: {}.".format("; ".join(problems)),
            sorted(set(fields), key=lambda item: item.value),
        )
    return None


def _unclear_credential_access(record: AppResearchRecord):
    if record.credential_access.status in (
        ResolutionStatus.UNCLEAR,
        ResolutionStatus.NOT_FOUND,
    ):
        return (
            "How a developer obtains credentials could not be established, which "
            "decides buildability.",
            [F.CREDENTIAL_ACCESS],
        )
    return None


def _unclear_api(record: AppResearchRecord):
    if record.api_exists.status in (ResolutionStatus.UNCLEAR, ResolutionStatus.NOT_FOUND):
        return ("Whether a public API exists could not be established.", [F.API_EXISTS])
    if record.api_breadth.status is ResolutionStatus.UNCLEAR:
        return (
            "The API exists but its breadth could not be judged from the "
            "documentation.",
            [F.API_BREADTH],
        )
    return None


def _unusual_authentication(record: AppResearchRecord):
    if record.authentication.status is ResolutionStatus.NOT_FOUND:
        return ("No authentication mechanism is documented.", [F.AUTHENTICATION])
    if AuthMethod.OTHER in record.authentication.values:
        return (
            "Authentication does not fit the standard mechanisms.",
            [F.AUTHENTICATION],
        )
    if record.authentication.values == [AuthMethod.BASIC_AUTH]:
        return (
            "Basic authentication alone is unusual for a modern integration and "
            "is often a sign the documentation was misread.",
            [F.AUTHENTICATION],
        )
    return None


def _unclear_buildability(record: AppResearchRecord):
    if record.buildability.status is ResolutionStatus.UNCLEAR:
        return (
            "The decision tree could not conclude: {}".format(
                record.buildability_assessment.reason
            ),
            [F.BUILDABILITY],
        )
    return None


def _non_standard_application_type(record: AppResearchRecord):
    value = record.application_type.value
    if value is not None and value not in _STANDARD_TYPES:
        return (
            "Application type '{}' sits outside the common SaaS shape the "
            "taxonomy is tuned for.".format(value.value),
            [F.APPLICATION_TYPE],
        )
    return None


#: The rules, paired with the trigger they raise. Order fixes the queue's output.
RULES: Tuple[Tuple[C.ReviewTrigger, TriggerRule], ...] = (
    (C.ReviewTrigger.UNRESOLVED_IDENTITY, _unresolved_identity),
    (C.ReviewTrigger.LOW_CONFIDENCE, _low_confidence),
    (C.ReviewTrigger.MISSING_CRITICAL_EVIDENCE, _missing_critical_evidence),
    (C.ReviewTrigger.SOURCE_CONTRADICTION, _source_contradiction),
    (C.ReviewTrigger.INTERNAL_CONTRADICTION, _internal_contradiction),
    (C.ReviewTrigger.UNCLEAR_CREDENTIAL_ACCESS, _unclear_credential_access),
    (C.ReviewTrigger.UNCLEAR_API, _unclear_api),
    (C.ReviewTrigger.UNUSUAL_AUTHENTICATION, _unusual_authentication),
    (C.ReviewTrigger.UNCLEAR_BUILDABILITY, _unclear_buildability),
    (C.ReviewTrigger.NON_STANDARD_APPLICATION_TYPE, _non_standard_application_type),
)


def triggers_for(
    record: AppResearchRecord,
    verification: Sequence[VerificationResult] = (),
) -> Tuple[List[C.ReviewTrigger], List[F], List[str]]:
    """Return the triggers a record raises, the fields involved, and why."""
    triggers: List[C.ReviewTrigger] = []
    fields: List[F] = []
    details: List[str] = []

    for trigger, rule in RULES:
        outcome = rule(record)
        if outcome is None:
            continue
        detail, affected = outcome
        triggers.append(trigger)
        fields.extend(affected)
        details.append(detail)

    disagreements = sorted(
        {
            field.value
            for result in verification
            for field in result.discrepancies
        }
    )
    if disagreements:
        triggers.append(C.ReviewTrigger.VERIFICATION_DISAGREEMENT)
        fields.extend(F(value) for value in disagreements)
        details.append(
            "A verification channel disagreed on: {}.".format(", ".join(disagreements))
        )

    return (
        sorted(set(triggers), key=lambda item: item.value),
        sorted(set(fields), key=lambda item: item.value),
        details,
    )


def build_queue(
    records: Sequence[AppResearchRecord],
    settings: Settings,
    verification: Optional[Dict[str, List[VerificationResult]]] = None,
) -> ReviewQueue:
    """Assemble the review queue over a set of research records."""
    entries: List[ReviewQueueEntry] = []
    for record in records:
        triggers, fields, details = triggers_for(
            record, (verification or {}).get(record.app_id, ())
        )
        if not triggers:
            continue
        entries.append(
            ReviewQueueEntry(
                app_id=record.app_id,
                app=record.app,
                category_id=record.category_id,
                triggers=triggers,
                fields=fields,
                confidence=record.confidence,
                detail=" ".join(details),
            )
        )

    entries.sort(key=lambda entry: entry.app_id)
    return ReviewQueue(
        metadata=ArtifactMetadata(
            stage=C.PipelineStage.TRIGGER_REVIEW,
            generated_at=settings.as_of,
            seed=settings.seed,
            record_count=len(entries),
            source_fingerprint=fingerprint([entry.to_jsonable() for entry in entries]),
            notes="Risk-based review triggers over {} records.".format(len(records)),
        ),
        population_size=len(records),
        entries=entries,
    )

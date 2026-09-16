"""Running the verification channels over a sample. Architecture section 11.

Three channels, three different ways of being wrong:

* **Channel B** re-reads the sources and reaches its own conclusion, which
  catches rules that are doing too much work.
* **Channel C** audits the citations themselves, which catches values that look
  well-sourced but rest on a page that does not actually say so.
* **Channel D** is a human, which catches the things a rule cannot see at all.

None of them runs over all 100 apps: they run over the samples and the
trigger-review queue, which is what makes the cost of verification bounded.
"""

from typing import Dict, List, Optional, Sequence, Tuple

from .. import constants as C
from ..config import Settings
from ..determinism import fingerprint
from ..errors import VerificationError
from ..io_utils import read_json
from ..research.rules import derives_restrictions
from ..schemas.base import ArtifactMetadata
from ..schemas.corpus import Corpus
from ..schemas.evidence import EvidenceItem
from ..schemas.research import AppResearchRecord
from ..schemas.verification import (
    CorrectedValue,
    EvidenceCheck,
    FieldObservation,
    FieldValue,
    HumanDecision,
    HumanDecisionSet,
    VerificationArtifact,
    VerificationResult,
    to_value_key,
)
from ..taxonomy import VERIFIED_FIELDS, ResearchFieldName, ResolutionStatus
from . import independent

F = ResearchFieldName

#: A page can never say "buildable". A conclusion drawn from other fields is
#: supported when the page speaks to one of those fields.
_DERIVED_FROM: Dict[F, frozenset] = {
    F.BUILDABILITY: frozenset(
        {F.API_EXISTS, F.API_BREADTH, F.CREDENTIAL_ACCESS, F.ACCESS_RESTRICTIONS}
    ),
    F.BLOCKER: frozenset(
        {F.API_EXISTS, F.API_BREADTH, F.CREDENTIAL_ACCESS, F.ACCESS_RESTRICTIONS}
    ),
}

#: Fields that any page published by the vendor establishes simply by existing.
_ESTABLISHED_BY_FIRST_PARTY = frozenset(
    {F.IDENTITY, F.DESCRIPTION, F.APPLICATION_TYPE}
)


def supports_field(
    item: EvidenceItem, field: F, derived: Optional[Dict[F, frozenset]] = None
) -> bool:
    """Does this page support being cited for this field?"""
    declared = set(item.supports)
    if field in declared:
        return True
    mapping = derived if derived is not None else _DERIVED_FROM
    if field in mapping:
        return bool(declared & mapping[field])
    if field in _ESTABLISHED_BY_FIRST_PARTY:
        return item.is_first_party
    return False


def derived_fields_for(record: AppResearchRecord) -> Dict[F, frozenset]:
    """Which of this record's fields are conclusions rather than quotations.

    Version-dependent, because that is exactly what the improvement phase
    changed: v1 quoted access restrictions from whichever page was to hand,
    while v2 states that it concludes them from the access conditions.
    """
    mapping = dict(_DERIVED_FROM)
    if derives_restrictions(record.classifier_version):
        mapping[F.ACCESS_RESTRICTIONS] = frozenset({F.CREDENTIAL_ACCESS})
    return mapping


def current_value(record: AppResearchRecord, field: F) -> FieldValue:
    """Channel A's value for a field, in comparable form."""
    researched = record.field(field)
    return FieldValue(
        field=field,
        status=researched.status,
        value=to_value_key(researched.key()),
    )


def _observation(
    field: F, observed: FieldValue, channel_a: FieldValue
) -> FieldObservation:
    """Compare one observation with Channel A's value without seeing it first."""
    known = observed.status in (ResolutionStatus.RESOLVED, ResolutionStatus.UNAVAILABLE)
    if not known:
        outcome = C.VerificationOutcome.INCONCLUSIVE
    elif observed.matches(channel_a):
        outcome = C.VerificationOutcome.AGREES
    else:
        outcome = C.VerificationOutcome.DISAGREES
    return FieldObservation(
        field=field,
        status=observed.status,
        value=observed.value,
        outcome=outcome,
        evidence_ids=[],
        notes=None,
    )


def run_channel_b(
    records: Sequence[AppResearchRecord],
    corpus: Corpus,
    settings: Settings,
    sample_of: Optional[Dict[str, C.SampleGroup]] = None,
) -> VerificationArtifact:
    """Independent re-derivation of every verified field, per app."""
    entries = corpus.by_app()
    results: List[VerificationResult] = []

    for record in records:
        entry = entries.get(record.app_id)
        if entry is None:
            raise VerificationError(
                "Channel B has no sources for this app", app_id=record.app_id
            )
        observed = independent.observe(entry)
        observations: List[FieldObservation] = []
        discrepancies: List[F] = []
        corrections: List[CorrectedValue] = []

        for field in VERIFIED_FIELDS:
            channel_a = current_value(record, field)
            observation = _observation(field, observed[field], channel_a)
            observations.append(observation)
            if observation.outcome is C.VerificationOutcome.DISAGREES:
                discrepancies.append(field)
                corrections.append(
                    CorrectedValue(
                        field=field,
                        status=observation.status,
                        value=observation.value,
                        reason=(
                            "An independent reading of the same sources gives "
                            "'{}' where Channel A recorded '{}'.".format(
                                ", ".join(observation.value or [observation.status.value]),
                                ", ".join(channel_a.value or [channel_a.status.value]),
                            )
                        ),
                    )
                )

        observations.sort(key=lambda item: item.field.value)
        corrections.sort(key=lambda item: item.field.value)
        results.append(
            VerificationResult(
                app_id=record.app_id,
                sample=(sample_of or {}).get(record.app_id),
                channel=C.Channel.CHANNEL_B,
                field_results=observations,
                evidence_results=[],
                discrepancies=sorted(discrepancies, key=lambda item: item.value),
                corrected_values=corrections,
                reviewer=None,
                checked_at=settings.as_of,
                notes="Re-derived from the same sources with independent rules.",
            )
        )

    return _artifact(C.Channel.CHANNEL_B, results, settings)


def run_channel_c(
    records: Sequence[AppResearchRecord],
    evidence_by_app: Dict[str, List[EvidenceItem]],
    settings: Settings,
    sample_of: Optional[Dict[str, C.SampleGroup]] = None,
) -> VerificationArtifact:
    """Audit the citations: does the cited page actually support the claim?

    Offline, "reachable" means the citation resolves to a source in the reviewed
    corpus with a well-formed https URL; it is not a live fetch, and the case
    study says so. "Supports the claim" is stricter and is where this channel
    earns its keep: a page counts only for the fields it declares support for,
    so a value propped up by a neighbouring page's citation is reported as
    unsupported rather than quietly accepted.
    """
    results: List[VerificationResult] = []

    for record in records:
        items = {item.evidence_id: item for item in evidence_by_app.get(record.app_id, [])}
        checks: List[EvidenceCheck] = []
        cited_fields: Dict[str, List[F]] = {}
        for field, researched in record.fields():
            for evidence_id in researched.evidence_ids:
                cited_fields.setdefault(evidence_id, []).append(field)

        declared_by_evidence: Dict[str, set] = {}
        for evidence_id in sorted(cited_fields):
            item = items.get(evidence_id)
            if item is None:
                checks.append(
                    EvidenceCheck(
                        evidence_id=evidence_id,
                        url="https://missing.invalid/{}".format(evidence_id),
                        supports=sorted(
                            set(cited_fields[evidence_id]), key=lambda x: x.value
                        ),
                        reachable=False,
                        supports_claim=False,
                        reason="The citation does not resolve to a recorded source.",
                    )
                )
                continue
            reachable = item.url.startswith("https://") and bool(item.domain)
            requested = set(cited_fields[evidence_id])
            supported = {
                field
                for field in requested
                if supports_field(item, field, derived_fields_for(record))
            }
            declared_by_evidence[evidence_id] = supported
            supports_claim = supported == requested
            checks.append(
                EvidenceCheck(
                    evidence_id=evidence_id,
                    url=item.url,
                    supports=sorted(requested, key=lambda x: x.value),
                    reachable=reachable,
                    supports_claim=supports_claim,
                    reason=(
                        "The source supports every field it is cited for: {}.".format(
                            ", ".join(sorted(x.value for x in supported))
                        )
                        if supports_claim
                        else "The source does not support {}.".format(
                            ", ".join(sorted(x.value for x in requested - supported))
                        )
                    ),
                )
            )

        observations: List[FieldObservation] = []
        discrepancies: List[F] = []
        for field in VERIFIED_FIELDS:
            researched = record.field(field)
            valid = [
                check
                for check in checks
                if field in check.supports
                and check.reachable
                and field in declared_by_evidence.get(check.evidence_id, set())
            ]
            channel_a = current_value(record, field)
            if researched.status is ResolutionStatus.RESOLVED and not valid:
                observations.append(
                    FieldObservation(
                        field=field,
                        status=ResolutionStatus.UNCLEAR,
                        value=None,
                        outcome=C.VerificationOutcome.INCONCLUSIVE,
                        evidence_ids=[],
                        notes="No cited page declares support for this field.",
                    )
                )
                discrepancies.append(field)
            elif valid:
                observations.append(
                    FieldObservation(
                        field=field,
                        status=channel_a.status,
                        value=channel_a.value,
                        outcome=C.VerificationOutcome.AGREES,
                        evidence_ids=sorted(check.evidence_id for check in valid),
                        notes="The cited pages declare support for this field.",
                    )
                )
            else:
                observations.append(
                    FieldObservation(
                        field=field,
                        status=ResolutionStatus.NOT_FOUND,
                        value=None,
                        outcome=C.VerificationOutcome.INCONCLUSIVE,
                        evidence_ids=[],
                        notes="Nothing was cited for this field to audit.",
                    )
                )

        observations.sort(key=lambda item: item.field.value)
        results.append(
            VerificationResult(
                app_id=record.app_id,
                sample=(sample_of or {}).get(record.app_id),
                channel=C.Channel.CHANNEL_C,
                field_results=observations,
                evidence_results=sorted(checks, key=lambda item: item.evidence_id),
                discrepancies=sorted(discrepancies, key=lambda item: item.value),
                corrected_values=[],
                reviewer=None,
                checked_at=settings.as_of,
                notes=(
                    "Citation audit: the cited source must itself declare support "
                    "for the field it is cited for."
                ),
            )
        )

    return _artifact(C.Channel.CHANNEL_C, results, settings)


def load_ground_truth(settings: Settings) -> Dict[str, object]:
    """The reviewer's established values, recorded once and applied per app."""
    path = settings.paths.ground_truth
    if not path.exists():
        return {"reviewer": "product-ops-reviewer", "overrides": []}
    payload = read_json(path)
    if not isinstance(payload, dict) or "overrides" not in payload:
        raise VerificationError(
            "Ground truth must be an object with an 'overrides' array",
            path=str(path),
        )
    return payload


def run_channel_d(
    records: Sequence[AppResearchRecord],
    settings: Settings,
    sample_of: Optional[Dict[str, C.SampleGroup]] = None,
    fields_by_app: Optional[Dict[str, Sequence[F]]] = None,
) -> Tuple[VerificationArtifact, HumanDecisionSet]:
    """Human review: confirm what holds up, correct what does not, say which.

    The reviewer's conclusions live in ``data/corpus/ground_truth.json`` so they
    are versioned, attributable and replayable, rather than typed into a console
    once and lost.

    ``fields_by_app`` is what keeps human review affordable: by default the
    reviewer looks only at the fields the other channels put in dispute or the
    triggers flagged, not at all eleven fields of all thirty apps.
    """
    payload = load_ground_truth(settings)
    reviewer = str(payload.get("reviewer") or "product-ops-reviewer")
    overrides: Dict[str, Dict[str, dict]] = {}
    for item in payload.get("overrides", []):
        overrides.setdefault(item["app_id"], {})[item["field"]] = item

    results: List[VerificationResult] = []
    decisions: List[HumanDecision] = []

    for record in records:
        app_overrides = overrides.get(record.app_id, {})
        observations: List[FieldObservation] = []
        discrepancies: List[F] = []
        corrections: List[CorrectedValue] = []
        reviewed = (
            list(fields_by_app.get(record.app_id, ()))
            if fields_by_app is not None
            else list(VERIFIED_FIELDS)
        )

        for field in reviewed:
            channel_a = current_value(record, field)
            override = app_overrides.get(field.value)
            if override is None:
                # No recorded human judgement means no human authority. Silence
                # here is what keeps reconciliation from rubber-stamping Channel
                # A's own answer as though a reviewer had endorsed it.
                continue

            status = ResolutionStatus(override["status"])
            value = override.get("value")
            observed = FieldValue(field=field, status=status, value=value)
            same = observed.matches(channel_a)
            observations.append(
                FieldObservation(
                    field=field,
                    status=status,
                    value=value,
                    outcome=(
                        C.VerificationOutcome.AGREES
                        if same
                        else C.VerificationOutcome.DISAGREES
                    )
                    if status
                    in (ResolutionStatus.RESOLVED, ResolutionStatus.UNAVAILABLE)
                    else C.VerificationOutcome.INCONCLUSIVE,
                    evidence_ids=sorted(override.get("evidence_ids", [])),
                    notes=override.get("reason"),
                )
            )
            if same:
                decisions.append(
                    HumanDecision(
                        app_id=record.app_id,
                        field=field,
                        decision=C.ReviewDecision.CONFIRM,
                        entry_path="sample",
                        original_status=channel_a.status,
                        original_value=channel_a.value,
                        reason=override.get("reason", "Confirmed against the sources."),
                        evidence_ids=sorted(override.get("evidence_ids", [])),
                        reviewer=reviewer,
                        decided_at=settings.as_of,
                    )
                )
                continue

            discrepancies.append(field)
            corrections.append(
                CorrectedValue(
                    field=field,
                    status=status,
                    value=value,
                    reason=override.get("reason", "Corrected on review."),
                )
            )
            decisions.append(
                HumanDecision(
                    app_id=record.app_id,
                    field=field,
                    decision=(
                        C.ReviewDecision.UNCLEAR
                        if status is ResolutionStatus.UNCLEAR
                        else C.ReviewDecision.CORRECT
                    ),
                    entry_path="sample",
                    original_status=channel_a.status,
                    original_value=channel_a.value,
                    corrected_status=None
                    if status is ResolutionStatus.UNCLEAR
                    else status,
                    corrected_value=None if status is ResolutionStatus.UNCLEAR else value,
                    reason=override.get("reason", "Corrected on review."),
                    evidence_ids=sorted(override.get("evidence_ids", [])),
                    reviewer=reviewer,
                    decided_at=settings.as_of,
                )
            )

        if not observations:
            continue
        observations.sort(key=lambda item: item.field.value)
        corrections.sort(key=lambda item: item.field.value)
        results.append(
            VerificationResult(
                app_id=record.app_id,
                sample=(sample_of or {}).get(record.app_id),
                channel=C.Channel.CHANNEL_D,
                field_results=observations,
                evidence_results=[],
                discrepancies=sorted(discrepancies, key=lambda item: item.value),
                corrected_values=corrections,
                reviewer=reviewer,
                checked_at=settings.as_of,
                notes="Human review against the recorded sources.",
            )
        )

    decisions.sort(key=lambda item: (item.app_id, item.field.value))
    decision_set = HumanDecisionSet(
        metadata=ArtifactMetadata(
            stage=C.PipelineStage.VERIFICATION,
            generated_at=settings.as_of,
            seed=settings.seed,
            record_count=len(decisions),
            source_fingerprint=fingerprint(
                [item.to_jsonable() for item in decisions]
            ),
            notes="Channel D decisions by {}.".format(reviewer),
        ),
        decisions=decisions,
    )
    return _artifact(C.Channel.CHANNEL_D, results, settings), decision_set


def _artifact(
    channel: C.Channel, results: List[VerificationResult], settings: Settings
) -> VerificationArtifact:
    results.sort(key=lambda item: item.app_id)
    return VerificationArtifact(
        metadata=ArtifactMetadata(
            stage=C.PipelineStage.VERIFICATION,
            generated_at=settings.as_of,
            seed=settings.seed,
            record_count=len(results),
            source_fingerprint=fingerprint([item.to_jsonable() for item in results]),
            notes="{}: {}".format(channel.value, C.CHANNEL_LABELS[channel]),
        ),
        channel=channel,
        results=results,
    )

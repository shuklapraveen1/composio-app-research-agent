"""Reconciliation: turning four channels' answers into one. Architecture section 12.

Precedence is fixed in advance, and it is not "whoever is most confident":

1. A human decision settles a field, because Channel D is the only channel that
   can read a page and notice that it does not mean what it appears to mean.
2. Two independent channels disagreeing with Channel A outweigh Channel A.
3. One channel disagreeing does not overturn a value - it destroys the claim to
   know it, so a single-valued field is downgraded to ``unclear`` rather than
   flipped.
4. A multi-valued field is reconciled as a set: when both readings are supported
   the union is the answer, because "OAuth 2.0 and API keys" is not a
   disagreement about which one is true.
5. A value whose citations do not survive the audit is downgraded, however
   plausible it looks.
"""

from typing import Dict, List, Optional, Sequence, Tuple

from .. import constants as C
from ..config import Settings
from ..determinism import fingerprint
from ..schemas.base import ArtifactMetadata
from ..schemas.research import AppResearchRecord
from ..schemas.verification import (
    FieldValue,
    HumanDecision,
    ReconciliationDecision,
    ReconciliationSet,
    VerificationResult,
)
from ..taxonomy import (
    MULTI_VALUED_FIELDS,
    VERIFIED_FIELDS,
    ResearchFieldName,
    ResolutionStatus,
)
from .channels import current_value

F = ResearchFieldName


def cardinality_of(field: F) -> str:
    return "multi" if field in MULTI_VALUED_FIELDS else "single"


def _union(first: FieldValue, second: FieldValue, field: F) -> FieldValue:
    """Set union of two resolved multi-valued readings."""
    tokens = sorted(set(first.value or []) | set(second.value or []))
    return FieldValue(field=field, status=ResolutionStatus.RESOLVED, value=tokens)


def _known(value: Optional[FieldValue]) -> bool:
    return value is not None and value.status in (
        ResolutionStatus.RESOLVED,
        ResolutionStatus.UNAVAILABLE,
    )


def reconcile_field(
    field: F,
    channel_a: FieldValue,
    channel_b: Optional[FieldValue],
    channel_c_valid: Optional[bool],
    human: Optional[HumanDecision],
) -> Tuple[C.ReconciliationOutcome, FieldValue, C.Channel, Optional[C.Channel], str]:
    """Apply the precedence rules to one field. Total: every input has an outcome."""
    if human is not None:
        established = human.established()
        if human.decision is C.ReviewDecision.CORRECT:
            return (
                C.ReconciliationOutcome.CORRECTED,
                established,
                C.Channel.CHANNEL_D,
                C.Channel.CHANNEL_A,
                "Human review corrected the value: {}".format(human.reason),
            )
        if human.decision is C.ReviewDecision.UNCLEAR:
            return (
                C.ReconciliationOutcome.DOWNGRADED_TO_UNCLEAR,
                FieldValue(field=field, status=ResolutionStatus.UNCLEAR),
                C.Channel.CHANNEL_D,
                C.Channel.CHANNEL_A,
                "Human review could not establish the value: {}".format(human.reason),
            )
        return (
            C.ReconciliationOutcome.CONFIRMED,
            established,
            C.Channel.CHANNEL_D,
            None,
            "Human review confirmed the value: {}".format(human.reason),
        )

    disagrees = _known(channel_b) and not channel_b.matches(channel_a)

    if disagrees and channel_c_valid is False:
        # Two channels against one: the independent reading disagrees and the
        # citations behind Channel A's value did not survive the audit.
        return (
            C.ReconciliationOutcome.CORRECTED,
            channel_b,
            C.Channel.CHANNEL_B,
            C.Channel.CHANNEL_A,
            "An independent reading disagreed and the cited evidence did not "
            "support the original value.",
        )

    if disagrees:
        if cardinality_of(field) == "multi" and _known(channel_a):
            merged = _union(channel_a, channel_b, field)
            if merged.matches(channel_a):
                return (
                    C.ReconciliationOutcome.CONFIRMED,
                    channel_a,
                    C.Channel.CHANNEL_A,
                    None,
                    "The independent reading is a subset of the recorded values.",
                )
            return (
                C.ReconciliationOutcome.CORRECTED,
                merged,
                C.Channel.CHANNEL_B,
                C.Channel.CHANNEL_A,
                "Multi-valued field reconciled as the union of two supported "
                "readings.",
            )
        return (
            C.ReconciliationOutcome.DOWNGRADED_TO_UNCLEAR,
            FieldValue(field=field, status=ResolutionStatus.UNCLEAR),
            C.Channel.CHANNEL_B,
            C.Channel.CHANNEL_A,
            "One independent channel disagreed, which is enough to lose the "
            "claim to know the value but not enough to replace it.",
        )

    if channel_c_valid is False and channel_a.status is ResolutionStatus.RESOLVED:
        return (
            C.ReconciliationOutcome.DOWNGRADED_TO_UNCLEAR,
            FieldValue(field=field, status=ResolutionStatus.UNCLEAR),
            C.Channel.CHANNEL_C,
            C.Channel.CHANNEL_A,
            "No cited page supports this field, so the value is not established.",
        )

    if _known(channel_a):
        return (
            C.ReconciliationOutcome.CONFIRMED,
            channel_a,
            C.Channel.CHANNEL_B if channel_b is not None else C.Channel.CHANNEL_A,
            None,
            "Independent checks agree with the recorded value.",
        )

    return (
        C.ReconciliationOutcome.UNRESOLVED,
        channel_a,
        C.Channel.CHANNEL_A,
        None,
        "No channel could establish the value.",
    )


def reconcile(
    records: Sequence[AppResearchRecord],
    results: Dict[str, List[VerificationResult]],
    decisions: Sequence[HumanDecision],
    settings: Settings,
    fields: Sequence[F] = VERIFIED_FIELDS,
) -> ReconciliationSet:
    """Reconcile every verified field of every verified app."""
    human_index: Dict[Tuple[str, str], HumanDecision] = {
        (item.app_id, item.field.value): item for item in decisions
    }

    outcomes: List[ReconciliationDecision] = []
    for record in records:
        app_results = results.get(record.app_id, [])
        by_channel = {result.channel: result for result in app_results}
        channel_b = by_channel.get(C.Channel.CHANNEL_B)
        channel_c = by_channel.get(C.Channel.CHANNEL_C)

        for field in fields:
            channel_a = current_value(record, field)
            b_value = None
            if channel_b is not None:
                observation = channel_b.observation(field)
                if observation is not None:
                    b_value = observation.as_field_value()

            c_valid: Optional[bool] = None
            if channel_c is not None:
                observation = channel_c.observation(field)
                if observation is not None:
                    c_valid = observation.outcome is C.VerificationOutcome.AGREES

            outcome, value, authoritative, superseded, rationale = reconcile_field(
                field=field,
                channel_a=channel_a,
                channel_b=b_value,
                channel_c_valid=c_valid,
                human=human_index.get((record.app_id, field.value)),
            )
            outcomes.append(
                ReconciliationDecision(
                    app_id=record.app_id,
                    field=field,
                    outcome=outcome,
                    cardinality=cardinality_of(field),
                    final_status=value.status,
                    final_value=value.value,
                    authoritative_channel=authoritative,
                    superseded_channel=superseded,
                    rationale=rationale,
                    decided_at=settings.as_of,
                    decided_by=(
                        human_index[(record.app_id, field.value)].reviewer
                        if (record.app_id, field.value) in human_index
                        else None
                    ),
                )
            )

    outcomes.sort(key=lambda item: (item.app_id, item.field.value))
    return ReconciliationSet(
        metadata=ArtifactMetadata(
            stage=C.PipelineStage.RECONCILIATION,
            generated_at=settings.as_of,
            seed=settings.seed,
            record_count=len(outcomes),
            source_fingerprint=fingerprint([item.to_jsonable() for item in outcomes]),
            notes="Reconciled {} fields across {} apps.".format(
                len(outcomes), len(records)
            ),
        ),
        decisions=outcomes,
    )


def established_values(
    reconciliation: ReconciliationSet,
) -> Dict[str, Dict[F, FieldValue]]:
    """The reconciled truth, keyed by app and field, for the accuracy protocol."""
    truth: Dict[str, Dict[F, FieldValue]] = {}
    for decision in reconciliation.decisions:
        truth.setdefault(decision.app_id, {})[decision.field] = FieldValue(
            field=decision.field,
            status=decision.final_status,
            value=decision.final_value,
        )
    return truth

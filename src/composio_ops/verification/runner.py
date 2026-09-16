"""Orchestrating verification over a sample.

The order matters and is the point: the cheap independent channels run first and
decide where the expensive one looks. Channel D only sees the fields that
Channel B or Channel C put in dispute, or that the review triggers flagged, so
human attention scales with the number of doubtful values rather than with the
size of the registry.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set

from .. import constants as C
from ..config import Settings
from ..schemas.corpus import Corpus
from ..schemas.evidence import EvidenceItem, EvidenceSet
from ..schemas.research import AppResearchRecord, ResearchSet
from ..schemas.review import ReviewQueue
from ..schemas.verification import (
    HumanDecisionSet,
    ReconciliationSet,
    SampleSelection,
    VerificationArtifact,
    VerificationResult,
)
from ..taxonomy import VERIFIED_FIELDS, ResearchFieldName
from . import channels
from .reconcile import reconcile as reconcile_fields

F = ResearchFieldName


@dataclass(frozen=True)
class VerificationRun:
    """Everything one verification pass produced."""

    group: C.SampleGroup
    channel_b: VerificationArtifact
    channel_c: VerificationArtifact
    channel_d: VerificationArtifact
    human_decisions: HumanDecisionSet
    reconciliation: ReconciliationSet

    def results_by_app(self) -> Dict[str, List[VerificationResult]]:
        grouped: Dict[str, List[VerificationResult]] = {}
        for artifact in (self.channel_b, self.channel_c, self.channel_d):
            for result in artifact.results:
                grouped.setdefault(result.app_id, []).append(result)
        for results in grouped.values():
            results.sort(key=lambda item: item.channel.value)
        return grouped

    def all_results(self) -> List[VerificationResult]:
        return [
            result
            for results in self.results_by_app().values()
            for result in results
        ]


def disputed_fields(
    app_id: str,
    results: Sequence[VerificationResult],
    queue: Optional[ReviewQueue] = None,
    overrides: Optional[Dict[str, Set[str]]] = None,
) -> List[F]:
    """Which fields deserve a human: disputed, triggered, or already ruled on."""
    fields: Set[F] = set()
    for result in results:
        fields.update(result.discrepancies)
    if queue is not None:
        for entry in queue.entries:
            if entry.app_id == app_id:
                fields.update(field for field in entry.fields if field in VERIFIED_FIELDS)
    for name in (overrides or {}).get(app_id, set()):
        try:
            field = F(name)
        except ValueError:
            continue
        if field in VERIFIED_FIELDS:
            fields.add(field)
    return sorted(fields, key=lambda item: item.value)


def verify(
    selection: SampleSelection,
    research: ResearchSet,
    evidence: EvidenceSet,
    corpus: Corpus,
    settings: Settings,
    queue: Optional[ReviewQueue] = None,
) -> VerificationRun:
    """Run channels B, C and D over one sample, then reconcile them."""
    sampled = set(selection.app_ids())
    records = [record for record in research.records if record.app_id in sampled]
    groups = {app_id: selection.group for app_id in sampled}

    evidence_by_app: Dict[str, List[EvidenceItem]] = {}
    for item in evidence.items:
        if item.app_id in sampled:
            evidence_by_app.setdefault(item.app_id, []).append(item)

    channel_b = channels.run_channel_b(records, corpus, settings, groups)
    channel_c = channels.run_channel_c(records, evidence_by_app, settings, groups)

    payload = channels.load_ground_truth(settings)
    overrides: Dict[str, Set[str]] = {}
    for item in payload.get("overrides", []):
        overrides.setdefault(item["app_id"], set()).add(item["field"])

    interim: Dict[str, List[VerificationResult]] = {}
    for artifact in (channel_b, channel_c):
        for result in artifact.results:
            interim.setdefault(result.app_id, []).append(result)

    fields_by_app = {
        record.app_id: disputed_fields(
            record.app_id, interim.get(record.app_id, []), queue, overrides
        )
        for record in records
    }
    channel_d, decisions = channels.run_channel_d(
        [record for record in records if fields_by_app.get(record.app_id)],
        settings,
        groups,
        fields_by_app=fields_by_app,
    )

    results_by_app: Dict[str, List[VerificationResult]] = {
        app_id: list(results) for app_id, results in interim.items()
    }
    for result in channel_d.results:
        results_by_app.setdefault(result.app_id, []).append(result)
    for results in results_by_app.values():
        results.sort(key=lambda item: item.channel.value)

    reconciliation = reconcile_fields(
        records=records,
        results=results_by_app,
        decisions=decisions.decisions,
        settings=settings,
    )

    return VerificationRun(
        group=selection.group,
        channel_b=channel_b,
        channel_c=channel_c,
        channel_d=channel_d,
        human_decisions=decisions,
        reconciliation=reconciliation,
    )


def apply_verification_state(
    records: Sequence[AppResearchRecord],
    run: VerificationRun,
) -> List[AppResearchRecord]:
    """Stamp each verified record with what verification concluded about it.

    Records are immutable, so this returns new ones; the dataset is assembled
    from the result rather than mutated in place.
    """
    results = run.results_by_app()
    corrected_by_app: Dict[str, List[F]] = {}
    for decision in run.reconciliation.decisions:
        if decision.outcome in (
            C.ReconciliationOutcome.CORRECTED,
            C.ReconciliationOutcome.DOWNGRADED_TO_UNCLEAR,
        ):
            corrected_by_app.setdefault(decision.app_id, []).append(decision.field)

    updated: List[AppResearchRecord] = []
    for record in records:
        app_results = results.get(record.app_id)
        if not app_results:
            updated.append(record)
            continue
        discrepancies = sorted(
            {field for result in app_results for field in result.discrepancies},
            key=lambda item: item.value,
        )
        corrected = corrected_by_app.get(record.app_id, [])
        status = (
            C.VerificationStatus.CORRECTED
            if corrected
            else C.VerificationStatus.VERIFIED
        )
        updated.append(
            record.model_copy(
                update={
                    "verification": record.verification.model_copy(
                        update={
                            "status": status,
                            "channels": [result.channel for result in app_results],
                            "sample": run.group,
                            "discrepancies": discrepancies,
                            "corrected": bool(corrected),
                        }
                    )
                }
            )
        )
    return updated

"""Assembling the canonical dataset.

There is one dataset type and two instances of it: the initial dataset, which is
Channel A plus deterministic validation, and the final dataset, which is the
same records after verification and reconciliation. Building both through one
function is what keeps the promise that nothing downstream can read a different
shape depending on which stage produced it.
"""

from typing import Dict, Iterable, List, Optional, Sequence

from . import constants as C
from .config import Settings
from .determinism import fingerprint
from .schemas.base import ArtifactMetadata
from .schemas.dataset import Dataset, DatasetRecord
from .schemas.evidence import EvidenceSet
from .schemas.registry import NormalizedRegistry
from .schemas.research import ResearchSet
from .schemas.verification import (
    FieldValue,
    ReconciliationDecision,
    VerificationResult,
    to_value_key,
)
from .taxonomy import ResearchFieldName


def build_dataset(
    registry: NormalizedRegistry,
    research: ResearchSet,
    evidence: EvidenceSet,
    settings: Settings,
    stage: C.DatasetStage,
    verification: Optional[Sequence[VerificationResult]] = None,
    reconciliation: Optional[Sequence[ReconciliationDecision]] = None,
    sample_groups: Optional[Dict[str, C.SampleGroup]] = None,
    notes: str = "",
) -> Dataset:
    """Join registry, research, evidence and verification into one dataset."""
    apps = {record.app_id: record for record in registry.records}
    evidence_by_app: Dict[str, List] = {}
    for item in evidence.items:
        evidence_by_app.setdefault(item.app_id, []).append(item)

    verification_by_app: Dict[str, List[VerificationResult]] = {}
    for result in verification or ():
        verification_by_app.setdefault(result.app_id, []).append(result)
    reconciliation_by_app: Dict[str, List[ReconciliationDecision]] = {}
    for decision in reconciliation or ():
        reconciliation_by_app.setdefault(decision.app_id, []).append(decision)

    records: List[DatasetRecord] = []
    for research_record in research.records:
        app = apps.get(research_record.app_id)
        if app is None:
            raise ValueError(
                "research record '{}' has no registry entry".format(
                    research_record.app_id
                )
            )
        items = sorted(
            evidence_by_app.get(app.app_id, []), key=lambda item: item.evidence_id
        )
        results = sorted(
            verification_by_app.get(app.app_id, []), key=lambda item: item.channel.value
        )
        decisions = sorted(
            reconciliation_by_app.get(app.app_id, []),
            key=lambda item: item.field.value,
        )
        records.append(
            DatasetRecord(
                app=app,
                research=research_record,
                evidence=items,
                sample_group=(sample_groups or {}).get(app.app_id),
                verification=results,
                reconciliation=decisions,
            )
        )

    records.sort(key=lambda record: record.app_id)
    classifier_versions = {record.research.classifier_version for record in records}
    providers = {record.research.provider for record in records}

    return Dataset(
        metadata=ArtifactMetadata(
            stage=C.PipelineStage.INITIAL_DATASET
            if stage is C.DatasetStage.INITIAL
            else C.PipelineStage.FINAL_DATASET,
            generated_at=settings.as_of,
            seed=settings.seed,
            record_count=len(records),
            source_fingerprint=fingerprint(
                [record.research.to_jsonable() for record in records]
            ),
            notes=notes,
        ),
        stage=stage,
        classifier_version=(
            sorted(classifier_versions)[0] if len(classifier_versions) == 1 else "mixed"
        ),
        provider=sorted(providers, key=lambda item: item.value)[0]
        if providers
        else C.ResearchProvider.CORPUS,
        categories=list(registry.categories),
        records=records,
    )


def final_value(record: DatasetRecord, field: ResearchFieldName) -> FieldValue:
    """The dataset's answer for one field: reconciled where verification spoke.

    Everything downstream - analytics, exports, the case study - reads values
    through here, so a corrected value cannot be reported in one place and the
    original in another.
    """
    for decision in record.reconciliation:
        if decision.field is field:
            return FieldValue(
                field=field,
                status=decision.final_status,
                value=decision.final_value,
            )
    researched = record.research.field(field)
    return FieldValue(
        field=field, status=researched.status, value=to_value_key(researched.key())
    )


def research_set_from(dataset: Dataset, settings: Settings) -> ResearchSet:
    """Recover the research records from a dataset, for stages that only need them."""
    records = [record.research for record in dataset.records]
    return ResearchSet(
        metadata=ArtifactMetadata(
            stage=C.PipelineStage.CLASSIFICATION,
            generated_at=settings.as_of,
            seed=settings.seed,
            record_count=len(records),
            source_fingerprint=dataset.metadata.source_fingerprint,
            notes="Recovered from the {} dataset.".format(dataset.stage.value),
        ),
        records=records,
    )


def evidence_set_from(dataset: Dataset, settings: Settings) -> EvidenceSet:
    """Recover the evidence from a dataset."""
    items = sorted(
        (item for record in dataset.records for item in record.evidence),
        key=lambda item: item.evidence_id,
    )
    return EvidenceSet(
        metadata=ArtifactMetadata(
            stage=C.PipelineStage.EVIDENCE_EXTRACTION,
            generated_at=settings.as_of,
            seed=settings.seed,
            record_count=len(items),
            source_fingerprint=dataset.metadata.source_fingerprint,
            notes="Recovered from the {} dataset.".format(dataset.stage.value),
        ),
        items=items,
    )


def app_names(dataset: Dataset) -> Dict[str, str]:
    """App id to display name, for reports that render names rather than ids."""
    return {record.app_id: record.app.name for record in dataset.records}


def category_names(dataset: Dataset) -> Dict[str, str]:
    return {category.category_id: category.name for category in dataset.categories}


def iter_records(dataset: Dataset, app_ids: Optional[Iterable[str]] = None):
    """Iterate dataset records, optionally restricted to a set of app ids."""
    wanted = set(app_ids) if app_ids is not None else None
    for record in dataset.records:
        if wanted is None or record.app_id in wanted:
            yield record

"""Canonical dataset schemas.

There is exactly one final dataset. Analytics, the accuracy report, and the
published case study all read from it and never from an intermediate artifact,
which is why the record type carries its evidence and verification trail inline.
"""

from typing import List, Optional

from pydantic import Field, model_validator

from .. import constants as C
from .base import ArtifactMetadata, NonEmptyStr, StrictModel
from .evidence import EvidenceItem
from .registry import Category, NormalizedAppRecord
from .research import AppResearchRecord
from .verification import ReconciliationDecision, VerificationResult


class DatasetRecord(StrictModel):
    """Everything known about one app, self-contained."""

    app: NormalizedAppRecord
    research: AppResearchRecord
    evidence: List[EvidenceItem] = Field(default_factory=list)
    sample_group: Optional[C.SampleGroup] = None
    verification: List[VerificationResult] = Field(default_factory=list)
    reconciliation: List[ReconciliationDecision] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_internal_consistency(self) -> "DatasetRecord":
        app_id = self.app.app_id
        if self.research.app_id != app_id:
            raise ValueError("research record app_id does not match the app record")
        if self.research.category_id != self.app.category_id:
            raise ValueError("research record category does not match the registry")

        for item in self.evidence:
            if item.app_id != app_id:
                raise ValueError("evidence item belongs to a different app")
        for result in self.verification:
            if result.app_id != app_id:
                raise ValueError("verification result belongs to a different app")
        for decision in self.reconciliation:
            if decision.app_id != app_id:
                raise ValueError("reconciliation decision belongs to a different app")

        evidence_ids = [item.evidence_id for item in self.evidence]
        if evidence_ids != sorted(evidence_ids):
            raise ValueError("evidence must be sorted by evidence_id")
        available = set(evidence_ids)
        missing = sorted(self.research.evidence_ids() - available)
        if missing:
            raise ValueError(
                "research cites evidence not present on the record: {}".format(
                    ", ".join(missing[:5])
                )
            )

        channels = [result.channel.value for result in self.verification]
        if len(set(channels)) != len(channels):
            raise ValueError("at most one verification result per channel")
        if channels != sorted(channels):
            raise ValueError("verification results must be sorted by channel")

        triggered = bool(self.research.verification.triggers)
        if self.verification and self.sample_group is None and not triggered:
            raise ValueError(
                "verification runs over sampled or trigger-reviewed apps only"
            )
        if (
            self.research.verification.sample is not None
            and self.research.verification.sample is not self.sample_group
        ):
            raise ValueError("verification metadata disagrees with the sample group")
        return self

    @property
    def app_id(self) -> str:
        return self.app.app_id


class Dataset(StrictModel):
    """A canonical dataset: either the initial one or the final one."""

    metadata: ArtifactMetadata
    stage: C.DatasetStage
    classifier_version: NonEmptyStr
    provider: C.ResearchProvider
    categories: List[Category] = Field(default_factory=list)
    records: List[DatasetRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_records(self) -> "Dataset":
        if self.metadata.record_count != len(self.records):
            raise ValueError("metadata.record_count does not match the number of records")

        app_ids = [record.app_id for record in self.records]
        if len(set(app_ids)) != len(app_ids):
            raise ValueError("app_id values must be unique")
        if app_ids != sorted(app_ids):
            raise ValueError("records must be sorted by app_id for canonical output")

        category_ids = [category.category_id for category in self.categories]
        if category_ids != sorted(category_ids):
            raise ValueError("categories must be sorted by category_id")

        known = set(category_ids)
        unknown = sorted({record.app.category_id for record in self.records} - known)
        if unknown:
            raise ValueError(
                "records reference categories that are not declared: {}".format(
                    ", ".join(unknown)
                )
            )
        return self

    def record_for(self, app_id: str) -> Optional[DatasetRecord]:
        for record in self.records:
            if record.app_id == app_id:
                return record
        return None

    def app_ids(self) -> List[str]:
        return [record.app_id for record in self.records]

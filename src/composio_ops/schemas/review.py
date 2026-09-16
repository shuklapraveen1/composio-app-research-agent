"""Trigger-review queue and improvement-phase schemas.

Architecture sections 4.4 and 4.6. Trigger review is risk-based and deliberately
uncapped: if too many records qualify, that is reported as a workload finding
rather than silently truncated.
"""

from typing import List, Optional

from pydantic import Field, model_validator

from .. import constants as C
from ..taxonomy import ResearchFieldName
from .base import AppId, ArtifactMetadata, NonEmptyStr, StrictModel


class ReviewQueueEntry(StrictModel):
    """One record that risk rules pulled into the human review queue."""

    app_id: AppId
    app: NonEmptyStr
    category_id: NonEmptyStr
    triggers: List[C.ReviewTrigger] = Field(min_length=1)
    fields: List[ResearchFieldName] = Field(default_factory=list)
    confidence: C.Confidence
    detail: NonEmptyStr

    @model_validator(mode="after")
    def _sorted(self) -> "ReviewQueueEntry":
        triggers = [item.value for item in self.triggers]
        if len(set(triggers)) != len(triggers):
            raise ValueError("triggers must be unique")
        if triggers != sorted(triggers):
            raise ValueError("triggers must be sorted")
        fields = [item.value for item in self.fields]
        if fields != sorted(fields):
            raise ValueError("fields must be sorted")
        return self


class ReviewQueue(StrictModel):
    """Every record flagged for human attention, with the rule that flagged it."""

    metadata: ArtifactMetadata
    population_size: int = Field(ge=0)
    entries: List[ReviewQueueEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_entries(self) -> "ReviewQueue":
        if self.metadata.record_count != len(self.entries):
            raise ValueError("metadata.record_count does not match the number of entries")
        app_ids = [entry.app_id for entry in self.entries]
        if len(set(app_ids)) != len(app_ids):
            raise ValueError("an app may appear at most once in the queue")
        if app_ids != sorted(app_ids):
            raise ValueError("entries must be sorted by app_id")
        if len(self.entries) > self.population_size:
            raise ValueError("queue is larger than the population")
        return self

    def app_ids(self) -> List[str]:
        return [entry.app_id for entry in self.entries]

    @property
    def share(self) -> Optional[float]:
        if self.population_size == 0:
            return None
        return round(len(self.entries) / self.population_size, 4)


class Improvement(StrictModel):
    """One change made in response to an observed Sample A failure mode.

    Every improvement names the failure it answers, so the improvement phase is
    diagnosis-driven rather than arbitrary prompt tuning.
    """

    key: NonEmptyStr
    failure_mode: NonEmptyStr
    fields: List[ResearchFieldName] = Field(min_length=1)
    observed_in_sample_a: int = Field(ge=0)
    change: NonEmptyStr
    implemented_in: NonEmptyStr

    @model_validator(mode="after")
    def _sorted_fields(self) -> "Improvement":
        fields = [item.value for item in self.fields]
        if fields != sorted(fields):
            raise ValueError("fields must be sorted")
        return self


class ImprovementReport(StrictModel):
    """The improvement phase: what Sample A revealed and what changed because of it."""

    metadata: ArtifactMetadata
    from_classifier: NonEmptyStr
    to_classifier: NonEmptyStr
    improvements: List[Improvement] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_improvements(self) -> "ImprovementReport":
        if self.metadata.record_count != len(self.improvements):
            raise ValueError(
                "metadata.record_count does not match the number of improvements"
            )
        keys = [item.key for item in self.improvements]
        if len(set(keys)) != len(keys):
            raise ValueError("improvement keys must be unique")
        if keys != sorted(keys):
            raise ValueError("improvements must be sorted by key")
        if self.from_classifier == self.to_classifier:
            raise ValueError("an improvement phase must change the classifier version")
        return self

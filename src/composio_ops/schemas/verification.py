"""Sampling, verification, reconciliation, and accuracy schemas.

Verification is expensive, so it runs only over the selected samples and the
trigger-review queue. Every assignment records the seed and namespace that
produced it, which is what makes the selection auditable rather than merely
random.

Implements architecture sections 5.3, 9, 10 and 11.
"""

from typing import Dict, List, Optional

from pydantic import Field, field_validator, model_validator

from .. import constants as C
from ..taxonomy import ResearchFieldName, ResolutionStatus
from .base import AppId, ArtifactMetadata, NonEmptyStr, StrictModel, UtcDatetime
from .research import FieldKey

#: Persisted form of a field's value: ``None`` when the field is unresolved, and
#: a list of value tokens otherwise (length 1 for a single-valued field). One
#: shape for both arities keeps comparison and JSON output simple.
ValueKey = Optional[List[str]]


def to_value_key(key: FieldKey) -> ValueKey:
    """Convert a field's comparable key into its persisted form."""
    if key is None:
        return None
    if isinstance(key, tuple):
        return list(key)
    return [key]


def describe_value(key: ValueKey) -> str:
    """Render a value key for a report or an HTML cell."""
    if key is None:
        return ""
    return ", ".join(key)


class FieldValue(StrictModel):
    """One field's value at a point in time, comparable across channels."""

    field: ResearchFieldName
    status: ResolutionStatus
    value: ValueKey = None

    @model_validator(mode="after")
    def _check_value(self) -> "FieldValue":
        if self.status is ResolutionStatus.RESOLVED:
            if not self.value:
                raise ValueError("a resolved value must carry at least one token")
        elif self.value is not None:
            raise ValueError(
                "status '{}' must not carry a value".format(self.status.value)
            )
        return self

    def matches(self, other: "FieldValue") -> bool:
        """Agreement on status and value. Used by the accuracy metric.

        Values are compared as sets, because a multi-valued field lists which
        mechanisms exist, not the order somebody wrote them down in.
        """
        return self.status is other.status and sorted(self.value or []) == sorted(
            other.value or []
        )


class SampleAssignment(StrictModel):
    """One app's membership in a verification sample."""

    app_id: AppId
    category_id: NonEmptyStr
    group: C.SampleGroup
    #: Position within the app's category stratum, for auditing the allocation.
    stratum_rank: int = Field(ge=0)


class SampleSelection(StrictModel):
    """One verification sample, with the values frozen at selection time.

    Freezing matters for Sample A: architecture section 4.5 requires first-pass
    accuracy to be computed against the values the system produced *before* any
    correction, so later corrections cannot improve the initial metric.
    """

    metadata: ArtifactMetadata
    group: C.SampleGroup
    master_seed: int = Field(ge=0)
    seed_namespace: NonEmptyStr
    derived_seed: int = Field(ge=0)
    population_size: int = Field(ge=0)
    #: Apps excluded from this draw and why, so the exclusion rule is auditable.
    excluded: Dict[str, List[str]] = Field(default_factory=dict)
    assignments: List[SampleAssignment] = Field(default_factory=list)
    frozen_values: List["FrozenFieldValue"] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_assignments(self) -> "SampleSelection":
        app_ids = [item.app_id for item in self.assignments]
        if len(set(app_ids)) != len(app_ids):
            raise ValueError("an app may appear at most once in a sample")
        if app_ids != sorted(app_ids):
            raise ValueError("assignments must be sorted by app_id")
        if len(self.assignments) > self.population_size:
            raise ValueError("sample is larger than the population")
        if any(item.group is not self.group for item in self.assignments):
            raise ValueError("every assignment must belong to this sample's group")
        if self.metadata.record_count != len(self.assignments):
            raise ValueError("metadata.record_count does not match the sample size")

        sampled = set(app_ids)
        stray = sorted({value.app_id for value in self.frozen_values} - sampled)
        if stray:
            raise ValueError(
                "frozen values reference unsampled apps: {}".format(", ".join(stray[:5]))
            )
        keys = [(value.app_id, value.field.value) for value in self.frozen_values]
        if len(set(keys)) != len(keys):
            raise ValueError("at most one frozen value per (app_id, field)")
        if keys != sorted(keys):
            raise ValueError("frozen values must be sorted by (app_id, field)")
        return self

    def app_ids(self) -> List[str]:
        return [item.app_id for item in self.assignments]

    def frozen_for(self, app_id: str) -> Dict[ResearchFieldName, FieldValue]:
        return {
            value.field: value.as_field_value()
            for value in self.frozen_values
            if value.app_id == app_id
        }


class FrozenFieldValue(StrictModel):
    """A Channel A value captured at sample-selection time and never rewritten."""

    app_id: AppId
    field: ResearchFieldName
    status: ResolutionStatus
    value: ValueKey = None
    classifier_version: NonEmptyStr
    confidence: C.Confidence

    @model_validator(mode="after")
    def _check_value(self) -> "FrozenFieldValue":
        if self.status is ResolutionStatus.RESOLVED and not self.value:
            raise ValueError("a resolved value must carry at least one token")
        if self.status is not ResolutionStatus.RESOLVED and self.value is not None:
            raise ValueError(
                "status '{}' must not carry a value".format(self.status.value)
            )
        return self

    def as_field_value(self) -> FieldValue:
        return FieldValue(field=self.field, status=self.status, value=self.value)


class FieldObservation(StrictModel):
    """One channel's independent observation of one field.

    A verification channel records what it found and how that compares with
    Channel A. It never receives Channel A's answer before observing.
    """

    field: ResearchFieldName
    status: ResolutionStatus
    value: ValueKey = None
    outcome: C.VerificationOutcome
    evidence_ids: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

    @field_validator("evidence_ids")
    @classmethod
    def _sorted_unique(cls, value: List[str]) -> List[str]:
        return sorted({item.strip() for item in value if item.strip()})

    @model_validator(mode="after")
    def _check_observation(self) -> "FieldObservation":
        if self.status is ResolutionStatus.RESOLVED and not self.value:
            raise ValueError("a resolved observation must carry a value")
        if self.status is not ResolutionStatus.RESOLVED and self.value is not None:
            raise ValueError(
                "status '{}' must not carry a value".format(self.status.value)
            )
        if self.outcome is C.VerificationOutcome.INCONCLUSIVE and self.status is (
            ResolutionStatus.RESOLVED
        ):
            raise ValueError("an inconclusive check cannot also resolve the field")
        return self

    def as_field_value(self) -> FieldValue:
        return FieldValue(field=self.field, status=self.status, value=self.value)


class EvidenceCheck(StrictModel):
    """Whether a cited evidence item genuinely supports what it is cited for."""

    evidence_id: NonEmptyStr
    url: NonEmptyStr
    supports: List[ResearchFieldName] = Field(min_length=1)
    reachable: bool
    supports_claim: bool
    reason: NonEmptyStr

    @field_validator("supports")
    @classmethod
    def _sorted(cls, value: List[ResearchFieldName]) -> List[ResearchFieldName]:
        return sorted(set(value), key=lambda item: item.value)

    @property
    def is_valid(self) -> bool:
        return self.reachable and self.supports_claim


class CorrectedValue(StrictModel):
    """A value a verification channel asserts should replace Channel A's."""

    field: ResearchFieldName
    status: ResolutionStatus
    value: ValueKey = None
    reason: NonEmptyStr

    @model_validator(mode="after")
    def _check_value(self) -> "CorrectedValue":
        if self.status is ResolutionStatus.RESOLVED and not self.value:
            raise ValueError("a resolved correction must carry a value")
        if self.status is not ResolutionStatus.RESOLVED and self.value is not None:
            raise ValueError(
                "status '{}' must not carry a value".format(self.status.value)
            )
        return self

    def as_field_value(self) -> FieldValue:
        return FieldValue(field=self.field, status=self.status, value=self.value)


class VerificationResult(StrictModel):
    """One channel's full verification of one app. Architecture section 5.3."""

    app_id: AppId
    sample: Optional[C.SampleGroup] = None
    channel: C.Channel
    field_results: List[FieldObservation] = Field(default_factory=list)
    evidence_results: List[EvidenceCheck] = Field(default_factory=list)
    discrepancies: List[ResearchFieldName] = Field(default_factory=list)
    corrected_values: List[CorrectedValue] = Field(default_factory=list)
    reviewer: Optional[str] = None
    checked_at: UtcDatetime
    notes: Optional[str] = None

    @field_validator("discrepancies")
    @classmethod
    def _sorted_fields(cls, value: List[ResearchFieldName]) -> List[ResearchFieldName]:
        return sorted(set(value), key=lambda item: item.value)

    @model_validator(mode="after")
    def _check_result(self) -> "VerificationResult":
        if self.channel is C.Channel.CHANNEL_A:
            raise ValueError("Channel A produces research, not verification results")
        if self.channel is C.Channel.CHANNEL_D and not self.reviewer:
            raise ValueError("human verification must record a reviewer")

        fields = [item.field.value for item in self.field_results]
        if len(set(fields)) != len(fields):
            raise ValueError("at most one observation per field per channel")
        if fields != sorted(fields):
            raise ValueError("field results must be sorted by field")

        observed = {item.field for item in self.field_results}
        unobserved = sorted(
            item.value for item in set(self.discrepancies) - observed
        )
        if unobserved:
            raise ValueError(
                "discrepancies must come from observed fields: {}".format(
                    ", ".join(unobserved)
                )
            )
        corrected = [item.field.value for item in self.corrected_values]
        if len(set(corrected)) != len(corrected):
            raise ValueError("at most one correction per field per channel")
        if corrected != sorted(corrected):
            raise ValueError("corrections must be sorted by field")
        return self

    def observation(self, field: ResearchFieldName) -> Optional[FieldObservation]:
        for item in self.field_results:
            if item.field is field:
                return item
        return None


class VerificationArtifact(StrictModel):
    """Everything one verification channel produced, as persisted on disk."""

    metadata: ArtifactMetadata
    channel: C.Channel
    results: List[VerificationResult] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_results(self) -> "VerificationArtifact":
        if self.metadata.record_count != len(self.results):
            raise ValueError("metadata.record_count does not match the number of results")
        if any(item.channel is not self.channel for item in self.results):
            raise ValueError("every result must belong to this artifact's channel")
        app_ids = [item.app_id for item in self.results]
        if len(set(app_ids)) != len(app_ids):
            raise ValueError("at most one result per app per channel")
        if app_ids != sorted(app_ids):
            raise ValueError("results must be sorted by app_id")
        return self

    def for_app(self, app_id: str) -> Optional[VerificationResult]:
        for item in self.results:
            if item.app_id == app_id:
                return item
        return None


class HumanDecision(StrictModel):
    """One reviewer decision. Architecture section 11.

    A correction carries the original value, the corrected value, a reason, and
    supporting evidence, so every change to the dataset is attributable.
    """

    app_id: AppId
    field: ResearchFieldName
    decision: C.ReviewDecision
    entry_path: NonEmptyStr
    original_status: ResolutionStatus
    original_value: ValueKey = None
    corrected_status: Optional[ResolutionStatus] = None
    corrected_value: ValueKey = None
    reason: NonEmptyStr
    evidence_ids: List[str] = Field(default_factory=list)
    reviewer: NonEmptyStr
    decided_at: UtcDatetime

    @field_validator("evidence_ids")
    @classmethod
    def _sorted_unique(cls, value: List[str]) -> List[str]:
        return sorted({item.strip() for item in value if item.strip()})

    @model_validator(mode="after")
    def _check_decision(self) -> "HumanDecision":
        if self.decision is C.ReviewDecision.CORRECT:
            if self.corrected_status is None:
                raise ValueError("a correction must record the corrected status")
            if (
                self.corrected_status is ResolutionStatus.RESOLVED
                and not self.corrected_value
            ):
                raise ValueError("a correction to 'resolved' must record the value")
            if (
                self.corrected_status is not ResolutionStatus.RESOLVED
                and self.corrected_value is not None
            ):
                raise ValueError("a non-resolved correction must not carry a value")
            if (
                self.corrected_status is self.original_status
                and (self.corrected_value or []) == (self.original_value or [])
            ):
                raise ValueError("a correction must change something")
        elif self.corrected_status is not None or self.corrected_value is not None:
            raise ValueError(
                "decision '{}' must not carry a corrected value".format(
                    self.decision.value
                )
            )
        if self.original_status is ResolutionStatus.RESOLVED and not self.original_value:
            raise ValueError("a resolved original must carry a value")
        if (
            self.original_status is not ResolutionStatus.RESOLVED
            and self.original_value is not None
        ):
            raise ValueError("a non-resolved original must not carry a value")
        return self

    def established(self) -> FieldValue:
        """What the reviewer holds to be true, whether confirmed or corrected."""
        if self.decision is C.ReviewDecision.CORRECT:
            return FieldValue(
                field=self.field,
                status=self.corrected_status,
                value=self.corrected_value,
            )
        if self.decision is C.ReviewDecision.UNCLEAR:
            return FieldValue(field=self.field, status=ResolutionStatus.UNCLEAR)
        return FieldValue(
            field=self.field, status=self.original_status, value=self.original_value
        )


class HumanDecisionSet(StrictModel):
    """Every human decision taken across the run."""

    metadata: ArtifactMetadata
    decisions: List[HumanDecision] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_decisions(self) -> "HumanDecisionSet":
        if self.metadata.record_count != len(self.decisions):
            raise ValueError("metadata.record_count does not match the number of decisions")
        keys = [(item.app_id, item.field.value) for item in self.decisions]
        if len(set(keys)) != len(keys):
            raise ValueError("at most one decision per (app_id, field)")
        if keys != sorted(keys):
            raise ValueError("decisions must be sorted by (app_id, field)")
        return self

    def for_app(self, app_id: str) -> List[HumanDecision]:
        return [item for item in self.decisions if item.app_id == app_id]


class ReconciliationDecision(StrictModel):
    """How one field was finally resolved after verification.

    ``cardinality`` is recorded because architecture section 1.12 requires
    multi-valued fields to be reconciled as sets and single-valued fields to
    resolve to exactly one value.
    """

    app_id: AppId
    field: ResearchFieldName
    outcome: C.ReconciliationOutcome
    cardinality: NonEmptyStr
    final_status: ResolutionStatus
    final_value: ValueKey = None
    authoritative_channel: C.Channel
    superseded_channel: Optional[C.Channel] = None
    rationale: NonEmptyStr
    decided_at: UtcDatetime
    decided_by: Optional[str] = None

    @model_validator(mode="after")
    def _check_decision(self) -> "ReconciliationDecision":
        if self.final_status is ResolutionStatus.RESOLVED and not self.final_value:
            raise ValueError("a resolved outcome must carry a value")
        if (
            self.final_status is not ResolutionStatus.RESOLVED
            and self.final_value is not None
        ):
            raise ValueError(
                "status '{}' must not carry a final value".format(
                    self.final_status.value
                )
            )
        if (
            self.outcome is C.ReconciliationOutcome.DOWNGRADED_TO_UNCLEAR
            and self.final_status is not ResolutionStatus.UNCLEAR
        ):
            raise ValueError("a downgrade must end in the unclear status")
        if self.cardinality not in ("single", "multi"):
            raise ValueError("cardinality must be 'single' or 'multi'")
        if (
            self.cardinality == "single"
            and self.final_value is not None
            and len(self.final_value) != 1
        ):
            raise ValueError("a single-valued field must resolve to exactly one value")
        return self


class ReconciliationSet(StrictModel):
    """All reconciliation decisions for one dataset."""

    metadata: ArtifactMetadata
    decisions: List[ReconciliationDecision] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_decisions(self) -> "ReconciliationSet":
        if self.metadata.record_count != len(self.decisions):
            raise ValueError("metadata.record_count does not match the number of decisions")
        keys = [(item.app_id, item.field.value) for item in self.decisions]
        if len(set(keys)) != len(keys):
            raise ValueError("at most one decision per (app_id, field)")
        if keys != sorted(keys):
            raise ValueError("decisions must be sorted by (app_id, field)")
        return self

    def for_app(self, app_id: str) -> List[ReconciliationDecision]:
        return [item for item in self.decisions if item.app_id == app_id]


class FieldAccuracy(StrictModel):
    """Accuracy for one field within one sample."""

    field: ResearchFieldName
    checked: int = Field(ge=0)
    correct: int = Field(ge=0)

    @model_validator(mode="after")
    def _check_counts(self) -> "FieldAccuracy":
        if self.correct > self.checked:
            raise ValueError("correct cannot exceed checked")
        return self

    @property
    def accuracy(self) -> Optional[float]:
        if self.checked == 0:
            return None
        return round(self.correct / self.checked, 4)


class SampleAccuracy(StrictModel):
    """The accuracy protocol's output for one sample. Architecture section 10."""

    group: C.SampleGroup
    #: ``first_pass`` for Sample A's frozen values, ``final`` for Sample B.
    measurement: NonEmptyStr
    classifier_version: NonEmptyStr
    apps: int = Field(ge=0)
    fields_checked: int = Field(ge=0)
    fields_correct: int = Field(ge=0)
    rows_checked: int = Field(ge=0)
    rows_correct: int = Field(ge=0)
    claims_checked: int = Field(ge=0)
    claims_with_valid_evidence: int = Field(ge=0)
    per_field: List[FieldAccuracy] = Field(default_factory=list)
    trigger_reviewed_apps: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_counts(self) -> "SampleAccuracy":
        if self.fields_correct > self.fields_checked:
            raise ValueError("fields_correct cannot exceed fields_checked")
        if self.rows_correct > self.rows_checked:
            raise ValueError("rows_correct cannot exceed rows_checked")
        if self.claims_with_valid_evidence > self.claims_checked:
            raise ValueError("valid claims cannot exceed checked claims")
        fields = [item.field.value for item in self.per_field]
        if fields != sorted(fields):
            raise ValueError("per-field accuracy must be sorted by field")
        total = sum(item.checked for item in self.per_field)
        if total != self.fields_checked:
            raise ValueError("per-field checks must sum to fields_checked")
        return self

    @property
    def field_level_accuracy(self) -> Optional[float]:
        if self.fields_checked == 0:
            return None
        return round(self.fields_correct / self.fields_checked, 4)

    @property
    def row_level_accuracy(self) -> Optional[float]:
        if self.rows_checked == 0:
            return None
        return round(self.rows_correct / self.rows_checked, 4)

    @property
    def evidence_validity(self) -> Optional[float]:
        if self.claims_checked == 0:
            return None
        return round(self.claims_with_valid_evidence / self.claims_checked, 4)


class AccuracyReport(StrictModel):
    """Both samples plus the headline metric, fixed before the results were known."""

    metadata: ArtifactMetadata
    #: Named here so the reader can check it against the architecture rather than
    #: against whichever number came out best.
    headline_metric: NonEmptyStr = "sample_b_field_level_accuracy"
    verified_fields: List[ResearchFieldName] = Field(min_length=1)
    samples: List[SampleAccuracy] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_samples(self) -> "AccuracyReport":
        groups = [item.group.value for item in self.samples]
        if len(set(groups)) != len(groups):
            raise ValueError("at most one accuracy result per sample group")
        if groups != sorted(groups):
            raise ValueError("samples must be sorted by group")
        return self

    def sample(self, group: C.SampleGroup) -> Optional[SampleAccuracy]:
        for item in self.samples:
            if item.group is group:
                return item
        return None

    @property
    def headline_value(self) -> Optional[float]:
        result = self.sample(C.SampleGroup.B)
        return result.field_level_accuracy if result else None


SampleSelection.model_rebuild()

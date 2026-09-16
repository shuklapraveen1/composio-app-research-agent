"""Deterministic analytics and pattern-analysis schemas.

Analytics are computed from the final dataset by pure functions: no model call,
no network, no clock beyond the recorded ``generated_at``. The case study is
rendered from these artifacts, so no statistic is ever typed by hand.
"""

from typing import Dict, List, Optional, Union

from pydantic import Field, model_validator

from .base import ArtifactMetadata, NonEmptyStr, StrictModel

MetricValue = Union[int, float, str]


class Metric(StrictModel):
    """A single computed figure, with the wording used to present it."""

    key: NonEmptyStr
    label: NonEmptyStr
    value: MetricValue
    unit: Optional[str] = None
    description: Optional[str] = None


class Distribution(StrictModel):
    """Counts across the values of one attribute, including unresolved ones.

    ``unresolved`` is a first-class bucket rather than a missing row: how often
    the pipeline could not establish a field is itself a finding.
    """

    attribute: NonEmptyStr
    label: NonEmptyStr
    counts: Dict[str, int] = Field(default_factory=dict)
    unresolved: Dict[str, int] = Field(default_factory=dict)
    total: int = Field(default=0, ge=0)
    #: True when one app may contribute to several buckets, so the counts
    #: legitimately sum to more than ``total``.
    multi_valued: bool = False

    @model_validator(mode="after")
    def _check_total(self) -> "Distribution":
        if any(count < 0 for count in self.counts.values()):
            raise ValueError("counts must be non-negative")
        if any(count < 0 for count in self.unresolved.values()):
            raise ValueError("unresolved counts must be non-negative")
        if not self.multi_valued:
            observed = sum(self.counts.values()) + sum(self.unresolved.values())
            if observed != self.total:
                raise ValueError(
                    "counts plus unresolved must equal total for a single-valued field"
                )
        return self

    @property
    def unresolved_total(self) -> int:
        return sum(self.unresolved.values())


class CrossTab(StrictModel):
    """Counts of one attribute broken down by another, e.g. buildability by category."""

    key: NonEmptyStr
    label: NonEmptyStr
    row_attribute: NonEmptyStr
    column_attribute: NonEmptyStr
    rows: List[str] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)
    cells: Dict[str, Dict[str, int]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_cells(self) -> "CrossTab":
        if self.rows != sorted(self.rows):
            raise ValueError("rows must be sorted")
        if self.columns != sorted(self.columns):
            raise ValueError("columns must be sorted")
        if sorted(self.cells) != self.rows:
            raise ValueError("cells must cover exactly the declared rows")
        for row, values in self.cells.items():
            if sorted(values) != self.columns:
                raise ValueError(
                    "row '{}' must cover exactly the declared columns".format(row)
                )
        return self

    def row_total(self, row: str) -> int:
        return sum(self.cells.get(row, {}).values())


class AnalyticsReport(StrictModel):
    """The analytics artifact derived from the final dataset."""

    metadata: ArtifactMetadata
    dataset_fingerprint: NonEmptyStr
    metrics: List[Metric] = Field(default_factory=list)
    distributions: List[Distribution] = Field(default_factory=list)
    cross_tabs: List[CrossTab] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_ordering(self) -> "AnalyticsReport":
        metric_keys = [metric.key for metric in self.metrics]
        if len(set(metric_keys)) != len(metric_keys):
            raise ValueError("metric keys must be unique")
        if metric_keys != sorted(metric_keys):
            raise ValueError("metrics must be sorted by key")
        attributes = [item.attribute for item in self.distributions]
        if attributes != sorted(attributes):
            raise ValueError("distributions must be sorted by attribute")
        tabs = [item.key for item in self.cross_tabs]
        if tabs != sorted(tabs):
            raise ValueError("cross tabs must be sorted by key")
        return self

    def metric(self, key: str) -> Optional[Metric]:
        for metric in self.metrics:
            if metric.key == key:
                return metric
        return None

    def distribution(self, attribute: str) -> Optional[Distribution]:
        for item in self.distributions:
            if item.attribute == attribute:
                return item
        return None

    def cross_tab(self, key: str) -> Optional[CrossTab]:
        for item in self.cross_tabs:
            if item.key == key:
                return item
        return None


class Pattern(StrictModel):
    """One observed regularity, stated together with the numbers behind it.

    ``supporting_app_ids`` is required so a reader can check the claim against
    the dataset instead of taking the sentence on trust.
    """

    key: NonEmptyStr
    title: NonEmptyStr
    statement: NonEmptyStr
    observed: int = Field(ge=0)
    population: int = Field(ge=0)
    supporting_app_ids: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_support(self) -> "Pattern":
        if self.observed > self.population:
            raise ValueError("observed cannot exceed the population")
        if self.supporting_app_ids != sorted(self.supporting_app_ids):
            raise ValueError("supporting app ids must be sorted")
        if len(set(self.supporting_app_ids)) != len(self.supporting_app_ids):
            raise ValueError("supporting app ids must be unique")
        if len(self.supporting_app_ids) != self.observed:
            raise ValueError("supporting app ids must match the observed count")
        return self

    @property
    def share(self) -> Optional[float]:
        if self.population == 0:
            return None
        return round(self.observed / self.population, 4)


class PatternReport(StrictModel):
    """Pattern analysis derived from the final dataset."""

    metadata: ArtifactMetadata
    dataset_fingerprint: NonEmptyStr
    patterns: List[Pattern] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_patterns(self) -> "PatternReport":
        if self.metadata.record_count != len(self.patterns):
            raise ValueError("metadata.record_count does not match the number of patterns")
        keys = [pattern.key for pattern in self.patterns]
        if len(set(keys)) != len(keys):
            raise ValueError("pattern keys must be unique")
        if keys != sorted(keys):
            raise ValueError("patterns must be sorted by key")
        return self

    def pattern(self, key: str) -> Optional[Pattern]:
        for item in self.patterns:
            if item.key == key:
                return item
        return None

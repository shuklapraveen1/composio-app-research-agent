"""Registry schemas: the supplied app list, its categories, and its normal form.

The registry is input data. Categories are supplied and preserved verbatim, so
the research agent is never asked to rediscover something already known.
"""

from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator, model_validator

from .base import AppId, ArtifactMetadata, NonEmptyStr, StrictModel, UtcDatetime

#: A category identifier is a slug, like an app id.
CategoryId = AppId


class RawAppRecord(StrictModel):
    """One row of the supplied app list, preserved verbatim.

    ``fields`` keeps the original columns untouched so a normalization bug can
    always be diagnosed against the true source.
    """

    source_index: int = Field(ge=0, description="Zero-based row position in the source.")
    name: NonEmptyStr
    category: NonEmptyStr
    fields: Dict[str, Any] = Field(default_factory=dict)


class Category(StrictModel):
    """A supplied category and how many apps it holds."""

    category_id: CategoryId
    name: NonEmptyStr
    app_count: int = Field(ge=0)


class NormalizedAppRecord(StrictModel):
    """An app after normalization: stable id, canonical name, supplied category."""

    app_id: AppId
    name: NonEmptyStr
    canonical_name: NonEmptyStr
    category_id: CategoryId
    homepage_url: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    source_index: int = Field(ge=0)

    @field_validator("homepage_url")
    @classmethod
    def _check_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if not cleaned.startswith(("http://", "https://")):
            raise ValueError("homepage_url must be an http(s) URL")
        return cleaned

    @field_validator("aliases")
    @classmethod
    def _dedupe_aliases(cls, value: List[str]) -> List[str]:
        return sorted({alias.strip() for alias in value if alias.strip()})


class DuplicateGroup(StrictModel):
    """Two or more source rows that appear to describe the same application."""

    reason: NonEmptyStr
    key: NonEmptyStr
    source_indexes: List[int] = Field(min_length=2)

    @field_validator("source_indexes")
    @classmethod
    def _sorted(cls, value: List[int]) -> List[int]:
        return sorted(value)


class RawRegistry(StrictModel):
    """The ingested source list, before normalization."""

    metadata: ArtifactMetadata
    source_name: NonEmptyStr
    retrieved_at: UtcDatetime
    records: List[RawAppRecord]

    @model_validator(mode="after")
    def _check_counts(self) -> "RawRegistry":
        if self.metadata.record_count != len(self.records):
            raise ValueError("metadata.record_count does not match the number of records")
        indexes = [record.source_index for record in self.records]
        if len(set(indexes)) != len(indexes):
            raise ValueError("source_index values must be unique")
        if indexes != sorted(indexes):
            raise ValueError("records must keep their source order")
        return self


class NormalizedRegistry(StrictModel):
    """The canonical app list every downstream stage iterates over."""

    metadata: ArtifactMetadata
    categories: List[Category] = Field(default_factory=list)
    records: List[NormalizedAppRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_records(self) -> "NormalizedRegistry":
        if self.metadata.record_count != len(self.records):
            raise ValueError("metadata.record_count does not match the number of records")

        app_ids = [record.app_id for record in self.records]
        if len(set(app_ids)) != len(app_ids):
            raise ValueError("app_id values must be unique")
        if app_ids != sorted(app_ids):
            raise ValueError("records must be sorted by app_id for canonical output")

        source_indexes = [record.source_index for record in self.records]
        if len(set(source_indexes)) != len(source_indexes):
            raise ValueError("source_index values must be unique")

        category_ids = [category.category_id for category in self.categories]
        if len(set(category_ids)) != len(category_ids):
            raise ValueError("category_id values must be unique")
        if category_ids != sorted(category_ids):
            raise ValueError("categories must be sorted by category_id")

        known = set(category_ids)
        unknown = sorted({r.category_id for r in self.records} - known)
        if unknown:
            raise ValueError(
                "records reference categories that are not declared: {}".format(
                    ", ".join(unknown)
                )
            )

        for category in self.categories:
            actual = sum(1 for r in self.records if r.category_id == category.category_id)
            if actual != category.app_count:
                raise ValueError(
                    "category '{}' declares {} apps but holds {}".format(
                        category.category_id, category.app_count, actual
                    )
                )
        return self

    def app_ids(self) -> List[str]:
        return [record.app_id for record in self.records]

    def category_ids(self) -> List[str]:
        return [category.category_id for category in self.categories]

    def apps_in(self, category_id: str) -> List[NormalizedAppRecord]:
        return [record for record in self.records if record.category_id == category_id]

    def require_exact_counts(self, apps: int, categories: int) -> None:
        """Fail loudly unless the registry is exactly the expected shape."""
        problems = []
        if len(self.records) != apps:
            problems.append(
                "expected {} applications, found {}".format(apps, len(self.records))
            )
        if len(self.categories) != categories:
            problems.append(
                "expected {} categories, found {}".format(
                    categories, len(self.categories)
                )
            )
        if problems:
            raise ValueError("; ".join(problems))

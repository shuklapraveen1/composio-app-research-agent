"""Deterministic validation report schemas.

Validation is a pure function of the dataset: the same input always yields the
same issue list, in the same order, with no model involvement.
"""

from typing import List, Optional

from pydantic import Field, model_validator

from .. import constants as C
from .base import AppId, ArtifactMetadata, AttributeName, NonEmptyStr, StrictModel


class ValidationIssue(StrictModel):
    """One finding from the deterministic validator."""

    code: NonEmptyStr
    severity: C.Severity
    message: NonEmptyStr
    app_id: Optional[AppId] = None
    attribute: Optional[AttributeName] = None
    location: Optional[str] = None

    def sort_key(self) -> tuple:
        return (
            self.app_id or "",
            self.attribute or "",
            self.code,
            self.message,
        )


class ValidationReport(StrictModel):
    """The full validation outcome for one dataset."""

    metadata: ArtifactMetadata
    checked_records: int = Field(ge=0)
    issues: List[ValidationIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_sorted(self) -> "ValidationReport":
        keys = [issue.sort_key() for issue in self.issues]
        if keys != sorted(keys):
            raise ValueError("issues must be sorted for a byte-stable report")
        return self

    @property
    def errors(self) -> List[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity is C.Severity.ERROR]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity is C.Severity.WARNING]

    @property
    def is_valid(self) -> bool:
        """True when nothing blocking was found. Warnings do not block."""
        return not self.errors

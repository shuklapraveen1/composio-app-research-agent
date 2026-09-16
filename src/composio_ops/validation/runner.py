"""Running validation and turning its issues into a persisted report."""

from typing import Sequence, Tuple

from .. import constants as C
from ..config import Settings
from ..determinism import fingerprint
from ..schemas.base import ArtifactMetadata
from ..schemas.evidence import EvidenceSet
from ..schemas.registry import NormalizedRegistry
from ..schemas.research import ResearchSet
from ..schemas.validation import ValidationIssue, ValidationReport
from .rules import validate


def build_report(
    issues: Sequence[ValidationIssue], checked: int, settings: Settings
) -> ValidationReport:
    """Wrap issues in an artifact whose fingerprint changes only when they do."""
    return ValidationReport(
        metadata=ArtifactMetadata(
            stage=C.PipelineStage.VALIDATION,
            generated_at=settings.as_of,
            seed=settings.seed,
            record_count=len(issues),
            source_fingerprint=fingerprint(
                [issue.to_jsonable() for issue in issues]
            ),
            notes="Deterministic validation over {} records.".format(checked),
        ),
        checked_records=checked,
        issues=list(issues),
    )


def run_validation(
    registry: NormalizedRegistry,
    research: ResearchSet,
    evidence: EvidenceSet,
    settings: Settings,
) -> Tuple[ValidationReport, bool]:
    """Validate a research pass; the flag says whether anything blocking was found."""
    issues = validate(registry=registry, research=research, evidence=evidence)
    report = build_report(issues, checked=len(research.records), settings=settings)
    return report, report.is_valid

"""Application-level error hierarchy and process exit codes.

Every failure the pipeline raises on purpose derives from :class:`PipelineError`,
carries a stable ``code`` for logging, and maps to a distinct exit code so a CI
step can tell a configuration problem apart from a data problem.
"""

from typing import Any, Dict, Optional


class ExitCode:
    """Process exit codes. Stable; scripts and CI may depend on them."""

    OK = 0
    UNEXPECTED = 1
    CONFIGURATION = 2
    #: 3 was "stage not implemented"; retired now that every stage is built.
    MISSING_ARTIFACT = 4
    DATA_VALIDATION = 5
    PIPELINE = 6


class PipelineError(Exception):
    """Base class for all deliberate failures in this project."""

    code = "pipeline_error"
    exit_code = ExitCode.PIPELINE

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context: Dict[str, Any] = context

    def __str__(self) -> str:
        if not self.context:
            return self.message
        rendered = ", ".join(
            "{}={!r}".format(key, self.context[key]) for key in sorted(self.context)
        )
        return "{} ({})".format(self.message, rendered)

    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "message": self.message, "context": dict(self.context)}


class ConfigurationError(PipelineError):
    """Settings are missing, malformed, or mutually inconsistent."""

    code = "configuration_error"
    exit_code = ExitCode.CONFIGURATION


class MissingArtifactError(PipelineError):
    """A required upstream artifact has not been produced yet."""

    code = "missing_artifact"
    exit_code = ExitCode.MISSING_ARTIFACT

    def __init__(self, path: Any, produced_by: Optional[str] = None) -> None:
        message = "Required artifact is missing: {}".format(path)
        if produced_by:
            message += "; produce it by running the '{}' stage".format(produced_by)
        super().__init__(message, path=str(path), produced_by=produced_by)


class RegistryError(PipelineError):
    """The 100-app registry is absent, malformed, or the wrong size."""

    code = "registry_error"


class ResearchError(PipelineError):
    """Channel A research failed for a reason the run cannot recover from."""

    code = "research_error"


class EvidenceError(PipelineError):
    """Evidence extraction produced an unusable result."""

    code = "evidence_error"


class ClassificationError(PipelineError):
    """Structured classification failed or violated the evidence rule."""

    code = "classification_error"


class DataValidationError(PipelineError):
    """Deterministic validation found blocking errors.

    Named to avoid colliding with :class:`pydantic.ValidationError`.
    """

    code = "data_validation_error"
    exit_code = ExitCode.DATA_VALIDATION


class SamplingError(PipelineError):
    """Sample A/B selection could not satisfy its constraints."""

    code = "sampling_error"


class VerificationError(PipelineError):
    """A sampled verification channel failed."""

    code = "verification_error"


class ReconciliationError(PipelineError):
    """Channel A and verification results could not be reconciled."""

    code = "reconciliation_error"


class AnalyticsError(PipelineError):
    """Deterministic analytics could not be computed."""

    code = "analytics_error"


class CaseStudyError(PipelineError):
    """Case-study generation failed or was not grounded in the final dataset."""

    code = "case_study_error"


class PublicationError(PipelineError):
    """Site or export generation failed."""

    code = "publication_error"


__all__ = [
    "AnalyticsError",
    "CaseStudyError",
    "ClassificationError",
    "ConfigurationError",
    "DataValidationError",
    "EvidenceError",
    "ExitCode",
    "MissingArtifactError",
    "PipelineError",
    "PublicationError",
    "ReconciliationError",
    "RegistryError",
    "ResearchError",
    "SamplingError",
    "VerificationError",
]

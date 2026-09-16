"""Shared constants and closed vocabularies for the pipeline.

Everything here is structural: stages, channels, artifact names, seed
namespaces. The classification vocabulary lives in :mod:`composio_ops.taxonomy`.
"""

from enum import Enum
from typing import Final

PROJECT_NAME: Final[str] = "composio-ops"
PACKAGE_NAME: Final[str] = "composio_ops"

#: Bumped whenever a persisted schema changes shape. Every artifact records it so
#: a stale dataset can never be silently consumed by a newer stage.
SCHEMA_VERSION: Final[str] = "2.0.0"

#: Canonical spelling of "we looked and could not establish this". A missing value
#: and an unknown value are different things and must never be conflated.
UNKNOWN: Final[str] = "unknown"

#: Environment variable prefix for every setting this project reads.
ENV_PREFIX: Final[str] = "COMPOSIO_OPS_"

#: Master seed default. Overridable via COMPOSIO_OPS_SEED.
DEFAULT_SEED: Final[int] = 20260916

#: The registry is expected to hold exactly this many apps; the loader fails loudly
#: on a mismatch rather than quietly researching a short list.
DEFAULT_EXPECTED_APP_COUNT: Final[int] = 100

#: The supplied list is expected to span exactly this many categories.
DEFAULT_EXPECTED_CATEGORY_COUNT: Final[int] = 10

#: Fixed by architecture section 9. Both samples are this size and disjoint.
DEFAULT_SAMPLE_SIZE: Final[int] = 15

#: The pipeline clock. Every artifact timestamp comes from this value rather than
#: from the wall clock, so re-running a stage with unchanged inputs produces a
#: byte-identical file and a diff always means a real change. Overridable via
#: COMPOSIO_OPS_AS_OF when a run genuinely needs to record its own time.
DEFAULT_AS_OF: Final[str] = "2026-09-16T00:00:00+00:00"


class PipelineStage(str, Enum):
    """The locked architecture's stages, in execution order."""

    REGISTRY = "registry"
    NORMALIZATION = "normalization"
    RESEARCH = "research"
    EVIDENCE_EXTRACTION = "evidence_extraction"
    CLASSIFICATION = "classification"
    VALIDATION = "validation"
    INITIAL_DATASET = "initial_dataset"
    TRIGGER_REVIEW = "trigger_review"
    SAMPLE_SELECTION = "sample_selection"
    VERIFICATION = "verification"
    RECONCILIATION = "reconciliation"
    ACCURACY = "accuracy"
    FINAL_DATASET = "final_dataset"
    ANALYTICS = "analytics"
    CASE_STUDY = "case_study"
    PUBLICATION = "publication"


#: Execution order, used for ordering checks and reporting.
STAGE_ORDER: Final[tuple] = tuple(stage for stage in PipelineStage)


class Channel(str, Enum):
    """Where a claim came from. Architecture section 4.1.

    Channel A is the single research pass over all 100 apps. B, C and D are
    verification channels and only ever run over the samples plus the
    trigger-review queue.
    """

    CHANNEL_A = "channel_a"
    CHANNEL_B = "channel_b"
    CHANNEL_C = "channel_c"
    CHANNEL_D = "channel_d"


#: What each channel is, for logs, reports, and the case study.
CHANNEL_LABELS: Final[dict] = {
    Channel.CHANNEL_A: "Research agent (all 100 apps)",
    Channel.CHANNEL_B: "Independent agent re-check (sampled)",
    Channel.CHANNEL_C: "Browser / page verification (sampled)",
    Channel.CHANNEL_D: "Human review (sampled and triggered)",
}

#: Channels that are expensive and therefore sampled, never run over all 100.
SAMPLED_CHANNELS: Final[tuple] = (
    Channel.CHANNEL_B,
    Channel.CHANNEL_C,
    Channel.CHANNEL_D,
)


class ResearchProvider(str, Enum):
    """How Channel A reaches the outside world.

    ``composio`` is the primary path described by architecture section 12;
    ``direct`` is the documented fallback; ``corpus`` replays a curated,
    reviewed source corpus committed to the repository and makes no network
    calls, which is what keeps the pipeline reproducible offline.
    """

    COMPOSIO = "composio"
    DIRECT = "direct"
    CORPUS = "corpus"


class EvidenceRetrieval(str, Enum):
    """Whether an evidence item's page was read in this run."""

    #: The page was fetched and the excerpt is verbatim from it.
    FETCHED = "fetched"
    #: The source was cited from the reviewed corpus without a live fetch.
    CITED = "cited"


class Confidence(str, Enum):
    """Coarse confidence. Computed deterministically; never asserted by a model."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SampleGroup(str, Enum):
    """Verification sample membership."""

    A = "A"
    B = "B"


class VerificationStatus(str, Enum):
    """Where a record stands in the verification workflow. Section 6.10."""

    NOT_SELECTED = "not_selected"
    SELECTED = "selected"
    VERIFIED = "verified"
    CORRECTED = "corrected"
    NEEDS_REVIEW = "needs_review"
    UNRESOLVED = "unresolved"


class VerificationOutcome(str, Enum):
    """Result of a single verification check against a Channel A value."""

    AGREES = "agrees"
    DISAGREES = "disagrees"
    INCONCLUSIVE = "inconclusive"


class ReviewDecision(str, Enum):
    """What a human reviewer concluded. Architecture section 11."""

    CONFIRM = "confirm"
    CORRECT = "correct"
    UNCLEAR = "unclear"


class ReviewTrigger(str, Enum):
    """Risk-based reasons a record enters the review queue. Section 4.4."""

    UNRESOLVED_IDENTITY = "unresolved_identity"
    LOW_CONFIDENCE = "low_confidence"
    MISSING_CRITICAL_EVIDENCE = "missing_critical_evidence"
    SOURCE_CONTRADICTION = "source_contradiction"
    INTERNAL_CONTRADICTION = "internal_contradiction"
    UNCLEAR_CREDENTIAL_ACCESS = "unclear_credential_access"
    UNCLEAR_API = "unclear_api"
    UNUSUAL_AUTHENTICATION = "unusual_authentication"
    UNCLEAR_BUILDABILITY = "unclear_buildability"
    VERIFICATION_DISAGREEMENT = "verification_disagreement"
    NON_STANDARD_APPLICATION_TYPE = "non_standard_application_type"


class ReconciliationOutcome(str, Enum):
    """How a Channel A value was resolved after verification."""

    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
    DOWNGRADED_TO_UNCLEAR = "downgraded_to_unclear"
    UNRESOLVED = "unresolved"


class Severity(str, Enum):
    """Severity of a deterministic validation finding."""

    ERROR = "error"
    WARNING = "warning"


class DatasetStage(str, Enum):
    """Which canonical dataset an artifact represents."""

    INITIAL = "initial"
    FINAL = "final"


class LogFormat(str, Enum):
    CONSOLE = "console"
    JSON = "json"


class Environment(str, Enum):
    LOCAL = "local"
    CI = "ci"


LOG_LEVELS: Final[frozenset] = frozenset(
    {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
)

#: Classifier rule-set versions. Sample A measures v1; the improvement phase
#: promotes v2 and Sample B measures it. Recorded on every research record.
CLASSIFIER_V1: Final[str] = "v1"
CLASSIFIER_V2: Final[str] = "v2"
CLASSIFIER_VERSIONS: Final[tuple] = (CLASSIFIER_V1, CLASSIFIER_V2)

#: Title and standfirst for the published case study.
CASE_STUDY_TITLE: Final[str] = (
    "Which integrations can actually be built, and how we know"
)
CASE_STUDY_DESCRIPTION: Final[str] = (
    "A research operations pipeline over 100 applications: evidence-first "
    "classification, deterministic validation, four verification channels, and "
    "an accuracy number measured on applications the final rules had never seen."
)

#: Canonical artifact file names. Paths are assembled in composio_ops.paths.
REGISTRY_RAW_FILENAME: Final[str] = "registry_raw.json"
REGISTRY_NORMALIZED_FILENAME: Final[str] = "registry_normalized.json"
RESEARCH_RESPONSES_DIRNAME: Final[str] = "research_responses"
RUN_METADATA_FILENAME: Final[str] = "run_metadata.json"
EVIDENCE_FILENAME: Final[str] = "evidence.json"
CLASSIFICATION_FILENAME: Final[str] = "classification.json"
VALIDATION_REPORT_FILENAME: Final[str] = "validation_report.json"
INITIAL_DATASET_FILENAME: Final[str] = "initial_dataset.json"
REVIEW_QUEUE_FILENAME: Final[str] = "review_queue.json"
SAMPLE_A_FILENAME: Final[str] = "sample_a.json"
SAMPLE_B_FILENAME: Final[str] = "sample_b.json"
CHANNEL_B_FILENAME: Final[str] = "channel_b.json"
CHANNEL_C_FILENAME: Final[str] = "channel_c.json"
HUMAN_DECISIONS_FILENAME: Final[str] = "human_decisions.json"
RECONCILIATION_FILENAME: Final[str] = "reconciliation.json"
ACCURACY_FILENAME: Final[str] = "accuracy.json"
IMPROVEMENTS_FILENAME: Final[str] = "improvements.json"
FINAL_DATASET_FILENAME: Final[str] = "final_dataset.json"
FINAL_DATASET_CSV_FILENAME: Final[str] = "final_dataset.csv"
ANALYTICS_FILENAME: Final[str] = "analytics.json"
PATTERNS_FILENAME: Final[str] = "patterns.json"
CASE_STUDY_FILENAME: Final[str] = "index.html"
SITE_STYLES_FILENAME: Final[str] = "styles.css"
SITE_SCRIPT_FILENAME: Final[str] = "app.js"
SITE_PAYLOAD_FILENAME: Final[str] = "dataset.js"

#: Global the payload script defines and the page reads.
SITE_PAYLOAD_GLOBAL: Final[str] = "COMPOSIO_RESEARCH"

#: Seed namespaces, so two stages never share an RNG stream.
SEED_NAMESPACE_SAMPLE_A: Final[str] = "sample_selection:A"
SEED_NAMESPACE_SAMPLE_B: Final[str] = "sample_selection:B"

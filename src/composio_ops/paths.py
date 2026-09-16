"""Artifact path layout.

One place decides where every stage reads and writes. Stages must never build
paths by hand, so that renaming an artifact is a single-file change and so the
"one canonical final dataset" rule is structurally enforced.

Layout under the data directory::

    registry/     supplied app list, normalized registry          (tracked)
    corpus/       reviewed research corpus backing Channel A      (tracked)
    raw/          verbatim research responses, run metadata       (generated)
    interim/      evidence, classification, validation, review    (generated)
    verification/ sample A/B, channel B/C, human decisions        (tracked)
    final/        the canonical final dataset and its derivatives (tracked)

The ``verification/`` and ``final/`` names come straight from architecture
sections 11 and 13.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from . import constants as C
from .errors import MissingArtifactError


@dataclass(frozen=True)
class ArtifactPaths:
    """Resolved, absolute locations of every pipeline artifact."""

    project_root: Path
    data_dir: Path
    site_dir: Path

    # --- directories -------------------------------------------------------
    @property
    def registry_dir(self) -> Path:
        return self.data_dir / "registry"

    @property
    def corpus_dir(self) -> Path:
        return self.data_dir / "corpus"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def interim_dir(self) -> Path:
        return self.data_dir / "interim"

    @property
    def verification_dir(self) -> Path:
        return self.data_dir / "verification"

    @property
    def final_dir(self) -> Path:
        return self.data_dir / "final"

    @property
    def research_responses_dir(self) -> Path:
        """Verbatim Channel A responses, one file per app, kept as provenance."""
        return self.raw_dir / C.RESEARCH_RESPONSES_DIRNAME

    # --- inputs ------------------------------------------------------------
    @property
    def apps_source(self) -> Path:
        """The supplied 100-app list, at the repository root per section 13."""
        return self.project_root / "apps.json"

    @property
    def registry_raw(self) -> Path:
        return self.registry_dir / C.REGISTRY_RAW_FILENAME

    @property
    def registry_normalized(self) -> Path:
        return self.registry_dir / C.REGISTRY_NORMALIZED_FILENAME

    @property
    def corpus_apps_dir(self) -> Path:
        """Reviewed source corpus, one file per supplied category."""
        return self.corpus_dir / "apps"

    @property
    def ground_truth(self) -> Path:
        """Human-established field values for the sampled apps, used by Channel D."""
        return self.corpus_dir / "ground_truth.json"

    # --- run provenance ----------------------------------------------------
    @property
    def run_metadata(self) -> Path:
        return self.raw_dir / C.RUN_METADATA_FILENAME

    # --- interim -----------------------------------------------------------
    @property
    def evidence(self) -> Path:
        return self.interim_dir / C.EVIDENCE_FILENAME

    @property
    def classification(self) -> Path:
        return self.interim_dir / C.CLASSIFICATION_FILENAME

    @property
    def validation_report(self) -> Path:
        return self.interim_dir / C.VALIDATION_REPORT_FILENAME

    @property
    def initial_dataset(self) -> Path:
        return self.interim_dir / C.INITIAL_DATASET_FILENAME

    @property
    def review_queue(self) -> Path:
        return self.interim_dir / C.REVIEW_QUEUE_FILENAME

    @property
    def reconciliation(self) -> Path:
        return self.interim_dir / C.RECONCILIATION_FILENAME

    @property
    def improvements(self) -> Path:
        return self.interim_dir / C.IMPROVEMENTS_FILENAME

    # --- verification artifacts (architecture section 11) ------------------
    @property
    def sample_a(self) -> Path:
        return self.verification_dir / C.SAMPLE_A_FILENAME

    @property
    def sample_b(self) -> Path:
        return self.verification_dir / C.SAMPLE_B_FILENAME

    @property
    def channel_b(self) -> Path:
        return self.verification_dir / C.CHANNEL_B_FILENAME

    @property
    def channel_c(self) -> Path:
        return self.verification_dir / C.CHANNEL_C_FILENAME

    @property
    def human_decisions(self) -> Path:
        return self.verification_dir / C.HUMAN_DECISIONS_FILENAME

    def sample(self, group: C.SampleGroup) -> Path:
        return self.sample_a if group is C.SampleGroup.A else self.sample_b

    # --- final -------------------------------------------------------------
    @property
    def final_dataset(self) -> Path:
        """The single canonical dataset. Everything downstream reads only this."""
        return self.final_dir / C.FINAL_DATASET_FILENAME

    @property
    def final_dataset_csv(self) -> Path:
        return self.final_dir / C.FINAL_DATASET_CSV_FILENAME

    @property
    def analytics(self) -> Path:
        return self.final_dir / C.ANALYTICS_FILENAME

    @property
    def patterns(self) -> Path:
        return self.final_dir / C.PATTERNS_FILENAME

    @property
    def accuracy(self) -> Path:
        return self.final_dir / C.ACCURACY_FILENAME

    # --- published site ----------------------------------------------------
    @property
    def case_study(self) -> Path:
        return self.site_dir / C.CASE_STUDY_FILENAME

    @property
    def site_data_dir(self) -> Path:
        """Published copies of the artifacts the case study cites."""
        return self.site_dir / "data"

    @property
    def site_dataset(self) -> Path:
        return self.site_data_dir / C.FINAL_DATASET_FILENAME

    @property
    def site_dataset_csv(self) -> Path:
        return self.site_data_dir / C.FINAL_DATASET_CSV_FILENAME

    @property
    def site_analytics(self) -> Path:
        return self.site_data_dir / C.ANALYTICS_FILENAME

    @property
    def site_patterns(self) -> Path:
        return self.site_data_dir / C.PATTERNS_FILENAME

    @property
    def site_accuracy(self) -> Path:
        return self.site_data_dir / C.ACCURACY_FILENAME

    @property
    def site_nojekyll(self) -> Path:
        """GitHub Pages serves the directory verbatim when this file is present."""
        return self.site_dir / ".nojekyll"

    # --- behaviour ---------------------------------------------------------
    def all_directories(self) -> Tuple[Path, ...]:
        return (
            self.data_dir,
            self.registry_dir,
            self.corpus_dir,
            self.corpus_apps_dir,
            self.raw_dir,
            self.research_responses_dir,
            self.interim_dir,
            self.verification_dir,
            self.final_dir,
            self.site_dir,
            self.site_data_dir,
        )

    def ensure_directories(self) -> None:
        """Create every directory the pipeline writes into. Idempotent."""
        for directory in self.all_directories():
            directory.mkdir(parents=True, exist_ok=True)

    def require(self, path: Path, produced_by: str) -> Path:
        """Return ``path`` if it exists, otherwise fail with an actionable error."""
        if not path.exists():
            raise MissingArtifactError(path, produced_by=produced_by)
        return path

    def relative(self, path: Path) -> str:
        """Render a path relative to the project root for logs and reports."""
        try:
            return str(path.relative_to(self.project_root))
        except ValueError:
            return str(path)

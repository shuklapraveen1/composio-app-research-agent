"""The pipeline, stage by stage, in the order the architecture locks them into.

Each function here is one stage: it reads the artifacts the previous stage
wrote, does one thing, and writes its own. They are separate so that any stage
can be re-run on its own, and sequenced by :func:`run_all` so that a reviewer
can reproduce the entire study with one command and the same seed.

The shape of the run is fixed by the architecture and is not a tuning knob:
research runs across all 100 apps exactly once per classifier version;
verification runs only over the two samples; Sample A is measured before the
improvement phase and Sample B after it.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from . import constants as C
from .config import Settings
from .dataset import build_dataset
from .errors import DataValidationError
from .io_utils import read_json, write_json
from .logging_setup import get_logger, stage_context
from .analytics import analyse_dataset, analyse_patterns
from .publish import publish_case_study, write_dataset_exports
from .research import load_corpus, research_registry
from .research.runner import persist as persist_research
from .review import build_improvement_report, build_queue, count_failures
from .schemas.analytics import AnalyticsReport, PatternReport
from .schemas.corpus import Corpus
from .schemas.review import ImprovementReport
from .schemas.dataset import Dataset
from .schemas.evidence import EvidenceSet
from .schemas.registry import NormalizedRegistry
from .schemas.research import ResearchSet
from .schemas.review import ReviewQueue
from .schemas.validation import ValidationReport  # noqa: F401  (re-exported type)
from .schemas.verification import AccuracyReport, SampleSelection
from .validation import run_validation
from .verification import (
    apply_verification_state,
    build_accuracy_report,
    current_values,
    established_values,
    frozen_values,
    measure_sample,
    select_both,
    verify,
)
from .verification.accuracy import MEASUREMENT_FINAL, MEASUREMENT_FIRST_PASS
from .verification.runner import VerificationRun


@dataclass(frozen=True)
class PipelineResult:
    """What a full run produced, for the CLI and the tests to assert against."""

    registry: NormalizedRegistry
    initial_dataset: Dataset
    final_dataset: Dataset
    validation: ValidationReport
    review_queue: ReviewQueue
    sample_a: SampleSelection
    sample_b: SampleSelection
    run_a: VerificationRun
    run_b: VerificationRun
    accuracy: AccuracyReport
    improvements: ImprovementReport
    analytics: AnalyticsReport
    patterns: PatternReport
    case_study_path: Optional[str]


def load_registry(settings: Settings) -> NormalizedRegistry:
    """The normalized registry, which every stage iterates over."""
    payload = read_json(
        settings.paths.require(
            settings.paths.registry_normalized, produced_by="registry load"
        )
    )
    return NormalizedRegistry.model_validate(payload)


def load_corpus_for(settings: Settings, registry: NormalizedRegistry) -> Corpus:
    return load_corpus(
        corpus_apps_dir=settings.paths.corpus_apps_dir,
        as_of=settings.as_of,
        seed=settings.seed,
        expected_app_ids=registry.app_ids(),
    )


def research(
    settings: Settings,
    registry: NormalizedRegistry,
    classifier_version: str,
    write: bool = True,
) -> Tuple[ResearchSet, EvidenceSet]:
    """Channel A across the whole registry."""
    with stage_context(
        C.PipelineStage.RESEARCH,
        apps=len(registry.records),
        classifier=classifier_version,
        provider=settings.research_provider.value,
    ):
        research_set, evidence_set, raw = research_registry(
            registry=registry, settings=settings, classifier_version=classifier_version
        )
        if write and not settings.dry_run:
            persist_research(settings, research_set, evidence_set, raw)
    return research_set, evidence_set


def validate(
    settings: Settings,
    registry: NormalizedRegistry,
    research_set: ResearchSet,
    evidence_set: EvidenceSet,
    write: bool = True,
) -> ValidationReport:
    """Deterministic validation; blocking errors stop the run here."""
    with stage_context(C.PipelineStage.VALIDATION, records=len(research_set.records)):
        report, ok = run_validation(registry, research_set, evidence_set, settings)
        if write and not settings.dry_run:
            write_json(settings.paths.validation_report, report.to_jsonable())
        if not ok:
            raise DataValidationError(
                "Validation found blocking errors",
                errors=len(report.errors),
                report=settings.paths.relative(settings.paths.validation_report),
            )
    return report


def initial_dataset(
    settings: Settings,
    registry: NormalizedRegistry,
    research_set: ResearchSet,
    evidence_set: EvidenceSet,
    write: bool = True,
) -> Dataset:
    """Channel A plus validation, frozen as the initial dataset."""
    with stage_context(C.PipelineStage.INITIAL_DATASET):
        dataset = build_dataset(
            registry=registry,
            research=research_set,
            evidence=evidence_set,
            settings=settings,
            stage=C.DatasetStage.INITIAL,
            notes="Channel A output after deterministic validation.",
        )
        if write and not settings.dry_run:
            write_json(settings.paths.initial_dataset, dataset.to_jsonable())
    return dataset


def review_queue(
    settings: Settings, research_set: ResearchSet, write: bool = True
) -> ReviewQueue:
    """Risk-based triggers over the whole registry."""
    with stage_context(C.PipelineStage.TRIGGER_REVIEW):
        queue = build_queue(research_set.records, settings)
        if write and not settings.dry_run:
            write_json(settings.paths.review_queue, queue.to_jsonable())
        get_logger().info(
            "review.queue", queued=len(queue.entries), share=queue.share
        )
    return queue


def samples(
    settings: Settings,
    registry: NormalizedRegistry,
    research_set: ResearchSet,
    write: bool = True,
) -> Tuple[SampleSelection, SampleSelection]:
    """Draw both samples and freeze the values they will be measured against."""
    with stage_context(
        C.PipelineStage.SAMPLE_SELECTION,
        seed=settings.seed,
        size_a=settings.sample_size_a,
        size_b=settings.sample_size_b,
    ):
        sample_a, sample_b = select_both(registry, research_set, settings)
        if write and not settings.dry_run:
            write_json(settings.paths.sample_a, sample_a.to_jsonable())
            write_json(settings.paths.sample_b, sample_b.to_jsonable())
    return sample_a, sample_b


def verification(
    settings: Settings,
    selection: SampleSelection,
    research_set: ResearchSet,
    evidence_set: EvidenceSet,
    corpus: Corpus,
    queue: Optional[ReviewQueue] = None,
    write: bool = True,
) -> VerificationRun:
    """Channels B, C and D over one sample, then reconciliation."""
    with stage_context(
        C.PipelineStage.VERIFICATION,
        group=selection.group.value,
        apps=len(selection.assignments),
    ):
        run = verify(
            selection=selection,
            research=research_set,
            evidence=evidence_set,
            corpus=corpus,
            settings=settings,
            queue=queue,
        )
        if write and not settings.dry_run:
            suffix = selection.group.value.lower()
            paths = settings.paths
            write_json(
                paths.verification_dir / "channel_b_{}.json".format(suffix),
                run.channel_b.to_jsonable(),
            )
            write_json(
                paths.verification_dir / "channel_c_{}.json".format(suffix),
                run.channel_c.to_jsonable(),
            )
            write_json(
                paths.verification_dir / "channel_d_{}.json".format(suffix),
                run.channel_d.to_jsonable(),
            )
            write_json(
                paths.verification_dir / "human_decisions_{}.json".format(suffix),
                run.human_decisions.to_jsonable(),
            )
            write_json(
                paths.verification_dir / "reconciliation_{}.json".format(suffix),
                run.reconciliation.to_jsonable(),
            )
    return run


def run_all(settings: Settings, write: bool = True) -> PipelineResult:
    """Every stage, in order, from the registry to the accuracy report.

    The two classifier passes are what make the improvement phase measurable:
    the first pass produces the values Sample A is frozen against, and the
    second produces the values Sample B is scored on.
    """
    logger = get_logger()
    registry = load_registry(settings)
    corpus = load_corpus_for(settings, registry)

    # --- first pass: classifier v1 -----------------------------------------
    research_v1, evidence_v1 = research(settings, registry, C.CLASSIFIER_V1, write=write)
    validate(settings, registry, research_v1, evidence_v1, write=write)
    initial = initial_dataset(settings, registry, research_v1, evidence_v1, write=write)
    queue_v1 = review_queue(settings, research_v1, write=write)
    sample_a, sample_b_preview = samples(settings, registry, research_v1, write=write)

    run_a = verification(
        settings, sample_a, research_v1, evidence_v1, corpus, queue_v1, write=write
    )
    truth_a = established_values(run_a.reconciliation)
    accuracy_a = measure_sample(
        group=C.SampleGroup.A,
        measurement=MEASUREMENT_FIRST_PASS,
        classifier_version=C.CLASSIFIER_V1,
        measured=frozen_values(sample_a),
        truth=truth_a,
        verification=run_a.results_by_app(),
        trigger_reviewed=[
            app_id for app_id in queue_v1.app_ids() if app_id in set(sample_a.app_ids())
        ],
    )

    # --- improvement phase --------------------------------------------------
    failures = count_failures(frozen_values(sample_a), truth_a)
    improvements = build_improvement_report(failures, settings)
    if write and not settings.dry_run:
        write_json(settings.paths.improvements, improvements.to_jsonable())
    logger.info(
        "improvements.diagnosed",
        improvements=len(improvements.improvements),
        sample_a_field_accuracy=accuracy_a.field_level_accuracy,
    )

    # --- second pass: classifier v2 ----------------------------------------
    research_v2, evidence_v2 = research(settings, registry, C.CLASSIFIER_V2, write=write)
    # The second pass overwrites validation_report.json, so this is the report
    # the published page and the committed artifact both have to agree on.
    validation_report = validate(settings, registry, research_v2, evidence_v2, write=write)
    queue_v2 = review_queue(settings, research_v2, write=write)
    sample_a_v2, sample_b = samples(settings, registry, research_v2, write=write)
    if sorted(sample_b.app_ids()) == sorted(sample_a.app_ids()):
        raise DataValidationError("Samples A and B must be disjoint")

    run_b = verification(
        settings, sample_b, research_v2, evidence_v2, corpus, queue_v2, write=write
    )
    truth_b = established_values(run_b.reconciliation)
    sampled_b = set(sample_b.app_ids())
    accuracy_b = measure_sample(
        group=C.SampleGroup.B,
        measurement=MEASUREMENT_FINAL,
        classifier_version=C.CLASSIFIER_V2,
        measured=current_values(
            [record for record in research_v2.records if record.app_id in sampled_b]
        ),
        truth=truth_b,
        verification=run_b.results_by_app(),
        trigger_reviewed=[
            app_id for app_id in queue_v2.app_ids() if app_id in sampled_b
        ],
    )

    accuracy = build_accuracy_report(
        [accuracy_a, accuracy_b],
        settings,
        notes=(
            "Sample A measures classifier {} before the improvement phase; "
            "Sample B measures classifier {} on apps it had never been "
            "evaluated against.".format(C.CLASSIFIER_V1, C.CLASSIFIER_V2)
        ),
    )
    if write and not settings.dry_run:
        write_json(settings.paths.accuracy, accuracy.to_jsonable())

    # --- final dataset ------------------------------------------------------
    final = final_dataset(
        settings=settings,
        registry=registry,
        research_set=research_v2,
        evidence_set=evidence_v2,
        runs=[run_a, run_b],
        selections=[sample_a_v2, sample_b],
        write=write,
    )

    # --- analytics and publication -----------------------------------------
    analytics_report, patterns_report = analytics(settings, final, write=write)
    case_study_path = None
    if write and not settings.dry_run:
        write_dataset_exports(
            dataset=final,
            analytics=analytics_report,
            patterns=patterns_report,
            accuracy=accuracy,
            settings=settings,
        )
        case_study_path = publish_case_study(
            dataset=final,
            analytics=analytics_report,
            patterns=patterns_report,
            accuracy=accuracy,
            improvements=improvements,
            validation=validation_report,
            queue=queue_v2,
            settings=settings,
        )

    return PipelineResult(
        registry=registry,
        initial_dataset=initial,
        final_dataset=final,
        validation=validation_report,
        review_queue=queue_v2,
        sample_a=sample_a,
        sample_b=sample_b,
        run_a=run_a,
        run_b=run_b,
        accuracy=accuracy,
        improvements=improvements,
        analytics=analytics_report,
        patterns=patterns_report,
        case_study_path=case_study_path,
    )


def analytics(
    settings: Settings, dataset: Dataset, write: bool = True
) -> Tuple[AnalyticsReport, PatternReport]:
    """Deterministic metrics and patterns, computed from the final dataset only."""
    with stage_context(C.PipelineStage.ANALYTICS, records=len(dataset.records)):
        report = analyse_dataset(dataset, settings)
        found = analyse_patterns(dataset, settings)
        if write and not settings.dry_run:
            write_json(settings.paths.analytics, report.to_jsonable())
            write_json(settings.paths.patterns, found.to_jsonable())
    return report, found


def final_dataset(
    settings: Settings,
    registry: NormalizedRegistry,
    research_set: ResearchSet,
    evidence_set: EvidenceSet,
    runs: List[VerificationRun],
    selections: List[SampleSelection],
    write: bool = True,
) -> Dataset:
    """The one canonical dataset: improved research plus everything verification found."""
    with stage_context(C.PipelineStage.FINAL_DATASET):
        sample_groups: Dict[str, C.SampleGroup] = {}
        for selection in selections:
            for app_id in selection.app_ids():
                sample_groups[app_id] = selection.group

        results = [result for run in runs for result in run.all_results()]
        decisions = [
            decision
            for run in runs
            for decision in run.reconciliation.decisions
        ]

        records = list(research_set.records)
        for run in runs:
            records = apply_verification_state(records, run)
        updated = ResearchSet(
            metadata=research_set.metadata,
            records=sorted(records, key=lambda item: item.app_id),
        )

        dataset = build_dataset(
            registry=registry,
            research=updated,
            evidence=evidence_set,
            settings=settings,
            stage=C.DatasetStage.FINAL,
            verification=results,
            reconciliation=decisions,
            sample_groups=sample_groups,
            notes=(
                "Classifier {} across all {} apps, with verification and "
                "reconciliation attached for the {} sampled apps.".format(
                    updated.records[0].classifier_version if updated.records else "-",
                    len(updated.records),
                    len(sample_groups),
                )
            ),
        )
        if write and not settings.dry_run:
            write_json(settings.paths.final_dataset, dataset.to_jsonable())
    return dataset

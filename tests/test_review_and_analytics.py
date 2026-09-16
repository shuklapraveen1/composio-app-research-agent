"""Review triggers, analytics, and pattern analysis."""

from datetime import datetime, timezone

from composio_ops import constants as C
from composio_ops.analytics import compute, patterns
from composio_ops.config import load_settings
from composio_ops.dataset import build_dataset, final_value
from composio_ops.research.evidence import EvidenceIndex, build_evidence
from composio_ops.research.rules import classify
from composio_ops.review import build_improvement_report, build_queue, count_failures
from composio_ops.review.triggers import triggers_for
from composio_ops.schemas.evidence import EvidenceSet
from composio_ops.schemas.research import ResearchSet
from composio_ops.schemas.verification import FieldValue
from composio_ops.taxonomy import ResearchFieldName, ResolutionStatus

from factories import corpus_entry, metadata, registry

F = ResearchFieldName
WHEN = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _world(tmp_path, **entry_kwargs):
    settings = load_settings(_env_file=None, project_root=tmp_path, data_dir="data")
    reg = registry(WHEN, app_count=4, category_count=2)
    records, items = [], []
    for record in reg.records:
        entry = corpus_entry(app_id=record.app_id, **entry_kwargs)
        built = build_evidence(entry, captured_at=WHEN)
        items.extend(built)
        records.append(
            classify(
                entry=entry,
                app=record,
                index=EvidenceIndex(built),
                version=C.CLASSIFIER_V2,
                provider=C.ResearchProvider.CORPUS,
                generated_at=WHEN,
            ).model_copy(update={"category_id": record.category_id})
        )
    research = ResearchSet(
        metadata=metadata(C.PipelineStage.CLASSIFICATION, len(records), WHEN),
        records=sorted(records, key=lambda item: item.app_id),
    )
    evidence = EvidenceSet(
        metadata=metadata(C.PipelineStage.EVIDENCE_EXTRACTION, len(items), WHEN),
        items=sorted(items, key=lambda item: item.evidence_id),
    )
    dataset = build_dataset(
        registry=reg,
        research=research,
        evidence=evidence,
        settings=settings,
        stage=C.DatasetStage.FINAL,
    )
    return settings, research, dataset


def test_a_clean_record_raises_no_triggers(tmp_path):
    _, research, _ = _world(tmp_path)
    triggers, fields, details = triggers_for(research.records[0])
    assert triggers == []
    assert fields == [] and details == []


def test_contradictions_and_low_confidence_reach_the_queue(tmp_path):
    settings, research, _ = _world(
        tmp_path, conflicts=["The pricing page contradicts the docs on the paid plan."]
    )
    queue = build_queue(research.records, settings)
    assert len(queue.entries) == len(research.records)
    assert queue.share == 1.0
    entry = queue.entries[0]
    assert C.ReviewTrigger.SOURCE_CONTRADICTION in entry.triggers
    assert F.CREDENTIAL_ACCESS in entry.fields
    assert entry.detail


def test_unresolved_identity_is_always_a_trigger(tmp_path):
    _, research, _ = _world(tmp_path, identity_ambiguous=True)
    triggers, _, _ = triggers_for(research.records[0])
    assert C.ReviewTrigger.UNRESOLVED_IDENTITY in triggers
    assert C.ReviewTrigger.LOW_CONFIDENCE in triggers


def test_distributions_count_unresolved_values_rather_than_dropping_them(tmp_path):
    _, _, dataset = _world(tmp_path, api_exists=None)
    distribution = compute.distribution(dataset, F.API_BREADTH)
    assert distribution.total == len(dataset.records)
    assert sum(distribution.counts.values()) + sum(
        distribution.unresolved.values()
    ) == len(dataset.records)
    assert distribution.unresolved


def test_metrics_are_computed_from_the_dataset(tmp_path):
    _, _, dataset = _world(tmp_path)
    metrics = {item.key: item.value for item in compute.metrics(dataset)}
    assert metrics["apps_total"] == len(dataset.records)
    assert metrics["buildable"] + metrics["buildable_with_friction"] + metrics[
        "blocked"
    ] <= len(dataset.records)


def test_patterns_list_the_applications_behind_each_claim(tmp_path):
    settings, _, dataset = _world(tmp_path)
    report = patterns.analyse(dataset, settings)
    assert report.patterns
    for pattern in report.patterns:
        assert pattern.observed == len(pattern.supporting_app_ids)
        assert pattern.population == len(dataset.records)
        assert "{}".format(pattern.observed) in pattern.statement


def test_reconciled_values_win_over_the_classifier_in_every_readout(tmp_path):
    settings, research, dataset = _world(tmp_path)
    record = dataset.records[0]
    assert final_value(record, F.API_EXISTS).value == ["true"]


def test_improvements_count_the_failures_they_answer(tmp_path):
    settings, _, _ = _world(tmp_path)
    measured = {
        "app-1": {
            F.CREDENTIAL_ACCESS: FieldValue(
                field=F.CREDENTIAL_ACCESS,
                status=ResolutionStatus.RESOLVED,
                value=["self_serve_free"],
            )
        }
    }
    truth = {
        "app-1": {
            F.CREDENTIAL_ACCESS: FieldValue(
                field=F.CREDENTIAL_ACCESS,
                status=ResolutionStatus.RESOLVED,
                value=["self_serve_paid"],
            )
        }
    }
    failures = count_failures(measured, truth)
    assert failures[F.CREDENTIAL_ACCESS] == 1
    report = build_improvement_report(failures, settings)
    gated = next(
        item
        for item in report.improvements
        if item.key == "credential-access-plan-gating"
    )
    assert gated.observed_in_sample_a == 1

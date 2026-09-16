"""Sampling, the verification channels, reconciliation, and accuracy.

The properties under test are the ones the accuracy claim rests on: the samples
are reproducible, stratified and disjoint; Sample A's values are frozen before
the improvement phase; reconciliation follows a fixed precedence; and a human
who never ruled on a field cannot be counted as having endorsed it.
"""

from datetime import datetime, timezone

import pytest

from composio_ops import constants as C
from composio_ops.config import load_settings
from composio_ops.research.evidence import EvidenceIndex, build_evidence
from composio_ops.research.rules import classify
from composio_ops.schemas.evidence import EvidenceSet
from composio_ops.schemas.research import ResearchSet
from composio_ops.schemas.verification import FieldValue, HumanDecision
from composio_ops.taxonomy import ResearchFieldName, ResolutionStatus
from composio_ops.verification import channels, reconcile_field, sampling
from composio_ops.verification.accuracy import measure_sample
from composio_ops.verification.reconcile import established_values

from factories import app_record, corpus, corpus_entry, metadata, registry

F = ResearchFieldName
WHEN = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


@pytest.fixture()
def world(tmp_path):
    """A small synthetic registry, corpus and research pass wired together."""
    settings = load_settings(
        _env_file=None,
        project_root=tmp_path,
        data_dir="data",
        sample_size_a=2,
        sample_size_b=2,
    )
    reg = registry(WHEN, app_count=8, category_count=2)
    entries = [
        corpus_entry(app_id=record.app_id, account="free", api_plan="paid")
        for record in reg.records
    ]
    records = []
    items = []
    for record, entry in zip(reg.records, entries):
        built = build_evidence(entry, captured_at=WHEN)
        items.extend(built)
        records.append(
            classify(
                entry=entry,
                app=record,
                index=EvidenceIndex(built),
                version=C.CLASSIFIER_V1,
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
    return settings, reg, research, evidence, corpus(WHEN, entries)


def test_samples_are_reproducible_disjoint_and_stratified(world):
    settings, reg, research, _, _ = world
    first_a, first_b = sampling.select_both(reg, research, settings)
    second_a, second_b = sampling.select_both(reg, research, settings)

    assert first_a.app_ids() == second_a.app_ids()
    assert first_b.app_ids() == second_b.app_ids()
    assert not set(first_a.app_ids()) & set(first_b.app_ids())
    assert len(first_a.assignments) == settings.sample_size_a
    categories = {item.category_id for item in first_a.assignments}
    assert len(categories) == len(reg.categories)


def test_a_different_seed_draws_a_different_sample(world):
    settings, reg, research, _, _ = world
    other = settings.model_copy(update={"seed": settings.seed + 1})
    first, _ = sampling.select_both(reg, research, settings)
    second, _ = sampling.select_both(reg, research, other)
    assert first.app_ids() != second.app_ids()


def test_sample_a_values_are_frozen_at_selection(world):
    settings, reg, research, _, _ = world
    sample_a, _ = sampling.select_both(reg, research, settings)
    frozen = {
        (item.app_id, item.field): item for item in sample_a.frozen_values
    }
    assert frozen
    for (app_id, field), item in frozen.items():
        assert item.classifier_version == C.CLASSIFIER_V1
        current = channels.current_value(
            next(record for record in research.records if record.app_id == app_id), field
        )
        assert item.as_field_value().matches(current)


def test_channel_b_disagrees_with_v1_on_plan_gated_credentials(world):
    settings, reg, research, _, book = world
    sample_a, _ = sampling.select_both(reg, research, settings)
    records = [
        record for record in research.records if record.app_id in set(sample_a.app_ids())
    ]
    artifact = channels.run_channel_b(records, book, settings)
    assert artifact.channel is C.Channel.CHANNEL_B
    assert all(
        F.CREDENTIAL_ACCESS in result.discrepancies for result in artifact.results
    )


def test_channel_c_audits_citations_against_the_fields_they_support(world):
    settings, reg, research, evidence, _ = world
    sample_a, _ = sampling.select_both(reg, research, settings)
    sampled = set(sample_a.app_ids())
    records = [record for record in research.records if record.app_id in sampled]
    by_app = {}
    for item in evidence.items:
        by_app.setdefault(item.app_id, []).append(item)
    artifact = channels.run_channel_c(records, by_app, settings)
    checks = [check for result in artifact.results for check in result.evidence_results]
    assert checks
    assert all(check.reachable for check in checks)


def test_channel_d_is_silent_without_a_recorded_human_judgement(world):
    settings, _, research, _, _ = world
    artifact, decisions = channels.run_channel_d(
        research.records, settings, fields_by_app={}
    )
    assert artifact.results == []
    assert decisions.decisions == []


# --- reconciliation ---------------------------------------------------------


def _value(field, status=ResolutionStatus.RESOLVED, tokens=None):
    return FieldValue(field=field, status=status, value=tokens)


def test_human_decisions_outrank_every_automated_channel():
    human = HumanDecision(
        app_id="example-app-001",
        field=F.CREDENTIAL_ACCESS,
        decision=C.ReviewDecision.CORRECT,
        entry_path="sample",
        original_status=ResolutionStatus.RESOLVED,
        original_value=["self_serve_free"],
        corrected_status=ResolutionStatus.RESOLVED,
        corrected_value=["self_serve_paid"],
        reason="The API is on the paid plan.",
        evidence_ids=["ev-1"],
        reviewer="tester",
        decided_at=WHEN,
    )
    outcome, value, authoritative, superseded, _ = reconcile_field(
        field=F.CREDENTIAL_ACCESS,
        channel_a=_value(F.CREDENTIAL_ACCESS, tokens=["self_serve_free"]),
        channel_b=_value(F.CREDENTIAL_ACCESS, tokens=["enterprise"]),
        channel_c_valid=True,
        human=human,
    )
    assert outcome is C.ReconciliationOutcome.CORRECTED
    assert value.value == ["self_serve_paid"]
    assert authoritative is C.Channel.CHANNEL_D
    assert superseded is C.Channel.CHANNEL_A


def test_one_disagreeing_channel_downgrades_a_single_valued_field():
    outcome, value, _, _, _ = reconcile_field(
        field=F.CREDENTIAL_ACCESS,
        channel_a=_value(F.CREDENTIAL_ACCESS, tokens=["self_serve_free"]),
        channel_b=_value(F.CREDENTIAL_ACCESS, tokens=["admin_approval"]),
        channel_c_valid=True,
        human=None,
    )
    assert outcome is C.ReconciliationOutcome.DOWNGRADED_TO_UNCLEAR
    assert value.status is ResolutionStatus.UNCLEAR


def test_multi_valued_fields_reconcile_as_a_union():
    outcome, value, _, _, _ = reconcile_field(
        field=F.AUTHENTICATION,
        channel_a=_value(F.AUTHENTICATION, tokens=["oauth2"]),
        channel_b=_value(F.AUTHENTICATION, tokens=["api_key"]),
        channel_c_valid=True,
        human=None,
    )
    assert outcome is C.ReconciliationOutcome.CORRECTED
    assert value.value == ["api_key", "oauth2"]


def test_two_channels_against_one_replace_the_value():
    outcome, value, authoritative, _, _ = reconcile_field(
        field=F.API_BREADTH,
        channel_a=_value(F.API_BREADTH, tokens=["very_broad"]),
        channel_b=_value(F.API_BREADTH, tokens=["moderate"]),
        channel_c_valid=False,
        human=None,
    )
    assert outcome is C.ReconciliationOutcome.CORRECTED
    assert value.value == ["moderate"]
    assert authoritative is C.Channel.CHANNEL_B


def test_a_value_without_surviving_citations_is_downgraded():
    outcome, value, authoritative, _, _ = reconcile_field(
        field=F.RATE_LIMIT_INFO,
        channel_a=_value(F.RATE_LIMIT_INFO, tokens=["documented_quantitative"]),
        channel_b=None,
        channel_c_valid=False,
        human=None,
    )
    assert outcome is C.ReconciliationOutcome.DOWNGRADED_TO_UNCLEAR
    assert authoritative is C.Channel.CHANNEL_C
    assert value.status is ResolutionStatus.UNCLEAR


def test_agreement_confirms_without_changing_anything():
    outcome, value, _, superseded, _ = reconcile_field(
        field=F.API_EXISTS,
        channel_a=_value(F.API_EXISTS, tokens=["true"]),
        channel_b=_value(F.API_EXISTS, tokens=["true"]),
        channel_c_valid=True,
        human=None,
    )
    assert outcome is C.ReconciliationOutcome.CONFIRMED
    assert value.value == ["true"]
    assert superseded is None


# --- accuracy ---------------------------------------------------------------


def test_row_level_accuracy_requires_every_field_to_be_right():
    truth = {
        "app-1": {
            F.API_EXISTS: _value(F.API_EXISTS, tokens=["true"]),
            F.MCP: _value(F.MCP, tokens=["official"]),
        }
    }
    measured = {
        "app-1": {
            F.API_EXISTS: _value(F.API_EXISTS, tokens=["true"]),
            F.MCP: _value(F.MCP, tokens=["third_party"]),
        }
    }
    accuracy = measure_sample(
        group=C.SampleGroup.A,
        measurement="first_pass",
        classifier_version=C.CLASSIFIER_V1,
        measured=measured,
        truth=truth,
        verification={},
    )
    assert accuracy.fields_checked == 2
    assert accuracy.fields_correct == 1
    assert accuracy.field_level_accuracy == 0.5
    assert accuracy.row_level_accuracy == 0.0

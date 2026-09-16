"""Deterministic validation.

Each test constructs a record that is wrong in one specific way and asserts that
validation says so, because a validator that never fails is indistinguishable
from no validator at all.
"""

from datetime import datetime, timezone

from composio_ops import constants as C
from composio_ops.research.evidence import EvidenceIndex, build_evidence
from composio_ops.research.rules import classify
from composio_ops.schemas.base import ArtifactMetadata
from composio_ops.schemas.evidence import EvidenceSet
from composio_ops.schemas.research import ResearchSet
from composio_ops.validation.rules import registrable_domain, summarize, validate
from composio_ops.taxonomy import Buildability, Dimension, ResolutionStatus

from factories import app_record, corpus_entry, metadata, registry

WHEN = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _artifacts(record, items):
    research = ResearchSet(
        metadata=metadata(C.PipelineStage.CLASSIFICATION, 1, WHEN), records=[record]
    )
    evidence = EvidenceSet(
        metadata=metadata(C.PipelineStage.EVIDENCE_EXTRACTION, len(items), WHEN),
        items=items,
    )
    return research, evidence


def _classified(app_id="example-app-001", version=C.CLASSIFIER_V2):
    entry = corpus_entry(app_id=app_id)
    items = build_evidence(entry, captured_at=WHEN)
    record = classify(
        entry=entry,
        app=app_record(app_id=app_id),
        index=EvidenceIndex(items),
        version=version,
        provider=C.ResearchProvider.CORPUS,
        generated_at=WHEN,
    )
    return record, items


def _single_app_registry():
    reg = registry(WHEN, app_count=1, category_count=1)
    return reg


def test_a_clean_research_pass_produces_no_blocking_errors():
    record, items = _classified()
    reg = _single_app_registry()
    record = record.model_copy(update={"category_id": reg.records[0].category_id})
    research, evidence = _artifacts(record, items)
    issues = validate(reg, research, evidence)
    assert [issue for issue in issues if issue.severity is C.Severity.ERROR] == []


def test_missing_records_are_errors():
    record, items = _classified()
    reg = registry(WHEN, app_count=2, category_count=1)
    record = record.model_copy(
        update={
            "app_id": reg.records[0].app_id,
            "category_id": reg.records[0].category_id,
        }
    )
    items = [item.model_copy(update={"app_id": reg.records[0].app_id}) for item in items]
    research, evidence = _artifacts(record, items)
    codes = summarize(validate(reg, research, evidence))
    assert codes.get("record_missing") == 1


def test_citing_evidence_that_does_not_exist_is_an_error():
    record, items = _classified()
    reg = _single_app_registry()
    record = record.model_copy(update={"category_id": reg.records[0].category_id})
    research, evidence = _artifacts(record, items[:1])
    codes = summarize(validate(reg, research, evidence))
    assert codes.get("evidence_missing", 0) > 0


def test_confidence_must_follow_from_its_recorded_inputs():
    record, items = _classified()
    reg = _single_app_registry()
    record = record.model_copy(
        update={
            "category_id": reg.records[0].category_id,
            "confidence": C.Confidence.LOW,
        }
    )
    research, evidence = _artifacts(record, items)
    codes = summarize(validate(reg, research, evidence))
    assert codes.get("confidence_not_derived") == 1


def test_buildability_must_follow_from_its_dimensions():
    record, items = _classified()
    reg = _single_app_registry()
    broken = record.buildability_assessment.model_copy(
        update={"credential_accessibility": Dimension.FAIL}
    )
    record = record.model_copy(
        update={
            "category_id": reg.records[0].category_id,
            "buildability_assessment": broken,
        }
    )
    research, evidence = _artifacts(record, items)
    codes = summarize(validate(reg, research, evidence))
    assert codes.get("buildability_not_derived") == 1


def test_category_mismatch_with_the_registry_is_an_error():
    record, items = _classified()
    reg = _single_app_registry()
    record = record.model_copy(update={"category_id": "invented-category"})
    research, evidence = _artifacts(record, items)
    codes = summarize(validate(reg, research, evidence))
    assert codes.get("category_mismatch") == 1


def test_unresolved_fields_are_warnings_not_errors():
    entry = corpus_entry(api_exists=None)
    items = build_evidence(entry, captured_at=WHEN)
    reg = _single_app_registry()
    record = classify(
        entry=entry,
        app=app_record(app_id=entry.app_id),
        index=EvidenceIndex(items),
        version=C.CLASSIFIER_V2,
        provider=C.ResearchProvider.CORPUS,
        generated_at=WHEN,
    ).model_copy(update={"category_id": reg.records[0].category_id})
    research, evidence = _artifacts(record, items)
    issues = validate(reg, research, evidence)
    assert any(issue.code == "field_unresolved" for issue in issues)
    assert all(issue.severity is not C.Severity.ERROR for issue in issues)


def test_registrable_domain_treats_documentation_subdomains_as_the_same_vendor():
    assert registrable_domain("developers.example.test") == registrable_domain(
        "workspace.example.test"
    )
    assert registrable_domain("docs.example.co.uk") == "example.co.uk"
    assert registrable_domain("example.test") == "example.test"

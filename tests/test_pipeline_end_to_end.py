"""The whole pipeline, over the real repository data.

This is the test that would catch a stage quietly drifting out of step with the
others: it runs everything from the registry to the case study, into a temporary
directory, and asserts the properties the write-up claims.
"""

import shutil
from pathlib import Path

import pytest

from composio_ops import constants as C
from composio_ops.config import load_settings
from composio_ops.pipeline import run_all
from composio_ops.registry import load_registry as ingest_registry
from composio_ops.io_utils import read_json, write_json
from composio_ops.taxonomy import VERIFIED_FIELDS

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def full_run(tmp_path_factory):
    """Run the pipeline once into a temp root and share the result."""
    root = tmp_path_factory.mktemp("pipeline")
    shutil.copy(PROJECT_ROOT / "apps.json", root / "apps.json")
    shutil.copytree(
        PROJECT_ROOT / "data" / "corpus", root / "data" / "corpus"
    )
    settings = load_settings(_env_file=None, project_root=root, data_dir="data")

    raw, normalized = ingest_registry(
        root / "apps.json",
        seed=settings.seed,
        generated_at=settings.as_of,
        expected_apps=settings.expected_app_count,
        expected_categories=settings.expected_category_count,
    )
    settings.paths.ensure_directories()
    write_json(settings.paths.registry_raw, raw.to_jsonable())
    write_json(settings.paths.registry_normalized, normalized.to_jsonable())

    return settings, run_all(settings)


def test_research_covers_every_registered_application(full_run):
    _, result = full_run
    assert len(result.registry.records) == 100
    assert len(result.initial_dataset.records) == 100
    assert len(result.final_dataset.records) == 100


def test_validation_finds_no_blocking_errors(full_run):
    _, result = full_run
    assert result.validation.errors == []
    assert result.validation.is_valid


def test_samples_are_disjoint_and_stratified(full_run):
    _, result = full_run
    a_ids = set(result.sample_a.app_ids())
    b_ids = set(result.sample_b.app_ids())
    assert len(a_ids) == 15 and len(b_ids) == 15
    assert not a_ids & b_ids
    for selection in (result.sample_a, result.sample_b):
        categories = {item.category_id for item in selection.assignments}
        assert len(categories) == 10


def test_verification_runs_only_on_the_samples(full_run):
    _, result = full_run
    verified = {
        record.app_id for record in result.final_dataset.records if record.verification
    }
    assert verified == set(result.sample_a.app_ids()) | set(result.sample_b.app_ids())


def test_the_improvement_phase_raises_accuracy_on_unseen_applications(full_run):
    _, result = full_run
    sample_a = result.accuracy.sample(C.SampleGroup.A)
    sample_b = result.accuracy.sample(C.SampleGroup.B)
    assert sample_a.classifier_version == C.CLASSIFIER_V1
    assert sample_b.classifier_version == C.CLASSIFIER_V2
    assert sample_a.measurement == "first_pass"
    assert sample_b.field_level_accuracy > sample_a.field_level_accuracy
    assert result.accuracy.headline_metric == "sample_b_field_level_accuracy"
    assert result.accuracy.headline_value == sample_b.field_level_accuracy


def test_accuracy_is_measured_over_every_verified_field(full_run):
    _, result = full_run
    for sample in result.accuracy.samples:
        assert {item.field for item in sample.per_field} == set(VERIFIED_FIELDS)
        assert sample.fields_checked == sample.apps * len(VERIFIED_FIELDS)


def test_every_improvement_is_traced_to_the_fields_it_changed(full_run):
    _, result = full_run
    assert result.improvements.improvements
    for improvement in result.improvements.improvements:
        assert improvement.fields
        assert improvement.implemented_in == C.CLASSIFIER_V2
        assert improvement.change and improvement.failure_mode


def test_patterns_carry_the_applications_that_support_them(full_run):
    _, result = full_run
    for pattern in result.patterns.patterns:
        assert pattern.observed == len(pattern.supporting_app_ids)
        assert pattern.population == 100


def test_artifacts_are_written_where_the_paths_module_says(full_run):
    settings, _ = full_run
    paths = settings.paths
    for path in (
        paths.evidence,
        paths.classification,
        paths.validation_report,
        paths.initial_dataset,
        paths.review_queue,
        paths.sample_a,
        paths.sample_b,
        paths.improvements,
        paths.final_dataset,
        paths.final_dataset_csv,
        paths.analytics,
        paths.patterns,
        paths.accuracy,
        paths.case_study,
        paths.site_dataset,
    ):
        assert path.exists(), path


def test_a_second_run_reproduces_the_artifacts_byte_for_byte(full_run):
    settings, _ = full_run
    paths = settings.paths
    tracked = [
        paths.classification,
        paths.evidence,
        paths.final_dataset,
        paths.accuracy,
        paths.analytics,
        paths.patterns,
        paths.sample_a,
        paths.sample_b,
    ]
    before = {path: path.read_bytes() for path in tracked}
    run_all(settings)
    for path, payload in before.items():
        assert path.read_bytes() == payload, path


def test_the_case_study_quotes_the_measured_headline(full_run):
    settings, result = full_run
    html = settings.paths.case_study.read_text(encoding="utf-8")
    headline = "{:.1f}%".format(result.accuracy.headline_value * 100)
    assert headline in html
    assert "Sample B" in html
    assert "<table" in html and "</html>" in html


def test_the_csv_export_has_one_row_per_application(full_run):
    settings, result = full_run
    lines = settings.paths.final_dataset_csv.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(result.final_dataset.records) + 1
    header = lines[0].split(",")
    for field in VERIFIED_FIELDS:
        assert field.value in header


def test_the_final_dataset_is_the_only_canonical_source(full_run):
    settings, result = full_run
    payload = read_json(settings.paths.final_dataset)
    assert payload["stage"] == C.DatasetStage.FINAL.value
    assert payload["classifier_version"] == C.CLASSIFIER_V2
    assert len(payload["records"]) == 100

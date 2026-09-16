"""Artifact paths and deterministic I/O."""

import json

import pytest

from composio_ops.errors import MissingArtifactError, PipelineError
from composio_ops.io_utils import (
    atomic_write_text,
    dumps_json,
    read_json,
    read_jsonl,
    write_csv,
    write_json,
    write_jsonl,
)


def test_every_artifact_lives_under_the_data_directory(settings):
    paths = settings.paths
    for path in (
        paths.registry_raw,
        paths.registry_normalized,
        paths.evidence,
        paths.classification,
        paths.validation_report,
        paths.initial_dataset,
        paths.review_queue,
        paths.improvements,
        paths.sample_a,
        paths.sample_b,
        paths.channel_b,
        paths.channel_c,
        paths.human_decisions,
        paths.reconciliation,
        paths.final_dataset,
        paths.final_dataset_csv,
        paths.analytics,
        paths.patterns,
        paths.accuracy,
        paths.corpus_apps_dir,
        paths.ground_truth,
    ):
        assert paths.data_dir in path.parents


def test_ensure_directories_is_idempotent(settings):
    paths = settings.paths
    paths.ensure_directories()
    paths.ensure_directories()
    for directory in paths.all_directories():
        assert directory.is_dir()


def test_require_reports_the_producing_stage(settings):
    paths = settings.paths
    with pytest.raises(MissingArtifactError) as excinfo:
        paths.require(paths.final_dataset, produced_by="reconciliation")
    assert "reconciliation" in str(excinfo.value)


def test_relative_rendering(settings):
    paths = settings.paths
    assert paths.relative(paths.final_dataset).startswith("data/")


def test_json_round_trip_and_stability(tmp_path):
    payload = {"b": [3, 2, 1], "a": {"z": 1, "y": 2}}
    target = tmp_path / "nested" / "artifact.json"
    write_json(target, payload)
    assert read_json(target) == payload

    first = target.read_text(encoding="utf-8")
    write_json(target, json.loads(json.dumps(payload)))
    assert target.read_text(encoding="utf-8") == first
    assert first.endswith("\n")
    assert first.index('"a"') < first.index('"b"')


def test_dumps_json_sorts_keys():
    assert dumps_json({"b": 1, "a": 2}) == dumps_json({"a": 2, "b": 1})


def test_read_json_missing_file_raises_missing_artifact(tmp_path):
    with pytest.raises(MissingArtifactError):
        read_json(tmp_path / "absent.json")


def test_read_json_rejects_malformed_content(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(PipelineError):
        read_json(broken)


def test_jsonl_round_trip(tmp_path):
    rows = [{"a": 1}, {"b": 2}]
    target = tmp_path / "rows.jsonl"
    write_jsonl(target, rows)
    assert read_jsonl(target) == rows


def test_csv_uses_the_declared_column_order(tmp_path):
    target = tmp_path / "out.csv"
    write_csv(
        target,
        [{"name": "alpha", "tags": ["x", "y"], "ok": True, "missing": None}],
        columns=["name", "ok", "tags", "missing"],
    )
    lines = target.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "name,ok,tags,missing"
    assert lines[1] == "alpha,true,x|y,"


def test_atomic_write_leaves_no_temp_files(tmp_path):
    target = tmp_path / "file.txt"
    atomic_write_text(target, "content")
    assert target.read_text(encoding="utf-8") == "content"
    assert [item.name for item in tmp_path.iterdir()] == ["file.txt"]


def test_failed_write_does_not_clobber_the_previous_file(tmp_path, monkeypatch):
    target = tmp_path / "file.json"
    write_json(target, {"version": 1})

    def explode(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("composio_ops.io_utils.os.replace", explode)
    with pytest.raises(OSError):
        write_json(target, {"version": 2})

    assert read_json(target) == {"version": 1}
    assert [item.name for item in tmp_path.iterdir()] == ["file.json"]

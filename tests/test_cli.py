"""CLI wiring: help, configuration overrides, and exit codes."""

import pytest
from typer.testing import CliRunner

from composio_ops import constants as C
from composio_ops.cli import (
    analyze,
    casestudy,
    pipeline,
    registry,
    research,
    verify,
)
from composio_ops.cli.main import app
from composio_ops.errors import ExitCode

from factories import synthetic_rows, write_csv_source

runner = CliRunner()


def combined_output(result) -> str:
    """Stdout plus stderr, across click versions that separate the two."""
    text = result.output or ""
    try:
        text += result.stderr or ""
    except ValueError:
        pass
    return text

#: Stage commands that need artifacts an empty data directory does not have.
STAGE_COMMANDS = [
    ("research", ["run"]),
    ("research", ["validate"]),
    ("research", ["review-queue"]),
    ("verify", ["sample"]),
    ("verify", ["run"]),
    ("analyze", ["run"]),
    ("casestudy", ["build"]),
    ("pipeline", ["run"]),
]

GROUPS = ["registry", "research", "verify", "analyze", "casestudy", "pipeline"]


def test_root_help_lists_every_stage():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for group in GROUPS:
        assert group in result.stdout


@pytest.mark.parametrize("group", GROUPS)
def test_stage_help_works_without_any_data(group):
    result = runner.invoke(app, [group, "--help"])
    assert result.exit_code == 0


@pytest.mark.parametrize(
    "stage_app",
    [
        registry.app,
        research.app,
        verify.app,
        analyze.app,
        casestudy.app,
        pipeline.app,
    ],
)
def test_stage_apps_are_independently_runnable(stage_app):
    assert runner.invoke(stage_app, ["--help"]).exit_code == 0


def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert C.SCHEMA_VERSION in result.stdout


def test_init_creates_the_artifact_layout(tmp_path):
    result = runner.invoke(app, ["--data-dir", str(tmp_path / "data"), "init"])
    assert result.exit_code == 0
    assert (tmp_path / "data" / "final").is_dir()
    assert (tmp_path / "data" / "registry").is_dir()


def test_init_is_idempotent(tmp_path):
    args = ["--data-dir", str(tmp_path / "data"), "init"]
    assert runner.invoke(app, args).exit_code == 0
    assert runner.invoke(app, args).exit_code == 0


def test_status_reports_missing_artifacts(tmp_path):
    result = runner.invoke(app, ["--data-dir", str(tmp_path / "data"), "status"])
    assert result.exit_code == 0
    assert "final_dataset" in result.stdout
    assert "missing" in result.stdout


def test_status_reflects_a_seed_override(tmp_path):
    result = runner.invoke(
        app, ["--seed", "12345", "--data-dir", str(tmp_path / "data"), "status"]
    )
    assert result.exit_code == 0
    assert "12345" in result.stdout


def test_invalid_configuration_exits_with_the_configuration_code(tmp_path):
    result = runner.invoke(app, ["--log-level", "LOUD", "status"])
    assert result.exit_code != 0


@pytest.mark.parametrize("group,command", STAGE_COMMANDS)
def test_stages_name_the_artifact_they_are_missing(group, command, tmp_path):
    """A stage run out of order should say what to run first, not stack-trace."""
    result = runner.invoke(
        app, ["--data-dir", str(tmp_path / "data"), group] + command
    )
    assert result.exit_code == ExitCode.MISSING_ARTIFACT
    assert "Error:" in combined_output(result)


def test_a_missing_registry_points_at_the_command_that_produces_it(tmp_path):
    result = runner.invoke(app, ["--data-dir", str(tmp_path / "data"), "research", "run"])
    assert result.exit_code == ExitCode.MISSING_ARTIFACT
    assert "registry" in combined_output(result)


def test_stage_options_are_accepted(tmp_path):
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path / "data"),
            "research",
            "run",
            "--classifier",
            C.CLASSIFIER_V2,
            "--provider",
            C.ResearchProvider.CORPUS.value,
        ],
    )
    assert result.exit_code == ExitCode.MISSING_ARTIFACT


def test_unknown_option_is_rejected():
    assert runner.invoke(app, ["--nonsense"]).exit_code != 0


# --- registry ---------------------------------------------------------------


@pytest.fixture()
def source(tmp_path):
    path = tmp_path / "apps.csv"
    write_csv_source(path, synthetic_rows())
    return path


def test_registry_load_writes_both_artifacts(tmp_path, source):
    data_dir = tmp_path / "data"
    result = runner.invoke(
        app, ["--data-dir", str(data_dir), "registry", "load", "--source", str(source)]
    )
    assert result.exit_code == 0, combined_output(result)
    assert (data_dir / "registry" / "registry_raw.json").exists()
    assert (data_dir / "registry" / "registry_normalized.json").exists()
    assert "100 applications across 10 categories" in result.stdout


def test_registry_load_is_byte_stable(tmp_path, source):
    """Registry artifacts carry the pipeline clock, not the wall clock."""
    data_dir = tmp_path / "data"
    args = ["--data-dir", str(data_dir), "registry", "load", "--source", str(source)]
    assert runner.invoke(app, args).exit_code == 0
    written = [
        data_dir / "registry" / "registry_raw.json",
        data_dir / "registry" / "registry_normalized.json",
    ]
    first = [path.read_bytes() for path in written]
    assert runner.invoke(app, args).exit_code == 0
    assert [path.read_bytes() for path in written] == first


def test_registry_dry_run_writes_nothing(tmp_path, source):
    data_dir = tmp_path / "data"
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "--dry-run",
            "registry",
            "load",
            "--source",
            str(source),
        ],
    )
    assert result.exit_code == 0
    assert not (data_dir / "registry" / "registry_normalized.json").exists()


def test_registry_load_rejects_a_short_list(tmp_path):
    path = tmp_path / "short.csv"
    write_csv_source(path, synthetic_rows(app_count=99))
    result = runner.invoke(
        app,
        ["--data-dir", str(tmp_path / "data"), "registry", "load", "--source", str(path)],
    )
    assert result.exit_code == ExitCode.PIPELINE


def test_registry_validate_and_show(tmp_path, source):
    data_dir = tmp_path / "data"
    assert (
        runner.invoke(
            app,
            ["--data-dir", str(data_dir), "registry", "load", "--source", str(source)],
        ).exit_code
        == 0
    )

    validated = runner.invoke(app, ["--data-dir", str(data_dir), "registry", "validate"])
    assert validated.exit_code == 0
    assert "no duplicates" in validated.stdout

    listed = runner.invoke(
        app, ["--data-dir", str(data_dir), "registry", "show", "--by-category"]
    )
    assert listed.exit_code == 0
    assert "Category Alpha" in listed.stdout


def test_registry_validate_without_a_registry_reports_the_missing_artifact(tmp_path):
    result = runner.invoke(
        app, ["--data-dir", str(tmp_path / "data"), "registry", "validate"]
    )
    assert result.exit_code == ExitCode.MISSING_ARTIFACT

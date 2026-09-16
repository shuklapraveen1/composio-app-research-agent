"""Configuration loading and validation."""

from pathlib import Path

import pytest

from composio_ops import constants as C
from composio_ops.config import get_settings, load_settings, reset_settings_cache
from composio_ops.errors import ConfigurationError


def test_defaults_are_usable_without_any_environment(settings):
    assert settings.seed == C.DEFAULT_SEED
    assert settings.expected_app_count == C.DEFAULT_EXPECTED_APP_COUNT
    assert settings.log_level == "INFO"
    assert settings.dry_run is False
    assert settings.research_api_key is None


def test_environment_variables_are_read(monkeypatch, tmp_path):
    monkeypatch.setenv(C.ENV_PREFIX + "SEED", "7")
    monkeypatch.setenv(C.ENV_PREFIX + "LOG_LEVEL", "debug")
    monkeypatch.setenv(C.ENV_PREFIX + "DRY_RUN", "true")
    loaded = load_settings(_env_file=None, project_root=tmp_path)
    assert loaded.seed == 7
    assert loaded.log_level == "DEBUG"
    assert loaded.dry_run is True


def test_invalid_log_level_raises_configuration_error(tmp_path):
    with pytest.raises(ConfigurationError):
        load_settings(_env_file=None, project_root=tmp_path, log_level="LOUD")


def test_negative_seed_raises_configuration_error(tmp_path):
    with pytest.raises(ConfigurationError):
        load_settings(_env_file=None, project_root=tmp_path, seed=-1)


def test_samples_may_not_exceed_the_population(tmp_path):
    with pytest.raises(ConfigurationError):
        load_settings(
            _env_file=None,
            project_root=tmp_path,
            expected_app_count=10,
            sample_size_a=6,
            sample_size_b=6,
        )


def test_unknown_environment_variables_are_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv(C.ENV_PREFIX + "NOT_A_SETTING", "x")
    assert load_settings(_env_file=None, project_root=tmp_path).seed == C.DEFAULT_SEED


def test_relative_paths_resolve_against_the_project_root(settings, tmp_path):
    assert settings.paths.data_dir == (tmp_path / "data").resolve()
    assert settings.paths.final_dataset.name == C.FINAL_DATASET_FILENAME


def test_absolute_paths_are_left_alone(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    loaded = load_settings(_env_file=None, project_root=tmp_path, data_dir=elsewhere)
    assert loaded.paths.data_dir == elsewhere


def test_missing_api_key_fails_only_at_the_point_of_use(settings):
    with pytest.raises(ConfigurationError):
        settings.require_research_api_key()


def test_api_key_is_returned_when_set(tmp_path):
    loaded = load_settings(
        _env_file=None, project_root=tmp_path, research_api_key="secret-value"
    )
    assert loaded.require_research_api_key() == "secret-value"


def test_summary_never_leaks_the_api_key(tmp_path):
    loaded = load_settings(
        _env_file=None, project_root=tmp_path, research_api_key="secret-value"
    )
    summary = loaded.summary()
    assert summary["research_api_key_set"] is True
    assert "secret-value" not in str(summary)


def test_settings_are_immutable(settings):
    with pytest.raises(Exception):
        settings.seed = 1


def test_get_settings_is_cached():
    reset_settings_cache()
    assert get_settings() is get_settings()
    reset_settings_cache()


def test_project_root_default_points_at_the_repository():
    root = load_settings(_env_file=None).project_root
    assert (root / "pyproject.toml").exists()
    assert isinstance(root, Path)

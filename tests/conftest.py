"""Shared test fixtures.

Tests run against declared defaults, not the developer's shell: every
``COMPOSIO_OPS_*`` variable is removed and the project ``.env`` is bypassed.
"""

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from composio_ops import constants as C
from composio_ops.config import Settings, load_settings, reset_settings_cache
from composio_ops.io_utils import write_json
from composio_ops.logging_setup import reset_logging
from composio_ops.pipeline import run_all
from composio_ops.registry import load_registry as ingest_registry

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for key in list(os.environ):
        if key.startswith(C.ENV_PREFIX):
            monkeypatch.delenv(key, raising=False)
    reset_settings_cache()
    reset_logging()
    yield
    reset_settings_cache()
    reset_logging()


@pytest.fixture()
def settings(tmp_path) -> Settings:
    """Settings rooted in a temp directory, isolated from any local ``.env``."""
    return load_settings(_env_file=None, project_root=tmp_path, data_dir="data")


@pytest.fixture()
def fixed_time() -> datetime:
    return datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


@pytest.fixture(scope="session")
def pipeline_run(tmp_path_factory):
    """The whole pipeline, over the real repository data, run once per session.

    Shared because it is the only fixture expensive enough to be worth sharing,
    and because tests that assert across stages should all be looking at the
    same run.
    """
    root = tmp_path_factory.mktemp("pipeline")
    shutil.copy(PROJECT_ROOT / "apps.json", root / "apps.json")
    shutil.copytree(PROJECT_ROOT / "data" / "corpus", root / "data" / "corpus")
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

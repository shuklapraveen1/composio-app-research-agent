"""Shared test fixtures.

Tests run against declared defaults, not the developer's shell: every
``COMPOSIO_OPS_*`` variable is removed and the project ``.env`` is bypassed.
"""

import os
from datetime import datetime, timezone

import pytest

from composio_ops import constants as C
from composio_ops.config import Settings, load_settings, reset_settings_cache
from composio_ops.logging_setup import reset_logging


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

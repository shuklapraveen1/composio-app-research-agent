"""Configuration loading.

Settings come from, in decreasing precedence: explicit overrides, process
environment, a local ``.env`` file, then defaults. Every value has a usable
default so the project imports and its CLI runs before any data exists; secrets
are optional here and demanded only at the point of use.
"""

import functools
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from . import constants as C
from .errors import ConfigurationError
from .paths import ArtifactPaths


def _default_project_root() -> Path:
    """Repository root, derived from this file's location (``src`` layout)."""
    return Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Validated runtime configuration for every stage."""

    model_config = SettingsConfigDict(
        env_prefix=C.ENV_PREFIX,
        # Anchored to the repository, not the current directory, so the CLI
        # behaves the same no matter where it is invoked from.
        env_file=_default_project_root() / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_assignment=True,
        frozen=True,
    )

    # --- runtime -----------------------------------------------------------
    environment: C.Environment = C.Environment.LOCAL
    log_level: str = "INFO"
    log_format: C.LogFormat = C.LogFormat.CONSOLE
    run_id: Optional[str] = Field(
        default=None,
        description="Fixed run identifier; generated per invocation when unset.",
    )

    # --- determinism -------------------------------------------------------
    seed: int = Field(
        default=C.DEFAULT_SEED,
        ge=0,
        description="Master seed; per-stage seeds are derived from it.",
    )

    # --- paths (relative values resolve against the project root) ----------
    project_root: Path = Field(default_factory=_default_project_root)
    data_dir: Path = Path("data")
    site_dir: Path = Path("site")

    # --- pipeline sizing ---------------------------------------------------
    expected_app_count: int = Field(default=C.DEFAULT_EXPECTED_APP_COUNT, ge=1)
    expected_category_count: int = Field(
        default=C.DEFAULT_EXPECTED_CATEGORY_COUNT, ge=1
    )
    sample_size_a: int = Field(default=C.DEFAULT_SAMPLE_SIZE, ge=1)
    sample_size_b: int = Field(default=C.DEFAULT_SAMPLE_SIZE, ge=1)

    # --- the pipeline clock ------------------------------------------------
    as_of: datetime = Field(
        default_factory=lambda: datetime.fromisoformat(C.DEFAULT_AS_OF),
        description="Timestamp stamped on every artifact, so re-runs are byte-stable.",
    )

    # --- research provider -------------------------------------------------
    research_provider: C.ResearchProvider = C.ResearchProvider.CORPUS

    # --- research / verification transport ---------------------------------
    request_timeout_seconds: float = Field(default=60.0, gt=0)
    max_concurrency: int = Field(default=4, ge=1, le=32)
    max_retries: int = Field(default=3, ge=0, le=10)
    research_model: Optional[str] = None
    verification_model: Optional[str] = None
    research_api_key: Optional[SecretStr] = None
    research_api_base_url: Optional[str] = None

    # --- safety ------------------------------------------------------------
    dry_run: bool = False

    # --- validation --------------------------------------------------------
    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("log_level")
    @classmethod
    def _check_log_level(cls, value: str) -> str:
        if value not in C.LOG_LEVELS:
            raise ValueError(
                "log_level must be one of {}".format(", ".join(sorted(C.LOG_LEVELS)))
            )
        return value

    @field_validator("run_id")
    @classmethod
    def _check_run_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        return cleaned

    @field_validator("as_of")
    @classmethod
    def _check_as_of(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _check_sample_sizes(self) -> "Settings":
        total = self.sample_size_a + self.sample_size_b
        if total > self.expected_app_count:
            raise ValueError(
                "sample_size_a + sample_size_b ({}) exceeds expected_app_count ({})".format(
                    total, self.expected_app_count
                )
            )
        return self

    # --- derived -----------------------------------------------------------
    def _resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else (self.project_root / path).resolve()

    @property
    def paths(self) -> ArtifactPaths:
        """Absolute artifact locations implied by this configuration."""
        return ArtifactPaths(
            project_root=self.project_root.resolve(),
            data_dir=self._resolve(self.data_dir),
            site_dir=self._resolve(self.site_dir),
        )

    def require_research_api_key(self) -> str:
        """Return the research API key, failing loudly when it is absent.

        Called at the point of use so that importing the package, running
        ``--help``, and running offline stages never require a secret.
        """
        if self.research_api_key is None:
            raise ConfigurationError(
                "Research API key is not configured",
                env_var="{}RESEARCH_API_KEY".format(C.ENV_PREFIX),
            )
        secret = self.research_api_key.get_secret_value()
        if not secret.strip():
            raise ConfigurationError(
                "Research API key is empty",
                env_var="{}RESEARCH_API_KEY".format(C.ENV_PREFIX),
            )
        return secret

    def summary(self) -> dict:
        """Log- and display-safe view of the configuration. Never includes secrets."""
        return {
            "environment": self.environment.value,
            "log_level": self.log_level,
            "log_format": self.log_format.value,
            "seed": self.seed,
            "expected_app_count": self.expected_app_count,
            "expected_category_count": self.expected_category_count,
            "sample_size_a": self.sample_size_a,
            "sample_size_b": self.sample_size_b,
            "as_of": self.as_of.isoformat(),
            "research_provider": self.research_provider.value,
            "max_concurrency": self.max_concurrency,
            "max_retries": self.max_retries,
            "request_timeout_seconds": self.request_timeout_seconds,
            "research_model": self.research_model,
            "verification_model": self.verification_model,
            "research_api_key_set": self.research_api_key is not None,
            "dry_run": self.dry_run,
            "project_root": str(self.project_root),
            "data_dir": str(self.paths.data_dir),
            "schema_version": C.SCHEMA_VERSION,
        }


def load_settings(**overrides: Any) -> Settings:
    """Build a fresh :class:`Settings`, translating validation failures.

    Bypasses the cache, which makes it the right entrypoint for tests and for
    CLI flags that override the environment.
    """
    try:
        return Settings(**overrides)
    except ValidationError as exc:
        raise ConfigurationError(
            "Invalid configuration", errors=exc.errors(include_url=False)
        ) from exc


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, loaded once."""
    return load_settings()


def reset_settings_cache() -> None:
    """Drop the cached settings so the next call re-reads the environment."""
    get_settings.cache_clear()

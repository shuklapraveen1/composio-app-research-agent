"""Structured logging.

All logs go to stderr so that stdout stays clean for machine-readable output.
Every event carries the run id, and stage helpers bind the stage name plus a
duration, which is what makes a run's provenance reconstructable from the log
stream alone.
"""

import logging
import sys
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator, Optional

import structlog

from . import constants as C
from .config import Settings

_configured = False
_configured_stderr = None


def generate_run_id() -> str:
    return uuid.uuid4().hex[:12]


def configure_logging(
    settings: Optional[Settings] = None,
    level: Optional[str] = None,
    log_format: Optional[C.LogFormat] = None,
    run_id: Optional[str] = None,
    force: bool = False,
) -> str:
    """Configure structlog and return the active run id.

    Configuration is reused while the process is using the same stderr stream.
    Test runners such as Click's CliRunner replace sys.stderr between
    invocations, so a changed stream must trigger reconfiguration.
    """
    global _configured, _configured_stderr

    resolved_level = (
        level or (settings.log_level if settings else "INFO")
    ).upper()

    if resolved_level not in C.LOG_LEVELS:
        resolved_level = "INFO"

    resolved_format = (
        log_format
        or (settings.log_format if settings else C.LogFormat.CONSOLE)
    )

    resolved_run_id = (
        run_id
        or (settings.run_id if settings else None)
        or generate_run_id()
    )

    stderr_changed = _configured_stderr is not sys.stderr

    if _configured and not force and not stderr_changed:
        structlog.contextvars.bind_contextvars(run_id=resolved_run_id)
        return resolved_run_id

    if resolved_format == C.LogFormat.JSON:
        renderer: Any = structlog.processors.JSONRenderer(sort_keys=True)
    else:
        renderer = structlog.dev.ConsoleRenderer(
            colors=sys.stderr.isatty()
        )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(resolved_level)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        run_id=resolved_run_id,
        schema_version=C.SCHEMA_VERSION,
    )

    _configured = True
    _configured_stderr = sys.stderr

    return resolved_run_id


def reset_logging() -> None:
    """Return logging to its unconfigured state (used by tests)."""
    global _configured, _configured_stderr

    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()

    _configured = False
    _configured_stderr = None


def get_logger(name: Optional[str] = None) -> Any:
    """Return a bound logger, configuring defaults lazily if needed."""
    if not _configured or _configured_stderr is not sys.stderr:
        configure_logging()

    return structlog.get_logger(name or C.PACKAGE_NAME)


@contextmanager
def stage_context(stage: C.PipelineStage, **fields: Any) -> Iterator[Any]:
    """Bind a pipeline stage for the duration of a block and log its outcome."""
    logger = get_logger().bind(stage=stage.value, **fields)
    started = time.monotonic()

    logger.info("stage.start")

    try:
        yield logger
    except Exception as exc:
        logger.error(
            "stage.failed",
            error_type=type(exc).__name__,
            error=str(exc),
            duration_seconds=round(time.monotonic() - started, 3),
        )
        raise
    else:
        logger.info(
            "stage.complete",
            duration_seconds=round(time.monotonic() - started, 3),
        )
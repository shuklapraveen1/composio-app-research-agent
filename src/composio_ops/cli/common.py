"""Shared CLI plumbing: global options, run context, and error translation.

Every stage command accepts the same global options and resolves them the same
way, whether it is reached through the root ``composio-ops`` entrypoint or run
standalone as ``python -m composio_ops.cli.research``.
"""

import functools
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import click
import typer

from .. import constants as C
from ..config import Settings, load_settings
from ..errors import ExitCode, PipelineError
from ..logging_setup import configure_logging, get_logger
from ..paths import ArtifactPaths


@dataclass(frozen=True)
class AppContext:
    """Everything a stage command needs, resolved once per invocation."""

    settings: Settings
    run_id: str

    @property
    def paths(self) -> ArtifactPaths:
        return self.settings.paths

    @property
    def logger(self) -> Any:
        return get_logger()


def handle_errors(func):
    """Translate deliberate failures into a message plus a stable exit code.

    Applied to every command and to the shared callback so the exit code is the
    same whether the CLI is driven by a shell, CI, or a test runner.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PipelineError as exc:
            get_logger().error("command.failed", **exc.to_dict())
            typer.secho("Error: {}".format(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=exc.exit_code)

    return wrapper


def _explicit(ctx: typer.Context, name: str) -> bool:
    """True when the user actually passed this option on the command line.

    Without this check, a subcommand's default would silently overwrite a value
    the user set on the parent command.
    """
    source = ctx.get_parameter_source(name)
    return source is not None and source != click.core.ParameterSource.DEFAULT


@handle_errors
def global_options_callback(
    ctx: typer.Context,
    log_level: Optional[str] = typer.Option(
        None, "--log-level", help="DEBUG, INFO, WARNING, ERROR, or CRITICAL."
    ),
    log_format: Optional[C.LogFormat] = typer.Option(
        None, "--log-format", help="Log renderer: console or json."
    ),
    seed: Optional[int] = typer.Option(
        None, "--seed", help="Master seed; every stage derives its seed from it."
    ),
    data_dir: Optional[Path] = typer.Option(
        None, "--data-dir", help="Override the artifact data directory."
    ),
    run_id: Optional[str] = typer.Option(
        None, "--run-id", help="Fixed run identifier, for reproducible log streams."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Plan only: make no outbound calls and write nothing."
    ),
) -> None:
    """Resolve configuration and logging for this invocation."""
    overrides: Dict[str, Any] = {}
    if _explicit(ctx, "log_level") and log_level is not None:
        overrides["log_level"] = log_level
    if _explicit(ctx, "log_format") and log_format is not None:
        overrides["log_format"] = log_format
    if _explicit(ctx, "seed") and seed is not None:
        overrides["seed"] = seed
    if _explicit(ctx, "data_dir") and data_dir is not None:
        overrides["data_dir"] = data_dir
    if _explicit(ctx, "run_id") and run_id is not None:
        overrides["run_id"] = run_id
    if _explicit(ctx, "dry_run"):
        overrides["dry_run"] = dry_run

    root = ctx.find_root()
    existing: Optional[AppContext] = root.obj if isinstance(root.obj, AppContext) else None

    if existing is not None and not overrides:
        ctx.obj = existing
        return

    if existing is not None:
        base = existing.settings.model_dump(exclude_none=True)
        base.update(overrides)
        overrides = base

    settings = load_settings(**overrides)
    resolved_run_id = configure_logging(settings=settings, force=existing is not None)
    context = AppContext(settings=settings, run_id=resolved_run_id)
    root.obj = context
    ctx.obj = context


def get_context(ctx: typer.Context) -> AppContext:
    """Return the resolved context, building a default one if none exists."""
    root = ctx.find_root()
    if isinstance(root.obj, AppContext):
        return root.obj
    settings = load_settings()
    context = AppContext(settings=settings, run_id=configure_logging(settings=settings))
    root.obj = context
    return context


def build_app(help_text: str) -> typer.Typer:
    """Create a Typer app that carries the shared global options."""
    app = typer.Typer(
        help=help_text,
        no_args_is_help=True,
        add_completion=False,
        pretty_exceptions_enable=False,
    )
    app.callback()(global_options_callback)
    return app


def run_app(app: typer.Typer) -> None:
    """Invoke a Typer app, mapping deliberate failures to stable exit codes."""
    try:
        app()
    except PipelineError as exc:
        get_logger().error("command.failed", **exc.to_dict())
        typer.secho("Error: {}".format(exc), fg=typer.colors.RED, err=True)
        sys.exit(exc.exit_code)
    except Exception as exc:  # noqa: BLE001 - last resort, still reported cleanly
        get_logger().exception("command.crashed", error_type=type(exc).__name__)
        typer.secho("Unexpected error: {}".format(exc), fg=typer.colors.RED, err=True)
        sys.exit(ExitCode.UNEXPECTED)

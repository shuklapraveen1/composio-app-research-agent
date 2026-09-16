"""Root CLI: ``composio-ops``.

Each pipeline stage is a subcommand group that can also be run standalone, e.g.
``python -m composio_ops.cli.research run``.
"""

import typer

from .. import __version__
from .. import constants as C
from ..determinism import derive_seed
from . import analyze, casestudy, pipeline, registry, research, verify
from .common import build_app, get_context, handle_errors, run_app

app = build_app("Evidence-first research pipeline for the Composio Product Ops take-home.")

app.add_typer(registry.app, name="registry")
app.add_typer(research.app, name="research")
app.add_typer(verify.app, name="verify")
app.add_typer(analyze.app, name="analyze")
app.add_typer(casestudy.app, name="casestudy")
app.add_typer(pipeline.app, name="pipeline")


@app.command("version")
@handle_errors
def version() -> None:
    """Print the package and schema versions."""
    typer.echo("{} {} (schema {})".format(C.PROJECT_NAME, __version__, C.SCHEMA_VERSION))


@app.command("init")
@handle_errors
def init(ctx: typer.Context) -> None:
    """Create the artifact directory layout. Idempotent and safe to re-run."""
    context = get_context(ctx)
    paths = context.paths
    paths.ensure_directories()
    context.logger.info("init.complete", data_dir=str(paths.data_dir))
    for directory in paths.all_directories():
        typer.echo("ready  {}".format(paths.relative(directory)))


@app.command("status")
@handle_errors
def status(ctx: typer.Context) -> None:
    """Show resolved configuration, derived seeds, and artifact readiness."""
    context = get_context(ctx)
    settings = context.settings
    paths = context.paths

    typer.echo("configuration")
    for key, value in sorted(settings.summary().items()):
        typer.echo("  {:<26} {}".format(key, value))

    typer.echo("derived seeds")
    for namespace in (C.SEED_NAMESPACE_SAMPLE_A, C.SEED_NAMESPACE_SAMPLE_B):
        typer.echo(
            "  {:<26} {}".format(namespace, derive_seed(settings.seed, namespace))
        )

    typer.echo("artifacts")
    artifacts = (
        ("registry_raw", paths.registry_raw),
        ("registry_normalized", paths.registry_normalized),
        ("evidence", paths.evidence),
        ("classification", paths.classification),
        ("validation_report", paths.validation_report),
        ("initial_dataset", paths.initial_dataset),
        ("review_queue", paths.review_queue),
        ("sample_a", paths.sample_a),
        ("sample_b", paths.sample_b),
        ("improvements", paths.improvements),
        ("final_dataset", paths.final_dataset),
        ("final_dataset_csv", paths.final_dataset_csv),
        ("analytics", paths.analytics),
        ("patterns", paths.patterns),
        ("accuracy", paths.accuracy),
        ("case_study", paths.case_study),
    )
    for label, path in artifacts:
        marker = "present" if path.exists() else "missing"
        typer.echo("  {:<26} {:<8} {}".format(label, marker, paths.relative(path)))


def main() -> None:
    run_app(app)


if __name__ == "__main__":
    main()

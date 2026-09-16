"""The whole pipeline in one command.

``composio-ops pipeline run`` is the reproducibility claim made executable: one
seed, one clock, every stage in the locked order, from the registry to the
published case study.
"""

import typer

from .. import constants as C
from ..pipeline import run_all
from .common import build_app, get_context, handle_errors, run_app

app = build_app("Run every pipeline stage in order.")


@app.command("run")
@handle_errors
def run(ctx: typer.Context) -> None:
    """Research, validate, sample, verify, reconcile, measure, analyse, publish."""
    context = get_context(ctx)
    settings = context.settings
    result = run_all(settings)

    typer.echo(
        "Registry: {} apps across {} categories.".format(
            len(result.registry.records), len(result.registry.categories)
        )
    )
    typer.echo(
        "Validation: {} errors, {} warnings. Review queue: {} apps.".format(
            len(result.validation.errors),
            len(result.validation.warnings),
            len(result.review_queue.entries),
        )
    )
    for group in (C.SampleGroup.A, C.SampleGroup.B):
        sample = result.accuracy.sample(group)
        if sample is None:
            continue
        typer.echo(
            "Sample {} ({}, classifier {}): field-level {:.1%}, row-level {:.1%}, "
            "evidence validity {:.1%}.".format(
                group.value,
                sample.measurement.replace("_", " "),
                sample.classifier_version,
                sample.field_level_accuracy or 0.0,
                sample.row_level_accuracy or 0.0,
                sample.evidence_validity or 0.0,
            )
        )
    typer.echo(
        "Headline ({}): {:.1%}".format(
            result.accuracy.headline_metric, result.accuracy.headline_value or 0.0
        )
    )
    typer.echo(
        "Final dataset: {} records at {}.".format(
            len(result.final_dataset.records),
            settings.paths.relative(settings.paths.final_dataset),
        )
    )
    if result.case_study_path:
        typer.echo("Case study: {}".format(result.case_study_path))


def main() -> None:
    run_app(app)


if __name__ == "__main__":
    main()

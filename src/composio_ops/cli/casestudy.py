"""Case study and export commands."""

import typer

from ..io_utils import read_json
from ..publish import publish_case_study, write_dataset_exports
from ..schemas.analytics import AnalyticsReport, PatternReport
from ..schemas.dataset import Dataset
from ..schemas.review import ImprovementReport, ReviewQueue
from ..schemas.validation import ValidationReport
from ..schemas.verification import AccuracyReport
from .common import build_app, get_context, handle_errors, run_app

app = build_app("Build the case study page and the publishable exports.")


def _artifacts(settings):
    paths = settings.paths
    return (
        Dataset.model_validate(
            read_json(paths.require(paths.final_dataset, produced_by="pipeline run"))
        ),
        AnalyticsReport.model_validate(
            read_json(paths.require(paths.analytics, produced_by="analyze run"))
        ),
        PatternReport.model_validate(
            read_json(paths.require(paths.patterns, produced_by="analyze run"))
        ),
        AccuracyReport.model_validate(
            read_json(paths.require(paths.accuracy, produced_by="verify run"))
        ),
        ImprovementReport.model_validate(
            read_json(paths.require(paths.improvements, produced_by="pipeline run"))
        ),
        ValidationReport.model_validate(
            read_json(paths.require(paths.validation_report, produced_by="research validate"))
        ),
        ReviewQueue.model_validate(
            read_json(paths.require(paths.review_queue, produced_by="research review-queue"))
        ),
    )


@app.command("build")
@handle_errors
def build(ctx: typer.Context) -> None:
    """Render the case study and write the published exports."""
    context = get_context(ctx)
    settings = context.settings
    dataset, analytics, patterns, accuracy, improvements, validation, queue = _artifacts(
        settings
    )

    written = write_dataset_exports(
        dataset=dataset,
        analytics=analytics,
        patterns=patterns,
        accuracy=accuracy,
        settings=settings,
    )
    path = publish_case_study(
        dataset=dataset,
        analytics=analytics,
        patterns=patterns,
        accuracy=accuracy,
        improvements=improvements,
        validation=validation,
        queue=queue,
        settings=settings,
    )
    typer.echo("Case study: {}".format(path))
    for item in written:
        typer.echo("  wrote {}".format(item))


def main() -> None:
    run_app(app)


if __name__ == "__main__":
    main()

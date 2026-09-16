"""Analytics commands over the final dataset."""

import typer

from ..io_utils import read_json
from ..pipeline import analytics
from ..schemas.dataset import Dataset
from .common import build_app, get_context, handle_errors, run_app

app = build_app("Compute deterministic analytics and patterns from the final dataset.")


def _load_dataset(settings) -> Dataset:
    path = settings.paths.require(
        settings.paths.final_dataset, produced_by="pipeline run"
    )
    return Dataset.model_validate(read_json(path))


@app.command("run")
@handle_errors
def run(ctx: typer.Context) -> None:
    """Write analytics.json and patterns.json from the final dataset."""
    context = get_context(ctx)
    settings = context.settings
    dataset = _load_dataset(settings)
    report, patterns = analytics(settings, dataset)
    typer.echo(
        "Analytics: {} metrics, {} distributions, {} cross-tabs, {} patterns.".format(
            len(report.metrics),
            len(report.distributions),
            len(report.cross_tabs),
            len(patterns.patterns),
        )
    )
    for pattern in patterns.patterns:
        typer.echo("  - {}".format(pattern.statement))


def main() -> None:
    run_app(app)


if __name__ == "__main__":
    main()

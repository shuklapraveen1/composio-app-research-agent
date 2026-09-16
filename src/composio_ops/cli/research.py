"""Channel A research and deterministic validation commands."""

from typing import Optional

import typer

from .. import constants as C
from ..io_utils import write_json
from ..pipeline import (
    initial_dataset,
    load_registry,
    research,
    review_queue,
    validate,
)
from .common import build_app, get_context, handle_errors, run_app

app = build_app("Run Channel A research, validation, and the review queue.")


@app.command("run")
@handle_errors
def run(
    ctx: typer.Context,
    classifier: str = typer.Option(
        C.CLASSIFIER_V1,
        "--classifier",
        help="Classifier version to apply: {}.".format(", ".join(C.CLASSIFIER_VERSIONS)),
    ),
    provider: Optional[C.ResearchProvider] = typer.Option(
        None,
        "--provider",
        help="Where observations come from. The corpus provider is offline and "
        "reproducible; the others need credentials.",
    ),
) -> None:
    """Research every registered application and write the research artifacts."""
    context = get_context(ctx)
    settings = context.settings
    if provider is not None:
        settings = settings.model_copy(update={"research_provider": provider})

    registry = load_registry(settings)
    research_set, evidence_set = research(settings, registry, classifier)
    typer.echo(
        "Researched {} apps with classifier {} via {}: {} evidence items.".format(
            len(research_set.records),
            classifier,
            settings.research_provider.value,
            len(evidence_set.items),
        )
    )


@app.command("validate")
@handle_errors
def validate_command(
    ctx: typer.Context,
    classifier: str = typer.Option(C.CLASSIFIER_V1, "--classifier"),
) -> None:
    """Re-run research in memory and validate it, writing the validation report."""
    context = get_context(ctx)
    settings = context.settings
    registry = load_registry(settings)
    research_set, evidence_set = research(settings, registry, classifier, write=False)
    report = validate(settings, registry, research_set, evidence_set)
    typer.echo(
        "Validation: {} records, {} errors, {} warnings.".format(
            report.checked_records, len(report.errors), len(report.warnings)
        )
    )


@app.command("dataset")
@handle_errors
def dataset_command(
    ctx: typer.Context,
    classifier: str = typer.Option(C.CLASSIFIER_V1, "--classifier"),
) -> None:
    """Build the initial dataset from the current research pass."""
    context = get_context(ctx)
    settings = context.settings
    registry = load_registry(settings)
    research_set, evidence_set = research(settings, registry, classifier, write=False)
    validate(settings, registry, research_set, evidence_set, write=False)
    dataset = initial_dataset(settings, registry, research_set, evidence_set)
    typer.echo(
        "Initial dataset: {} records at {}.".format(
            len(dataset.records), settings.paths.relative(settings.paths.initial_dataset)
        )
    )


@app.command("review-queue")
@handle_errors
def review_queue_command(
    ctx: typer.Context,
    classifier: str = typer.Option(C.CLASSIFIER_V1, "--classifier"),
) -> None:
    """Build the risk-based review queue over the current research pass."""
    context = get_context(ctx)
    settings = context.settings
    registry = load_registry(settings)
    research_set, _ = research(settings, registry, classifier, write=False)
    queue = review_queue(settings, research_set)
    typer.echo(
        "Queued {} of {} apps ({:.0%}) for human attention.".format(
            len(queue.entries), queue.population_size, queue.share
        )
    )
    for entry in queue.entries:
        typer.echo(
            "  {:<24} {}".format(
                entry.app_id, ", ".join(trigger.value for trigger in entry.triggers)
            )
        )


def main() -> None:
    run_app(app)


if __name__ == "__main__":
    main()

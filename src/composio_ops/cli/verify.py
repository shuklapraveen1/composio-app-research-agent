"""Sampling, verification channels, reconciliation, and accuracy commands."""

import typer

from .. import constants as C
from ..io_utils import write_json
from ..pipeline import (
    load_corpus_for,
    load_registry,
    research,
    review_queue,
    samples,
    verification,
)
from ..verification import (
    build_accuracy_report,
    current_values,
    established_values,
    frozen_values,
    measure_sample,
)
from ..verification.accuracy import MEASUREMENT_FINAL, MEASUREMENT_FIRST_PASS
from .common import build_app, get_context, handle_errors, run_app

app = build_app("Draw samples, run verification channels, and measure accuracy.")


@app.command("sample")
@handle_errors
def sample_command(
    ctx: typer.Context,
    classifier: str = typer.Option(C.CLASSIFIER_V1, "--classifier"),
) -> None:
    """Draw Samples A and B and freeze the values they will be measured against."""
    context = get_context(ctx)
    settings = context.settings
    registry = load_registry(settings)
    research_set, _ = research(settings, registry, classifier, write=False)
    sample_a, sample_b = samples(settings, registry, research_set)
    for selection in (sample_a, sample_b):
        typer.echo(
            "Sample {}: {} apps, derived seed {}.".format(
                selection.group.value, len(selection.assignments), selection.derived_seed
            )
        )
        typer.echo("  {}".format(", ".join(selection.app_ids())))


@app.command("run")
@handle_errors
def run(
    ctx: typer.Context,
    group: C.SampleGroup = typer.Option(
        C.SampleGroup.A, "--sample", help="Which sample to verify."
    ),
    classifier: str = typer.Option(C.CLASSIFIER_V1, "--classifier"),
) -> None:
    """Run channels B, C and D over one sample, then reconcile and score it."""
    context = get_context(ctx)
    settings = context.settings
    registry = load_registry(settings)
    corpus = load_corpus_for(settings, registry)
    research_set, evidence_set = research(settings, registry, classifier, write=False)
    queue = review_queue(settings, research_set, write=False)
    sample_a, sample_b = samples(settings, registry, research_set, write=False)
    selection = sample_a if group is C.SampleGroup.A else sample_b

    run_result = verification(
        settings, selection, research_set, evidence_set, corpus, queue
    )
    truth = established_values(run_result.reconciliation)

    first_pass = group is C.SampleGroup.A
    sampled = set(selection.app_ids())
    measured = (
        frozen_values(selection)
        if first_pass
        else current_values(
            [record for record in research_set.records if record.app_id in sampled]
        )
    )
    accuracy = measure_sample(
        group=group,
        measurement=MEASUREMENT_FIRST_PASS if first_pass else MEASUREMENT_FINAL,
        classifier_version=classifier,
        measured=measured,
        truth=truth,
        verification=run_result.results_by_app(),
        trigger_reviewed=[app_id for app_id in queue.app_ids() if app_id in sampled],
    )
    report = build_accuracy_report(
        [accuracy], settings, notes="Sample {} only.".format(group.value)
    )
    if not settings.dry_run:
        write_json(settings.paths.accuracy, report.to_jsonable())

    typer.echo(
        "Sample {}: field-level {:.1%}, row-level {:.1%}, evidence validity {:.1%}.".format(
            group.value,
            accuracy.field_level_accuracy or 0.0,
            accuracy.row_level_accuracy or 0.0,
            accuracy.evidence_validity or 0.0,
        )
    )
    typer.echo(
        "  {} human decisions, {} reconciled fields.".format(
            len(run_result.human_decisions.decisions),
            len(run_result.reconciliation.decisions),
        )
    )


def main() -> None:
    run_app(app)


if __name__ == "__main__":
    main()

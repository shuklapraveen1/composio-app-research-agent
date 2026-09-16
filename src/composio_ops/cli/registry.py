"""Registry ingestion entrypoint.

Loads the supplied application list into the canonical registry. This stage
performs no research: it reads, validates, assigns stable ids, and stops.
"""

from pathlib import Path
from typing import Optional

import typer

from .. import constants as C
from ..errors import MissingArtifactError, RegistryError
from ..io_utils import read_json, write_json
from ..logging_setup import stage_context
from ..registry import find_duplicates, load_registry
from ..schemas.registry import NormalizedRegistry, RawRegistry
from .common import build_app, get_context, handle_errors, run_app

app = build_app("Load and validate the supplied application registry.")


def _load_normalized(paths) -> NormalizedRegistry:
    payload = read_json(paths.registry_normalized, produced_by="registry load")
    return NormalizedRegistry.model_validate(payload)


@app.command("load")
@handle_errors
def load(
    ctx: typer.Context,
    source: Path = typer.Option(
        ..., "--source", help="Path to the supplied app list (CSV, TSV, JSON, JSONL)."
    ),
    name_column: Optional[str] = typer.Option(
        None, "--name-column", help="Override the detected application-name column."
    ),
    category_column: Optional[str] = typer.Option(
        None, "--category-column", help="Override the detected category column."
    ),
    url_column: Optional[str] = typer.Option(
        None, "--url-column", help="Override the detected homepage-url column."
    ),
    id_column: Optional[str] = typer.Option(
        None, "--id-column", help="Use ids supplied by the source instead of deriving them."
    ),
    expect_apps: Optional[int] = typer.Option(
        None, "--expect-apps", min=1, help="Required application count."
    ),
    expect_categories: Optional[int] = typer.Option(
        None, "--expect-categories", min=1, help="Required category count."
    ),
) -> None:
    """Ingest the supplied list and write the raw and normalized registries."""
    context = get_context(ctx)
    settings = context.settings
    paths = context.paths

    apps = expect_apps or settings.expected_app_count
    categories = expect_categories or settings.expected_category_count

    with stage_context(
        C.PipelineStage.REGISTRY,
        source=str(source),
        expect_apps=apps,
        expect_categories=categories,
    ) as logger:
        raw, normalized = load_registry(
            source,
            seed=settings.seed,
            expected_apps=apps,
            expected_categories=categories,
            generated_at=settings.as_of,
            mapping_overrides={
                "name": name_column,
                "category": category_column,
                "url": url_column,
                "app_id": id_column,
            },
        )

        if settings.dry_run:
            logger.info("registry.dry_run", apps=len(normalized.records))
        else:
            paths.ensure_directories()
            write_json(paths.registry_raw, raw.to_jsonable())
            write_json(paths.registry_normalized, normalized.to_jsonable())

        logger.info(
            "registry.loaded",
            apps=len(normalized.records),
            categories=len(normalized.categories),
            dry_run=settings.dry_run,
        )

    typer.echo(
        "Loaded {} applications across {} categories.".format(
            len(normalized.records), len(normalized.categories)
        )
    )
    if settings.dry_run:
        typer.echo("Dry run: nothing written.")
    else:
        typer.echo("  {}".format(paths.relative(paths.registry_raw)))
        typer.echo("  {}".format(paths.relative(paths.registry_normalized)))


@app.command("validate")
@handle_errors
def validate(
    ctx: typer.Context,
    expect_apps: Optional[int] = typer.Option(None, "--expect-apps", min=1),
    expect_categories: Optional[int] = typer.Option(None, "--expect-categories", min=1),
) -> None:
    """Re-check the stored registry: counts, categories, and duplicates."""
    context = get_context(ctx)
    settings = context.settings
    paths = context.paths

    apps = expect_apps or settings.expected_app_count
    categories = expect_categories or settings.expected_category_count

    with stage_context(C.PipelineStage.REGISTRY, check="validate"):
        normalized = _load_normalized(paths)
        try:
            normalized.require_exact_counts(apps=apps, categories=categories)
        except ValueError as exc:
            raise RegistryError("Registry is not the expected shape", detail=str(exc))

        raw_payload = read_json(paths.registry_raw, produced_by="registry load")
        raw = RawRegistry.model_validate(raw_payload)
        urls = {
            record.source_index: record.homepage_url
            for record in normalized.records
            if record.homepage_url
        }
        duplicates = find_duplicates(raw.records, urls=urls)
        if duplicates:
            raise RegistryError(
                "Registry contains duplicate applications", groups=len(duplicates)
            )

    typer.echo(
        "Registry is valid: {} applications, {} categories, no duplicates.".format(
            len(normalized.records), len(normalized.categories)
        )
    )


@app.command("show")
@handle_errors
def show(
    ctx: typer.Context,
    by_category: bool = typer.Option(
        False, "--by-category", help="Group the listing by supplied category."
    ),
) -> None:
    """Print the stored registry."""
    context = get_context(ctx)
    paths = context.paths
    try:
        normalized = _load_normalized(paths)
    except MissingArtifactError:
        raise

    if by_category:
        for category in normalized.categories:
            typer.echo("{} ({})".format(category.name, category.app_count))
            for record in normalized.apps_in(category.category_id):
                typer.echo("  {:<40} {}".format(record.app_id, record.name))
        return

    for record in normalized.records:
        typer.echo(
            "{:<40} {:<24} {}".format(record.app_id, record.category_id, record.name)
        )


def main() -> None:
    run_app(app)


if __name__ == "__main__":
    main()

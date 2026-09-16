"""Loading the supplied 100-app list into the canonical registry.

The loader reads the list exactly as supplied and refuses to improvise: a
missing column, a blank cell, a duplicate row, or the wrong number of apps or
categories is an error, never something to be filled in. Categories are carried
through untouched, because they are input data.

Supported formats: CSV, TSV, JSON (a list of objects, or an object with a list
under ``apps``/``applications``/``records``/``data``), and JSONL.
"""

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .. import constants as C
from ..determinism import fingerprint
from ..errors import RegistryError
from ..schemas.base import ArtifactMetadata, utc_now
from ..schemas.registry import (
    Category,
    NormalizedAppRecord,
    NormalizedRegistry,
    RawAppRecord,
    RawRegistry,
)
from .duplicates import describe, find_duplicates
from .ids import generate_category_ids, generate_ids, slugify

#: Column names accepted for each field, in priority order.
NAME_COLUMNS = (
    "name",
    "app",
    "app_name",
    "application",
    "application_name",
    "tool",
    "tool_name",
    "product",
)
CATEGORY_COLUMNS = ("category", "app_category", "application_category", "segment")
URL_COLUMNS = ("url", "website", "homepage", "homepage_url", "site", "link", "domain")
ID_COLUMNS = ("id", "app_id", "slug", "identifier")

JSON_LIST_KEYS = ("apps", "applications", "records", "data", "items")


@dataclass(frozen=True)
class ColumnMapping:
    """Which source column supplies each registry field."""

    name: str
    category: str
    url: Optional[str] = None
    app_id: Optional[str] = None


def _normalize_header(header: str) -> str:
    return header.strip().lower().replace(" ", "_").replace("-", "_")


def _pick(headers: Dict[str, str], candidates: Sequence[str]) -> Optional[str]:
    for candidate in candidates:
        if candidate in headers:
            return headers[candidate]
    return None


def resolve_columns(
    headers: Sequence[str],
    name_column: Optional[str] = None,
    category_column: Optional[str] = None,
    url_column: Optional[str] = None,
    id_column: Optional[str] = None,
) -> ColumnMapping:
    """Work out which columns to read, honouring explicit overrides."""
    available = {_normalize_header(header): header for header in headers}

    def require(explicit: Optional[str], candidates: Sequence[str], label: str) -> str:
        if explicit is not None:
            if explicit not in headers:
                raise RegistryError(
                    "Source has no column named '{}'".format(explicit),
                    column=explicit,
                    available=sorted(headers),
                )
            return explicit
        found = _pick(available, candidates)
        if found is None:
            raise RegistryError(
                "Source has no recognizable {} column".format(label),
                tried=list(candidates),
                available=sorted(headers),
            )
        return found

    def optional(explicit: Optional[str], candidates: Sequence[str]) -> Optional[str]:
        if explicit is not None:
            if explicit not in headers:
                raise RegistryError(
                    "Source has no column named '{}'".format(explicit),
                    column=explicit,
                    available=sorted(headers),
                )
            return explicit
        return _pick(available, candidates)

    return ColumnMapping(
        name=require(name_column, NAME_COLUMNS, "application name"),
        category=require(category_column, CATEGORY_COLUMNS, "category"),
        url=optional(url_column, URL_COLUMNS),
        app_id=optional(id_column, ID_COLUMNS),
    )


def _read_rows(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Return the source rows and their column order."""
    if not path.exists():
        raise RegistryError("Source file does not exist", path=str(path))

    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8-sig")

    if suffix in (".csv", ".tsv", ".txt"):
        delimiter = "\t" if suffix == ".tsv" else ","
        reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
        if reader.fieldnames is None:
            raise RegistryError("Source has no header row", path=str(path))
        headers = [header for header in reader.fieldnames if header is not None]
        return [dict(row) for row in reader], headers

    if suffix == ".jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    elif suffix == ".json":
        payload = json.loads(text)
        if isinstance(payload, dict):
            for key in JSON_LIST_KEYS:
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
            else:
                raise RegistryError(
                    "JSON object does not contain a list of applications",
                    path=str(path),
                    tried=list(JSON_LIST_KEYS),
                )
        if not isinstance(payload, list):
            raise RegistryError("JSON source must be a list of objects", path=str(path))
        rows = payload
    else:
        raise RegistryError(
            "Unsupported source format", path=str(path), supported=[".csv", ".tsv", ".json", ".jsonl"]
        )

    if not all(isinstance(row, dict) for row in rows):
        raise RegistryError("Every source record must be an object", path=str(path))

    headers: List[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    return rows, headers


def load_raw(
    path: Path,
    seed: int,
    mapping_overrides: Optional[Dict[str, Optional[str]]] = None,
    generated_at: Optional[datetime] = None,
) -> Tuple[RawRegistry, ColumnMapping, Dict[int, str]]:
    """Read the source list verbatim into a :class:`RawRegistry`.

    Also returns the resolved column mapping and any supplied homepage URLs,
    both of which normalization needs.
    """
    rows, headers = _read_rows(path)
    if not rows:
        raise RegistryError("Source list is empty", path=str(path))

    overrides = mapping_overrides or {}
    mapping = resolve_columns(
        headers,
        name_column=overrides.get("name"),
        category_column=overrides.get("category"),
        url_column=overrides.get("url"),
        id_column=overrides.get("app_id"),
    )

    records: List[RawAppRecord] = []
    urls: Dict[int, str] = {}
    blank_rows: List[int] = []

    for index, row in enumerate(rows):
        name = str(row.get(mapping.name) or "").strip()
        category = str(row.get(mapping.category) or "").strip()
        if not name or not category:
            blank_rows.append(index)
            continue
        if mapping.url:
            url = str(row.get(mapping.url) or "").strip()
            if url:
                urls[index] = url
        records.append(
            RawAppRecord(
                source_index=index,
                name=name,
                category=category,
                fields={key: row.get(key) for key in headers},
            )
        )

    if blank_rows:
        raise RegistryError(
            "Source rows are missing a name or a category",
            rows=blank_rows[:10],
            count=len(blank_rows),
        )

    metadata = ArtifactMetadata(
        stage=C.PipelineStage.REGISTRY,
        generated_at=generated_at or utc_now(),
        seed=seed,
        record_count=len(records),
        source_fingerprint=fingerprint(path.read_bytes().decode("utf-8-sig")),
        notes="Loaded verbatim from {}".format(path.name),
    )
    registry = RawRegistry(
        metadata=metadata,
        source_name=path.name,
        retrieved_at=generated_at or utc_now(),
        records=records,
    )
    return registry, mapping, urls


def normalize(
    raw: RawRegistry,
    seed: int,
    urls: Optional[Dict[int, str]] = None,
    supplied_ids: Optional[Dict[int, str]] = None,
    generated_at: Optional[datetime] = None,
) -> NormalizedRegistry:
    """Turn a raw registry into the canonical, sorted, id-bearing form."""
    urls = urls or {}
    supplied_ids = supplied_ids or {}

    duplicates = find_duplicates(raw.records, urls=urls)
    if duplicates:
        raise RegistryError(
            "Source list contains duplicate applications",
            duplicates=describe(duplicates),
            groups=len(duplicates),
        )

    generated = generate_ids([record.name for record in raw.records])
    category_ids = generate_category_ids(record.category for record in raw.records)

    records: List[NormalizedAppRecord] = []
    for position, record in enumerate(raw.records):
        supplied = supplied_ids.get(record.source_index)
        app_id = slugify(supplied) if supplied else generated[position]
        records.append(
            NormalizedAppRecord(
                app_id=app_id,
                name=record.name,
                canonical_name=record.name.strip(),
                category_id=category_ids[record.category],
                homepage_url=urls.get(record.source_index),
                source_index=record.source_index,
            )
        )

    records.sort(key=lambda item: item.app_id)
    app_ids = [record.app_id for record in records]
    if len(set(app_ids)) != len(app_ids):
        colliding = sorted({item for item in app_ids if app_ids.count(item) > 1})
        raise RegistryError(
            "Application ids are not unique", app_ids=colliding[:10]
        )

    categories = [
        Category(
            category_id=category_id,
            name=name,
            app_count=sum(1 for r in records if r.category_id == category_id),
        )
        for name, category_id in sorted(category_ids.items(), key=lambda pair: pair[1])
    ]

    metadata = ArtifactMetadata(
        stage=C.PipelineStage.NORMALIZATION,
        generated_at=generated_at or utc_now(),
        seed=seed,
        record_count=len(records),
        source_fingerprint=raw.metadata.source_fingerprint,
        notes="Normalized from {}".format(raw.source_name),
    )
    return NormalizedRegistry(metadata=metadata, categories=categories, records=records)


def load_registry(
    path: Path,
    seed: int,
    expected_apps: int = C.DEFAULT_EXPECTED_APP_COUNT,
    expected_categories: int = C.DEFAULT_EXPECTED_CATEGORY_COUNT,
    mapping_overrides: Optional[Dict[str, Optional[str]]] = None,
    generated_at: Optional[datetime] = None,
) -> Tuple[RawRegistry, NormalizedRegistry]:
    """Load, normalize, and verify the supplied list in one step.

    Fails rather than truncating or padding when the list is not exactly the
    expected shape.
    """
    raw, mapping, urls = load_raw(
        path,
        seed=seed,
        mapping_overrides=mapping_overrides,
        generated_at=generated_at,
    )

    supplied_ids: Dict[int, str] = {}
    if mapping.app_id:
        for record in raw.records:
            value = str(record.fields.get(mapping.app_id) or "").strip()
            if value:
                supplied_ids[record.source_index] = value
        if supplied_ids and len(supplied_ids) != len(raw.records):
            raise RegistryError(
                "Source supplies ids for only some rows",
                column=mapping.app_id,
                with_id=len(supplied_ids),
                total=len(raw.records),
            )

    normalized = normalize(
        raw,
        seed=seed,
        urls=urls,
        supplied_ids=supplied_ids,
        generated_at=generated_at,
    )

    try:
        normalized.require_exact_counts(
            apps=expected_apps, categories=expected_categories
        )
    except ValueError as exc:
        raise RegistryError(
            "Source list is not the expected shape",
            detail=str(exc),
            path=str(path),
        ) from exc

    return raw, normalized

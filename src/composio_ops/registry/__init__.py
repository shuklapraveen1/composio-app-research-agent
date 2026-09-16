"""Deterministic ingestion of the supplied application registry."""

from .duplicates import describe, find_duplicates
from .ids import generate_category_ids, generate_ids, normalize_name, slugify
from .loader import (
    ColumnMapping,
    load_raw,
    load_registry,
    normalize,
    resolve_columns,
)

__all__ = [
    "ColumnMapping",
    "describe",
    "find_duplicates",
    "generate_category_ids",
    "generate_ids",
    "load_raw",
    "load_registry",
    "normalize",
    "normalize_name",
    "resolve_columns",
    "slugify",
]

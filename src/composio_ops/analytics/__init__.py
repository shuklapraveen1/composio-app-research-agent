"""Deterministic analytics and pattern analysis over the final dataset."""

from .compute import analyse as analyse_dataset
from .compute import (
    cross_tab,
    distribution,
    export_columns,
    metrics,
    rows_for_export,
)
from .patterns import analyse as analyse_patterns
from .patterns import by_key, top_patterns

__all__ = [
    "analyse_dataset",
    "analyse_patterns",
    "by_key",
    "cross_tab",
    "distribution",
    "export_columns",
    "metrics",
    "rows_for_export",
    "top_patterns",
]

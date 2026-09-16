"""Publishable exports of the final dataset.

The case study is the argument; these are the workings. A reader who disagrees
with a conclusion can open the CSV in a spreadsheet or the JSON in a script and
check it, which is the difference between a claim and a result.
"""

from typing import List

from ..analytics.compute import export_columns, rows_for_export
from ..config import Settings
from ..io_utils import write_csv, write_json
from ..schemas.analytics import AnalyticsReport, PatternReport
from ..schemas.dataset import Dataset
from ..schemas.verification import AccuracyReport


def write_dataset_exports(
    dataset: Dataset,
    analytics: AnalyticsReport,
    patterns: PatternReport,
    accuracy: AccuracyReport,
    settings: Settings,
) -> List[str]:
    """Write the dataset and its derivatives, both under ``data/`` and on the site."""
    paths = settings.paths
    paths.ensure_directories()
    written: List[str] = []

    rows = rows_for_export(dataset)
    columns = list(export_columns())

    targets = (
        (paths.final_dataset, dataset.to_jsonable()),
        (paths.analytics, analytics.to_jsonable()),
        (paths.patterns, patterns.to_jsonable()),
        (paths.accuracy, accuracy.to_jsonable()),
        (paths.site_dataset, dataset.to_jsonable()),
        (paths.site_analytics, analytics.to_jsonable()),
        (paths.site_patterns, patterns.to_jsonable()),
        (paths.site_accuracy, accuracy.to_jsonable()),
    )
    for path, payload in targets:
        write_json(path, payload)
        written.append(paths.relative(path))

    for path in (paths.final_dataset_csv, paths.site_dataset_csv):
        write_csv(path, rows=rows, columns=columns)
        written.append(paths.relative(path))

    # GitHub Pages would otherwise run the directory through Jekyll and drop
    # anything it does not recognise.
    paths.site_nojekyll.write_text("", encoding="utf-8")
    written.append(paths.relative(paths.site_nojekyll))

    return sorted(written)

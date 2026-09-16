"""Deterministic analytics over the final dataset.

Pure functions, one input, no clock and no model: the same dataset always yields
the same numbers, which is what lets the case study quote them without a human
retyping anything.

Two conventions run through everything here. Unresolved values are counted, not
dropped, because how often a field could not be established is a finding about
the research rather than a gap in the chart. And multi-valued fields are counted
per value, so their buckets legitimately sum to more than the number of apps.
"""

from typing import Dict, List, Optional, Sequence, Tuple

from .. import constants as C
from ..config import Settings
from ..dataset import final_value
from ..determinism import fingerprint
from ..schemas.analytics import AnalyticsReport, CrossTab, Distribution, Metric
from ..schemas.base import ArtifactMetadata
from ..schemas.dataset import Dataset, DatasetRecord
from ..taxonomy import (
    MULTI_VALUED_FIELDS,
    VERIFIED_FIELDS,
    ApiBreadth,
    Blocker,
    Buildability,
    CredentialAccess,
    McpStatus,
    RateLimitInfo,
    ResearchFieldName,
    ResolutionStatus,
    WebhookSupport,
)

F = ResearchFieldName

#: Fields the analytics layer reports distributions for, in presentation order.
DISTRIBUTION_FIELDS: Tuple[F, ...] = (
    F.APPLICATION_TYPE,
    F.AUTHENTICATION,
    F.CREDENTIAL_ACCESS,
    F.ACCESS_RESTRICTIONS,
    F.API_TYPES,
    F.API_BREADTH,
    F.API_CAPABILITIES,
    F.MCP,
    F.WEBHOOK_SUPPORT,
    F.RATE_LIMIT_INFO,
    F.BUILDABILITY,
    F.BLOCKER,
)

#: Human labels, so the case study never has to translate a field name.
FIELD_LABELS: Dict[F, str] = {
    F.APPLICATION_TYPE: "Application type",
    F.AUTHENTICATION: "Authentication mechanisms",
    F.CREDENTIAL_ACCESS: "How credentials are obtained",
    F.ACCESS_RESTRICTIONS: "Conditions on API access",
    F.API_TYPES: "Interface types",
    F.API_BREADTH: "API breadth",
    F.API_CAPABILITIES: "API capabilities",
    F.MCP: "MCP server availability",
    F.WEBHOOK_SUPPORT: "Event delivery",
    F.RATE_LIMIT_INFO: "Published rate limits",
    F.BUILDABILITY: "Buildability",
    F.BLOCKER: "Blockers",
}


def distribution(dataset: Dataset, field: F) -> Distribution:
    """Counts for one field, with unresolved statuses kept as their own buckets."""
    counts: Dict[str, int] = {}
    unresolved: Dict[str, int] = {}
    multi = field in MULTI_VALUED_FIELDS

    for record in dataset.records:
        value = final_value(record, field)
        if value.status is ResolutionStatus.RESOLVED and value.value:
            for token in value.value:
                counts[token] = counts.get(token, 0) + 1
        else:
            unresolved[value.status.value] = unresolved.get(value.status.value, 0) + 1

    return Distribution(
        attribute=field.value,
        label=FIELD_LABELS.get(field, field.value.replace("_", " ").title()),
        counts=dict(sorted(counts.items())),
        unresolved=dict(sorted(unresolved.items())),
        total=len(dataset.records),
        multi_valued=multi,
    )


def _token(record: DatasetRecord, field: F) -> str:
    """One label per app for a single-valued field, unresolved statuses included."""
    value = final_value(record, field)
    if value.status is ResolutionStatus.RESOLVED and value.value:
        return value.value[0]
    return value.status.value


def cross_tab(
    dataset: Dataset,
    key: str,
    label: str,
    row_field: str,
    column_field: F,
    row_of=None,
) -> CrossTab:
    """Counts of ``column_field`` broken down by a row dimension."""
    row_of = row_of or (lambda record: record.app.category_id)
    cells: Dict[str, Dict[str, int]] = {}
    columns: set = set()

    for record in dataset.records:
        row = row_of(record)
        column = _token(record, column_field)
        columns.add(column)
        cells.setdefault(row, {})[column] = cells.setdefault(row, {}).get(column, 0) + 1

    ordered_columns = sorted(columns)
    for row in cells:
        for column in ordered_columns:
            cells[row].setdefault(column, 0)
        cells[row] = dict(sorted(cells[row].items()))

    return CrossTab(
        key=key,
        label=label,
        row_attribute=row_field,
        column_attribute=column_field.value,
        rows=sorted(cells),
        columns=ordered_columns,
        cells=dict(sorted(cells.items())),
    )


def _share(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def metrics(dataset: Dataset) -> List[Metric]:
    """The headline figures, each one computed from the dataset it is quoted with."""
    total = len(dataset.records)
    values = {
        field: [final_value(record, field) for record in dataset.records]
        for field in VERIFIED_FIELDS
    }

    def count_where(field: F, predicate) -> int:
        return sum(1 for value in values[field] if predicate(value))

    resolved = lambda value: value.status is ResolutionStatus.RESOLVED  # noqa: E731
    has = lambda token: (  # noqa: E731
        lambda value: resolved(value) and token in (value.value or [])
    )

    buildable = count_where(F.BUILDABILITY, has(Buildability.BUILDABLE.value))
    friction = count_where(
        F.BUILDABILITY, has(Buildability.BUILDABLE_WITH_FRICTION.value)
    )
    blocked = count_where(F.BUILDABILITY, has(Buildability.BLOCKED.value))
    self_serve = count_where(
        F.CREDENTIAL_ACCESS,
        lambda value: resolved(value)
        and bool(
            {
                CredentialAccess.SELF_SERVE_FREE.value,
                CredentialAccess.SELF_SERVE_TRIAL.value,
            }
            & set(value.value or [])
        ),
    )
    mcp_any = count_where(F.MCP, resolved)
    mcp_official = count_where(F.MCP, has(McpStatus.OFFICIAL.value))
    native_events = count_where(
        F.WEBHOOK_SUPPORT, has(WebhookSupport.NATIVE_WEBHOOKS.value)
    )
    quantitative_limits = count_where(
        F.RATE_LIMIT_INFO, has(RateLimitInfo.DOCUMENTED_QUANTITATIVE.value)
    )
    broad_apis = count_where(
        F.API_BREADTH,
        lambda value: resolved(value)
        and bool(
            {ApiBreadth.BROAD.value, ApiBreadth.VERY_BROAD.value}
            & set(value.value or [])
        ),
    )
    no_blocker = count_where(F.BLOCKER, has(Blocker.NONE.value))
    unresolved_fields = sum(
        1
        for field in VERIFIED_FIELDS
        for value in values[field]
        if value.status in (ResolutionStatus.NOT_FOUND, ResolutionStatus.UNCLEAR)
    )
    verified_apps = sum(1 for record in dataset.records if record.verification)
    confidence = {level.value: 0 for level in C.Confidence}
    for record in dataset.records:
        confidence[record.research.confidence.value] += 1

    entries: List[Metric] = [
        Metric(key="apps_total", label="Applications researched", value=total),
        Metric(
            key="categories_total",
            label="Supplied categories",
            value=len(dataset.categories),
        ),
        Metric(key="buildable", label="Buildable today", value=buildable),
        Metric(
            key="buildable_share",
            label="Share buildable today",
            value=_share(buildable, total),
            unit="share",
        ),
        Metric(
            key="buildable_with_friction",
            label="Buildable with friction",
            value=friction,
        ),
        Metric(key="blocked", label="Blocked", value=blocked),
        Metric(
            key="blocked_share",
            label="Share blocked",
            value=_share(blocked, total),
            unit="share",
        ),
        Metric(
            key="self_serve_credentials",
            label="Credentials obtainable free or on a trial",
            value=self_serve,
        ),
        Metric(
            key="self_serve_share",
            label="Share with self-serve credentials",
            value=_share(self_serve, total),
            unit="share",
        ),
        Metric(key="mcp_any", label="Applications with an MCP server", value=mcp_any),
        Metric(
            key="mcp_official",
            label="Applications with a vendor-published MCP server",
            value=mcp_official,
        ),
        Metric(
            key="mcp_share",
            label="Share with any MCP server",
            value=_share(mcp_any, total),
            unit="share",
        ),
        Metric(
            key="native_webhooks",
            label="Applications with native webhooks",
            value=native_events,
        ),
        Metric(
            key="quantitative_rate_limits",
            label="Applications publishing numeric rate limits",
            value=quantitative_limits,
        ),
        Metric(
            key="broad_apis",
            label="Applications with broad or very broad APIs",
            value=broad_apis,
        ),
        Metric(
            key="no_blocker",
            label="Applications with nothing in the way",
            value=no_blocker,
        ),
        Metric(
            key="unresolved_field_values",
            label="Verified field values left unresolved",
            value=unresolved_fields,
            description=(
                "Counted across {} apps x {} verified fields.".format(
                    total, len(VERIFIED_FIELDS)
                )
            ),
        ),
        Metric(
            key="unresolved_field_share",
            label="Share of verified field values left unresolved",
            value=_share(unresolved_fields, total * len(VERIFIED_FIELDS)),
            unit="share",
        ),
        Metric(
            key="verified_apps",
            label="Applications carried through verification",
            value=verified_apps,
        ),
        Metric(
            key="confidence_high",
            label="Records at high confidence",
            value=confidence[C.Confidence.HIGH.value],
        ),
        Metric(
            key="confidence_medium",
            label="Records at medium confidence",
            value=confidence[C.Confidence.MEDIUM.value],
        ),
        Metric(
            key="confidence_low",
            label="Records at low confidence",
            value=confidence[C.Confidence.LOW.value],
        ),
    ]
    return sorted(entries, key=lambda item: item.key)


def analyse(dataset: Dataset, settings: Settings) -> AnalyticsReport:
    """Compute every metric, distribution and cross-tab the case study reads."""
    distributions = [distribution(dataset, field) for field in DISTRIBUTION_FIELDS]
    distributions.sort(key=lambda item: item.attribute)

    tabs = [
        cross_tab(
            dataset,
            key="buildability_by_category",
            label="Buildability by supplied category",
            row_field="category_id",
            column_field=F.BUILDABILITY,
        ),
        cross_tab(
            dataset,
            key="buildability_by_credential_access",
            label="Buildability by how credentials are obtained",
            row_field="credential_access",
            column_field=F.BUILDABILITY,
            row_of=lambda record: _token(record, F.CREDENTIAL_ACCESS),
        ),
        cross_tab(
            dataset,
            key="mcp_by_category",
            label="MCP server availability by supplied category",
            row_field="category_id",
            column_field=F.MCP,
        ),
        cross_tab(
            dataset,
            key="webhooks_by_api_breadth",
            label="Event delivery by API breadth",
            row_field="api_breadth",
            column_field=F.WEBHOOK_SUPPORT,
            row_of=lambda record: _token(record, F.API_BREADTH),
        ),
    ]
    tabs.sort(key=lambda item: item.key)

    return AnalyticsReport(
        metadata=ArtifactMetadata(
            stage=C.PipelineStage.ANALYTICS,
            generated_at=settings.as_of,
            seed=settings.seed,
            record_count=len(dataset.records),
            source_fingerprint=dataset.metadata.source_fingerprint,
            notes="Computed from the final dataset; no model involved.",
        ),
        dataset_fingerprint=dataset.metadata.source_fingerprint,
        metrics=metrics(dataset),
        distributions=distributions,
        cross_tabs=tabs,
    )


def metric_value(report: AnalyticsReport, key: str) -> Optional[object]:
    metric = report.metric(key)
    return metric.value if metric else None


def rows_for_export(dataset: Dataset) -> List[Dict[str, object]]:
    """One flat row per app, for the CSV export and the case study tables."""
    rows: List[Dict[str, object]] = []
    for record in dataset.records:
        row: Dict[str, object] = {
            "app_id": record.app_id,
            "app": record.app.name,
            "category": record.app.category_id,
            "confidence": record.research.confidence.value,
            "classifier_version": record.research.classifier_version,
            "provider": record.research.provider.value,
            "sample_group": record.sample_group.value if record.sample_group else "",
            "verification_status": record.research.verification.status.value,
            "evidence_count": len(record.evidence),
        }
        for field in VERIFIED_FIELDS:
            value = final_value(record, field)
            row[field.value] = (
                "|".join(value.value) if value.value else value.status.value
            )
            row["{}_status".format(field.value)] = value.status.value
        rows.append(row)
    return rows


def export_columns() -> Sequence[str]:
    """Fixed column order for the CSV export."""
    columns = [
        "app_id",
        "app",
        "category",
        "confidence",
        "classifier_version",
        "provider",
        "sample_group",
        "verification_status",
        "evidence_count",
    ]
    for field in VERIFIED_FIELDS:
        columns.append(field.value)
        columns.append("{}_status".format(field.value))
    return columns


def dataset_fingerprint(dataset: Dataset) -> str:
    return fingerprint([record.research.to_jsonable() for record in dataset.records])

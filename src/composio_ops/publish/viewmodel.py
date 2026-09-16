"""The projection of the artifacts that the case study page interacts with.

The page is an explorer, not a report, so the browser needs the dataset in a
shape it can filter and sort. This module builds that shape and nothing else: it
reads the final dataset, analytics, patterns, accuracy and improvement artifacts
and rearranges them. It computes no research value of its own — every number
here already exists in an artifact, and anything this module cannot find there
is reported as unresolved rather than filled in.

Keys are emitted sorted and values keep their artifact ordering, so the embedded
payload is byte-stable across runs like every other generated file.
"""

import json
from typing import Any, Dict, List

from .. import constants as C
from ..analytics.compute import FIELD_LABELS
from ..config import Settings
from ..dataset import final_value
from ..schemas.analytics import AnalyticsReport, PatternReport
from ..schemas.dataset import Dataset, DatasetRecord
from ..schemas.review import ImprovementReport, ReviewQueue
from ..schemas.validation import ValidationReport
from ..schemas.verification import AccuracyReport, SampleAccuracy
from ..taxonomy import (
    MULTI_VALUED_FIELDS,
    VERIFIED_FIELDS,
    ResearchFieldName,
    ResolutionStatus,
)

F = ResearchFieldName

#: Columns the explorer filters and sorts on, in table order.
TABLE_FIELDS = (
    F.BUILDABILITY,
    F.CREDENTIAL_ACCESS,
    F.MCP,
)

#: Fields shown in an application's detail panel, in reading order.
DETAIL_FIELDS = (
    F.APPLICATION_TYPE,
    F.AUTHENTICATION,
    F.CREDENTIAL_ACCESS,
    F.ACCESS_RESTRICTIONS,
    F.API_EXISTS,
    F.API_TYPES,
    F.API_BREADTH,
    F.API_CAPABILITIES,
    F.MCP,
    F.WEBHOOK_SUPPORT,
    F.RATE_LIMIT_INFO,
    F.BUILDABILITY,
    F.BLOCKER,
)


def humanise(token: str) -> str:
    """Render a taxonomy token the way the rest of the project prints it."""
    return token.replace("_", " ")


#: Labels for fields the analytics layer does not report a distribution for, so
#: the page never has to fall back to a capitalised token.
EXTRA_LABELS: Dict[F, str] = {
    F.API_EXISTS: "API exists",
    F.IDENTITY: "Identity",
    F.DESCRIPTION: "Description",
}


def field_label(field: F) -> str:
    if field in FIELD_LABELS:
        return FIELD_LABELS[field]
    return EXTRA_LABELS.get(field, humanise(field.value).capitalize())


def _token(record: DatasetRecord, field: F) -> str:
    """The single token a column filters on: the value, or the status if unresolved."""
    value = final_value(record, field)
    if value.status is ResolutionStatus.RESOLVED and value.value:
        return value.value[0]
    return value.status.value


def field_schema() -> List[Dict[str, Any]]:
    """Field metadata, shared once instead of repeated on all hundred records."""
    return [
        {
            "field": field.value,
            "label": field_label(field),
            "multi": field in MULTI_VALUED_FIELDS,
            "verified": field in VERIFIED_FIELDS,
        }
        for field in DETAIL_FIELDS
    ]


def _field_entry(record: DatasetRecord, field: F) -> Dict[str, Any]:
    """One field of one app, positionally matched to :func:`field_schema`.

    Empty members are omitted rather than serialised as nulls: the payload is
    embedded in the page, and thirteen fields across a hundred applications make
    every repeated key expensive.
    """
    researched = record.research.field(field)
    value = final_value(record, field)
    entry: Dict[str, Any] = {"status": value.status.value}
    if value.value:
        entry["values"] = list(value.value)
    if researched.rationale:
        entry["rationale"] = researched.rationale
    if researched.evidence_ids:
        entry["evidence_ids"] = list(researched.evidence_ids)
    return entry


def _evidence_entry(item: Any) -> Dict[str, Any]:
    return {
        "claim": item.claim,
        "id": item.evidence_id,
        "retrieval": item.retrieval.value,
        "supports": [field.value for field in item.supports],
        "title": item.title,
        "type": item.source_type.value,
        "url": item.url,
    }


def _verification_entries(record: DatasetRecord) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for result in record.verification:
        outcomes: Dict[str, int] = {}
        for item in result.field_results:
            outcomes[item.outcome.value] = outcomes.get(item.outcome.value, 0) + 1
        entries.append(
            {
                "channel": result.channel.value,
                "checked": len(result.field_results),
                "corrections": [
                    {
                        "field": item.field.value,
                        "reason": item.reason,
                        "value": list(item.value or []) or [item.status.value],
                    }
                    for item in result.corrected_values
                ],
                "discrepancies": [item.value for item in result.discrepancies],
                "evidence_checked": len(result.evidence_results),
                "evidence_valid": sum(
                    1 for item in result.evidence_results if item.is_valid
                ),
                "outcomes": dict(sorted(outcomes.items())),
                "reviewer": result.reviewer,
            }
        )
    return entries


def _reconciliation_entries(record: DatasetRecord) -> List[Dict[str, Any]]:
    return [
        {
            "authoritative": decision.authoritative_channel.value
            if decision.authoritative_channel
            else None,
            "decided_by": decision.decided_by,
            "field": decision.field.value,
            "outcome": decision.outcome.value,
            "rationale": decision.rationale,
            "status": decision.final_status.value,
            "value": list(decision.final_value or []),
        }
        for decision in record.reconciliation
    ]


def _app_entry(record: DatasetRecord, categories: Dict[str, str]) -> Dict[str, Any]:
    research = record.research
    assessment = research.buildability_assessment
    description = research.description
    entry: Dict[str, Any] = {
        "blockers": list(final_value(record, F.BLOCKER).value or []),
        "category": categories.get(record.app.category_id, record.app.category_id),
        "category_id": record.app.category_id,
        "channels": [channel.value for channel in research.verification.channels],
        "confidence": research.confidence.value,
        "description": description.value if description.is_resolved else None,
        "evidence": [_evidence_entry(item) for item in record.evidence],
        "evidence_count": len(record.evidence),
        "fields": [_field_entry(record, field) for field in DETAIL_FIELDS],
        "homepage": record.app.homepage_url,
        "id": record.app_id,
        "name": record.app.name,
        "reconciliation": _reconciliation_entries(record),
        "sample": record.sample_group.value if record.sample_group else None,
        "triggers": [trigger.value for trigger in research.verification.triggers],
        "verification": _verification_entries(record),
        "verification_status": research.verification.status.value,
    }
    for field in TABLE_FIELDS:
        entry[field.value] = _token(record, field)
    entry["api_breadth"] = _token(record, F.API_BREADTH)
    # The assessment's own reason is the buildability rationale verbatim, so it
    # is read from the field rather than carried twice.
    entry["dimensions"] = (
        {
            "commercial": assessment.commercial_accessibility.value,
            "credential": assessment.credential_accessibility.value,
            "technical": assessment.technical_feasibility.value,
        }
        if assessment
        else None
    )
    entry["mcp_details"] = (
        {
            "maintained": research.mcp_details.maintained.value,
            "official": research.mcp_details.official,
            "source_url": research.mcp_details.source_url,
        }
        if research.mcp_details
        else None
    )
    return entry


def _facet(apps: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    """Filter options for one column, ordered by how common the value is."""
    counts: Dict[str, int] = {}
    for app in apps:
        value = app.get(key)
        if value is None:
            continue
        counts[value] = counts.get(value, 0) + 1
    return [
        {"count": count, "label": humanise(value), "value": value}
        for value, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]


def _sample_entry(sample: SampleAccuracy) -> Dict[str, Any]:
    return {
        "apps": sample.apps,
        "claims_checked": sample.claims_checked,
        "claims_valid": sample.claims_with_valid_evidence,
        "classifier": sample.classifier_version,
        "evidence_validity": sample.evidence_validity,
        "field_level": sample.field_level_accuracy,
        "fields_checked": sample.fields_checked,
        "fields_correct": sample.fields_correct,
        "group": sample.group.value,
        "measurement": sample.measurement,
        "row_level": sample.row_level_accuracy,
        "rows_checked": sample.rows_checked,
        "rows_correct": sample.rows_correct,
    }


def per_field_accuracy(accuracy: AccuracyReport) -> List[Dict[str, Any]]:
    """Per-field first-pass and final accuracy, paired field by field."""
    sample_a = accuracy.sample(C.SampleGroup.A)
    sample_b = accuracy.sample(C.SampleGroup.B)
    if sample_b is None:
        return []
    before = {item.field: item for item in (sample_a.per_field if sample_a else [])}
    rows: List[Dict[str, Any]] = []
    for item in sample_b.per_field:
        earlier = before.get(item.field)
        rows.append(
            {
                "a": earlier.accuracy if earlier else None,
                "a_correct": earlier.correct if earlier else None,
                "a_checked": earlier.checked if earlier else None,
                "b": item.accuracy,
                "b_checked": item.checked,
                "b_correct": item.correct,
                "field": item.field.value,
                "label": field_label(item.field),
            }
        )
    return rows


def build(
    dataset: Dataset,
    analytics: AnalyticsReport,
    patterns: PatternReport,
    accuracy: AccuracyReport,
    improvements: ImprovementReport,
    validation: ValidationReport,
    queue: ReviewQueue,
    settings: Settings,
) -> Dict[str, Any]:
    """Assemble everything the page needs, straight from the artifacts."""
    categories = {item.category_id: item.name for item in dataset.categories}
    apps = [_app_entry(record, categories) for record in dataset.records]
    metrics = {item.key: item.value for item in analytics.metrics}

    return {
        "accuracy": {
            "headline": accuracy.headline_value,
            "headline_metric": accuracy.headline_metric,
            "note": accuracy.metadata.notes,
            "per_field": per_field_accuracy(accuracy),
            "samples": [_sample_entry(sample) for sample in accuracy.samples],
        },
        "apps": apps,
        "categories": [
            {"id": item.category_id, "name": item.name} for item in dataset.categories
        ],
        "distributions": [
            {
                "attribute": item.attribute,
                "counts": item.counts,
                "label": item.label,
                "multi_valued": item.multi_valued,
                "total": item.total,
                "unresolved": item.unresolved,
            }
            for item in analytics.distributions
        ],
        "field_schema": field_schema(),
        "facets": {
            "buildability": _facet(apps, F.BUILDABILITY.value),
            "category": [
                {
                    "count": sum(
                        1 for app in apps if app["category_id"] == item.category_id
                    ),
                    "label": item.name,
                    "value": item.category_id,
                }
                for item in dataset.categories
            ],
            "confidence": _facet(apps, "confidence"),
            "credential_access": _facet(apps, F.CREDENTIAL_ACCESS.value),
            "mcp": _facet(apps, F.MCP.value),
            "sample": _facet(apps, "sample"),
        },
        "findings": [
            {
                "app_ids": list(pattern.supporting_app_ids),
                "key": pattern.key,
                "observed": pattern.observed,
                "population": pattern.population,
                "statement": pattern.statement,
                "title": pattern.title,
            }
            for pattern in sorted(
                patterns.patterns, key=lambda item: (-item.observed, item.key)
            )
        ],
        "improvements": [
            {
                "change": item.change,
                "failure_mode": item.failure_mode,
                "fields": [field.value for field in item.fields],
                "key": item.key,
                "observed": item.observed_in_sample_a,
            }
            for item in improvements.improvements
        ],
        "meta": {
            "apps": len(dataset.records),
            "as_of": settings.as_of.date().isoformat(),
            "classifier": dataset.classifier_version,
            "evidence": sum(len(record.evidence) for record in dataset.records),
            "fingerprint": dataset.metadata.source_fingerprint,
            "from_classifier": improvements.from_classifier,
            "metrics": metrics,
            "provider": dataset.provider.value,
            "queued": len(queue.entries),
            "sample_size": settings.sample_size_a,
            "schema": C.SCHEMA_VERSION,
            "seed": settings.seed,
            "to_classifier": improvements.to_classifier,
            "validation": {
                "checked": validation.checked_records,
                "errors": len(validation.errors),
                "warnings": len(validation.warnings),
            },
            "verified_fields": len(VERIFIED_FIELDS),
        },
    }


def serialise(payload: Dict[str, Any]) -> str:
    """Canonical JSON, safe to embed in a script element."""
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    # A literal "</script>" inside the payload would end the element early; the
    # escaped forms parse identically as JSON.
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

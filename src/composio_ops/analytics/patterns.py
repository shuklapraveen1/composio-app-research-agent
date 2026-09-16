"""Pattern analysis: the regularities worth saying out loud.

A pattern here is not a sentence somebody found interesting; it is a predicate
over the final dataset, evaluated deterministically, carrying the app ids that
satisfy it. If the underlying data changes, the sentence changes with it, and a
reader who doubts a claim can check it against the list rather than argue with
the prose.
"""

from typing import Callable, Dict, List, Sequence, Tuple

from .. import constants as C
from ..config import Settings
from ..dataset import final_value
from ..determinism import fingerprint
from ..schemas.analytics import Pattern, PatternReport
from ..schemas.base import ArtifactMetadata
from ..schemas.dataset import Dataset, DatasetRecord
from ..taxonomy import (
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

Predicate = Callable[[DatasetRecord], bool]


def _tokens(record: DatasetRecord, field: F) -> List[str]:
    value = final_value(record, field)
    if value.status is ResolutionStatus.RESOLVED and value.value:
        return list(value.value)
    return []


def _status(record: DatasetRecord, field: F) -> ResolutionStatus:
    return final_value(record, field).status


def _is(record: DatasetRecord, field: F, token: str) -> bool:
    return token in _tokens(record, field)


def _blocked_by_access(record: DatasetRecord) -> bool:
    return _is(record, F.BUILDABILITY, Buildability.BLOCKED.value) and bool(
        {
            Blocker.ENTERPRISE_ONLY.value,
            Blocker.PARTNER_REQUIRED.value,
            Blocker.CREDENTIALS_UNAVAILABLE.value,
        }
        & set(_tokens(record, F.BLOCKER))
    )


def _no_public_api(record: DatasetRecord) -> bool:
    """Established absence, not a gap: ``unavailable`` means the vendor offers none."""
    return _status(record, F.API_EXISTS) is ResolutionStatus.UNAVAILABLE or (
        Blocker.NO_PUBLIC_API.value in _tokens(record, F.BLOCKER)
    )


def _broad_api_but_gated(record: DatasetRecord) -> bool:
    broad = bool(
        {ApiBreadth.BROAD.value, ApiBreadth.VERY_BROAD.value}
        & set(_tokens(record, F.API_BREADTH))
    )
    gated = bool(
        {
            CredentialAccess.ENTERPRISE.value,
            CredentialAccess.CONTACT_SALES.value,
            CredentialAccess.PARTNER_REQUIRED.value,
            CredentialAccess.ADMIN_APPROVAL.value,
        }
        & set(_tokens(record, F.CREDENTIAL_ACCESS))
    )
    return broad and gated


def _mcp_without_official(record: DatasetRecord) -> bool:
    return McpStatus.THIRD_PARTY.value in _tokens(record, F.MCP)


def _official_mcp(record: DatasetRecord) -> bool:
    return McpStatus.OFFICIAL.value in _tokens(record, F.MCP)


def _events_without_webhooks(record: DatasetRecord) -> bool:
    return bool(
        {
            WebhookSupport.POLLING_ONLY.value,
            WebhookSupport.NO_EVENTS.value,
            WebhookSupport.EVENT_STREAMING.value,
        }
        & set(_tokens(record, F.WEBHOOK_SUPPORT))
    )


def _undisclosed_limits(record: DatasetRecord) -> bool:
    return bool(
        {
            RateLimitInfo.ENFORCED_BUT_UNDISCLOSED.value,
            RateLimitInfo.NO_PUBLISHED_LIMITS.value,
        }
        & set(_tokens(record, F.RATE_LIMIT_INFO))
    )


def _unresolved_mcp(record: DatasetRecord) -> bool:
    return _status(record, F.MCP) in (
        ResolutionStatus.NOT_FOUND,
        ResolutionStatus.UNCLEAR,
    )


def _friction_from_credentials(record: DatasetRecord) -> bool:
    return _is(
        record, F.BUILDABILITY, Buildability.BUILDABLE_WITH_FRICTION.value
    ) and bool(
        {Blocker.PAID_ACCESS.value, Blocker.ADMIN_APPROVAL.value}
        & set(_tokens(record, F.BLOCKER))
    )


#: Each pattern: key, title, the sentence template, and the predicate behind it.
PATTERNS: Tuple[Tuple[str, str, str, Predicate], ...] = (
    (
        "access-gates-beat-missing-apis",
        "Access, not absence of an API, is what blocks",
        "{observed} of {population} applications are blocked by who may obtain "
        "credentials rather than by the absence of an API.",
        _blocked_by_access,
    ),
    (
        "no-public-api",
        "Products with no public API at all",
        "{observed} of {population} applications offer no public API, so no "
        "toolkit is possible regardless of commercial terms.",
        _no_public_api,
    ),
    (
        "broad-api-behind-a-gate",
        "Capable APIs behind a human gate",
        "{observed} of {population} applications document a broad API that a "
        "developer cannot reach without an administrator, a contract or a "
        "partner programme.",
        _broad_api_but_gated,
    ),
    (
        "mcp-is-community-first",
        "MCP coverage is community-first",
        "{observed} of {population} applications are reachable through an MCP "
        "server that the vendor did not publish.",
        _mcp_without_official,
    ),
    (
        "mcp-official",
        "Vendors publishing their own MCP servers",
        "{observed} of {population} applications ship a vendor-published MCP "
        "server.",
        _official_mcp,
    ),
    (
        "mcp-unestablished",
        "MCP status is often unestablished",
        "{observed} of {population} applications have no MCP status that the "
        "sources could establish either way.",
        _unresolved_mcp,
    ),
    (
        "events-are-not-always-webhooks",
        "Event delivery is not always a webhook",
        "{observed} of {population} applications deliver change events by "
        "streaming, polling, or not at all.",
        _events_without_webhooks,
    ),
    (
        "limits-are-undisclosed",
        "Rate limits are frequently undisclosed",
        "{observed} of {population} applications publish no usable numeric "
        "rate limit, which is a capacity-planning risk rather than a "
        "documentation nicety.",
        _undisclosed_limits,
    ),
    (
        "friction-is-commercial",
        "Friction is commercial, not technical",
        "{observed} of {population} applications are buildable only past a paid "
        "plan or an administrator's approval.",
        _friction_from_credentials,
    ),
)


def analyse(dataset: Dataset, settings: Settings) -> PatternReport:
    """Evaluate every pattern against the dataset and record who supports it."""
    population = len(dataset.records)
    patterns: List[Pattern] = []

    for key, title, template, predicate in PATTERNS:
        supporting = sorted(
            record.app_id for record in dataset.records if predicate(record)
        )
        patterns.append(
            Pattern(
                key=key,
                title=title,
                statement=template.format(
                    observed=len(supporting), population=population
                ),
                observed=len(supporting),
                population=population,
                supporting_app_ids=supporting,
            )
        )

    patterns.sort(key=lambda item: item.key)
    return PatternReport(
        metadata=ArtifactMetadata(
            stage=C.PipelineStage.ANALYTICS,
            generated_at=settings.as_of,
            seed=settings.seed,
            record_count=len(patterns),
            source_fingerprint=fingerprint([item.to_jsonable() for item in patterns]),
            notes="Patterns evaluated as predicates over the final dataset.",
        ),
        dataset_fingerprint=dataset.metadata.source_fingerprint,
        patterns=patterns,
    )


def top_patterns(report: PatternReport, limit: int = 5) -> Sequence[Pattern]:
    """The most-supported patterns, for the case study's summary section."""
    ordered = sorted(
        report.patterns, key=lambda item: (-item.observed, item.key)
    )
    return ordered[:limit]


def by_key(report: PatternReport) -> Dict[str, Pattern]:
    return {pattern.key: pattern for pattern in report.patterns}

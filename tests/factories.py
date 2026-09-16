"""Synthetic fixtures for tests.

Everything here is obviously fake ("Example App 001"). No real application is
described, and nothing built here is ever written into ``data/``.
"""

import csv
from datetime import datetime
from typing import Dict, List, Optional

from composio_ops import constants as C
from composio_ops.schemas import (
    ArtifactMetadata,
    Category,
    EvidenceItem,
    NormalizedAppRecord,
    NormalizedRegistry,
)
from composio_ops.schemas.corpus import (
    AccessObservations,
    ApiObservations,
    Corpus,
    CorpusEntry,
    CorpusSource,
    McpObservations,
)
from composio_ops.taxonomy import (
    AccessRestriction,
    ApiCapability,
    ApiType,
    ApplicationType,
    AuthMethod,
    McpMaintenance,
    McpStatus,
    RateLimitInfo,
    ResearchFieldName,
    SourceType,
    WebhookSupport,
)

F = ResearchFieldName

#: Ten obviously synthetic category names.
CATEGORY_NAMES = [
    "Category Alpha",
    "Category Bravo",
    "Category Charlie",
    "Category Delta",
    "Category Echo",
    "Category Foxtrot",
    "Category Golf",
    "Category Hotel",
    "Category India",
    "Category Juliett",
]


def synthetic_rows(app_count: int = 100, category_count: int = 10) -> List[dict]:
    """A well-formed synthetic source list, evenly spread across categories."""
    return [
        {
            "name": "Example App {:03d}".format(index + 1),
            "category": CATEGORY_NAMES[index % category_count],
            "url": "https://example{:03d}.test".format(index + 1),
        }
        for index in range(app_count)
    ]


def write_csv_source(path, rows: List[dict]) -> None:
    columns = list(rows[0].keys()) if rows else ["name", "category", "url"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def metadata(stage: C.PipelineStage, count: int, when: datetime) -> ArtifactMetadata:
    return ArtifactMetadata(stage=stage, generated_at=when, seed=1, record_count=count)


def app_record(
    app_id: str = "example-app-001",
    category_id: str = "category-alpha",
    index: int = 0,
) -> NormalizedAppRecord:
    return NormalizedAppRecord(
        app_id=app_id,
        name="Example App {:03d}".format(index + 1),
        canonical_name="Example App {:03d}".format(index + 1),
        category_id=category_id,
        homepage_url="https://example{:03d}.test".format(index + 1),
        source_index=index,
    )


def category(category_id: str = "category-alpha", count: int = 1) -> Category:
    return Category(category_id=category_id, name="Category Alpha", app_count=count)


def registry(when: datetime, app_count: int = 4, category_count: int = 2) -> NormalizedRegistry:
    """A small synthetic registry, evenly spread across categories."""
    records = []
    counts: Dict[str, int] = {}
    for index in range(app_count):
        category_id = "category-{}".format(chr(ord("a") + index % category_count))
        counts[category_id] = counts.get(category_id, 0) + 1
        records.append(
            app_record(
                app_id="example-app-{:03d}".format(index + 1),
                category_id=category_id,
                index=index,
            )
        )
    return NormalizedRegistry(
        metadata=metadata(C.PipelineStage.NORMALIZATION, len(records), when),
        categories=[
            Category(
                category_id=category_id,
                name="Category {}".format(category_id[-1].upper()),
                app_count=count,
            )
            for category_id, count in sorted(counts.items())
        ],
        records=sorted(records, key=lambda item: item.app_id),
    )


def source(
    source_id: str,
    supports: List[F],
    claim: str = "The documentation states this.",
    source_type: SourceType = SourceType.FIRST_PARTY_DOCS,
    url: Optional[str] = None,
    current: bool = True,
) -> CorpusSource:
    return CorpusSource(
        id=source_id,
        url=url or "https://example001.test/docs/{}".format(source_id),
        title="Example docs: {}".format(source_id),
        type=source_type,
        supports=supports,
        claim=claim,
        current=current,
    )


def corpus_entry(
    app_id: str = "example-app-001",
    account: str = "free",
    api_plan: str = "free",
    approval_required: bool = False,
    partner_only: bool = False,
    admin_only: bool = False,
    self_hosted: bool = False,
    restrictions: Optional[List[AccessRestriction]] = None,
    api_exists: Optional[bool] = True,
    resource_groups: Optional[List[str]] = None,
    coverage: str = "most",
    enumerated: bool = True,
    webhooks: Optional[WebhookSupport] = WebhookSupport.NATIVE_WEBHOOKS,
    mcp_status: Optional[McpStatus] = None,
    identity_ambiguous: bool = False,
    integration_model: bool = True,
    conflicts: Optional[List[str]] = None,
) -> CorpusEntry:
    """A synthetic corpus entry that exercises every field the classifier reads."""
    groups = resource_groups if resource_groups is not None else [
        "objects",
        "records",
        "users",
        "files",
    ]
    sources = [
        source("docs", [F.API_EXISTS, F.API_TYPES, F.API_BREADTH, F.API_CAPABILITIES, F.DESCRIPTION]),
        source("auth", [F.AUTHENTICATION, F.CREDENTIAL_ACCESS, F.ACCESS_RESTRICTIONS]),
        source("limits", [F.RATE_LIMIT_INFO]),
        source("events", [F.WEBHOOK_SUPPORT]),
    ]
    if mcp_status is not None:
        sources.append(
            source(
                "mcp",
                [F.MCP],
                source_type=SourceType.REPOSITORY,
                url="https://github.com/example/example-mcp",
            )
        )
    return CorpusEntry(
        app_id=app_id,
        canonical_name="Example App 001",
        vendor="Example Vendor",
        homepage_url="https://example001.test",
        docs_url="https://example001.test/docs",
        description="A synthetic example application.",
        application_type=ApplicationType.AMBIGUOUS_IDENTITY
        if identity_ambiguous
        else ApplicationType.SAAS_APPLICATION,
        integration_model=integration_model,
        identity_ambiguous=identity_ambiguous,
        auth_methods=[AuthMethod.OAUTH2, AuthMethod.API_KEY],
        access=AccessObservations(
            account=account,
            api_plan=api_plan,
            approval_required=approval_required,
            partner_only=partner_only,
            admin_only=admin_only,
            self_hosted=self_hosted,
            restrictions=restrictions or [],
        ),
        api=ApiObservations(
            exists=api_exists,
            documented=api_exists is True,
            types=[ApiType.REST] if api_exists else [],
            resource_groups=groups if api_exists else [],
            enumerated=enumerated if api_exists else False,
            capabilities=[ApiCapability.READ, ApiCapability.WRITE] if api_exists else [],
            coverage=coverage,
        ),
        mcp=McpObservations(
            status=mcp_status,
            official=mcp_status is McpStatus.OFFICIAL,
            maintained=McpMaintenance.MAINTAINED
            if mcp_status
            else McpMaintenance.UNCLEAR,
            source_url="https://github.com/example/example-mcp" if mcp_status else None,
            searched=True,
        ),
        webhooks=webhooks,
        rate_limits=RateLimitInfo.DOCUMENTED_QUANTITATIVE,
        conflicts=conflicts or [],
        sources=sources,
    )


def corpus(when: datetime, entries: Optional[List[CorpusEntry]] = None) -> Corpus:
    items = entries or [corpus_entry()]
    return Corpus(
        metadata=metadata(C.PipelineStage.RESEARCH, len(items), when),
        entries=sorted(items, key=lambda item: item.app_id),
    )


def evidence_item(
    app_id: str,
    evidence_id: str,
    when: datetime,
    supports: Optional[List[F]] = None,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        app_id=app_id,
        url="https://example001.test/docs",
        title="Example docs",
        domain="example001.test",
        source_type=SourceType.FIRST_PARTY_DOCS,
        claim="The documentation states this.",
        retrieval=C.EvidenceRetrieval.CITED,
        supports=[F.API_EXISTS] if supports is None else supports,
        channel=C.Channel.CHANNEL_A,
        captured_at=when,
    )

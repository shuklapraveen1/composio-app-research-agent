"""Channel A: one research pass over the whole registry.

Channel A is the only stage that runs across all 100 apps. It writes three
things: the verbatim observations it worked from (provenance), the evidence
those observations cite, and the classified research records. Keeping the three
separate is what lets a reviewer check a classification against its source
without re-running anything.
"""

from typing import Dict, List, Optional, Sequence, Tuple

from .. import constants as C
from ..config import Settings
from ..determinism import fingerprint
from ..errors import ResearchError
from ..io_utils import write_json
from ..logging_setup import get_logger
from ..schemas.base import ArtifactMetadata
from ..schemas.evidence import EvidenceItem, EvidenceSet
from ..schemas.registry import NormalizedAppRecord, NormalizedRegistry
from ..schemas.research import AppResearchRecord, ResearchSet
from .evidence import EvidenceIndex, build_evidence
from .providers import ResearchProvider, build_provider
from .rules import classify


def research_registry(
    registry: NormalizedRegistry,
    settings: Settings,
    classifier_version: str = C.CLASSIFIER_V1,
    provider: Optional[ResearchProvider] = None,
    app_ids: Optional[Sequence[str]] = None,
) -> Tuple[ResearchSet, EvidenceSet, Dict[str, dict]]:
    """Research every app and return the records, their evidence, and the raw observations."""
    logger = get_logger()
    selected = [
        record
        for record in registry.records
        if app_ids is None or record.app_id in set(app_ids)
    ]
    if not selected:
        raise ResearchError(
            "No apps selected for research",
            requested=sorted(app_ids) if app_ids else None,
        )

    active = provider or build_provider(
        settings, expected_app_ids=registry.app_ids()
    )

    records: List[AppResearchRecord] = []
    evidence: List[EvidenceItem] = []
    raw: Dict[str, dict] = {}

    for app in selected:
        entry = active.observe(app)
        items = build_evidence(entry, captured_at=settings.as_of)
        index = EvidenceIndex(items)
        record = classify(
            entry=entry,
            app=app,
            index=index,
            version=classifier_version,
            provider=active.kind,
            generated_at=settings.as_of,
        )
        records.append(record)
        evidence.extend(items)
        raw[app.app_id] = entry.to_jsonable()
        logger.debug(
            "research.app",
            app_id=app.app_id,
            confidence=record.confidence.value,
            buildability=record.buildability.status.value,
        )

    records.sort(key=lambda item: item.app_id)
    evidence.sort(key=lambda item: item.evidence_id)

    source_fingerprint = fingerprint([item.to_jsonable() for item in evidence])
    research_set = ResearchSet(
        metadata=ArtifactMetadata(
            stage=C.PipelineStage.CLASSIFICATION,
            generated_at=settings.as_of,
            seed=settings.seed,
            record_count=len(records),
            source_fingerprint=source_fingerprint,
            notes="Channel A, classifier {}, provider {}.".format(
                classifier_version, active.kind.value
            ),
        ),
        records=records,
    )
    evidence_set = EvidenceSet(
        metadata=ArtifactMetadata(
            stage=C.PipelineStage.EVIDENCE_EXTRACTION,
            generated_at=settings.as_of,
            seed=settings.seed,
            record_count=len(evidence),
            source_fingerprint=source_fingerprint,
            notes="Evidence cited by Channel A.",
        ),
        items=evidence,
    )
    return research_set, evidence_set, raw


def persist(
    settings: Settings,
    research_set: ResearchSet,
    evidence_set: EvidenceSet,
    raw: Dict[str, dict],
) -> None:
    """Write the research artifacts, including the verbatim observations."""
    paths = settings.paths
    paths.ensure_directories()
    write_json(paths.classification, research_set.to_jsonable())
    write_json(paths.evidence, evidence_set.to_jsonable())
    for app_id, payload in sorted(raw.items()):
        write_json(paths.research_responses_dir / "{}.json".format(app_id), payload)
    write_json(
        paths.run_metadata,
        {
            "schema_version": C.SCHEMA_VERSION,
            "stage": C.PipelineStage.RESEARCH.value,
            "generated_at": settings.as_of.isoformat(),
            "seed": settings.seed,
            "provider": research_set.records[0].provider.value
            if research_set.records
            else None,
            "classifier_version": research_set.records[0].classifier_version
            if research_set.records
            else None,
            "apps": len(research_set.records),
            "evidence_items": len(evidence_set.items),
            "source_fingerprint": research_set.metadata.source_fingerprint,
        },
    )

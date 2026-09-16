"""Deterministic stratified sampling. Architecture section 9.

Two samples of fifteen, disjoint, stratified across the ten supplied categories.
Sample A measures the first pass and drives the improvement phase; Sample B
measures the improved classifier on apps it has never been evaluated against,
which is the only way the headline accuracy number means anything.

Everything is derived from the master seed through a per-sample namespace, so
the selection is reproducible, and the selection artifact records the derived
seed so it is auditable rather than merely repeatable.
"""

from typing import Dict, List, Optional, Sequence, Set, Tuple

from .. import constants as C
from ..config import Settings
from ..determinism import derive_seed, deterministic_sample, fingerprint, rng_for
from ..errors import SamplingError
from ..schemas.base import ArtifactMetadata
from ..schemas.registry import NormalizedRegistry
from ..schemas.research import AppResearchRecord, ResearchSet
from ..schemas.verification import (
    FrozenFieldValue,
    SampleAssignment,
    SampleSelection,
    to_value_key,
)
from ..taxonomy import VERIFIED_FIELDS

#: Which namespace seeds which sample. Separate streams, so adding Sample B
#: cannot reshuffle Sample A.
NAMESPACES: Dict[C.SampleGroup, str] = {
    C.SampleGroup.A: C.SEED_NAMESPACE_SAMPLE_A,
    C.SampleGroup.B: C.SEED_NAMESPACE_SAMPLE_B,
}


def allocate_quotas(
    category_sizes: Dict[str, int], size: int, master_seed: int, namespace: str
) -> Dict[str, int]:
    """Spread ``size`` draws across categories as evenly as the sizes allow.

    Every category gets the same base quota. The remainder goes to categories
    drawn with the sample's own RNG rather than to the largest or the first,
    so the allocation is unbiased and still reproducible.
    """
    categories = sorted(category_sizes)
    if not categories:
        raise SamplingError("Cannot stratify without categories")

    quotas = {category: 0 for category in categories}
    remaining = size
    # Round-robin the base quota so a small category cannot be over-drawn.
    while remaining > 0:
        eligible = [
            category
            for category in categories
            if quotas[category] < category_sizes[category]
        ]
        if not eligible:
            raise SamplingError(
                "Sample size exceeds the eligible population",
                requested=size,
                available=sum(category_sizes.values()),
            )
        base, remainder = divmod(remaining, len(eligible))
        if base:
            for category in eligible:
                take = min(base, category_sizes[category] - quotas[category])
                quotas[category] += take
                remaining -= take
        else:
            rng = rng_for(master_seed, "{}:remainder:{}".format(namespace, remaining))
            for category in rng.sample(eligible, remainder):
                quotas[category] += 1
                remaining -= 1
    return quotas


def select(
    registry: NormalizedRegistry,
    research: ResearchSet,
    settings: Settings,
    group: C.SampleGroup,
    size: Optional[int] = None,
    exclude: Optional[Sequence[str]] = None,
) -> SampleSelection:
    """Choose one sample and freeze the values it will be measured against."""
    namespace = NAMESPACES[group]
    sample_size = size or (
        settings.sample_size_a if group is C.SampleGroup.A else settings.sample_size_b
    )
    excluded_ids: Set[str] = set(exclude or ())

    researched = {record.app_id: record for record in research.records}
    exclusions: Dict[str, List[str]] = {}
    eligible_by_category: Dict[str, List[str]] = {}

    for app in registry.records:
        reasons: List[str] = []
        if app.app_id in excluded_ids:
            reasons.append("already drawn into the other sample")
        if app.app_id not in researched:
            reasons.append("no Channel A research record")
        if reasons:
            exclusions[app.app_id] = reasons
            continue
        eligible_by_category.setdefault(app.category_id, []).append(app.app_id)

    population = sum(len(ids) for ids in eligible_by_category.values())
    if population < sample_size:
        raise SamplingError(
            "Not enough eligible apps to draw the sample",
            group=group.value,
            requested=sample_size,
            eligible=population,
        )

    quotas = allocate_quotas(
        {category: len(ids) for category, ids in eligible_by_category.items()},
        size=sample_size,
        master_seed=settings.seed,
        namespace=namespace,
    )

    assignments: List[SampleAssignment] = []
    for category in sorted(eligible_by_category):
        quota = quotas.get(category, 0)
        if not quota:
            continue
        chosen = deterministic_sample(
            items=sorted(eligible_by_category[category]),
            size=quota,
            master_seed=settings.seed,
            namespace="{}:{}".format(namespace, category),
            key=lambda app_id: app_id,
        )
        for rank, app_id in enumerate(sorted(chosen)):
            assignments.append(
                SampleAssignment(
                    app_id=app_id,
                    category_id=category,
                    group=group,
                    stratum_rank=rank,
                )
            )

    assignments.sort(key=lambda item: item.app_id)
    frozen = freeze_values(
        [researched[item.app_id] for item in assignments]
    )

    return SampleSelection(
        metadata=ArtifactMetadata(
            stage=C.PipelineStage.SAMPLE_SELECTION,
            generated_at=settings.as_of,
            seed=settings.seed,
            record_count=len(assignments),
            source_fingerprint=fingerprint(
                [item.to_jsonable() for item in assignments]
            ),
            notes="Sample {} stratified across {} categories.".format(
                group.value, len(quotas)
            ),
        ),
        group=group,
        master_seed=settings.seed,
        seed_namespace=namespace,
        derived_seed=derive_seed(settings.seed, namespace),
        population_size=population,
        excluded=dict(sorted(exclusions.items())),
        assignments=assignments,
        frozen_values=frozen,
    )


def freeze_values(records: Sequence[AppResearchRecord]) -> List[FrozenFieldValue]:
    """Capture the verified fields exactly as they stand, before any correction.

    This is what makes first-pass accuracy honest: the numbers Sample A is
    scored on are written down before the improvement phase can touch them.
    """
    frozen: List[FrozenFieldValue] = []
    for record in records:
        for name in VERIFIED_FIELDS:
            field = record.field(name)
            frozen.append(
                FrozenFieldValue(
                    app_id=record.app_id,
                    field=name,
                    status=field.status,
                    value=to_value_key(field.key()),
                    classifier_version=record.classifier_version,
                    confidence=record.confidence,
                )
            )
    frozen.sort(key=lambda item: (item.app_id, item.field.value))
    return frozen


def select_both(
    registry: NormalizedRegistry, research: ResearchSet, settings: Settings
) -> Tuple[SampleSelection, SampleSelection]:
    """Draw Sample A, then Sample B from what is left. Disjoint by construction."""
    sample_a = select(registry, research, settings, group=C.SampleGroup.A)
    sample_b = select(
        registry,
        research,
        settings,
        group=C.SampleGroup.B,
        exclude=sample_a.app_ids(),
    )
    overlap = set(sample_a.app_ids()) & set(sample_b.app_ids())
    if overlap:
        raise SamplingError(
            "Samples must be disjoint", overlap=sorted(overlap)
        )
    return sample_a, sample_b

"""The improvement phase. Architecture section 4.6.

Sample A is not a score, it is a diagnosis. Each failure it exposes is traced to
the rule that produced it, the rule is changed once for every app, and the
changed rule set is then measured on Sample B, which it has never seen.

The improvements themselves live next to the rules they describe, in
:data:`composio_ops.research.rules.IMPROVEMENTS`, so the write-up cannot drift
away from the code. This module counts how often each one actually fired in
Sample A, which is what turns a list of intentions into a report.
"""

from typing import Dict, List, Sequence

from .. import constants as C
from ..config import Settings
from ..determinism import fingerprint
from ..research.rules import IMPROVEMENTS
from ..schemas.base import ArtifactMetadata
from ..schemas.review import Improvement, ImprovementReport
from ..schemas.verification import FieldValue
from ..taxonomy import ResearchFieldName


def count_failures(
    measured: Dict[str, Dict[ResearchFieldName, FieldValue]],
    truth: Dict[str, Dict[ResearchFieldName, FieldValue]],
) -> Dict[ResearchFieldName, int]:
    """How many sampled apps got each field wrong."""
    failures: Dict[ResearchFieldName, int] = {}
    for app_id, fields in measured.items():
        expected = truth.get(app_id, {})
        for field, value in fields.items():
            target = expected.get(field)
            if target is None:
                continue
            if not value.matches(target):
                failures[field] = failures.get(field, 0) + 1
    return failures


def build_report(
    failures: Dict[ResearchFieldName, int],
    settings: Settings,
    from_classifier: str = C.CLASSIFIER_V1,
    to_classifier: str = C.CLASSIFIER_V2,
) -> ImprovementReport:
    """Pair each rule change with the number of Sample A failures it answers."""
    improvements: List[Improvement] = []
    for entry in IMPROVEMENTS:
        fields: Sequence[ResearchFieldName] = entry["fields"]  # type: ignore[assignment]
        observed = sum(failures.get(field, 0) for field in fields)
        improvements.append(
            Improvement(
                key=str(entry["key"]),
                failure_mode=str(entry["failure_mode"]),
                fields=sorted(fields, key=lambda item: item.value),
                observed_in_sample_a=observed,
                change=str(entry["change"]),
                implemented_in=to_classifier,
            )
        )

    improvements.sort(key=lambda item: item.key)
    return ImprovementReport(
        metadata=ArtifactMetadata(
            stage=C.PipelineStage.RECONCILIATION,
            generated_at=settings.as_of,
            seed=settings.seed,
            record_count=len(improvements),
            source_fingerprint=fingerprint(
                [item.to_jsonable() for item in improvements]
            ),
            notes="Diagnosed from Sample A; measured on Sample B.",
        ),
        from_classifier=from_classifier,
        to_classifier=to_classifier,
        improvements=improvements,
    )

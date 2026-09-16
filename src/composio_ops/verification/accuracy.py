"""The accuracy protocol. Architecture section 10.

The metric is fixed before the numbers are known, and it is deliberately
unforgiving:

* **Field-level accuracy** over the eleven verified fields, which is the
  headline. A field counts as correct only if both its status and its value
  match the reconciled truth, so "unclear" scored against "resolved" is a miss
  even when the reasoning was defensible.
* **Row-level accuracy**, where an app counts only if every one of its verified
  fields is right. It is always much lower than field-level accuracy, and saying
  both is the honest way to report it.
* **Evidence validity**, the share of citations that survive the audit.

Sample A is scored against the values frozen before the improvement phase, so
improving the classifier cannot retroactively improve the first-pass number.
"""

from typing import Dict, List, Optional, Sequence

from .. import constants as C
from ..config import Settings
from ..determinism import fingerprint
from ..schemas.base import ArtifactMetadata
from ..schemas.research import AppResearchRecord
from ..schemas.verification import (
    AccuracyReport,
    FieldAccuracy,
    FieldValue,
    SampleAccuracy,
    SampleSelection,
    VerificationResult,
)
from ..taxonomy import VERIFIED_FIELDS, ResearchFieldName
from .channels import current_value

F = ResearchFieldName

#: What Sample A and Sample B each measure.
MEASUREMENT_FIRST_PASS = "first_pass"
MEASUREMENT_FINAL = "final"


def measure_sample(
    group: C.SampleGroup,
    measurement: str,
    classifier_version: str,
    measured: Dict[str, Dict[F, FieldValue]],
    truth: Dict[str, Dict[F, FieldValue]],
    verification: Dict[str, List[VerificationResult]],
    trigger_reviewed: Sequence[str] = (),
) -> SampleAccuracy:
    """Score one sample's values against the reconciled truth."""
    per_field: Dict[F, List[int]] = {field: [0, 0] for field in VERIFIED_FIELDS}
    rows_checked = 0
    rows_correct = 0
    claims_checked = 0
    claims_valid = 0

    for app_id in sorted(measured):
        app_truth = truth.get(app_id)
        if not app_truth:
            continue
        rows_checked += 1
        row_ok = True
        for field in VERIFIED_FIELDS:
            expected = app_truth.get(field)
            actual = measured[app_id].get(field)
            if expected is None or actual is None:
                continue
            per_field[field][0] += 1
            if actual.matches(expected):
                per_field[field][1] += 1
            else:
                row_ok = False
        if row_ok:
            rows_correct += 1

        for result in verification.get(app_id, []):
            for check in result.evidence_results:
                claims_checked += 1
                if check.is_valid:
                    claims_valid += 1

    fields_checked = sum(counts[0] for counts in per_field.values())
    fields_correct = sum(counts[1] for counts in per_field.values())

    return SampleAccuracy(
        group=group,
        measurement=measurement,
        classifier_version=classifier_version,
        apps=len(measured),
        fields_checked=fields_checked,
        fields_correct=fields_correct,
        rows_checked=rows_checked,
        rows_correct=rows_correct,
        claims_checked=claims_checked,
        claims_with_valid_evidence=claims_valid,
        per_field=[
            FieldAccuracy(field=field, checked=counts[0], correct=counts[1])
            for field, counts in sorted(
                per_field.items(), key=lambda pair: pair[0].value
            )
        ],
        trigger_reviewed_apps=sorted(set(trigger_reviewed)),
    )


def frozen_values(selection: SampleSelection) -> Dict[str, Dict[F, FieldValue]]:
    """The values as they stood at selection time, for the first-pass measurement."""
    values: Dict[str, Dict[F, FieldValue]] = {}
    for item in selection.frozen_values:
        values.setdefault(item.app_id, {})[item.field] = item.as_field_value()
    return values


def current_values(
    records: Sequence[AppResearchRecord],
) -> Dict[str, Dict[F, FieldValue]]:
    """The values as the classifier records them now."""
    return {
        record.app_id: {field: current_value(record, field) for field in VERIFIED_FIELDS}
        for record in records
    }


def build_report(
    samples: Sequence[SampleAccuracy], settings: Settings, notes: str = ""
) -> AccuracyReport:
    """Assemble the accuracy artifact, naming the headline metric explicitly."""
    ordered = sorted(samples, key=lambda item: item.group.value)
    return AccuracyReport(
        metadata=ArtifactMetadata(
            stage=C.PipelineStage.ACCURACY,
            generated_at=settings.as_of,
            seed=settings.seed,
            record_count=len(ordered),
            source_fingerprint=fingerprint([item.to_jsonable() for item in ordered]),
            notes=notes,
        ),
        headline_metric="sample_b_field_level_accuracy",
        verified_fields=list(VERIFIED_FIELDS),
        samples=ordered,
    )


def improvement_fields(
    first_pass: SampleAccuracy, final: Optional[SampleAccuracy]
) -> List[F]:
    """Fields whose accuracy improved between the two samples."""
    if final is None:
        return []
    before = {item.field: item.accuracy for item in first_pass.per_field}
    improved: List[F] = []
    for item in final.per_field:
        earlier = before.get(item.field)
        if earlier is None or item.accuracy is None:
            continue
        if item.accuracy > earlier:
            improved.append(item.field)
    return sorted(improved, key=lambda item: item.value)

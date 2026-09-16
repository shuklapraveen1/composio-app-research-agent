"""The confidence function. Architecture section 7.

Confidence is computed, never declared. A model can be fluent and wrong, so
asking it "how confident are you?" measures fluency; this function instead
measures properties of the evidence that were recorded before any judgement was
made: whether the product was identified, whether the vendor's own
documentation was cited, whether the critical fields carry evidence, and
whether anything contradicts anything else.

The rules are total and ordered, so every record lands in exactly one level and
the same inputs always produce the same answer.
"""

from typing import List, Tuple

from .. import constants as C
from ..schemas.research import ConfidenceInputs

#: Minimum distinct sources for the top level. Two sources agreeing is a
#: coincidence; three is a pattern.
HIGH_SOURCE_MINIMUM = 3

#: Below this, the record is treated as thinly sourced regardless of anything else.
LOW_SOURCE_MAXIMUM = 1


def calculate(inputs: ConfidenceInputs) -> C.Confidence:
    """Map recorded evidence properties onto a confidence level."""
    level, _ = explain(inputs)
    return level


def explain(inputs: ConfidenceInputs) -> Tuple[C.Confidence, List[str]]:
    """Return the level together with the reasons that produced it.

    The reasons are rendered into the case study, so a reader can check the
    confidence rather than take it on trust.
    """
    demotions: List[str] = []

    if not inputs.identity_resolved:
        demotions.append("the product could not be identified unambiguously")
    if inputs.has_unresolved_ambiguity:
        demotions.append("the supplied name did not resolve to a single product")
    if not inputs.has_critical_field_evidence:
        demotions.append("at least one critical field carries no evidence")
    if inputs.source_count <= LOW_SOURCE_MAXIMUM:
        demotions.append(
            "only {} source(s) were recorded".format(inputs.source_count)
        )
    if demotions:
        return C.Confidence.LOW, demotions

    caps: List[str] = []
    if inputs.has_contradiction:
        caps.append("sources contradict each other")
    if not inputs.has_first_party_source:
        caps.append("no first-party documentation was cited")
    if inputs.source_count < HIGH_SOURCE_MINIMUM:
        caps.append(
            "fewer than {} distinct sources were recorded".format(HIGH_SOURCE_MINIMUM)
        )
    if not inputs.has_current_source:
        caps.append("no source could be confirmed current")
    if not inputs.has_explicit_documentation:
        caps.append("the interface is not explicitly documented by the vendor")
    if caps:
        return C.Confidence.MEDIUM, caps

    return C.Confidence.HIGH, [
        "identity resolved, first-party documentation cited for every critical "
        "field, {} sources, no contradictions".format(inputs.source_count)
    ]

"""Classification, confidence, and the buildability decision tree.

The classifier is the component most able to be confidently wrong, so these
tests pin the rules that decide what a value means, and the two places where
v1 and v2 deliberately differ.
"""

from datetime import datetime, timezone

import pytest

from composio_ops import constants as C
from composio_ops.research import buildability as bd
from composio_ops.research import confidence as conf
from composio_ops.research.evidence import EvidenceIndex, build_evidence, evidence_id_for
from composio_ops.research.rules import classify
from composio_ops.schemas.research import ConfidenceInputs
from composio_ops.taxonomy import (
    AccessRestriction,
    ApiBreadth,
    Blocker,
    Buildability,
    CredentialAccess,
    Dimension,
    McpStatus,
    ResearchFieldName,
    ResolutionStatus,
    WebhookSupport,
)

from factories import app_record, corpus_entry

F = ResearchFieldName
WHEN = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def classify_entry(entry, version=C.CLASSIFIER_V1):
    index = EvidenceIndex(build_evidence(entry, captured_at=WHEN))
    return classify(
        entry=entry,
        app=app_record(app_id=entry.app_id),
        index=index,
        version=version,
        provider=C.ResearchProvider.CORPUS,
        generated_at=WHEN,
    )


def test_every_resolved_field_cites_evidence_that_exists():
    entry = corpus_entry()
    index = EvidenceIndex(build_evidence(entry, captured_at=WHEN))
    known = {item.evidence_id for item in index.items}
    record = classify_entry(entry)
    for _, field in record.fields():
        if field.status is ResolutionStatus.RESOLVED:
            assert field.evidence_ids
            assert set(field.evidence_ids) <= known


def test_evidence_ids_are_derived_not_generated():
    entry = corpus_entry()
    items = build_evidence(entry, captured_at=WHEN)
    assert items[0].evidence_id == evidence_id_for(entry.app_id, items[0].evidence_id.split("::")[1])
    again = build_evidence(entry, captured_at=WHEN)
    assert [item.evidence_id for item in items] == [item.evidence_id for item in again]


def test_v1_reads_credential_access_from_the_signup_tier_only():
    entry = corpus_entry(account="free", api_plan="paid")
    assert (
        classify_entry(entry, C.CLASSIFIER_V1).credential_access.value
        is CredentialAccess.SELF_SERVE_FREE
    )


def test_v2_resolves_credential_access_from_the_plan_that_unlocks_the_api():
    entry = corpus_entry(account="free", api_plan="paid")
    assert (
        classify_entry(entry, C.CLASSIFIER_V2).credential_access.value
        is CredentialAccess.SELF_SERVE_PAID
    )


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"partner_only": True}, CredentialAccess.PARTNER_REQUIRED),
        ({"api_plan": "enterprise"}, CredentialAccess.ENTERPRISE),
        ({"account": "contact_sales"}, CredentialAccess.CONTACT_SALES),
        ({"self_hosted": True}, CredentialAccess.SELF_HOSTED_DEPLOYMENT_DEPENDENT),
        ({"approval_required": True}, CredentialAccess.ADMIN_APPROVAL),
        ({"account": "trial", "api_plan": "trial"}, CredentialAccess.SELF_SERVE_TRIAL),
    ],
)
def test_v2_credential_gates_are_ordered(kwargs, expected):
    record = classify_entry(corpus_entry(**kwargs), C.CLASSIFIER_V2)
    assert record.credential_access.value is expected


def test_v1_counts_resource_groups_while_v2_respects_documented_coverage():
    entry = corpus_entry(
        resource_groups=["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k"],
        coverage="slice",
    )
    assert classify_entry(entry, C.CLASSIFIER_V1).api_breadth.value is ApiBreadth.VERY_BROAD
    assert classify_entry(entry, C.CLASSIFIER_V2).api_breadth.value is ApiBreadth.NARROW


def test_v1_collapses_event_mechanisms_and_v2_does_not():
    entry = corpus_entry(webhooks=WebhookSupport.EVENT_STREAMING)
    assert (
        classify_entry(entry, C.CLASSIFIER_V1).webhook_support.value
        is WebhookSupport.NATIVE_WEBHOOKS
    )
    assert (
        classify_entry(entry, C.CLASSIFIER_V2).webhook_support.value
        is WebhookSupport.EVENT_STREAMING
    )


def test_v2_records_no_blocker_explicitly_where_v1_says_nothing_was_found():
    entry = corpus_entry()
    assert classify_entry(entry, C.CLASSIFIER_V1).blocker.status is ResolutionStatus.NOT_FOUND
    v2 = classify_entry(entry, C.CLASSIFIER_V2)
    assert v2.blocker.values == [Blocker.NONE]


def test_absent_api_is_unavailable_rather_than_missing():
    record = classify_entry(corpus_entry(api_exists=False))
    assert record.api_exists.status is ResolutionStatus.UNAVAILABLE
    assert record.api_exists.evidence_ids
    assert record.api_types.status is ResolutionStatus.NOT_APPLICABLE


def test_unknown_api_is_not_found_rather_than_unavailable():
    record = classify_entry(corpus_entry(api_exists=None))
    assert record.api_exists.status is ResolutionStatus.NOT_FOUND
    assert record.api_exists.evidence_ids == []


def test_mcp_absence_is_evidenced_only_when_a_source_addresses_it():
    with_source = corpus_entry(mcp_status=McpStatus.OFFICIAL)
    assert classify_entry(with_source).mcp.value is McpStatus.OFFICIAL
    without = corpus_entry(mcp_status=None)
    assert classify_entry(without).mcp.status is ResolutionStatus.NOT_FOUND


def test_ambiguous_identity_is_unclear_and_drops_confidence():
    record = classify_entry(corpus_entry(identity_ambiguous=True))
    assert record.identity.status is ResolutionStatus.UNCLEAR
    assert record.confidence is C.Confidence.LOW


def test_conflicts_become_typed_contradictions():
    record = classify_entry(
        corpus_entry(conflicts=["The pricing page and the docs disagree on the paid plan."])
    )
    assert record.contradictions
    assert F.CREDENTIAL_ACCESS in record.contradictions[0].fields
    assert record.confidence is not C.Confidence.HIGH


def test_non_saas_tools_do_not_get_a_buildability_verdict():
    record = classify_entry(corpus_entry(integration_model=False, api_exists=None))
    assert record.buildability.status is ResolutionStatus.NOT_APPLICABLE
    assert Blocker.NON_SAAS_TOOL in record.blocker.values


# --- confidence -------------------------------------------------------------


def _inputs(**overrides) -> ConfidenceInputs:
    base = dict(
        identity_resolved=True,
        has_first_party_source=True,
        has_critical_field_evidence=True,
        has_contradiction=False,
        source_count=4,
        has_page_level_evidence=False,
        has_current_source=True,
        has_explicit_documentation=True,
        has_unresolved_ambiguity=False,
    )
    base.update(overrides)
    return ConfidenceInputs(**base)


def test_confidence_is_high_only_when_every_signal_holds():
    assert conf.calculate(_inputs()) is C.Confidence.HIGH


@pytest.mark.parametrize(
    "overrides",
    [
        {"identity_resolved": False},
        {"has_critical_field_evidence": False},
        {"source_count": 1},
        {"has_unresolved_ambiguity": True},
    ],
)
def test_confidence_falls_to_low_on_any_disqualifier(overrides):
    assert conf.calculate(_inputs(**overrides)) is C.Confidence.LOW


@pytest.mark.parametrize(
    "overrides",
    [
        {"has_contradiction": True},
        {"has_first_party_source": False},
        {"source_count": 2},
        {"has_current_source": False},
        {"has_explicit_documentation": False},
    ],
)
def test_contradictions_and_thin_sourcing_cap_confidence_at_medium(overrides):
    assert conf.calculate(_inputs(**overrides)) is C.Confidence.MEDIUM


def test_confidence_explains_itself():
    level, reasons = conf.explain(_inputs(has_contradiction=True))
    assert level is C.Confidence.MEDIUM
    assert any("contradict" in reason for reason in reasons)


# --- buildability -----------------------------------------------------------


@pytest.mark.parametrize(
    "legs,expected_status,expected_value",
    [
        (
            (Dimension.PASS, Dimension.PASS, Dimension.PASS),
            ResolutionStatus.RESOLVED,
            Buildability.BUILDABLE,
        ),
        (
            (Dimension.PASS, Dimension.FRICTION, Dimension.PASS),
            ResolutionStatus.RESOLVED,
            Buildability.BUILDABLE_WITH_FRICTION,
        ),
        (
            (Dimension.PASS, Dimension.FAIL, Dimension.UNCLEAR),
            ResolutionStatus.RESOLVED,
            Buildability.BLOCKED,
        ),
        (
            (Dimension.PASS, Dimension.UNCLEAR, Dimension.PASS),
            ResolutionStatus.UNCLEAR,
            None,
        ),
        (
            (Dimension.NOT_APPLICABLE, Dimension.PASS, Dimension.PASS),
            ResolutionStatus.NOT_APPLICABLE,
            None,
        ),
    ],
)
def test_decision_tree_takes_the_worst_leg(legs, expected_status, expected_value):
    status, value = bd.combine(*legs)
    assert status is expected_status
    assert value is expected_value


def test_a_capable_api_does_not_rescue_unobtainable_credentials():
    record = classify_entry(corpus_entry(partner_only=True), C.CLASSIFIER_V2)
    assert record.api_exists.is_resolved
    assert record.buildability.value is Buildability.BLOCKED
    assert Blocker.PARTNER_REQUIRED in record.blocker.values


def test_commercial_leg_fails_on_blocking_restrictions():
    dimension, _ = bd.commercial_accessibility(
        ResolutionStatus.RESOLVED, [AccessRestriction.ENTERPRISE_PLAN_REQUIRED]
    )
    assert dimension is Dimension.FAIL

"""Schema invariants.

These tests exist because the schema is the pipeline's contract: if a record can
be built that asserts a finding without evidence, or silently keeps an unknown
field, then every guarantee downstream is decoration.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from composio_ops import constants as C
from composio_ops.schemas.evidence import EvidenceItem, domain_of
from composio_ops.schemas.research import (
    AppIdentity,
    MultiResearchField,
    ResearchField,
)
from composio_ops.schemas.verification import FieldValue, to_value_key
from composio_ops.taxonomy import (
    AuthMethod,
    Buildability,
    ResearchFieldName,
    ResolutionStatus,
    SourceType,
)

from factories import evidence_item

F = ResearchFieldName
WHEN = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def test_records_are_immutable_and_reject_unknown_fields():
    item = evidence_item("example-app-001", "ev-1", WHEN)
    with pytest.raises(ValidationError):
        item.claim = "something else"
    with pytest.raises(ValidationError):
        EvidenceItem(**{**item.model_dump(), "surprise": True})


def test_resolved_field_requires_evidence():
    with pytest.raises(ValidationError):
        ResearchField[Buildability](
            status=ResolutionStatus.RESOLVED,
            value=Buildability.BUILDABLE,
            evidence_ids=[],
        )


def test_unresolved_field_requires_a_rationale():
    with pytest.raises(ValidationError):
        ResearchField[Buildability](status=ResolutionStatus.UNCLEAR, value=None)
    field = ResearchField[Buildability].unclear(rationale="Sources disagree.")
    assert field.rationale
    assert field.value is None


def test_resolved_field_must_carry_a_value():
    with pytest.raises(ValidationError):
        ResearchField[Buildability](
            status=ResolutionStatus.RESOLVED, value=None, evidence_ids=["ev-1"]
        )


def test_multi_valued_field_deduplicates_and_sorts():
    field = MultiResearchField[AuthMethod].resolved(
        values=[AuthMethod.OAUTH2, AuthMethod.API_KEY, AuthMethod.OAUTH2],
        evidence_ids=["ev-1"],
    )
    assert field.values == [AuthMethod.API_KEY, AuthMethod.OAUTH2]
    assert field.key() == ("api_key", "oauth2")


def test_unavailable_is_a_finding_and_carries_evidence():
    field = ResearchField[bool].unavailable(
        evidence_ids=["ev-1"], rationale="The vendor documents no public API."
    )
    assert field.is_known
    assert not field.is_resolved
    assert field.evidence_ids == ["ev-1"]


def test_not_found_is_not_a_finding():
    field = ResearchField[bool].not_found("No source addressed this.")
    assert not field.is_known
    assert field.evidence_ids == []


def test_evidence_domain_must_match_its_url():
    with pytest.raises(ValidationError):
        EvidenceItem(
            evidence_id="ev-1",
            app_id="example-app-001",
            url="https://example001.test/docs",
            title="Example docs",
            domain="somewhere-else.test",
            source_type=SourceType.FIRST_PARTY_DOCS,
            claim="A claim.",
            retrieval=C.EvidenceRetrieval.CITED,
            supports=[F.API_EXISTS],
            channel=C.Channel.CHANNEL_A,
            captured_at=WHEN,
        )


def test_fetched_evidence_must_carry_an_excerpt():
    with pytest.raises(ValidationError):
        EvidenceItem(
            evidence_id="ev-1",
            app_id="example-app-001",
            url="https://example001.test/docs",
            title="Example docs",
            domain="example001.test",
            source_type=SourceType.FIRST_PARTY_DOCS,
            claim="A claim.",
            retrieval=C.EvidenceRetrieval.FETCHED,
            supports=[F.API_EXISTS],
            channel=C.Channel.CHANNEL_A,
            captured_at=WHEN,
        )


def test_evidence_must_support_at_least_one_field():
    with pytest.raises(ValidationError):
        evidence_item("example-app-001", "ev-1", WHEN, supports=[])


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.Example.test/docs", "example.test"),
        ("https://developers.example.test/api", "developers.example.test"),
        ("https://example.test", "example.test"),
    ],
)
def test_domain_extraction(url, expected):
    assert domain_of(url) == expected


def test_field_values_compare_as_sets():
    first = FieldValue(
        field=F.AUTHENTICATION,
        status=ResolutionStatus.RESOLVED,
        value=["api_key", "oauth2"],
    )
    second = FieldValue(
        field=F.AUTHENTICATION,
        status=ResolutionStatus.RESOLVED,
        value=["oauth2", "api_key"],
    )
    assert first.matches(second)


def test_value_keys_round_trip_through_strings():
    field = ResearchField[AppIdentity].resolved(
        value=AppIdentity(canonical_name="Example App 001"),
        evidence_ids=["ev-1"],
    )
    assert to_value_key(field.key()) == ["Example App 001"]

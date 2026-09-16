"""Integrity of the committed research corpus and ground truth.

The corpus is input data, not code, so nothing else in the test suite would
notice if an entry lost its sources, cited a page over plain HTTP, or recorded
an observation that no source backs. These tests are that notice.
"""

from pathlib import Path

import pytest

from composio_ops.config import load_settings
from composio_ops.io_utils import read_json
from composio_ops.research import load_corpus
from composio_ops.schemas.registry import NormalizedRegistry
from composio_ops.taxonomy import VERIFIED_FIELDS, ResearchFieldName, ResolutionStatus

F = ResearchFieldName
PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: Every entry needs enough independent sources to reach high confidence.
MINIMUM_SOURCES = 3


@pytest.fixture(scope="module")
def book():
    settings = load_settings(_env_file=None, project_root=PROJECT_ROOT)
    return settings, load_corpus(
        corpus_apps_dir=settings.paths.corpus_apps_dir,
        as_of=settings.as_of,
        seed=settings.seed,
    )


def test_the_corpus_covers_the_registry_exactly(book):
    settings, corpus = book
    registry = NormalizedRegistry.model_validate(
        read_json(settings.paths.registry_normalized)
    )
    assert sorted(entry.app_id for entry in corpus.entries) == sorted(registry.app_ids())


def test_every_entry_carries_several_sources(book):
    _, corpus = book
    thin = [
        entry.app_id for entry in corpus.entries if len(entry.sources) < MINIMUM_SOURCES
    ]
    assert thin == []


def test_every_source_is_https_with_a_claim(book):
    _, corpus = book
    for entry in corpus.entries:
        for source in entry.sources:
            assert source.url.startswith("https://"), (entry.app_id, source.id)
            assert source.claim.strip(), (entry.app_id, source.id)
            assert source.supports, (entry.app_id, source.id)


def test_source_ids_are_unique_within_an_entry(book):
    _, corpus = book
    for entry in corpus.entries:
        ids = [source.id for source in entry.sources]
        assert len(ids) == len(set(ids)), entry.app_id


@pytest.mark.parametrize(
    "field,has_observation",
    [
        (F.WEBHOOK_SUPPORT, lambda entry: entry.webhooks is not None),
        (F.RATE_LIMIT_INFO, lambda entry: entry.rate_limits is not None),
        (F.MCP, lambda entry: entry.mcp.status is not None),
        (F.AUTHENTICATION, lambda entry: bool(entry.auth_methods)),
        (F.CREDENTIAL_ACCESS, lambda entry: True),
        (F.API_EXISTS, lambda entry: True),
    ],
)
def test_recorded_observations_are_backed_by_a_source(book, field, has_observation):
    """An observation nobody can cite is a guess wearing a fact's clothes."""
    _, corpus = book
    unbacked = [
        entry.app_id
        for entry in corpus.entries
        if has_observation(entry) and not entry.sources_for(field)
    ]
    assert unbacked == []


def test_official_mcp_servers_are_recorded_as_official(book):
    _, corpus = book
    for entry in corpus.entries:
        if entry.mcp.official:
            assert entry.mcp.status is not None, entry.app_id
            assert entry.mcp.source_url, entry.app_id


def test_ground_truth_entries_are_well_formed_and_point_at_real_evidence(book):
    settings, corpus = book
    payload = read_json(settings.paths.ground_truth)
    entries = {entry.app_id: entry for entry in corpus.entries}
    assert payload["reviewer"]
    assert payload["overrides"]

    seen = set()
    for override in payload["overrides"]:
        key = (override["app_id"], override["field"])
        assert key not in seen, key
        seen.add(key)

        entry = entries[override["app_id"]]
        field = F(override["field"])
        assert field in VERIFIED_FIELDS
        status = ResolutionStatus(override["status"])
        if status is ResolutionStatus.RESOLVED:
            assert override["value"], key
        else:
            assert override["value"] is None, key
        assert override["reason"].strip(), key

        known = {"{}::{}".format(entry.app_id, source.id) for source in entry.sources}
        assert set(override["evidence_ids"]) <= known, key
        assert override["evidence_ids"], key

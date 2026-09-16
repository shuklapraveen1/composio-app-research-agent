"""The published page against the artifacts it claims to render.

The presentation layer is the one place where a number could be retyped, a
percentage rounded into something friendlier, or an application quietly dropped
from a table. These tests read the page and the projection it embeds and check
them against the artifacts, so the site cannot say anything the dataset does not.
"""

import json
import re

import pytest

from composio_ops import constants as C
from composio_ops.publish import viewmodel
from composio_ops.publish.case_study import publish, render
from composio_ops.taxonomy import VERIFIED_FIELDS, ResearchFieldName

F = ResearchFieldName


@pytest.fixture(scope="module")
def published(pipeline_run):
    """Run the pipeline once, then publish, and return everything to compare."""
    settings, result = pipeline_run
    publish(
        dataset=result.final_dataset,
        analytics=result.analytics,
        patterns=result.patterns,
        accuracy=result.accuracy,
        improvements=result.improvements,
        validation=result.validation,
        queue=result.review_queue,
        settings=settings,
    )
    payload = json.loads(
        _payload_json(settings.paths.site_payload.read_text(encoding="utf-8"))
    )
    return settings, result, settings.paths.case_study.read_text(encoding="utf-8"), payload


def _payload_json(script: str) -> str:
    """The JSON out of ``window.NAME = {...};``."""
    prefix = "window.{} = ".format(C.SITE_PAYLOAD_GLOBAL)
    assert script.startswith(prefix)
    return script[len(prefix) :].rstrip().rstrip(";")


# --- the page is a complete, self-contained document -------------------------


def test_the_page_and_its_assets_are_all_written(published):
    settings, _, html, _ = published
    paths = settings.paths
    for path in (paths.case_study, paths.site_styles, paths.site_script, paths.site_payload):
        assert path.exists(), path
        assert path.read_text(encoding="utf-8").strip()
    assert html.startswith("<!DOCTYPE html>")
    assert html.rstrip().endswith("</html>")


def test_the_page_references_only_its_own_assets(published):
    """No CDN, no font service, no analytics beacon: the site works offline."""
    _, _, html, _ = published
    sources = re.findall(r'(?:src|href)="([^"]+)"', html)
    external = [
        src
        for src in sources
        if src.startswith(("http://", "https://", "//"))
    ]
    assert external == []


def test_the_assets_are_versioned_with_the_dataset_fingerprint(published):
    _, result, html, _ = published
    fingerprint = result.final_dataset.metadata.source_fingerprint
    for filename in (
        C.SITE_STYLES_FILENAME,
        C.SITE_SCRIPT_FILENAME,
        C.SITE_PAYLOAD_FILENAME,
    ):
        assert '{}?v={}'.format(filename, fingerprint) in html


def test_the_download_links_point_at_files_that_exist(published):
    settings, _, html, _ = published
    links = set(re.findall(r'href="data/([^"?]+)"', html))
    assert links
    for name in links:
        assert (settings.paths.site_data_dir / name).exists(), name


def test_the_static_table_still_carries_every_application(published):
    """With scripting off the page is still the whole dataset, not a teaser."""
    _, result, html, _ = published
    static = html.split('class="no-js-only"', 1)[1]
    for record in result.final_dataset.records:
        assert record.app.name in static


# --- the numbers on the page come from the artifacts -------------------------


def test_the_headline_accuracy_is_the_measured_one(published):
    _, result, html, payload = published
    headline = "{:.1f}%".format(result.accuracy.headline_value * 100)
    assert headline in html
    assert payload["accuracy"]["headline"] == result.accuracy.headline_value
    assert payload["accuracy"]["headline_metric"] == result.accuracy.headline_metric


def test_both_samples_are_reported_with_their_own_classifier(published):
    _, result, html, _ = published
    for sample in result.accuracy.samples:
        assert "{:.1f}%".format(sample.field_level_accuracy * 100) in html
        assert "{:.1f}%".format(sample.row_level_accuracy * 100) in html
    assert "Sample A" in html and "Sample B" in html


def test_per_field_accuracy_reports_declines_as_well_as_gains(published):
    """A field that got worse has to show up as worse, not be quietly dropped."""
    _, result, html, payload = published
    rows = payload["accuracy"]["per_field"]
    assert len(rows) == len(VERIFIED_FIELDS)

    sample_a = result.accuracy.sample(C.SampleGroup.A)
    sample_b = result.accuracy.sample(C.SampleGroup.B)
    truth_a = {item.field.value: item.accuracy for item in sample_a.per_field}
    truth_b = {item.field.value: item.accuracy for item in sample_b.per_field}
    for row in rows:
        assert row["a"] == truth_a[row["field"]]
        assert row["b"] == truth_b[row["field"]]

    declines = [row for row in rows if row["a"] is not None and row["b"] < row["a"]]
    for row in declines:
        assert "{:.1f}%".format(row["b"] * 100) in html


def test_the_headline_metrics_match_the_analytics_artifact(published):
    _, result, _, payload = published
    for metric in result.analytics.metrics:
        assert payload["meta"]["metrics"][metric.key] == metric.value


def test_the_distributions_match_the_analytics_artifact(published):
    _, result, _, payload = published
    published_by_attribute = {
        item["attribute"]: item for item in payload["distributions"]
    }
    for item in result.analytics.distributions:
        mirrored = published_by_attribute[item.attribute]
        assert mirrored["counts"] == item.counts
        assert mirrored["unresolved"] == item.unresolved
        assert mirrored["total"] == item.total


def test_the_findings_carry_the_applications_the_pattern_artifact_names(published):
    """Clicking a finding must land on exactly the apps the artifact counted."""
    _, result, _, payload = published
    published_by_key = {item["key"]: item for item in payload["findings"]}
    assert len(published_by_key) == len(result.patterns.patterns)
    for pattern in result.patterns.patterns:
        mirrored = published_by_key[pattern.key]
        assert mirrored["app_ids"] == list(pattern.supporting_app_ids)
        assert mirrored["observed"] == pattern.observed == len(mirrored["app_ids"])
        assert mirrored["statement"] == pattern.statement


def test_the_improvement_counts_are_the_observed_ones(published):
    _, result, _, payload = published
    published_by_key = {item["key"]: item for item in payload["improvements"]}
    for improvement in result.improvements.improvements:
        assert (
            published_by_key[improvement.key]["observed"]
            == improvement.observed_in_sample_a
        )


def test_the_run_facts_are_this_run(published):
    settings, result, html, payload = published
    assert payload["meta"]["seed"] == settings.seed
    assert payload["meta"]["schema"] == C.SCHEMA_VERSION
    assert payload["meta"]["fingerprint"] == result.final_dataset.metadata.source_fingerprint
    assert payload["meta"]["classifier"] == result.final_dataset.classifier_version
    assert str(settings.seed) in html
    assert result.final_dataset.metadata.source_fingerprint in html


def test_the_validation_counts_match_the_written_report(published):
    """The page must quote the report on disk, not an earlier pass of it."""
    settings, result, html, payload = published
    written = json.loads(settings.paths.validation_report.read_text(encoding="utf-8"))
    warnings = sum(1 for issue in written["issues"] if issue["severity"] == "warning")
    assert len(result.validation.warnings) == warnings
    assert payload["meta"]["validation"]["warnings"] == warnings
    assert "blocking errors and {}".format(warnings) in re.sub(r"\s+", " ", html)


# --- the explorer is the dataset, not a copy of it ---------------------------


def test_every_application_reaches_the_explorer_exactly_once(published):
    _, result, _, payload = published
    ids = [app["id"] for app in payload["apps"]]
    assert ids == sorted(ids)
    assert ids == [record.app_id for record in result.final_dataset.records]


def test_explorer_values_are_the_reconciled_values(published):
    from composio_ops.dataset import final_value

    _, result, _, payload = published
    published_by_id = {app["id"]: app for app in payload["apps"]}
    for record in result.final_dataset.records:
        app = published_by_id[record.app_id]
        for field in (F.BUILDABILITY, F.CREDENTIAL_ACCESS, F.MCP):
            value = final_value(record, field)
            expected = (
                value.value[0] if value.value else value.status.value
            )
            assert app[field.value] == expected, (record.app_id, field)
        assert app["confidence"] == record.research.confidence.value
        assert app["evidence_count"] == len(record.evidence)
        assert app["sample"] == (
            record.sample_group.value if record.sample_group else None
        )


def test_field_entries_line_up_with_the_shared_schema(published):
    _, _, _, payload = published
    schema = payload["field_schema"]
    assert [item["field"] for item in schema] == [
        field.value for field in viewmodel.DETAIL_FIELDS
    ]
    for app in payload["apps"]:
        assert len(app["fields"]) == len(schema)


def test_evidence_is_carried_verbatim_and_never_invented(published):
    _, result, _, payload = published
    published_by_id = {app["id"]: app for app in payload["apps"]}
    for record in result.final_dataset.records:
        published_evidence = {
            item["id"]: item for item in published_by_id[record.app_id]["evidence"]
        }
        assert len(published_evidence) == len(record.evidence)
        for item in record.evidence:
            mirrored = published_evidence[item.evidence_id]
            assert mirrored["url"] == item.url
            assert mirrored["title"] == item.title
            assert mirrored["claim"] == item.claim
            assert mirrored["retrieval"] == item.retrieval.value


def test_facet_counts_agree_with_the_rows_they_filter(published):
    _, _, _, payload = published
    apps = payload["apps"]
    for key in ("buildability", "credential_access", "mcp", "confidence"):
        for option in payload["facets"][key]:
            actual = sum(1 for app in apps if app.get(key) == option["value"])
            assert option["count"] == actual, (key, option["value"])


def test_the_projection_serialises_without_closing_the_script_element(published):
    settings, _, _, _ = published
    script = settings.paths.site_payload.read_text(encoding="utf-8")
    assert "</script" not in script.lower()
    assert "<" not in script.split("=", 1)[1]


# --- determinism -------------------------------------------------------------


def test_rendering_twice_produces_the_same_page(published):
    settings, result, html, _ = published
    again = render(
        dataset=result.final_dataset,
        analytics=result.analytics,
        patterns=result.patterns,
        accuracy=result.accuracy,
        improvements=result.improvements,
        validation=result.validation,
        queue=result.review_queue,
        settings=settings,
    )
    assert again == html

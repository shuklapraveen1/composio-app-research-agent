"""Registry ingestion: ids, counts, categories, and duplicates."""

import json

import pytest

from composio_ops.errors import RegistryError
from composio_ops.registry import (
    find_duplicates,
    generate_category_ids,
    generate_ids,
    load_raw,
    load_registry,
    normalize_name,
    resolve_columns,
    slugify,
)
from composio_ops.schemas.registry import RawAppRecord

from factories import CATEGORY_NAMES, synthetic_rows, write_csv_source


@pytest.fixture()
def source(tmp_path):
    path = tmp_path / "apps.csv"
    write_csv_source(path, synthetic_rows())
    return path


# --- identifier generation -------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Slack", "slack"),
        ("Google Drive", "google-drive"),
        ("  Trailing  Space  ", "trailing-space"),
        ("Notes & Tasks", "notes-and-tasks"),
        ("Notes and Tasks", "notes-and-tasks"),
        ("Qualtrics XM™", "qualtrics-xm"),
        ("Zoho CRM (Plus)", "zoho-crm-plus"),
        ("e-mail/SMS", "e-mail-sms"),
        ("Café Manager", "cafe-manager"),
        ("A.B.C.", "a-b-c"),
    ],
)
def test_slugify(text, expected):
    assert slugify(text) == expected


def test_slugify_rejects_unusable_text():
    with pytest.raises(ValueError):
        slugify("   ")
    with pytest.raises(ValueError):
        slugify("***")


def test_ids_are_independent_of_row_order():
    names = ["Zulu", "Alpha", "Mike"]
    forward = generate_ids(names)
    backward = generate_ids(list(reversed(names)))
    assert forward[0] == backward[2] == "zulu"
    assert forward[1] == backward[1] == "alpha"


def test_ids_are_stable_across_calls():
    names = ["Alpha", "Bravo"]
    assert generate_ids(names) == generate_ids(names)


def test_distinct_names_that_collide_get_disambiguated():
    ids = generate_ids(["Notes & Tasks", "Notes and Tasks"])
    assert ids[0] != ids[1]
    assert all(value.startswith("notes-and-tasks-") for value in ids.values())


def test_identical_names_keep_the_same_id_for_duplicate_reporting():
    ids = generate_ids(["Slack", "slack"])
    assert ids[0] == ids[1] == "slack"


def test_category_ids_are_stable_and_unique():
    mapping = generate_category_ids(CATEGORY_NAMES)
    assert len(set(mapping.values())) == len(CATEGORY_NAMES)
    assert mapping["Category Alpha"] == "category-alpha"
    assert mapping == generate_category_ids(CATEGORY_NAMES)


def test_normalize_name_folds_case_and_accents():
    assert normalize_name("  Café   Manager ") == normalize_name("cafe manager")


# --- column resolution -----------------------------------------------------


def test_columns_are_detected_from_common_headings():
    mapping = resolve_columns(["Application Name", "Category", "Website"])
    assert mapping.name == "Application Name"
    assert mapping.category == "Category"
    assert mapping.url == "Website"


def test_missing_required_column_is_an_error():
    with pytest.raises(RegistryError):
        resolve_columns(["name", "notes"])


def test_explicit_override_must_exist():
    with pytest.raises(RegistryError):
        resolve_columns(["name", "category"], name_column="absent")


# --- duplicate detection ---------------------------------------------------


def _raw(index, name, category="Category Alpha"):
    return RawAppRecord(source_index=index, name=name, category=category)


def test_identical_names_are_detected():
    groups = find_duplicates([_raw(0, "Slack"), _raw(1, "slack")])
    assert [group.reason for group in groups] == ["identical_name"]
    assert groups[0].source_indexes == [0, 1]


def test_punctuation_only_differences_are_detected():
    groups = find_duplicates([_raw(0, "Notes-Tasks"), _raw(1, "Notes Tasks")])
    assert [group.reason for group in groups] == ["identical_slug"]


def test_shared_homepage_is_detected():
    groups = find_duplicates(
        [_raw(0, "Alpha"), _raw(1, "Bravo")],
        urls={0: "https://www.example.test/", 1: "http://example.test"},
    )
    assert [group.reason for group in groups] == ["identical_homepage_url"]


def test_a_clean_list_has_no_duplicates():
    assert find_duplicates([_raw(0, "Alpha"), _raw(1, "Bravo")]) == []


def test_one_pair_is_reported_once():
    groups = find_duplicates([_raw(0, "Slack"), _raw(1, "Slack")])
    assert len(groups) == 1


# --- loading ---------------------------------------------------------------


def test_loads_exactly_one_hundred_apps_and_ten_categories(source):
    raw, normalized = load_registry(source, seed=1)
    assert len(raw.records) == 100
    assert len(normalized.records) == 100
    assert len(normalized.categories) == 10
    assert sum(category.app_count for category in normalized.categories) == 100


def test_supplied_categories_are_preserved(source):
    _, normalized = load_registry(source, seed=1)
    assert sorted(c.name for c in normalized.categories) == sorted(CATEGORY_NAMES)


def test_records_are_sorted_and_uniquely_identified(source):
    _, normalized = load_registry(source, seed=1)
    ids = normalized.app_ids()
    assert ids == sorted(ids)
    assert len(set(ids)) == 100


def test_loading_is_deterministic(source):
    first = load_registry(source, seed=1)[1]
    second = load_registry(source, seed=1)[1]
    assert first.app_ids() == second.app_ids()
    assert first.category_ids() == second.category_ids()


def test_row_order_does_not_affect_the_result(tmp_path):
    rows = synthetic_rows()
    forward = tmp_path / "forward.csv"
    reverse = tmp_path / "reverse.csv"
    write_csv_source(forward, rows)
    write_csv_source(reverse, list(reversed(rows)))
    assert load_registry(forward, seed=1)[1].app_ids() == (
        load_registry(reverse, seed=1)[1].app_ids()
    )


def test_ninety_nine_apps_is_rejected(tmp_path):
    path = tmp_path / "short.csv"
    write_csv_source(path, synthetic_rows(app_count=99))
    with pytest.raises(RegistryError) as excinfo:
        load_registry(path, seed=1)
    assert "99" in str(excinfo.value)


def test_nine_categories_is_rejected(tmp_path):
    path = tmp_path / "nine.csv"
    write_csv_source(path, synthetic_rows(app_count=100, category_count=9))
    with pytest.raises(RegistryError) as excinfo:
        load_registry(path, seed=1)
    assert "categor" in str(excinfo.value).lower()


def test_duplicates_block_the_load(tmp_path):
    rows = synthetic_rows()
    rows[50]["name"] = rows[10]["name"]
    rows[50]["url"] = rows[10]["url"]
    path = tmp_path / "dupes.csv"
    write_csv_source(path, rows)
    with pytest.raises(RegistryError) as excinfo:
        load_registry(path, seed=1)
    assert "duplicate" in str(excinfo.value).lower()


def test_blank_cells_are_rejected_not_guessed(tmp_path):
    rows = synthetic_rows()
    rows[3]["category"] = ""
    path = tmp_path / "blank.csv"
    write_csv_source(path, rows)
    with pytest.raises(RegistryError) as excinfo:
        load_registry(path, seed=1)
    assert "missing a name or a category" in str(excinfo.value)


def test_missing_file_is_reported(tmp_path):
    with pytest.raises(RegistryError):
        load_registry(tmp_path / "absent.csv", seed=1)


def test_unsupported_format_is_reported(tmp_path):
    path = tmp_path / "apps.xlsx"
    path.write_text("binary-ish", encoding="utf-8")
    with pytest.raises(RegistryError):
        load_registry(path, seed=1)


def test_empty_source_is_reported(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("name,category\n", encoding="utf-8")
    with pytest.raises(RegistryError):
        load_raw(path, seed=1)


def test_json_source_is_supported(tmp_path):
    path = tmp_path / "apps.json"
    path.write_text(json.dumps(synthetic_rows()), encoding="utf-8")
    _, normalized = load_registry(path, seed=1)
    assert len(normalized.records) == 100


def test_json_object_wrapper_is_supported(tmp_path):
    path = tmp_path / "apps.json"
    path.write_text(json.dumps({"apps": synthetic_rows()}), encoding="utf-8")
    assert len(load_registry(path, seed=1)[1].records) == 100


def test_jsonl_source_is_supported(tmp_path):
    path = tmp_path / "apps.jsonl"
    path.write_text(
        "\n".join(json.dumps(row) for row in synthetic_rows()), encoding="utf-8"
    )
    assert len(load_registry(path, seed=1)[1].records) == 100


def test_supplied_ids_are_preserved(tmp_path):
    rows = synthetic_rows()
    for index, row in enumerate(rows):
        row["id"] = "supplied-{:03d}".format(index)
    path = tmp_path / "with-ids.csv"
    write_csv_source(path, rows)
    _, normalized = load_registry(path, seed=1)
    assert normalized.app_ids()[0] == "supplied-000"


def test_partially_supplied_ids_are_rejected(tmp_path):
    rows = synthetic_rows()
    for index, row in enumerate(rows):
        row["id"] = "supplied-{:03d}".format(index) if index % 2 == 0 else ""
    path = tmp_path / "partial-ids.csv"
    write_csv_source(path, rows)
    with pytest.raises(RegistryError):
        load_registry(path, seed=1)


def test_raw_registry_keeps_the_original_columns(source):
    raw, _ = load_registry(source, seed=1)
    assert set(raw.records[0].fields) == {"name", "category", "url"}
    assert raw.records[0].source_index == 0


def test_homepage_urls_are_carried_over(source):
    _, normalized = load_registry(source, seed=1)
    assert all(record.homepage_url.startswith("https://") for record in normalized.records)

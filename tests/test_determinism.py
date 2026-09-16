"""Deterministic seeding, hashing, and sampling."""

import random

import pytest

from composio_ops.determinism import (
    canonical_json,
    derive_seed,
    deterministic_sample,
    fingerprint,
    rng_for,
    stable_hash,
)


def test_canonical_json_is_key_order_independent():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})


def test_stable_hash_is_reproducible_and_distinct():
    assert stable_hash("alpha") == stable_hash("alpha")
    assert stable_hash("alpha") != stable_hash("beta")
    assert len(stable_hash("alpha")) == 64


def test_fingerprint_length_is_bounded():
    assert len(fingerprint({"a": 1})) == 16
    assert len(fingerprint({"a": 1}, length=8)) == 8
    with pytest.raises(ValueError):
        fingerprint({"a": 1}, length=0)


def test_derive_seed_is_stable_and_namespace_separated():
    assert derive_seed(42, "sample:A") == derive_seed(42, "sample:A")
    assert derive_seed(42, "sample:A") != derive_seed(42, "sample:B")
    assert derive_seed(42, "sample:A") != derive_seed(43, "sample:A")


def test_rng_streams_are_independent_per_namespace():
    first = [rng_for(1, "alpha").random() for _ in range(3)]
    again = [rng_for(1, "alpha").random() for _ in range(3)]
    other = [rng_for(1, "beta").random() for _ in range(3)]
    assert first == again
    assert first != other


def test_rng_does_not_disturb_global_random_state():
    random.seed(99)
    expected = random.random()
    random.seed(99)
    rng_for(1, "alpha").random()
    assert random.random() == expected


def test_sample_is_reproducible():
    population = ["app-{:03d}".format(index) for index in range(50)]
    first = deterministic_sample(population, 10, 20260916, "sample:A", key=str)
    second = deterministic_sample(population, 10, 20260916, "sample:A", key=str)
    assert first == second
    assert len(first) == 10
    assert len(set(first)) == 10


def test_sample_is_independent_of_input_order():
    population = ["app-{:03d}".format(index) for index in range(50)]
    shuffled = list(reversed(population))
    assert deterministic_sample(population, 10, 7, "sample:A", key=str) == (
        deterministic_sample(shuffled, 10, 7, "sample:A", key=str)
    )


def test_sample_output_is_sorted():
    population = ["app-{:03d}".format(index) for index in range(50)]
    chosen = deterministic_sample(population, 10, 7, "sample:A", key=str)
    assert chosen == sorted(chosen)


def test_different_namespaces_give_different_samples():
    population = ["app-{:03d}".format(index) for index in range(50)]
    group_a = deterministic_sample(population, 10, 7, "sample:A", key=str)
    group_b = deterministic_sample(population, 10, 7, "sample:B", key=str)
    assert group_a != group_b


def test_oversized_sample_is_rejected():
    with pytest.raises(ValueError):
        deterministic_sample(["a", "b"], 3, 7, "sample:A", key=str)


def test_duplicate_keys_are_rejected():
    with pytest.raises(ValueError):
        deterministic_sample(["a", "a", "b"], 1, 7, "sample:A", key=str)

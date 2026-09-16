"""Deterministic seeding and stable hashing.

Two guarantees the architecture depends on:

* the same master seed and the same inputs always produce the same sample, and
* two stages never share an RNG stream, so adding a stage cannot reshuffle an
  earlier stage's choices.

Both follow from deriving every per-stage seed from ``(master_seed, namespace)``
via a stable hash rather than from Python's global ``random`` state.
"""

import hashlib
import json
import random
from typing import Any, Callable, Iterable, List, Optional, Sequence, TypeVar

T = TypeVar("T")

#: Width of a derived seed. 64 bits is plenty and keeps values printable.
_SEED_BITS = 64
_SEED_MODULUS = 2 ** _SEED_BITS


def canonical_json(value: Any) -> str:
    """Serialize ``value`` so equal data always yields an identical string."""
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def stable_hash(value: Any) -> str:
    """Return a hex SHA-256 digest that is stable across processes and runs.

    Python's built-in ``hash`` is randomized per process, so it must never be
    used for anything persisted or sampled.
    """
    payload = value if isinstance(value, str) else canonical_json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fingerprint(value: Any, length: int = 16) -> str:
    """Short stable digest for embedding in artifact metadata."""
    if length < 1 or length > 64:
        raise ValueError("fingerprint length must be between 1 and 64")
    return stable_hash(value)[:length]


def derive_seed(master_seed: int, namespace: str) -> int:
    """Derive a stage-specific seed from the master seed and a namespace."""
    digest = stable_hash("{}:{}".format(int(master_seed), namespace))
    return int(digest[: _SEED_BITS // 4], 16) % _SEED_MODULUS


def rng_for(master_seed: int, namespace: str) -> random.Random:
    """Return an isolated RNG for ``namespace``.

    Isolated on purpose: callers get their own ``random.Random`` instance and the
    global ``random`` module state is never touched.
    """
    return random.Random(derive_seed(master_seed, namespace))


def deterministic_sample(
    items: Sequence[T],
    size: int,
    master_seed: int,
    namespace: str,
    key: Optional[Callable[[T], str]] = None,
) -> List[T]:
    """Pick ``size`` items reproducibly, independent of input ordering.

    Items are first sorted by a stable key so that an upstream reordering cannot
    change the sample, then drawn with a namespaced RNG. Returned in sorted key
    order rather than draw order, so the output is byte-stable.
    """
    if size < 0:
        raise ValueError("sample size must be non-negative")
    if size > len(items):
        raise ValueError(
            "cannot sample {} items from a population of {}".format(size, len(items))
        )

    key_fn = key if key is not None else (lambda item: stable_hash(item))
    keyed = sorted(((key_fn(item), item) for item in items), key=lambda pair: pair[0])

    duplicate_keys = _duplicates(pair[0] for pair in keyed)
    if duplicate_keys:
        raise ValueError(
            "sampling keys must be unique; duplicates: {}".format(
                ", ".join(sorted(duplicate_keys)[:5])
            )
        )

    rng = rng_for(master_seed, namespace)
    chosen = rng.sample(range(len(keyed)), size)
    return [keyed[index][1] for index in sorted(chosen)]


def _duplicates(values: Iterable[str]) -> set:
    seen = set()
    repeated = set()
    for value in values:
        if value in seen:
            repeated.add(value)
        seen.add(value)
    return repeated

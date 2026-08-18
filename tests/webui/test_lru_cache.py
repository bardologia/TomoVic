"""Tests for LruCache eviction order, capacity validation and thread safety."""

from __future__ import annotations

import threading

import pytest

from lru_cache import LruCache


def test_a_missing_key_reads_as_none():
    """An unknown key reads as None and does not grow the cache."""
    cache = LruCache(2)

    assert cache.get("nothing") is None
    assert cache.size() == 0


def test_the_oldest_untouched_entry_is_evicted_first():
    """Insertion past the capacity evicts the least recently accessed key."""
    cache = LruCache(2)

    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")
    cache.put("c", 3)

    assert cache.get("a") == 1
    assert cache.get("c") == 3
    assert cache.get("b") is None
    assert cache.size() == 2


def test_reputting_a_key_refreshes_it_without_growing_the_cache():
    """Writing an existing key replaces its value and leaves the size unchanged."""
    cache = LruCache(2)

    cache.put("a", 1)
    cache.put("a", 2)

    assert cache.get("a") == 2
    assert cache.size() == 1


def test_a_capacity_below_one_is_refused():
    """Constructing a cache with a non-positive capacity raises ValueError."""
    with pytest.raises(ValueError, match="at least one entry"):
        LruCache(0)


def test_concurrent_writers_never_exceed_the_capacity():
    """Parallel writers leave the cache holding exactly its capacity in entries."""
    cache   = LruCache(8)
    workers = [threading.Thread(target=lambda index=index: [cache.put(f"{index}-{n}", n) for n in range(200)]) for index in range(8)]

    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert cache.size() == 8

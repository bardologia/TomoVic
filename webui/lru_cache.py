"""Thread-safe least-recently-used cache used by the web UI service layer.

Provides a small bounded key/value store that evicts the least recently
accessed entry once the configured capacity is exceeded.
"""

from __future__ import annotations

import threading
from collections import OrderedDict


class LruCache:
    """Bounded key/value cache with least-recently-used eviction.

    Attributes:
        capacity: Maximum number of entries retained before eviction.
        lock: Mutex guarding all reads and writes of the entry map.
        entries: Ordered mapping from key to value, oldest access first.
    """

    def __init__(self, capacity: int) -> None:
        """Creates an empty cache holding at most ``capacity`` entries.

        Args:
            capacity: Maximum number of entries to retain; must be at least one.

        Raises:
            ValueError: If ``capacity`` is smaller than one.
        """
        if capacity < 1:
            raise ValueError(f"an LRU cache needs room for at least one entry, got {capacity}")

        self.capacity = capacity
        self.lock     = threading.Lock()
        self.entries  = OrderedDict()

    def get(self, key: str):
        """Returns the cached value for ``key`` and marks it most recently used.

        Args:
            key: Cache key to look up.

        Returns:
            The stored value, or ``None`` when the key is absent.
        """
        with self.lock:
            if key not in self.entries:
                return None

            self.entries.move_to_end(key)
            return self.entries[key]

    def put(self, key: str, value) -> None:
        """Stores a value under ``key``, evicting oldest entries past capacity.

        Args:
            key: Cache key to write.
            value: Value to associate with the key.
        """
        with self.lock:
            self.entries[key] = value
            self.entries.move_to_end(key)

            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)

    def size(self) -> int:
        """Returns the number of entries currently held."""
        with self.lock:
            return len(self.entries)

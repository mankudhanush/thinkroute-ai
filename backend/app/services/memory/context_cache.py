from __future__ import annotations

from collections import OrderedDict
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class LRUCache(Generic[K, V]):
    """Tiny bounded LRU cache — no TTL, no deps. Used to memoise prompt
    analysis and thread reconstruction so repeated work is near-instant.
    """

    def __init__(self, capacity: int = 256) -> None:
        self._store: OrderedDict[K, V] = OrderedDict()
        self._capacity = capacity

    def get(self, key: K) -> V | None:
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def put(self, key: K, value: V) -> None:
        self._store[key] = value
        self._store.move_to_end(key)
        while len(self._store) > self._capacity:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()

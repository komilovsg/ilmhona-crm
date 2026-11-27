"""A small in-process sliding-window limiter for the public pages (no login in front of them).

One API process serves production, so the counts live in memory; a restart forgets them, which
is fine for slowing down guessing. Memory stays bounded: at most `max_keys` addresses are kept.
"""

import time
from collections import OrderedDict, deque


class SlidingWindow:
    def __init__(self, limit: int, window_s: float, max_keys: int = 10_000) -> None:
        self.limit = limit
        self.window_s = window_s
        self.max_keys = max_keys
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits.pop(key, None) or deque()
        while hits and now - hits[0] >= self.window_s:
            hits.popleft()
        allowed = len(hits) < self.limit
        if allowed:
            hits.append(now)
        self._hits[key] = hits  # most recently seen last
        while len(self._hits) > self.max_keys:
            self._hits.popitem(last=False)
        return allowed

    def reset(self) -> None:
        self._hits.clear()

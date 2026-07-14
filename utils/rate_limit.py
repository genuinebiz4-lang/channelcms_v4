"""Simple in-memory rate limiting helpers for Telegram command execution."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from telegram import Update

_BUCKETS: dict[tuple[int, str], deque[float]] = defaultdict(deque)


def enforce_rate_limit(update: Update, scope: str, max_calls: int, window_seconds: int) -> bool:
    """Return True when command execution is allowed for the user within the time window."""
    user = update.effective_user
    if user is None:
        return False

    key = (int(user.id), str(scope))
    now = time.time()
    cutoff = now - max(1, int(window_seconds))

    bucket = _BUCKETS[key]
    while bucket and bucket[0] < cutoff:
        bucket.popleft()

    if len(bucket) >= max(1, int(max_calls)):
        return False

    bucket.append(now)
    return True

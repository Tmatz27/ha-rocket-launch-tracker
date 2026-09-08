"""Shared, non-blocking request accounting for one HA runtime.

Reservations are synchronous on HA's event loop, before the first network
await, so concurrent config entries cannot claim the same final slot.
"""
from collections import deque
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import math
import time

from .const import DOMAIN


class BudgetDeferred(Exception):
    def __init__(self, retry_after: float):
        self.retry_after = max(1, math.ceil(retry_after))
        super().__init__(f"Shared Launch Library request budget: retry in {self.retry_after} seconds")


class RequestBudget:
    def __init__(self, *, limit=15, window=3600, clock=time.monotonic):
        self.limit = limit
        self.window = window
        self.clock = clock
        self.requests = deque()
        self.blocked_until = 0.0

    def reserve(self):
        now = self.clock()
        while self.requests and self.requests[0] <= now - self.window:
            self.requests.popleft()
        wait = self.blocked_until - now
        if len(self.requests) >= self.limit:
            wait = max(wait, self.requests[0] + self.window - now)
        if wait > 0:
            raise BudgetDeferred(wait)
        self.requests.append(now)

    def defer(self, seconds):
        self.blocked_until = max(self.blocked_until, self.clock() + seconds)


def shared_budget(hass_data, api_key=None):
    """Anonymous clients share one bucket; matching keys share another.

Use the conservative free-tier ceiling for keyed clients too: the presence
of a key does not tell us its quota. Never store a raw key in the registry.
Keep buckets across entry reloads, until Home Assistant restarts.
"""
    registry = hass_data.setdefault(DOMAIN + "_request_budgets", {})
    identity = hashlib.sha256(api_key.encode()).hexdigest() if api_key else "anonymous"
    if identity not in registry:
        registry[identity] = RequestBudget()
    return registry[identity]


def retry_after_seconds(value, *, now=None):
    """Accept both HTTP Retry-After formats, rejecting invalid values."""
    try:
        seconds = float(value)
        return max(0, seconds) if math.isfinite(seconds) else 0
    except (ValueError, TypeError):
        try:
            target = parsedate_to_datetime(value)
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            return max(0, (target - (now or datetime.now(timezone.utc))).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0


def backoff_seconds(far_seconds, current_seconds, retry_after=0):
    return max(3600, far_seconds * 2, current_seconds, retry_after)

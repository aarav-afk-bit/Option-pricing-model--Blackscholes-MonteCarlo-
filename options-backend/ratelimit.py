"""
Per-visitor rate limiting for the CPU-heavy Monte Carlo endpoints.

A 200,000-path simulation with every model, or a calibration, keeps a
free-tier server busy for seconds, so without a limit one visitor (or a
script) could make the app unusable for everyone else.

Each visitor gets a token bucket: it holds up to RATE_LIMIT_BURST tokens and
refills at RATE_LIMIT_PER_MINUTE tokens a minute. A request spends tokens
in proportion to its work (a standard 50,000-path run costs 1), and is
refused with HTTP 429 and a Retry-After header when the bucket is short.
State is in memory per process, which suits the single gunicorn worker the
app runs with.
"""

import math
import threading
import time
from functools import wraps

from flask import current_app, jsonify, request

import config


class TokenBucketLimiter:
    def __init__(self, burst, per_minute, max_clients=10_000, clock=time.monotonic):
        self.burst = float(burst)
        self.rate = per_minute / 60.0       # tokens per second
        self.max_clients = max_clients
        self.clock = clock
        self._buckets = {}                  # client -> (tokens, last_update)
        self._lock = threading.Lock()

    def take(self, client, cost):
        """Spend `cost` tokens. Returns (allowed, seconds_until_allowed)."""
        cost = min(float(cost), self.burst)  # a request can never cost more than a full bucket
        now = self.clock()
        with self._lock:
            tokens, last = self._buckets.pop(client, (self.burst, now))
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            allowed = tokens >= cost
            if allowed:
                tokens -= cost
            self._buckets[client] = (tokens, now)   # re-insert: most recently seen last
            while len(self._buckets) > self.max_clients:
                del self._buckets[next(iter(self._buckets))]
        wait = 0.0 if allowed else (cost - tokens) / self.rate
        return allowed, wait


def client_id():
    """
    The visitor's IP. Behind Render's proxy the real address is the last entry
    it appends to X-Forwarded-For (earlier entries can be forged by the client).
    """
    hops = config.TRUSTED_PROXY_HOPS
    forwarded = [part.strip() for part in request.headers.get("X-Forwarded-For", "").split(",") if part.strip()]
    if hops and len(forwarded) >= hops:
        return forwarded[-hops]
    return request.remote_addr or "unknown"


def _limiter():
    # One limiter per Flask app, so separate apps (e.g. in tests) never share state.
    ext = current_app.extensions
    if "mc_rate_limiter" not in ext:
        ext["mc_rate_limiter"] = TokenBucketLimiter(config.RATE_LIMIT_BURST, config.RATE_LIMIT_PER_MINUTE)
    return ext["mc_rate_limiter"]


def rate_limited(cost=lambda: 1.0):
    """Decorator: refuse the request with 429 when the visitor's bucket can't cover `cost()`."""
    def decorate(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if config.RATE_LIMIT_PER_MINUTE <= 0:   # 0 disables limiting
                return view(*args, **kwargs)
            try:
                amount = max(float(cost()), 0.0)
            except (TypeError, ValueError):
                amount = 1.0                        # malformed input: the view will reject it anyway
            allowed, wait = _limiter().take(client_id(), amount)
            if not allowed:
                seconds = max(1, math.ceil(wait))
                resp = jsonify({
                    "error": f"too many simulations from your connection — please wait {seconds}s and try again",
                    "status": 429,
                    "retryAfter": seconds,
                })
                resp.headers["Retry-After"] = str(seconds)
                return resp, 429
            return view(*args, **kwargs)
        return wrapper
    return decorate

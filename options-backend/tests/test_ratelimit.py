"""Rate limiting of the Monte Carlo endpoints."""

import pytest
from flask import Flask

import config
from mc_routes import mc_api
from ratelimit import TokenBucketLimiter

QUERY = "/api/montecarlo?spot=100&strike=100&days=30&vol=20&paths=2000"


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_bucket_allows_a_burst_then_refills():
    clock = Clock()
    lim = TokenBucketLimiter(burst=3, per_minute=6, clock=clock)   # one token every 10 s
    assert [lim.take("a", 1)[0] for _ in range(4)] == [True, True, True, False]
    allowed, wait = lim.take("a", 1)
    assert not allowed and wait == pytest.approx(10)
    clock.now = 10
    assert lim.take("a", 1)[0]
    assert lim.take("b", 1)[0]                                      # other visitors unaffected


def test_cost_scales_and_is_capped_at_a_full_bucket():
    lim = TokenBucketLimiter(burst=4, per_minute=60, clock=Clock())
    assert lim.take("a", 3)[0] and not lim.take("a", 3)[0]
    assert TokenBucketLimiter(4, 60, clock=Clock()).take("b", 100)[0]   # huge request still possible once


def test_forgets_oldest_visitors_beyond_the_limit():
    lim = TokenBucketLimiter(burst=1, per_minute=1, max_clients=2, clock=Clock())
    for c in ("a", "b", "c"):
        lim.take(c, 1)
    assert list(lim._buckets) == ["b", "c"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_BURST", 3)
    monkeypatch.setattr(config, "RATE_LIMIT_PER_MINUTE", 1)
    app = Flask(__name__)
    app.register_blueprint(mc_api)
    return app.test_client()


def test_endpoint_returns_429_with_retry_after(client):
    # 2,000 paths cost 0.04 units each, so the burst of 3 allows many small runs.
    assert all(client.get(QUERY).status_code == 200 for _ in range(50))
    # A 200,000-path run costs 4, capped to the bucket size of 3: it needs a full bucket.
    big = QUERY.replace("paths=2000", "paths=200000")
    resp = client.get(big)
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) >= 1
    body = resp.get_json()
    assert body["status"] == 429 and "please wait" in body["error"]


def test_visitors_are_told_apart_by_the_proxy_appended_address(client, monkeypatch):
    big = QUERY.replace("paths=2000", "paths=200000")
    hdr = {"X-Forwarded-For": "1.1.1.1, 203.0.113.7"}               # last entry is the one Render adds
    assert client.get(big, headers=hdr).status_code == 200
    assert client.get(big, headers=hdr).status_code == 429
    # Forging a different first entry doesn't escape the limit...
    assert client.get(big, headers={"X-Forwarded-For": "9.9.9.9, 203.0.113.7"}).status_code == 429
    # ...but a genuinely different visitor has their own bucket.
    assert client.get(big, headers={"X-Forwarded-For": "198.51.100.2"}).status_code == 200


def test_zero_per_minute_disables_the_limit(client, monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_PER_MINUTE", 0)
    big = QUERY.replace("paths=2000", "paths=200000")
    assert all(client.get(big).status_code == 200 for _ in range(3))

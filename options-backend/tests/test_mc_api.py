"""/api/montecarlo: Black-Scholes and Monte Carlo side by side for explicit inputs."""

import pytest
from flask import Flask

from mc_routes import mc_api

QUERY = "spot=24512.35&strike=24500&days=70&rate=6.5&div=0&vol=13&type=call&paths=20000&seed=7"


@pytest.fixture
def client():
    # The blueprint alone: no NSE client involved.
    app = Flask(__name__)
    app.register_blueprint(mc_api)
    return app.test_client()


def test_returns_black_scholes_and_monte_carlo_side_by_side(client):
    body = client.get(f"/api/montecarlo?{QUERY}").get_json()
    bs = body["blackScholes"]["price"]
    gbm = body["models"]["gbm"]
    assert bs == pytest.approx(725.28, abs=0.01)
    assert abs(gbm["price"] - bs) < 4 * gbm["stdError"]
    assert gbm["paths"] == 20000
    assert body["inputs"]["vol"] == pytest.approx(0.13)
    assert body["inputs"]["days"] == 70
    assert body["elapsedMs"] >= 0


def test_seed_makes_runs_reproducible(client):
    a = client.get(f"/api/montecarlo?{QUERY}").get_json()["models"]
    b = client.get(f"/api/montecarlo?{QUERY}").get_json()["models"]
    assert a == b


def test_defaults_for_optional_inputs(client):
    body = client.get("/api/montecarlo?spot=100&strike=100&days=30&vol=20").get_json()
    assert body["inputs"]["rate"] == pytest.approx(0.065)
    assert body["inputs"]["type"] == "call"
    assert body["inputs"]["paths"] == 50000


@pytest.mark.parametrize("query, message", [
    ("strike=100&days=30&vol=20", "spot is required"),
    ("spot=abc&strike=100&days=30&vol=20", "spot must be a number"),
    ("spot=100&strike=100&days=30&vol=0", "vol must be between"),
    ("spot=100&strike=100&days=30&vol=20&paths=10", "paths must be between"),
    ("spot=100&strike=100&days=30&vol=20&type=straddle", "type must be"),
    ("spot=100&strike=100&days=nan&vol=20", "days must be between"),
])
def test_rejects_bad_input(client, query, message):
    resp = client.get(f"/api/montecarlo?{query}")
    assert resp.status_code == 400
    assert message in resp.get_json()["error"]


def test_registered_on_the_main_app():
    from app import app
    assert any(rule.rule == "/api/montecarlo" for rule in app.url_map.iter_rules())

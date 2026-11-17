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


def test_heston_model_is_returned_with_its_settings(client):
    body = client.get(f"/api/montecarlo?{QUERY}").get_json()
    heston = body["models"]["heston"]
    assert heston["params"]["vol0"] == pytest.approx(0.13)
    assert heston["params"]["rho"] == pytest.approx(-0.6)
    assert abs(heston["price"] - heston["formulaPrice"]) < 4 * heston["stdError"] + 0.004 * heston["formulaPrice"]
    assert {"gbm", "heston"} <= set(body["fans"])


def test_custom_heston_settings(client):
    q = QUERY + "&hVol0=20&hVolLong=15&hKappa=3&hXi=0.8&hRho=-0.9"
    p = client.get(f"/api/montecarlo?{q}").get_json()["models"]["heston"]["params"]
    assert (p["vol0"], p["volLongRun"], p["kappa"], p["xi"], p["rho"]) == pytest.approx((0.2, 0.15, 3, 0.8, -0.9))


def test_bad_heston_setting(client):
    resp = client.get(f"/api/montecarlo?{QUERY}&hRho=-1.5")
    assert resp.status_code == 400 and "hRho" in resp.get_json()["error"]


def test_jump_model_is_returned_with_its_settings(client):
    body = client.get(f"/api/montecarlo?{QUERY}&jLambda=3&jMean=-8&jVol=10").get_json()
    jumps = body["models"]["jumps"]
    assert jumps["params"] == pytest.approx({"lam": 3, "jump_mean": -0.08, "jump_vol": 0.10})
    assert abs(jumps["price"] - jumps["formulaPrice"]) < 4 * jumps["stdError"]
    assert "jumps" in body["fans"]


def test_american_model_reports_premium_and_tree_check(client):
    q = "spot=24512.35&strike=25500&days=70&rate=6.5&vol=13&type=put&paths=40000&seed=3"
    am = client.get(f"/api/montecarlo?{q}").get_json()["models"]["american"]
    assert am["checkLabel"] == "Binomial tree check"
    assert abs(am["price"] - am["formulaPrice"]) < 4 * am["stdError"] + 0.01 * am["formulaPrice"]
    assert am["earlyExercisePremium"] > 0 and am["paths"] == 40000

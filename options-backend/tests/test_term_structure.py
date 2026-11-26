"""ATM implied-volatility term structure across expiries."""

import pytest
from flask import Flask

import analytics_routes
from analytics_routes import analytics_api, atm_iv

SPOT = 24512.35
EXPIRIES = ["30-Dec-2099", "27-Jan-2100", "24-Feb-2100"]


def row(expiry, strike, ce_iv, pe_iv):
    return {"expiryDate": expiry, "strikePrice": strike,
            "CE": {"impliedVolatility": ce_iv} if ce_iv is not None else None,
            "PE": {"impliedVolatility": pe_iv} if pe_iv is not None else None}


def test_atm_iv_interpolates_between_the_strikes_around_spot():
    rows = [row("x", 24400, 14.0, 16.0), row("x", 24600, 12.0, 14.0)]   # averages 15 and 13
    iv, strike = atm_iv(rows, 24500)
    assert iv == pytest.approx(14.0)
    assert strike == 24400   # nearest of equal distance: the first


def test_atm_iv_uses_whichever_side_exists_and_ignores_zero_iv():
    rows = [row("x", 24500, 0, 18.0), row("x", 24600, None, 0)]
    assert atm_iv(rows, 24500) == (18.0, 24500.0)


def test_atm_iv_outside_the_listed_strikes_and_empty_chain():
    rows = [row("x", 24000, 20.0, 20.0), row("x", 24100, 22.0, 22.0)]
    assert atm_iv(rows, 25000)[0] == 22.0
    assert atm_iv([], 25000) == (None, None)


@pytest.fixture
def client(monkeypatch):
    ivs = {EXPIRIES[0]: 16.0, EXPIRIES[1]: 14.5, EXPIRIES[2]: 13.0}   # inverted: front month richest

    def chain(symbol, expiry=None):
        rows = [row(expiry, k, ivs[expiry] + abs(k - 24500) / 1000, ivs[expiry] + abs(k - 24500) / 1000)
                for k in (24300, 24400, 24500, 24600, 24700)]
        return {"records": {"underlyingValue": SPOT, "data": rows}}

    monkeypatch.setattr(analytics_routes.nse_client, "get_expiries", lambda symbol: EXPIRIES)
    monkeypatch.setattr(analytics_routes.nse_client, "get_option_chain", chain)
    app = Flask(__name__)
    app.register_blueprint(analytics_api)
    return app.test_client()


def test_endpoint_returns_one_point_per_expiry(client):
    body = client.get("/api/term-structure/nifty").get_json()
    assert body["symbol"] == "NIFTY" and body["spot"] == SPOT
    assert [p["expiry"] for p in body["points"]] == EXPIRIES
    first = body["points"][0]
    assert first["atmIv"] == pytest.approx(16.0, abs=0.02)
    assert first["expectedMovePct"] == pytest.approx(16.0 * (first["days"] / 365) ** 0.5, rel=1e-3)
    assert first["expectedMove"] == pytest.approx(SPOT * first["expectedMovePct"] / 100, rel=1e-3)
    assert body["shape"] == "inverted"


def test_max_limits_the_number_of_expiries(client):
    assert len(client.get("/api/term-structure/NIFTY?max=2").get_json()["points"]) == 2
    assert client.get("/api/term-structure/NIFTY?max=abc").status_code == 400


def test_expiries_that_fail_are_skipped_not_fatal(client, monkeypatch):
    real = analytics_routes.nse_client.get_option_chain

    def flaky(symbol, expiry=None):
        if expiry == EXPIRIES[1]:
            raise RuntimeError("timeout")
        return real(symbol, expiry=expiry)
    monkeypatch.setattr(analytics_routes.nse_client, "get_option_chain", flaky)
    body = client.get("/api/term-structure/NIFTY").get_json()
    assert [p["expiry"] for p in body["points"]] == [EXPIRIES[0], EXPIRIES[2]]
    assert body["skipped"] == [EXPIRIES[1]]


def test_nse_failure_and_unknown_symbol(client, monkeypatch):
    monkeypatch.setattr(analytics_routes.nse_client, "get_expiries", lambda s: [])
    assert client.get("/api/term-structure/NOPE").status_code == 404

    def down(symbol):
        raise RuntimeError("blocked")
    monkeypatch.setattr(analytics_routes.nse_client, "get_expiries", down)
    assert client.get("/api/term-structure/NIFTY").status_code == 502


def test_registered_on_the_main_app():
    from app import app
    assert any(r.rule == "/api/term-structure/<symbol>" for r in app.url_map.iter_rules())

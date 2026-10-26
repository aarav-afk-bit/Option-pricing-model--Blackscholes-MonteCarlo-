"""Every error response is JSON, never Flask's default HTML page."""

import logging

import pytest

import app as app_module


@pytest.fixture
def client():
    return app_module.app.test_client()


def test_unknown_route_is_json_404(client):
    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404
    assert resp.is_json
    assert resp.get_json()["status"] == 404
    assert resp.get_json()["error"]


def test_wrong_method_is_json_405(client):
    resp = client.post("/api/health")
    assert resp.status_code == 405
    assert resp.is_json


def test_unexpected_exception_is_logged_and_hidden(client, monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise ZeroDivisionError("secret internals")

    monkeypatch.setattr(app_module.nse_client, "get_option_chain", boom)
    with caplog.at_level(logging.ERROR, logger="options_terminal"):
        resp = client.get("/api/option-chain/NIFTY")
    assert resp.status_code == 500
    assert resp.get_json() == {"error": "internal server error", "status": 500}
    assert "secret internals" not in resp.get_data(as_text=True)
    assert any("Unhandled error on GET /api/option-chain/NIFTY" in r.getMessage() for r in caplog.records)


def test_nse_failures_are_logged(monkeypatch, caplog):
    import nse_client

    class Down:
        status_code = 503

    monkeypatch.setattr(nse_client.NSEClient, "_refresh_session", lambda self: None)
    monkeypatch.setattr(nse_client.time, "sleep", lambda s: None)
    client = nse_client.NSEClient()
    monkeypatch.setattr(client.session, "get", lambda *a, **k: Down())
    with caplog.at_level(logging.WARNING, logger="nse_client"), pytest.raises(RuntimeError):
        client._get_json("https://example.invalid/api", params={"symbol": "NIFTY"})
    assert any("NSE request failed after 3 attempts" in r.getMessage() for r in caplog.records)

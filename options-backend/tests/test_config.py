"""config.py: environment parsing with safe fallbacks."""

import importlib

import pytest

import config


@pytest.mark.parametrize("raw, expected", [
    (None, 0.065),     # unset
    ("", 0.065),       # blank
    ("0.07", 0.07),
    ("abc", 0.065),    # not a number
    ("9", 0.065),      # out of range (900%)
])
def test_env_float(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("TEST_RATE", raising=False)
    else:
        monkeypatch.setenv("TEST_RATE", raw)
    assert config.env_float("TEST_RATE", 0.065, minimum=-0.05, maximum=0.5) == expected


@pytest.mark.parametrize("raw, expected", [("400", 400), ("12.5", 150), ("5", 150), ("x", 150)])
def test_env_int(monkeypatch, raw, expected):
    monkeypatch.setenv("TEST_STEPS", raw)
    assert config.env_int("TEST_STEPS", 150, minimum=10, maximum=5000) == expected


def test_settings_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("CRR_STEPS", "300")
    monkeypatch.setenv("MC_SIMULATIONS", "5000")
    reloaded = importlib.reload(config)
    try:
        assert reloaded.CRR_STEPS == 300
        assert reloaded.MC_SIMULATIONS == 5000
        assert reloaded.RISK_FREE_RATE == 0.065
    finally:
        monkeypatch.delenv("CRR_STEPS")
        monkeypatch.delenv("MC_SIMULATIONS")
        importlib.reload(config)

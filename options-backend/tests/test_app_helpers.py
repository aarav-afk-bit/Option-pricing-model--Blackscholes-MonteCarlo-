"""Unit tests for the small helpers behind /api/analyze."""

import pytest

from app import _by_side, _find_leg

RECORDS = {"data": [
    {"expiryDate": "30-Dec-2099", "strikePrice": 24500, "CE": {"lastPrice": 150}, "PE": {"lastPrice": 140}},
    {"expiryDate": "30-Dec-2099", "strikePrice": 24600.0, "CE": {"lastPrice": 100}, "PE": None},
    {"expiryDate": "27-Jan-2100", "strikePrice": 24500, "CE": {"lastPrice": 300}, "PE": {"lastPrice": 280}},
]}


def test_by_side():
    assert _by_side({"call": 1, "put": 2}, "call") == 1
    assert _by_side({"call": 1, "put": 2}, "put") == 2


@pytest.mark.parametrize("expiry, strike, side, price", [
    ("30-Dec-2099", 24500.0, "call", 150),
    ("30-Dec-2099", 24500.0, "put", 140),
    ("27-Jan-2100", 24500.0, "call", 300),   # same strike, other expiry
    ("30-Dec-2099", 24600.0, "call", 100),   # float strike in the data
])
def test_find_leg_matches_expiry_strike_and_side(expiry, strike, side, price):
    row, leg = _find_leg(RECORDS, expiry, strike, side)
    assert row is not None and leg["lastPrice"] == price


def test_find_leg_missing_contract_and_missing_side():
    assert _find_leg(RECORDS, "30-Dec-2099", 99999.0, "call") == (None, None)
    row, leg = _find_leg(RECORDS, "30-Dec-2099", 24600.0, "put")
    assert row is not None and leg is None
    assert _find_leg({}, "30-Dec-2099", 24500.0, "call") == (None, None)

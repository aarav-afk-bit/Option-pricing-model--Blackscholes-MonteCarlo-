"""The backend and frontend each ship a copy of the NSE symbol list; keep them identical."""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_SYMBOLS = os.path.join(HERE, "..", "data", "nse_symbols.json")
FRONTEND_SYMBOLS = os.path.join(HERE, "..", "..", "options-frontend", "data", "nse_companies.json")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_symbol_lists_are_identical():
    # The frontend copy powers instant search; the backend copy serves /api/symbols.
    # Edit one, then copy it over the other.
    assert load(BACKEND_SYMBOLS) == load(FRONTEND_SYMBOLS)


def test_symbols_are_unique_and_complete():
    symbols = load(BACKEND_SYMBOLS)["symbols"]
    names = [s["symbol"] for s in symbols]
    assert len(names) == len(set(names)), "duplicate symbols"
    for s in symbols:
        assert {"symbol", "name", "sector", "lotSize"} <= s.keys(), s
        assert isinstance(s["lotSize"], int) and s["lotSize"] > 0, s

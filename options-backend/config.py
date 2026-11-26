"""
Tunable settings, read once from environment variables at startup.

Set these in Render's "Environment" tab (or your shell) to change behaviour
without editing code:

  RISK_FREE_RATE   default r when the request doesn't pass one (decimal, 0.065 = 6.5%)
  FALLBACK_SIGMA   volatility used when NSE reports no IV for a strike (decimal)
  CRR_STEPS        binomial tree steps (more = slower, more precise)
  MC_SIMULATIONS   Monte Carlo paths (more = slower, smaller standard error)
  RATE_LIMIT_PER_MINUTE  Monte Carlo Lab work units each visitor regains per minute (0 = no limit)
  RATE_LIMIT_BURST       work units a visitor can spend at once
  TRUSTED_PROXY_HOPS     proxies in front of the app that append to X-Forwarded-For (Render: 1)
"""

import os


def env_float(name, default, minimum=None, maximum=None):
    """Float from the environment; falls back to `default` if unset, blank or out of range."""
    raw = os.environ.get(name, "").strip()
    try:
        value = float(raw) if raw else default
    except ValueError:
        return default
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        return default
    return value


def env_int(name, default, minimum=None, maximum=None):
    value = env_float(name, default, minimum, maximum)
    return int(value) if value == int(value) else default


RISK_FREE_RATE = env_float("RISK_FREE_RATE", 0.065, minimum=-0.05, maximum=0.5)
FALLBACK_SIGMA = env_float("FALLBACK_SIGMA", 0.25, minimum=0.01, maximum=5.0)
CRR_STEPS = env_int("CRR_STEPS", 150, minimum=10, maximum=5000)
MC_SIMULATIONS = env_int("MC_SIMULATIONS", 30000, minimum=1000, maximum=2_000_000)
# Monte Carlo Lab rate limit: one unit = one standard 50,000-path run.
RATE_LIMIT_PER_MINUTE = env_float("RATE_LIMIT_PER_MINUTE", 20, minimum=0, maximum=10_000)
RATE_LIMIT_BURST = env_float("RATE_LIMIT_BURST", 12, minimum=1, maximum=10_000)
TRUSTED_PROXY_HOPS = env_int("TRUSTED_PROXY_HOPS", 1, minimum=0, maximum=5)

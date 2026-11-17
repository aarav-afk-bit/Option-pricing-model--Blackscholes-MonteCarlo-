"""
Calibrate the lab's models to today's market prices for one expiry.

Black-Scholes has one volatility for every strike, so it cannot match the
"smile" in a real option chain: out-of-the-money puts and calls trade at
higher implied volatility than at-the-money ones. Here each model's
parameters are chosen to reproduce as many market prices as possible at
once, and the fit errors are compared:

* Black-Scholes - the single best volatility (a flat line through the smile)
* Heston        - volatility, vol-of-vol and correlation. One expiry cannot
                  tell today's variance from its long-run level (or pin down
                  the reversion speed), so v0 = theta and kappa is fixed.
* Merton jumps  - diffusion vol, jump frequency, average jump and jump spread

Errors are measured in implied-volatility points (price error / vega), the
usual way to compare fits across strikes of very different price. Last-traded
prices are noisy, so the fit uses a robust (soft-L1) loss that stops a few
stale quotes from dragging the parameters to extremes.
Fitting needs thousands of evaluations, so prices come from vectorised
closed forms (all strikes at once), not simulation; the calibrated
parameters are then used by the Monte Carlo models.
"""

import math

import numpy as np
from scipy.optimize import least_squares
from scipy.stats import norm

from montecarlo.heston import HestonParams, heston_prices
from montecarlo.jumps import JumpParams
from pricing import implied_volatility

HESTON_KAPPA = 2.0


def bs_prices(S, K, T, r, q, sigma, is_call):
    """Black-Scholes for arrays of strikes / vols / call flags."""
    sq = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / sq
    d2 = d1 - sq
    call = S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    put = K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)
    return np.where(is_call, call, put)


def bs_vega(S, K, T, r, q, sigma):
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return S * np.exp(-q * T) * norm.pdf(d1) * np.sqrt(T)


def merton_prices(S, K, T, r, q, sigma, p, is_call, terms=40):
    lam_prime = p.lam * (1 + p.k)
    total = np.zeros_like(K, dtype=float)
    weight = math.exp(-lam_prime * T)
    for n in range(terms):
        if n:
            weight *= lam_prime * T / n
        sigma_n = math.sqrt(sigma ** 2 + n * p.jump_vol ** 2 / T)
        r_n = r - p.lam * p.k + n * math.log(1 + p.k) / T
        total += weight * bs_prices(S, K, T, r_n, q, sigma_n, is_call)
        if n > lam_prime * T and weight < 1e-12:
            break
    return total


def select_quotes(rows, spot, option_side=None):
    """
    Liquid out-of-the-money quotes from a normalised chain: puts below spot,
    calls at or above it. Uses the bid/ask mid when both sides are quoted,
    otherwise the last price; drops prices under ₹0.5 and spreads over 40%.
    """
    quotes = []
    for row in rows:
        K = float(row["strikePrice"])
        is_call = K >= spot
        leg = row.get("CE" if is_call else "PE") or {}
        bid, ask, ltp = leg.get("bidprice") or 0, leg.get("askPrice") or 0, leg.get("lastPrice") or 0
        if bid > 0 and ask >= bid:
            price = 0.5 * (bid + ask)
            if (ask - bid) / price > 0.4:
                continue
        else:
            price = ltp
        if price >= 0.5:
            quotes.append({"strike": K, "type": "call" if is_call else "put", "market": float(price)})
    return sorted(quotes, key=lambda x: x["strike"])


def calibrate(quotes, S, T, r, q=0.0):
    """Fit all three models to `quotes` and return their parameters, prices and errors."""
    K = np.array([x["strike"] for x in quotes], dtype=float)
    is_call = np.array([x["type"] == "call" for x in quotes])
    market = np.array([x["market"] for x in quotes], dtype=float)
    ivs = np.array([implied_volatility(m, S, k, T, r, q, "call" if c else "put") or np.nan
                    for m, k, c in zip(market, K, is_call, strict=True)])
    keep = np.isfinite(ivs)
    K, is_call, market, ivs = K[keep], is_call[keep], market[keep], ivs[keep]
    if len(K) < 5:
        raise ValueError("need at least 5 liquid out-of-the-money quotes to calibrate")
    vega = np.maximum(bs_vega(S, K, T, r, q, ivs), 1e-8)

    def iv_error(model_prices):
        return (model_prices - market) / vega

    def summary(prices, params):
        err = iv_error(prices)
        return {
            "params": params,
            "prices": prices.round(4).tolist(),
            "rmseVolPts": float(np.sqrt(np.mean(err ** 2)) * 100),
            "rmseRupees": float(np.sqrt(np.mean((prices - market) ** 2))),
        }

    # Black-Scholes: one volatility for every strike.
    bs_fit = least_squares(lambda x: iv_error(bs_prices(S, K, T, r, q, x[0], is_call)),
                           [float(np.median(ivs))], bounds=([0.01], [3.0]))
    flat = float(bs_fit.x[0])

    # Robust loss scale: residuals beyond ~0.5 vol points count linearly, not quadratically.
    robust = {"loss": "soft_l1", "f_scale": 0.005}

    # Heston: x = [vol, vol of vol, rho], with v0 = theta.
    def heston_from(x):
        v = float(x[0]) ** 2
        return HestonParams(v0=v, theta=v, kappa=HESTON_KAPPA, xi=float(x[1]), rho=float(x[2]))
    h_fit = least_squares(lambda x: iv_error(heston_prices(S, K, T, r, q, heston_from(x), is_call)),
                          [flat, 0.5, -0.5], bounds=([0.02, 0.05, -0.99], [2.0, 4.0, 0.99]), **robust)
    heston = heston_from(h_fit.x)

    # Merton: x = [diffusion vol, jumps per year, mean log jump, jump spread]. The diffusion
    # vol is kept to a realistic share of the market level so jumps can't replace it entirely.
    def merton_from(x):
        return float(x[0]), JumpParams(lam=float(x[1]), jump_mean=float(x[2]), jump_vol=float(x[3]))
    m_fit = least_squares(lambda x: iv_error(merton_prices(S, K, T, r, q, *merton_from(x), is_call)),
                          [0.8 * flat, 1.0, -0.05, 0.08],
                          bounds=([0.4 * flat, 0.0, -0.4, 0.01], [1.5 * flat, 12.0, 0.2, 0.4]), **robust)
    m_sigma, jumps = merton_from(m_fit.x)

    fits = {
        "blackScholes": summary(bs_prices(S, K, T, r, q, flat, is_call), {"vol": flat}),
        "heston": summary(heston_prices(S, K, T, r, q, heston, is_call), heston.as_dict()),
        "jumps": summary(merton_prices(S, K, T, r, q, m_sigma, jumps, is_call), {"vol": m_sigma, **jumps.as_dict()}),
    }
    return {
        "quotes": [{"strike": float(k), "type": "call" if c else "put", "market": float(m), "iv": float(v)}
                   for k, c, m, v in zip(K, is_call, market, ivs, strict=True)],
        "fits": fits,
        "best": min(fits, key=lambda name: fits[name]["rmseVolPts"]),
    }

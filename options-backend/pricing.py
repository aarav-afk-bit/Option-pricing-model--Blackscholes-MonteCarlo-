"""
Black-Scholes / CRR / Monte Carlo options pricing engine.
Ported from the original research notebook, generalized into reusable functions.
"""

import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq

TRADING_DAYS = 252


# ------------------------------------------------------------------
# Core pricing models
# ------------------------------------------------------------------

def _forward_intrinsic(S, K, T, r, q):
    """S e^(-qT) - K e^(-rT): what a call is worth when nothing is uncertain."""
    t = max(T, 0.0)
    return float(S * np.exp(-q * t) - K * np.exp(-r * t))


def _limit_greeks(S, K, T, r, q):
    """
    Greeks in the limit T -> 0 or sigma -> 0, where the option is either surely
    in or surely out of the money. Delta is 0 or +/-1 (discounted for dividends),
    exactly at the money it is +/-0.5, and every curvature/vol Greek is 0.
    Theta and rho are those of the deterministic payoff.
    """
    t = max(T, 0.0)
    fwd = _forward_intrinsic(S, K, T, r, q)
    w_call = 1.0 if fwd > 0 else 0.5 if fwd == 0 else 0.0  # weight on "call finishes ITM"
    w_put = 1.0 - w_call
    disc_s, disc_k = S * np.exp(-q * t), K * np.exp(-r * t)
    return {
        "callDelta": float(np.exp(-q * t) * w_call),
        "putDelta": float(-np.exp(-q * t) * w_put),
        "gamma": 0.0,
        "vega": 0.0,
        "callTheta": float(w_call * (q * disc_s - r * disc_k)),
        "putTheta": float(w_put * (r * disc_k - q * disc_s)),
        "callRho": float(w_call * K * t * np.exp(-r * t)),
        "putRho": float(-w_put * K * t * np.exp(-r * t)),
        "vanna": 0.0,
        "vomma": 0.0,
        "callCharm": 0.0,
        "putCharm": 0.0,
    }


def black_scholes(S, K, T, r, sigma, q=0.0):
    """European option price via closed-form Black-Scholes-Merton."""
    if T <= 0 or sigma <= 0:
        # No uncertainty left (expired, or zero volatility): the option is worth
        # its discounted forward intrinsic value. At T=0 that is plain intrinsic.
        fwd = _forward_intrinsic(S, K, T, r, q)
        return {"call": max(fwd, 0.0), "put": max(-fwd, 0.0), "d1": None, "d2": None}

    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    call = S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    put = K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)

    return {"call": float(call), "put": float(put), "d1": float(d1), "d2": float(d2)}


def greeks(S, K, T, r, sigma, q=0.0):
    """
    Delta, Gamma, Vega, Theta, Rho for both call and put, plus the
    second-order Greeks Vanna (dDelta/dVol), Vomma (dVega/dVol) and Charm
    (delta drift per year as time passes). All per unit, per year.

    With T <= 0 or sigma <= 0 the formulas divide by zero, so the limiting
    values are returned instead (see _limit_greeks).
    """
    if T <= 0 or sigma <= 0:
        return _limit_greeks(S, K, T, r, q)

    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    pdf_d1 = norm.pdf(d1)

    call_delta = np.exp(-q * T) * norm.cdf(d1)
    put_delta = np.exp(-q * T) * (norm.cdf(d1) - 1)
    gamma = np.exp(-q * T) * pdf_d1 / (S * sigma * np.sqrt(T))
    vega = S * np.exp(-q * T) * pdf_d1 * np.sqrt(T)

    call_theta = (
        -(S * np.exp(-q * T) * pdf_d1 * sigma / (2 * np.sqrt(T)))
        - r * K * np.exp(-r * T) * norm.cdf(d2)
        + q * S * np.exp(-q * T) * norm.cdf(d1)
    )
    put_theta = (
        -(S * np.exp(-q * T) * pdf_d1 * sigma / (2 * np.sqrt(T)))
        + r * K * np.exp(-r * T) * norm.cdf(-d2)
        - q * S * np.exp(-q * T) * norm.cdf(-d1)
    )

    call_rho = K * T * np.exp(-r * T) * norm.cdf(d2)
    put_rho = -K * T * np.exp(-r * T) * norm.cdf(-d2)

    vanna = -np.exp(-q * T) * pdf_d1 * d2 / sigma
    vomma = vega * d1 * d2 / sigma
    charm_common = np.exp(-q * T) * pdf_d1 * (2 * (r - q) * T - d2 * sigma * np.sqrt(T)) / (
        2 * T * sigma * np.sqrt(T)
    )
    call_charm = q * np.exp(-q * T) * norm.cdf(d1) - charm_common
    put_charm = -q * np.exp(-q * T) * norm.cdf(-d1) - charm_common

    return {
        "callDelta": float(call_delta),
        "putDelta": float(put_delta),
        "gamma": float(gamma),
        "vega": float(vega),
        "callTheta": float(call_theta),
        "putTheta": float(put_theta),
        "callRho": float(call_rho),
        "putRho": float(put_rho),
        "vanna": float(vanna),
        "vomma": float(vomma),
        "callCharm": float(call_charm),
        "putCharm": float(put_charm),
    }


def crr_price(S, K, T, r, sigma, q=0.0, steps=150, option_type="call", american=True):
    """Cox-Ross-Rubinstein binomial tree price (European or American)."""
    if T <= 0 or sigma <= 0:
        # The tree collapses (u = d = 1); price the deterministic payoff directly.
        bs = black_scholes(S, K, T, r, sigma, q)
        european = bs["call"] if option_type.lower() == "call" else bs["put"]
        intrinsic = max(S - K, 0.0) if option_type.lower() == "call" else max(K - S, 0.0)
        return float(max(european, intrinsic)) if american else float(european)

    dt = T / steps
    u = np.exp(sigma * np.sqrt(dt))
    d = 1 / u
    discount = np.exp(-r * dt)
    p = (np.exp((r - q) * dt) - d) / (u - d)

    j = np.arange(steps + 1)
    stock_prices = S * (u ** j) * (d ** (steps - j))

    if option_type.lower() == "call":
        values = np.maximum(stock_prices - K, 0)
    else:
        values = np.maximum(K - stock_prices, 0)

    for i in range(steps - 1, -1, -1):
        j = np.arange(i + 1)
        stock_prices = S * (u ** j) * (d ** (i - j))
        continuation = discount * (p * values[1:i + 2] + (1 - p) * values[:i + 1])

        if american:
            if option_type.lower() == "call":
                exercise = np.maximum(stock_prices - K, 0)
            else:
                exercise = np.maximum(K - stock_prices, 0)
            values = np.maximum(continuation, exercise)
        else:
            values = continuation

    return float(values[0])


def monte_carlo(S, K, T, r, sigma, q=0.0, simulations=30000, option_type="call", seed=42):
    """
    Monte Carlo estimate of the European option price with standard error.

    Uses antithetic variates: every normal draw Z is paired with -Z and the
    two payoffs are averaged. Same number of simulated paths, noticeably
    lower standard error, because the pair's errors partly cancel.
    """
    if T <= 0 or sigma <= 0:
        # Nothing random left to simulate: every path gives the same payoff.
        bs = black_scholes(S, K, T, r, sigma, q)
        return float(bs["call"] if option_type.lower() == "call" else bs["put"]), 0.0

    rng = np.random.default_rng(seed)
    pairs = max(simulations // 2, 1)
    Z = rng.standard_normal(pairs)
    drift = (r - q - 0.5 * sigma ** 2) * T
    diffusion = sigma * np.sqrt(T)
    ST_up = S * np.exp(drift + diffusion * Z)
    ST_down = S * np.exp(drift - diffusion * Z)

    if option_type.lower() == "call":
        payoff = 0.5 * (np.maximum(ST_up - K, 0) + np.maximum(ST_down - K, 0))
    else:
        payoff = 0.5 * (np.maximum(K - ST_up, 0) + np.maximum(K - ST_down, 0))

    # The pair averages are i.i.d., so the standard error is taken over pairs.
    price = np.exp(-r * T) * np.mean(payoff)
    se = np.exp(-r * T) * np.std(payoff, ddof=1) / np.sqrt(pairs) if pairs > 1 else 0.0

    return float(price), float(se)


def implied_volatility(market_price, S, K, T, r, q=0.0, option_type="call"):
    """Solve for the volatility that reprices `market_price` under Black-Scholes."""
    if not market_price or market_price <= 0 or T <= 0:
        return None

    def objective(vol):
        result = black_scholes(S, K, T, r, vol, q)
        return (result["call"] if option_type.lower() == "call" else result["put"]) - market_price

    try:
        return float(brentq(objective, 1e-4, 5.0))
    except ValueError:
        return None


# ------------------------------------------------------------------
# Trading suggestion heuristic
# ------------------------------------------------------------------

def build_suggestion(K, option_type, fair_value, market_price, greeks_dict):
    """
    Compares Black-Scholes fair value to the live NSE premium and returns a
    plain-language, model-based read. This is an educational heuristic, not
    financial advice.
    """
    theta_per_day = (
        greeks_dict["callTheta"] if option_type == "call" else greeks_dict["putTheta"]
    ) / 365

    zone_low = fair_value * 0.97
    zone_high = fair_value * 1.01

    result = {
        "fairValue": round(fair_value, 4),
        "thetaPerDay": round(theta_per_day, 4),
        "thetaFiveDay": round(theta_per_day * 5, 4),
        "fairValueZone": {"low": round(zone_low, 4), "high": round(zone_high, 4)},
    }

    # A deep OTM contract can have a model value of ~0, which would make the
    # mispricing % below divide by zero — treat it like "no comparison".
    if market_price is None or fair_value <= 1e-8:
        result.update({
            "verdict": "MODEL_FAIR_VALUE",
            "headline": "MODEL FAIR VALUE",
            "suggestedEntry": round(fair_value, 4),
            "reasoning": (
                f"No live premium was available for this contract, so this is the theoretical "
                f"Black-Scholes fair value. Reasonable entry zone: {zone_low:.2f} to {zone_high:.2f}."
            ),
        })
        return result

    diff_pct = (market_price - fair_value) / fair_value

    if diff_pct <= -0.08:
        verdict, headline = "UNDERVALUED", f"BUY {option_type.upper()} — UNDERVALUED"
        entry = market_price
        reasoning = (
            f"LTP ({market_price:.2f}) is {abs(diff_pct) * 100:.1f}% below fair value "
            f"({fair_value:.2f}). Looks like a meaningful discount — confirm the quote isn't stale."
        )
    elif diff_pct <= -0.02:
        verdict, headline = "ATTRACTIVE", f"{option_type.upper()} LOOKS ATTRACTIVE"
        entry = min(market_price, zone_high)
        reasoning = (
            f"LTP is {abs(diff_pct) * 100:.1f}% cheaper than fair value ({fair_value:.2f}). "
            f"A reasonable entry is at or below {zone_high:.2f}."
        )
    elif diff_pct < 0.02:
        verdict, headline = "FAIR", "FAIRLY PRICED"
        entry = fair_value
        reasoning = (
            f"LTP ({market_price:.2f}) is within ~2% of fair value ({fair_value:.2f}). "
            f"No strong pricing edge either way; theta decay is {theta_per_day:.2f}/day."
        )
    elif diff_pct <= 0.08:
        verdict, headline = "SLIGHTLY_RICH", "SLIGHTLY RICH — WAIT"
        entry = zone_high
        reasoning = (
            f"LTP is {diff_pct * 100:.1f}% above fair value. Consider waiting for the premium "
            f"to ease toward {fair_value:.2f}."
        )
    else:
        verdict, headline = "OVERPRICED", f"{option_type.upper()} OVERPRICED — AVOID"
        entry = fair_value
        reasoning = (
            f"LTP ({market_price:.2f}) is {diff_pct * 100:.1f}% above fair value "
            f"({fair_value:.2f}). Buying here pays a premium the model doesn't support."
        )

    result.update({
        "verdict": verdict,
        "headline": headline,
        "marketPrice": market_price,
        "mispricingPct": round(diff_pct * 100, 2),
        "suggestedEntry": round(entry, 4),
        "reasoning": reasoning,
    })
    return result

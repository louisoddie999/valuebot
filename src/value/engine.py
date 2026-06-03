"""
Value engine: de-vig book odds -> fair implied prob, expected value, Kelly stake.
"""
from __future__ import annotations


def implied_probs_devig(odds: dict[str, float], method: str = "proportional") -> dict[str, float]:
    """
    Convert a complete set of decimal odds for one market into fair (margin-removed)
    probabilities. odds = {selection: decimal_odds} covering ALL outcomes.
    """
    raw = {k: 1.0 / v for k, v in odds.items() if v and v > 1.0}
    overround = sum(raw.values())
    if overround <= 0:
        return {}
    if method == "proportional":
        return {k: v / overround for k, v in raw.items()}
    # power method fallback (closer to true on longshots) — simple normalisation here
    return {k: v / overround for k, v in raw.items()}


def expected_value(model_prob: float, decimal_odds: float) -> float:
    """EV per 1 unit staked. >0 means positive expected value."""
    return model_prob * decimal_odds - 1.0


def kelly_fraction(model_prob: float, decimal_odds: float) -> float:
    """Full-Kelly fraction of bankroll. Negative => no bet."""
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    f = (model_prob * b - (1.0 - model_prob)) / b
    return max(0.0, f)


def stake_units(model_prob, decimal_odds, bankroll, kelly_mult=0.25, max_pct=0.02) -> float:
    """Quarter-Kelly stake in bankroll units, capped at max_pct of bankroll."""
    f = kelly_fraction(model_prob, decimal_odds) * kelly_mult
    f = min(f, max_pct)
    return round(bankroll * f, 2)

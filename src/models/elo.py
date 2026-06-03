"""
Elo strength ratings — pure results-based team strength (no odds, no edge).

Online/walk-forward: ratings update after each match, so when used in the backtest there is
zero look-ahead leakage. Margin-of-victory multiplier (Dixon-style) makes big wins move
ratings more. Provides an independent supremacy signal blended into the projector.
"""
from __future__ import annotations

import math

START = 1500.0
HOME_ADV = 65.0      # Elo points of home advantage
K = 20.0             # base update step


def expected_home(rh, ra, home_adv=HOME_ADV):
    """P(home win) from Elo (draw absorbed into the logistic, standard football Elo)."""
    return 1.0 / (1.0 + 10 ** (-((rh + home_adv) - ra) / 400.0))


def supremacy(rh, ra, home_adv=HOME_ADV):
    """Scaled to ~[-1,1] like the form/winrate diffs the projector blends."""
    return 2.0 * (expected_home(rh, ra, home_adv) - 0.5)


def _mov_mult(margin, rating_diff):
    """Margin-of-victory multiplier; dampened for large rating gaps (autocorrelation guard)."""
    return math.log(abs(margin) + 1) * (2.2 / ((rating_diff * 0.001) + 2.2))


def update(rh, ra, fthg, ftag, home_adv=HOME_ADV, k=K):
    """Return (new_rh, new_ra) after a finished match."""
    exp_h = expected_home(rh, ra, home_adv)
    score_h = 1.0 if fthg > ftag else (0.5 if fthg == ftag else 0.0)
    margin = fthg - ftag
    rd = (rh + home_adv) - ra if score_h else ra - (rh + home_adv)
    mult = _mov_mult(margin if margin != 0 else 1, rd)
    delta = k * mult * (score_h - exp_h)
    return rh + delta, ra - delta


class Ledger:
    """Maintains a rolling rating table; feed matches in date order."""
    def __init__(self):
        self.r = {}

    def get(self, team):
        return self.r.get(team, START)

    def feed(self, home, away, fthg, ftag):
        rh, ra = self.get(home), self.get(away)
        nh, na = update(rh, ra, fthg, ftag)
        self.r[home], self.r[away] = nh, na

    def sup(self, home, away):
        return supremacy(self.get(home), self.get(away))


if __name__ == "__main__":
    L = Ledger()
    # strong home team beats weak away repeatedly -> rating gap widens, sup -> +1
    for _ in range(10):
        L.feed("Strong", "Weak", 3, 1)
    print("Strong:", round(L.get("Strong")), "Weak:", round(L.get("Weak")))
    print("sup Strong v Weak:", round(L.sup("Strong", "Weak"), 3), "(expect strongly +)")
    print("sup Weak v Strong:", round(L.sup("Weak", "Strong"), 3), "(expect strongly -)")

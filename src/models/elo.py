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




# ---- persistent ratings for LIVE use (built from matches history) ----
import unicodedata
from difflib import SequenceMatcher


def _norm(name):
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = "".join(c if (c.isalnum() or c == " ") else " " for c in s)
    drop = {"fc","cf","afc","sc","ac","club","de","cd","ca","sad","ssd","calcio","if","fk","bk","sk"}
    return " ".join(t for t in s.split() if t and t not in drop).strip() or s.strip()


def build_team_table(conn):
    """Walk all matches in date order -> current Elo per team -> store in team_elo."""
    import pandas as pd
    m = pd.read_sql_query("SELECT home_team,away_team,fthg,ftag FROM matches WHERE fthg IS NOT NULL ORDER BY date", conn)
    L = Ledger()
    for r in m.itertuples(index=False):
        L.feed(r.home_team, r.away_team, r.fthg, r.ftag)
    conn.execute("CREATE TABLE IF NOT EXISTS team_elo (team TEXT PRIMARY KEY, norm TEXT, rating REAL, updated_at TEXT)")
    conn.execute("DELETE FROM team_elo")
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    for team, rating in L.r.items():
        conn.execute("INSERT OR REPLACE INTO team_elo(team,norm,rating,updated_at) VALUES (?,?,?,?)",
                     (team, _norm(team), round(rating, 1), now))
    conn.commit()
    return len(L.r)


def load_index(conn):
    """{norm_name: rating} for live fuzzy matching."""
    try:
        return {r[0]: r[1] for r in conn.execute("SELECT norm, rating FROM team_elo")}
    except Exception:
        return {}


def rating_for(name, index):
    """Fuzzy-match a live team name to a stored Elo rating, else None."""
    if not index:
        return None
    n = _norm(name)
    if n in index:
        return index[n]
    best, sc = None, 0.0
    for k, v in index.items():
        r = SequenceMatcher(None, n, k).ratio()
        if r > sc:
            best, sc = v, r
    return best if sc >= 0.82 else None


def live_sup(home_name, away_name, index):
    rh = rating_for(home_name, index); ra = rating_for(away_name, index)
    if rh is None or ra is None:
        return None
    return supremacy(rh, ra)


if __name__ == "__main__":
    L = Ledger()
    # strong home team beats weak away repeatedly -> rating gap widens, sup -> +1
    for _ in range(10):
        L.feed("Strong", "Weak", 3, 1)
    print("Strong:", round(L.get("Strong")), "Weak:", round(L.get("Weak")))
    print("sup Strong v Weak:", round(L.sup("Strong", "Weak"), 3), "(expect strongly +)")
    print("sup Weak v Strong:", round(L.sup("Weak", "Strong"), 3), "(expect strongly -)")

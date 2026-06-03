"""
Deep market projector (v2).

Per match, builds three Poisson models from that match's OWN data:
  - full-time goals   (recent scoring/conceding, tilted by form + win-rate + H2H)
  - half-time goals    (real 1st-half scoring splits)
  - corners + cards    (recent per-match counts)

From these it derives a probability for EVERY modelable SportyBet market the event offers.
Markets it cannot model from available data (player props, exotic combos) return None and are
SKIPPED by the caller — never guessed.

Balanced blend: goals are the base; form/win-rate/H2H meaningfully tilt the supremacy.
"""
from __future__ import annotations

import re

import numpy as np
from scipy.stats import poisson

HOME_ADJ = 1.06
AWAY_ADJ = 0.96
MAXG = 8
TILT = 0.25          # how strongly supremacy signal tilts expected goals
ELO_W = 0.30         # Elo supremacy blend weight — backtest-validated (acc +0.3pp, Brier -0.003)
BLEND = 0.6          # Poisson vs empirical rate (O2.5 / BTTS)

_CACHE: dict = {}    # sb_event_id -> Projection


def _pois_matrix(lh, la):
    h = poisson.pmf(np.arange(MAXG + 1), max(0.05, lh))
    a = poisson.pmf(np.arange(MAXG + 1), max(0.05, la))
    M = np.outer(h, a)
    return M / M.sum()


def _num(s):
    m = re.search(r"([0-9]+\.?[0-9]*)", s or "")
    return float(m.group(1)) if m else None


def _line(spec, desc):
    if spec:
        m = re.search(r"=\s*([0-9]+\.?[0-9]*)", spec)
        if m:
            return float(m.group(1))
    return _num(desc)


class Projection:
    def __init__(self, f: dict):
        self.f = f
        # ---- balanced supremacy blend (xG-weighted when available) ----
        goals_h = (f["home_gf"] + f["away_ga"]) / 2
        goals_a = (f["away_gf"] + f["home_ga"]) / 2
        hxf, hxa = f.get("home_xgf"), f.get("home_xga")
        axf, axa = f.get("away_xgf"), f.get("away_xga")
        if None not in (hxf, hxa, axf, axa):
            xg_h = (hxf + axa) / 2
            xg_a = (axf + hxa) / 2
            base_h = 0.6 * xg_h + 0.4 * goals_h   # xG more predictive than raw goals
            base_a = 0.6 * xg_a + 0.4 * goals_a
        else:
            base_h, base_a = goals_h, goals_a
        h2h_tot = (f["h2h_home_wins"] or 0) + (f["h2h_draws"] or 0) + (f["h2h_away_wins"] or 0)
        h2h_diff = ((f["h2h_home_wins"] - f["h2h_away_wins"]) / h2h_tot) if h2h_tot else 0.0
        sup = (0.35 * (f["home_form"] - f["away_form"])
               + 0.25 * (f["home_winrate"] - f["away_winrate"])
               + 0.20 * h2h_diff
               + ELO_W * (f.get("elo_sup") or 0.0))
        tilt = max(-0.6, min(0.6, sup))
        eh = base_h * (1 + TILT * tilt) * HOME_ADJ
        ea = base_a * (1 - TILT * tilt) * AWAY_ADJ

        # ---- availability (missing players) + congestion ----
        al_h = f.get("home_attack_loss") or 0.0   # home attackers out -> home scores less
        dw_h = f.get("home_def_weak") or 0.0       # home defenders out -> away scores more
        al_a = f.get("away_attack_loss") or 0.0
        dw_a = f.get("away_def_weak") or 0.0
        eh *= (1 - al_h) * (1 + 0.6 * dw_a)
        ea *= (1 - al_a) * (1 + 0.6 * dw_h)
        for side, rest in (("h", f.get("home_rest_days")), ("a", f.get("away_rest_days"))):
            if rest is not None and rest < 4:       # fatigue from short rest
                if side == "h": eh *= 0.97
                else: ea *= 0.97
        self.exp_h = float(np.clip(eh, 0.15, 6))
        self.exp_a = float(np.clip(ea, 0.15, 6))
        self._ctx = {"al_h": al_h, "dw_h": dw_h, "al_a": al_a, "dw_a": dw_a,
                     "miss_h": f.get("home_missing"), "miss_a": f.get("away_missing")}

        # ---- half-time + second-half ----
        self.ht_h = float(np.clip((f["home_htgf"] + f["away_htga"]) / 2 * (1 + TILT * tilt), 0.05, 4)) \
            if f["home_htgf"] is not None and f["away_htga"] is not None else None
        self.ht_a = float(np.clip((f["away_htgf"] + f["home_htga"]) / 2 * (1 - TILT * tilt), 0.05, 4)) \
            if f["away_htgf"] is not None and f["home_htga"] is not None else None

        self.M = _pois_matrix(self.exp_h, self.exp_a)
        if self.ht_h is not None:
            self.Mht = _pois_matrix(self.ht_h, self.ht_a)
            self.M2h = _pois_matrix(max(0.05, self.exp_h - self.ht_h),
                                    max(0.05, self.exp_a - self.ht_a))
            self._htft = self._build_htft()
        else:
            self.Mht = self.M2h = self._htft = None

        # corners
        if None not in (f["home_cf"], f["away_ca"], f["away_cf"], f["home_ca"]):
            self.cor_h = (f["home_cf"] + f["away_ca"]) / 2
            self.cor_a = (f["away_cf"] + f["home_ca"]) / 2
        else:
            self.cor_h = self.cor_a = None

        # cards (total expected)
        self.cards = (f["home_cards"] + f["away_cards"]) \
            if f["home_cards"] is not None and f["away_cards"] is not None else None

    # ---------- helpers on the FT matrix ----------
    def _totals(self, M):
        n = M.shape[0]
        return np.add.outer(np.arange(n), np.arange(n))

    def res_1x2(self, M):
        return float(np.tril(M, -1).sum()), float(np.trace(M)), float(np.triu(M, 1).sum())

    def ou(self, M, line, over=True):
        t = self._totals(M)
        o = M[t > line].sum()
        return float(o if over else 1 - o)

    def team_ou(self, lam, line, over=True):
        k = int(np.floor(line))
        u = poisson.cdf(k, lam)
        return float((1 - u) if over else u)

    def _build_htft(self):
        """3x3 table P(HT result, FT result) from independent halves. idx 0=H,1=D,2=A."""
        tab = np.zeros((3, 3))
        n = self.Mht.shape[0]
        for h1 in range(n):
            for a1 in range(n):
                p1 = self.Mht[h1, a1]
                if p1 < 1e-9:
                    continue
                htr = 0 if h1 > a1 else (1 if h1 == a1 else 2)
                for h2 in range(self.M2h.shape[0]):
                    for a2 in range(self.M2h.shape[1]):
                        p2 = self.M2h[h2, a2]
                        if p2 < 1e-9:
                            continue
                        H, A = h1 + h2, a1 + a2
                        ftr = 0 if H > A else (1 if H == A else 2)
                        tab[htr, ftr] += p1 * p2
        return tab / tab.sum()


def _proj(f) -> Projection:
    key = f["sb_event_id"]
    p = _CACHE.get(key)
    if p is None:
        p = Projection(f)
        _CACHE[key] = p
    return p


_RES = {"home": 0, "draw": 1, "away": 2, "h": 0, "d": 1, "a": 2,
        "1": 0, "x": 1, "2": 2}


def model_prob_for(f, market_id, specifier, desc) -> float | None:
    mid = str(market_id)
    d = (desc or "").lower().strip()
    P = _proj(f)
    M = P.M

    # ---------------- full-time result family ----------------
    if mid == "1":  # 1X2
        h, dr, a = P.res_1x2(M)
        return {"home": h, "draw": dr, "away": a}.get(d)
    if mid == "10":  # Double Chance
        h, dr, a = P.res_1x2(M)
        if "draw" in d and "away" in d: return dr + a
        if "home" in d and "away" in d: return h + a
        if "home" in d and "draw" in d: return h + dr
        return None
    if mid == "11":  # Draw No Bet
        h, dr, a = P.res_1x2(M)
        s = h + a
        return (h / s) if "home" in d else (a / s) if s else None
    if mid == "12":  # Home No Bet (Draw/Away)
        h, dr, a = P.res_1x2(M)
        return dr if "draw" in d else a
    if mid == "13":  # Away No Bet (Home/Draw)
        h, dr, a = P.res_1x2(M)
        return h if "home" in d else dr

    # ---------------- totals / goals ----------------
    if mid == "18":  # total O/U
        line = _line(specifier, desc)
        if line is None: return None
        over = "over" in d
        p = P.ou(M, line, over)
        if abs(line - 2.5) < 1e-6:
            emp = (f["home_over25"] + f["away_over25"]) / 2
            emp = emp if over else 1 - emp
            p = BLEND * p + (1 - BLEND) * emp
        return p
    if mid in ("19", "20"):  # team total O/U
        line = _line(specifier, desc)
        if line is None: return None
        lam = P.exp_h if mid == "19" else P.exp_a
        return P.team_ou(lam, line, "over" in d)
    if mid == "29":  # BTTS
        no = M[0, :].sum() + M[:, 0].sum() - M[0, 0]
        yes = 1 - no
        emp = (f["home_btts"] + f["away_btts"]) / 2
        yes = BLEND * yes + (1 - BLEND) * emp
        return float(yes if "yes" in d else 1 - yes)
    if mid in ("26", "27", "28"):  # odd/even (match / home / away)
        if mid == "26":
            t = P._totals(M); odd = M[t % 2 == 1].sum()
        else:
            lam = P.exp_h if mid == "27" else P.exp_a
            ks = np.arange(0, 30); pm = poisson.pmf(ks, lam)
            odd = pm[ks % 2 == 1].sum()
        return float(odd if "odd" in d else 1 - odd)
    if mid == "21":  # exact total goals
        t = P._totals(M)
        if "+" in d:
            k = int(_num(d)); return float(M[t >= k].sum())
        k = _num(d)
        return float(M[t == int(k)].sum()) if k is not None else None
    if mid == "25":  # goal range  e.g. 0-1, 2-3, 4-6, 7+
        t = P._totals(M)
        if "+" in d:
            k = int(_num(d)); return float(M[t >= k].sum())
        m = re.findall(r"\d+", d)
        if len(m) == 2:
            lo, hi = int(m[0]), int(m[1]); return float(M[(t >= lo) & (t <= hi)].sum())
        return None
    if mid in ("548", "549", "550"):  # multigoals (match/home/away)
        if mid == "548":
            t = P._totals(M); dist = lambda lo, hi: float(M[(t >= lo) & (t <= hi)].sum()); plus = lambda k: float(M[t >= k].sum())
        else:
            lam = P.exp_h if mid == "549" else P.exp_a
            ks = np.arange(0, 30); pm = poisson.pmf(ks, lam)
            dist = lambda lo, hi: float(pm[(ks >= lo) & (ks <= hi)].sum()); plus = lambda k: float(pm[ks >= k].sum())
        if "+" in d:
            return plus(int(_num(d)))
        m = re.findall(r"\d+", d)
        return dist(int(m[0]), int(m[1])) if len(m) == 2 else None

    # ---------------- correct score / margin ----------------
    if mid in ("45", "41"):  # correct score 'x:y'
        m = re.findall(r"\d+", d)
        if len(m) >= 2:
            h, a = int(m[0]), int(m[1])
            if h <= MAXG and a <= MAXG:
                return float(M[h, a])
        return None
    if mid == "15":  # winning margin
        diff = np.subtract.outer(np.arange(M.shape[0]), np.arange(M.shape[1]))
        if "draw" in d: return float(M[diff == 0].sum())
        k = _num(d)
        if k is None: return None
        k = int(k); plus = "+" in d
        if "home" in d:
            return float(M[diff >= k].sum()) if plus else float(M[diff == k].sum())
        if "away" in d:
            return float(M[diff <= -k].sum()) if plus else float(M[diff == -k].sum())
        return None

    # ---------------- score / clean sheet ----------------
    if mid == "30":  # which team to score
        none = float(M[0, 0]); oh = float(M[1:, 0].sum()); oa = float(M[0, 1:].sum()); both = float(M[1:, 1:].sum())
        if "none" in d: return none
        if "only home" in d: return oh
        if "only away" in d: return oa
        if "both" in d: return both
        return None
    if mid == "31":  # home clean sheet (away fails to score)
        cs = float(M[:, 0].sum()); return cs if "yes" in d else 1 - cs
    if mid == "32":  # away clean sheet
        cs = float(M[0, :].sum()); return cs if "yes" in d else 1 - cs
    if mid == "33":  # home win to nil
        wtn = float(M[1:, 0].sum()); return wtn if "yes" in d else 1 - wtn
    if mid == "34":  # away win to nil
        wtn = float(M[0, 1:].sum()); return wtn if "yes" in d else 1 - wtn

    # ---------------- corners ----------------
    if mid == "166":
        if P.cor_h is None: return None
        line = _line(specifier, desc)
        return P.team_ou(P.cor_h + P.cor_a, line, "over" in d) if line else None
    if mid in ("900300", "900301"):
        if P.cor_h is None: return None
        line = _line(specifier, desc)
        lam = P.cor_h if mid == "900300" else P.cor_a
        return P.team_ou(lam, line, "over" in d) if line else None

    # ---------------- half-time family ----------------
    if mid == "47" and P._htft is not None:  # HT/FT
        parts = re.split(r"[\/]", d)
        if len(parts) == 2:
            ht = _RES.get(parts[0].strip()); ft = _RES.get(parts[1].strip())
            if ht is not None and ft is not None:
                return float(P._htft[ht, ft])
        return None
    if mid == "68" and P.Mht is not None:  # 1st half O/U
        line = _line(specifier, desc)
        return P.ou(P.Mht, line, "over" in d) if line else None
    if mid == "90" and P.M2h is not None:  # 2nd half O/U
        line = _line(specifier, desc)
        return P.ou(P.M2h, line, "over" in d) if line else None
    if mid == "60" and P.Mht is not None:  # 1st half 1X2
        h, dr, a = P.res_1x2(P.Mht)
        return {"home": h, "draw": dr, "away": a}.get(d)
    if mid == "83" and P.M2h is not None:  # 2nd half 1X2
        h, dr, a = P.res_1x2(P.M2h)
        return {"home": h, "draw": dr, "away": a}.get(d)
    if mid == "63" and P.Mht is not None:  # 1st half double chance
        h, dr, a = P.res_1x2(P.Mht)
        if "draw" in d and "away" in d: return dr + a
        if "home" in d and "away" in d: return h + a
        if "home" in d and "draw" in d: return h + dr
        return None

    # ---------------- cards / bookings (by market name) ----------------
    name = (f.get("_market_name") or "").lower()
    if ("card" in name or "booking" in name) and P.cards is not None:
        line = _line(specifier, desc)
        if line is not None and ("over" in d or "under" in d):
            return P.team_ou(P.cards, line, "over" in d)
    return None


def _ctx_note(f) -> str:
    bits = []
    mh, ma = f.get("home_missing"), f.get("away_missing")
    if mh:
        bits.append(f"home out: {mh}")
    if ma:
        bits.append(f"away out: {ma}")
    return ("  | " + "; ".join(bits)) if bits else ""


def reason(f, market_id, desc) -> str:
    return _reason_core(f, market_id, desc) + _ctx_note(f)


def _reason_core(f, market_id, desc) -> str:
    P = _proj(f)
    mid = str(market_id)
    if mid in ("1", "10", "11", "12", "13", "15", "45", "41"):
        return (f"proj {P.exp_h:.1f}-{P.exp_a:.1f}; form {f['home_form']*100:.0f}/"
                f"{f['away_form']*100:.0f}%; WR {f['home_winrate']*100:.0f}/{f['away_winrate']*100:.0f}%; "
                f"H2H {f['h2h_home_wins']}-{f['h2h_draws']}-{f['h2h_away_wins']}")
    if mid in ("18", "19", "20", "21", "25", "548", "549", "550", "26", "27", "28"):
        return (f"goals/gm home {f['home_gf']:.1f}/{f['home_ga']:.1f}, away {f['away_gf']:.1f}/"
                f"{f['away_ga']:.1f}; O2.5 {f['home_over25']*100:.0f}/{f['away_over25']*100:.0f}%; "
                f"proj {P.exp_h+P.exp_a:.1f}")
    if mid == "29":
        return f"BTTS {f['home_btts']*100:.0f}/{f['away_btts']*100:.0f}%; proj {P.exp_h:.1f}-{P.exp_a:.1f}"
    if mid in ("166", "900300", "900301"):
        return f"corners proj {P.cor_h:.1f}+{P.cor_a:.1f}={P.cor_h+P.cor_a:.1f}" if P.cor_h else "corners n/a"
    if mid in ("47", "68", "90", "60", "83", "63"):
        return f"HT proj {P.ht_h:.1f}-{P.ht_a:.1f}, FT {P.exp_h:.1f}-{P.exp_a:.1f}" if P.ht_h else "HT n/a"
    if "card" in (f.get("_market_name") or "").lower():
        return f"cards proj {P.cards:.1f} (home {f['home_cards']}, away {f['away_cards']})" if P.cards else "cards n/a"
    return f"proj {P.exp_h:.1f}-{P.exp_a:.1f}"

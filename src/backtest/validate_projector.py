"""
Validate the projector on top-5 history.

Computes the SAME features the live engine uses (recent goals/over25/BTTS/form/win-rate,
HT goals, corners, cards, H2H) from football-data history — strictly pre-match (no leakage) —
then projects 1X2 + Over/Under 2.5, compares to the de-vigged CLOSING odds, and measures:

  ROI by EDGE BUCKET  <- the key test: if higher model-edge => higher ROI, the edge is real.

Markets limited to those with historical odds (1X2, O/U 2.5). Flat 1u stakes to isolate edge.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.db.db import connect, PROJECT_ROOT
from src.models import projector

MIN_HIST = 8
LAST_N = 10
LAST_5 = 5


def _team_feats(hist: list[dict]) -> dict | None:
    if len(hist) < MIN_HIST:
        return None
    r10 = hist[-LAST_N:]
    r5 = hist[-LAST_5:]
    n = len(r10)
    gf = np.mean([h["gf"] for h in r10])
    ga = np.mean([h["ga"] for h in r10])
    over25 = np.mean([1 if h["tot"] > 2.5 else 0 for h in r10])
    btts = np.mean([1 if h["btts"] else 0 for h in r10])
    pts = sum(h["pts"] for h in r10[-5:]) / (3 * min(5, n))
    wr = np.mean([1 if h["pts"] == 3 else 0 for h in r10])
    htgf = np.mean([h["htgf"] for h in r10])
    htga = np.mean([h["htga"] for h in r10])
    cf = np.mean([h["cf"] for h in r5]) if r5 else None
    ca = np.mean([h["ca"] for h in r5]) if r5 else None
    cards = np.mean([h["cards"] for h in r5]) if r5 else None
    return dict(gf=round(gf, 3), ga=round(ga, 3), over25=round(over25, 3), btts=round(btts, 3),
                form=round(pts, 3), winrate=round(wr, 3), htgf=round(htgf, 3), htga=round(htga, 3),
                cf=round(cf, 2), ca=round(ca, 2), cards=round(cards, 2))


def devig(odds: dict) -> dict:
    raw = {k: 1 / v for k, v in odds.items() if v and v > 1}
    s = sum(raw.values())
    return {k: v / s for k, v in raw.items()} if s else {}


def run():
    with connect() as conn:
        m = pd.read_sql_query(
            """SELECT match_id,date,league,home_team,away_team,fthg,ftag,ftr,hthg,htag,
                      home_corners,away_corners,home_yellow,away_yellow,home_red,away_red
               FROM matches WHERE fthg IS NOT NULL ORDER BY date""", conn)
        odds = pd.read_sql_query(
            "SELECT match_id,market,selection,odds_decimal FROM odds WHERE is_closing=1", conn)

    # index closing odds: match_id -> {market: {selection: odds}}
    oidx: dict = defaultdict(lambda: defaultdict(dict))
    for r in odds.itertuples(index=False):
        oidx[r.match_id][r.market][r.selection] = r.odds_decimal

    hist: dict = defaultdict(list)
    h2h: dict = defaultdict(list)     # frozenset({a,b}) -> winners
    bets, calib = [], []

    for r in m.itertuples(index=False):
        hm, aw = r.home_team, r.away_team
        fh, fa = _team_feats(hist[hm]), _team_feats(hist[aw])
        pair = frozenset({hm, aw})
        meet = h2h[pair]
        hw = sum(1 for w in meet if w == hm)
        aw_w = sum(1 for w in meet if w == aw)
        dr = sum(1 for w in meet if w == "draw")

        if fh and fa:
            f = {"sb_event_id": int(r.match_id),
                 **{f"home_{k}": v for k, v in fh.items()},
                 **{f"away_{k}": v for k, v in fa.items()},
                 "home_fouls": None, "away_fouls": None,
                 "h2h_home_wins": hw, "h2h_draws": dr, "h2h_away_wins": aw_w}
            total = r.fthg + r.ftag
            mo = oidx.get(r.match_id, {})

            # 1X2
            c1 = mo.get("1X2", {})
            if len(c1) == 3:
                bp = devig(c1)
                for sel, key in (("H", "home"), ("D", "draw"), ("A", "away")):
                    mp = projector.model_prob_for(f, "1", None, key)
                    calib.append(("1X2", mp, 1.0 if r.ftr == sel else 0.0))
                    edge = mp - bp[sel]
                    if edge > 0:
                        bets.append({"market": "1X2", "edge": edge, "odds": c1[sel],
                                     "won": int(r.ftr == sel)})
            # OU25
            cou = mo.get("OU25", {})
            if len(cou) == 2:
                bp = devig(cou)
                for sel, side in (("Over", "over"), ("Under", "under")):
                    mp = projector.model_prob_for(f, "18", "total=2.5", f"{side} 2.5")
                    win = (total >= 3) if sel == "Over" else (total <= 2)
                    calib.append(("OU25", mp, 1.0 if win else 0.0))
                    edge = mp - bp[sel]
                    if edge > 0:
                        bets.append({"market": "OU25", "edge": edge, "odds": cou[sel],
                                     "won": int(win)})

        # ---- append this match to history (after using it) ----
        tot = r.fthg + r.ftag
        both = (r.fthg > 0 and r.ftag > 0)
        hp = 3 if r.ftr == "H" else (1 if r.ftr == "D" else 0)
        ap = 3 if r.ftr == "A" else (1 if r.ftr == "D" else 0)
        hist[hm].append(dict(gf=r.fthg, ga=r.ftag, tot=tot, btts=both, pts=hp,
                             htgf=r.hthg or 0, htga=r.htag or 0,
                             cf=r.home_corners or 0, ca=r.away_corners or 0,
                             cards=(r.home_yellow or 0) + (r.home_red or 0)))
        hist[aw].append(dict(gf=r.ftag, ga=r.fthg, tot=tot, btts=both, pts=ap,
                             htgf=r.htag or 0, htga=r.hthg or 0,
                             cf=r.away_corners or 0, ca=r.home_corners or 0,
                             cards=(r.away_yellow or 0) + (r.away_red or 0)))
        h2h[pair].append(hm if r.ftr == "H" else aw if r.ftr == "A" else "draw")

    _report(pd.DataFrame(bets), pd.DataFrame(calib, columns=["market", "prob", "outcome"]))


def _report(bets: pd.DataFrame, calib: pd.DataFrame):
    L = ["# Projector Validation — top-5 history (closing odds, flat 1u, edge>0 bets)\n",
         f"Generated {datetime.now(timezone.utc).isoformat()}\n"]

    def roi(df):
        if df.empty:
            return 0.0, 0, 0.0
        pnl = np.where(df["won"] == 1, df["odds"] - 1, -1).sum()
        return pnl / len(df) * 100, len(df), df["won"].mean() * 100

    r, n, hit = roi(bets)
    L.append(f"## OVERALL\n- Bets: {n} | ROI: **{r:+.2f}%** | hit {hit:.1f}%\n")

    L.append("## By market")
    for mk in sorted(bets["market"].unique()):
        rr, nn, hh = roi(bets[bets["market"] == mk])
        L.append(f"- {mk}: {nn} bets, ROI **{rr:+.2f}%**, hit {hh:.0f}%")
    L.append("")

    L.append("## ROI by EDGE BUCKET (the real-edge test)")
    L.append("| Edge | Bets | ROI | Hit |")
    L.append("|---|---|---|---|")
    buckets = [(0, .04), (.04, .08), (.08, .12), (.12, .20), (.20, 1.0)]
    for lo, hi in buckets:
        b = bets[(bets["edge"] >= lo) & (bets["edge"] < hi)]
        rr, nn, hh = roi(b)
        L.append(f"| {lo*100:.0f}-{hi*100:.0f}% | {nn} | {rr:+.2f}% | {hh:.0f}% |")
    L.append("")

    L.append("## Calibration (Brier, 0.25=coinflip)")
    for mk in sorted(calib["market"].unique()):
        s = calib[calib["market"] == mk]
        L.append(f"- {mk}: {((s['prob']-s['outcome'])**2).mean():.4f}")
    L.append("")

    overall_high = bets[bets["edge"] >= .08]
    rh, nh, _ = roi(overall_high)
    L.append("## Verdict")
    L.append(f"- High-edge (>=8%) bets: {nh}, ROI **{rh:+.2f}%**")
    L.append("- If ROI climbs with edge bucket and is positive at high edges -> edge is REAL.")
    L.append("- If ROI is negative across buckets -> model edge is illusory; do not bet.")

    out = PROJECT_ROOT / "reports" / f"validate_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"\nWritten: {out}")


if __name__ == "__main__":
    run()

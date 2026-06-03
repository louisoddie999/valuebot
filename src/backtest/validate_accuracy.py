"""
Prediction ACCURACY validation (no odds, no edge).

Tests the real question: when the stats say a pick is 75% likely, does it land ~75%?
Computes the same features from top-5 history (pre-match only), takes the MOST-LIKELY pick
per market, settles it from the actual result, and reports hit-rate by confidence bucket.

Markets tested (all settleable from the historical scoreline/corners): 1X2, Double Chance,
O/U 1.5 / 2.5 / 3.5, BTTS.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.db.db import connect, PROJECT_ROOT
from src.models import projector
from src.backtest.validate_projector import _team_feats


def run():
    with connect() as conn:
        m = pd.read_sql_query(
            """SELECT match_id,date,home_team,away_team,fthg,ftag,ftr,hthg,htag,
                      home_corners,away_corners,home_yellow,away_yellow,home_red,away_red
               FROM matches WHERE fthg IS NOT NULL ORDER BY date""", conn)

    hist: dict = defaultdict(list)
    h2h: dict = defaultdict(list)
    rows = []   # (market, confidence, hit)

    for r in m.itertuples(index=False):
        hm, aw = r.home_team, r.away_team
        fh, fa = _team_feats(hist[hm]), _team_feats(hist[aw])
        pair = frozenset({hm, aw})
        meet = h2h[pair]
        hw = sum(1 for w in meet if w == hm)
        aww = sum(1 for w in meet if w == aw)
        dr = sum(1 for w in meet if w == "draw")

        if fh and fa:
            f = {"sb_event_id": int(r.match_id),
                 **{f"home_{k}": v for k, v in fh.items()},
                 **{f"away_{k}": v for k, v in fa.items()},
                 "home_fouls": None, "away_fouls": None,
                 "h2h_home_wins": hw, "h2h_draws": dr, "h2h_away_wins": aww}
            total = r.fthg + r.ftag
            both = (r.fthg > 0 and r.ftag > 0)

            # 1X2 — most likely
            probs = {"H": projector.model_prob_for(f, "1", None, "home"),
                     "D": projector.model_prob_for(f, "1", None, "draw"),
                     "A": projector.model_prob_for(f, "1", None, "away")}
            pick = max(probs, key=probs.get)
            rows.append(("1X2", probs[pick], int(pick == r.ftr)))

            # Double Chance — most likely
            dc = {"1X": probs["H"] + probs["D"], "12": probs["H"] + probs["A"],
                  "X2": probs["D"] + probs["A"]}
            dpick = max(dc, key=dc.get)
            dwin = {"1X": r.ftr in ("H", "D"), "12": r.ftr in ("H", "A"),
                    "X2": r.ftr in ("D", "A")}[dpick]
            rows.append(("DoubleChance", dc[dpick], int(dwin)))

            # O/U lines — most likely side
            for line in (1.5, 2.5, 3.5):
                po = projector.model_prob_for(f, "18", f"total={line}", f"over {line}")
                if po is None:
                    continue
                if po >= 0.5:
                    rows.append((f"O/U{line}", po, int(total > line)))
                else:
                    rows.append((f"O/U{line}", 1 - po, int(total < line)))

            # BTTS — most likely
            py = projector.model_prob_for(f, "29", None, "yes")
            if py is not None:
                if py >= 0.5:
                    rows.append(("BTTS", py, int(both)))
                else:
                    rows.append(("BTTS", 1 - py, int(not both)))

        # update history
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

    _report(pd.DataFrame(rows, columns=["market", "conf", "hit"]))


def _report(df: pd.DataFrame):
    L = ["# Prediction Accuracy — top-5 history (most-likely pick per market)\n",
         f"Generated {datetime.now(timezone.utc).isoformat()}",
         "Reads: does a pick predicted at X% confidence actually land ~X%? (calibration)\n"]

    L.append("## Accuracy by market (most-likely pick)")
    L.append("| Market | Picks | Avg confidence | Actual hit-rate |")
    L.append("|---|---|---|---|")
    for mk in sorted(df["market"].unique()):
        s = df[df["market"] == mk]
        L.append(f"| {mk} | {len(s)} | {s['conf'].mean()*100:.0f}% | **{s['hit'].mean()*100:.1f}%** |")
    L.append("")

    L.append("## Calibration — confidence bucket vs actual hit-rate (ALL markets)")
    L.append("| Confidence | Picks | Predicted | Actual hit | Calibrated? |")
    L.append("|---|---|---|---|---|")
    for lo, hi in [(.5, .6), (.6, .7), (.7, .8), (.8, .9), (.9, 1.01)]:
        s = df[(df["conf"] >= lo) & (df["conf"] < hi)]
        if s.empty:
            continue
        pred = s["conf"].mean() * 100
        act = s["hit"].mean() * 100
        ok = "yes" if abs(pred - act) <= 5 else ("close" if abs(pred - act) <= 10 else "OFF")
        L.append(f"| {lo*100:.0f}-{hi*100:.0f}% | {len(s)} | {pred:.0f}% | **{act:.1f}%** | {ok} |")
    L.append("")
    L.append("## How to read")
    L.append("- 'Actual hit' close to 'Predicted' => predictions are TRUSTWORTHY at that confidence.")
    L.append("- High-confidence picks (80%+) landing ~80%+ => safe acca legs.")
    L.append("- This measures prediction quality from DATA only — no odds, no edge.")

    out = PROJECT_ROOT / "reports" / f"accuracy_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"\nWritten: {out}")


if __name__ == "__main__":
    run()

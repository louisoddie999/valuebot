"""
Backtest gate for the Elo blend. Walk-forward over top-5 history, online Elo (no leakage).
Sweeps projector.ELO_W and reports 1X2 accuracy, Brier (lower=better), and calibration error.
Pick the weight that helps without regressing. ELO_W=0 = current validated model (baseline).
"""
from __future__ import annotations
from collections import defaultdict
import pandas as pd
from src.db.db import connect
from src.models import projector, elo
from src.backtest.validate_projector import _team_feats

WEIGHTS = [0.0, 0.15, 0.25, 0.35, 0.50]


def run():
    with connect() as conn:
        m = pd.read_sql_query(
            """SELECT match_id,date,home_team,away_team,fthg,ftag,ftr,hthg,htag,
                      home_corners,away_corners,home_yellow,away_yellow,home_red,away_red
               FROM matches WHERE fthg IS NOT NULL ORDER BY date""", conn)
    print(f"matches: {len(m)}")

    results = {}
    for w in WEIGHTS:
        projector.ELO_W = w
        projector._CACHE.clear()
        hist = defaultdict(list); h2h = defaultdict(list); led = elo.Ledger()
        n = hit = 0; brier = 0.0; cal_conf = 0.0; cal_hit = 0
        for r in m.itertuples(index=False):
            hm, aw = r.home_team, r.away_team
            fh, fa = _team_feats(hist[hm]), _team_feats(hist[aw])
            pair = frozenset({hm, aw}); meet = h2h[pair]
            hw = sum(1 for x in meet if x == hm); aww = sum(1 for x in meet if x == aw)
            dr = sum(1 for x in meet if x == "draw")
            if fh and fa:
                f = {"sb_event_id": int(r.match_id),
                     **{f"home_{k}": v for k, v in fh.items()},
                     **{f"away_{k}": v for k, v in fa.items()},
                     "home_fouls": None, "away_fouls": None,
                     "h2h_home_wins": hw, "h2h_draws": dr, "h2h_away_wins": aww,
                     "elo_sup": led.sup(hm, aw)}
                projector._CACHE.pop(int(r.match_id), None)
                pH = projector.model_prob_for(f, "1", None, "home") or 0
                pD = projector.model_prob_for(f, "1", None, "draw") or 0
                pA = projector.model_prob_for(f, "1", None, "away") or 0
                tot = pH + pD + pA
                if tot > 0:
                    pH, pD, pA = pH/tot, pD/tot, pA/tot
                    probs = {"H": pH, "D": pD, "A": pA}
                    pick = max(probs, key=probs.get)
                    yH, yD, yA = int(r.ftr=="H"), int(r.ftr=="D"), int(r.ftr=="A")
                    brier += (pH-yH)**2 + (pD-yD)**2 + (pA-yA)**2
                    h = int(pick == r.ftr); hit += h; n += 1
                    cal_conf += probs[pick]; cal_hit += h
            # walk-forward updates
            led.feed(hm, aw, r.fthg, r.ftag)
            hp = 3 if r.ftr=="H" else (1 if r.ftr=="D" else 0)
            ap = 3 if r.ftr=="A" else (1 if r.ftr=="D" else 0)
            both=(r.fthg>0 and r.ftag>0); tt=r.fthg+r.ftag
            hist[hm].append(dict(gf=r.fthg,ga=r.ftag,tot=tt,btts=both,pts=hp,htgf=r.hthg or 0,htga=r.htag or 0,cf=r.home_corners or 0,ca=r.away_corners or 0,cards=(r.home_yellow or 0)+(r.home_red or 0)))
            hist[aw].append(dict(gf=r.ftag,ga=r.fthg,tot=tt,btts=both,pts=ap,htgf=r.htag or 0,htga=r.hthg or 0,cf=r.away_corners or 0,ca=r.home_corners or 0,cards=(r.away_yellow or 0)+(r.away_red or 0)))
            h2h[pair].append(hm if r.ftr=="H" else aw if r.ftr=="A" else "draw")
        results[w] = {"n": n, "acc": hit/n, "brier": brier/n,
                      "cal_err": abs(cal_conf/n - cal_hit/n)}
    projector.ELO_W = 0.0
    print(f"\n{'ELO_W':>6} {'1X2 acc':>9} {'Brier':>8} {'cal_err':>8}   (n picks)")
    base = results[0.0]
    for w in WEIGHTS:
        r = results[w]
        flag = " <- baseline" if w == 0 else (f"  acc {(r['acc']-base['acc'])*100:+.2f}pp, Brier {r['brier']-base['brier']:+.4f}")
        print(f"{w:>6} {r['acc']*100:>8.2f}% {r['brier']:>8.4f} {r['cal_err']:>8.4f}   ({r['n']}){flag}")
    best = min(WEIGHTS, key=lambda w: results[w]["brier"])
    print(f"\nBEST by Brier: ELO_W={best}  (acc {results[best]['acc']*100:.2f}%, Brier {results[best]['brier']:.4f})")
    return best, results


if __name__ == "__main__":
    run()

"""
Walk-forward backtest (no look-ahead).

For each league, iterate matches in date order. Refit Dixon-Coles monthly on a rolling
window of prior matches (strictly before the current month). Predict 1X2 + Over/Under 2.5,
bet at OPENING Bet365 odds, measure CLV against CLOSING odds, settle vs real results,
stake quarter-Kelly. Report ROI / hit-rate / drawdown / Brier / CLV per market + overall.

Bet price = opening odds (realistic: place early). CLV = beat the closing line.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.db.db import connect, load_config, PROJECT_ROOT
from src.models import dixon_coles as dc
from src.value.engine import implied_probs_devig, expected_value, stake_units

ROLLING_SEASONS_DAYS = 730   # ~2-season rolling training window
MIN_TRAIN_MATCHES = 200      # need enough history before betting


def load_data():
    with connect() as conn:
        matches = pd.read_sql_query(
            "SELECT match_id,date,league,season,home_team,away_team,fthg,ftag,ftr "
            "FROM matches WHERE fthg IS NOT NULL ORDER BY date", conn)
        odds = pd.read_sql_query(
            "SELECT match_id,market,selection,odds_decimal,is_closing FROM odds", conn)
    matches["date"] = pd.to_datetime(matches["date"])
    return matches, odds


def build_odds_index(odds: pd.DataFrame) -> dict:
    """match_id -> {(market, is_closing): {selection: odds}}"""
    idx: dict = {}
    for r in odds.itertuples(index=False):
        idx.setdefault(r.match_id, {}).setdefault((r.market, r.is_closing), {})[r.selection] = r.odds_decimal
    return idx


def month_key(d: pd.Timestamp) -> str:
    return f"{d.year}-{d.month:02d}"


def settle_1x2(sel: str, ftr: str) -> bool:
    return sel == ftr


def settle_ou(sel: str, total: int) -> bool:
    return (total >= 3) if sel == "Over" else (total <= 2)


def run(ev_threshold=None):
    cfg = load_config()
    v = cfg["value"]
    ev_threshold = ev_threshold if ev_threshold is not None else v["ev_threshold"]
    bankroll = cfg["bankroll"]["units"]
    kelly_mult = v["kelly_multiplier"]
    max_pct = v["max_stake_pct"]

    matches, odds = load_data()
    oidx = build_odds_index(odds)

    bets = []          # flagged value bets
    calib = []         # (market, prob, outcome) for Brier over ALL predictions w/ odds

    for league in sorted(matches["league"].unique()):
        lm = matches[matches["league"] == league].sort_values("date").reset_index(drop=True)
        params = None
        cur_month = None

        for row in lm.itertuples(index=False):
            mdate = row.date
            mk = month_key(mdate)

            # refit when month changes, using rolling window strictly before this month
            if mk != cur_month:
                train_start = mdate - pd.Timedelta(days=ROLLING_SEASONS_DAYS)
                train = lm[(lm["date"] < mdate.replace(day=1)) & (lm["date"] >= train_start)]
                if len(train) >= MIN_TRAIN_MATCHES:
                    params = dc.fit(train[["date", "home_team", "away_team", "fthg", "ftag"]],
                                    ref_date=mdate)
                else:
                    params = None
                cur_month = mk

            if params is None:
                continue

            M = dc.score_matrix(params, row.home_team, row.away_team)
            if M is None:
                continue

            total = int(row.fthg + row.ftag)
            mo = oidx.get(row.match_id, {})

            # ---- 1X2 ----
            open_1x2 = mo.get(("1X2", 0))
            close_1x2 = mo.get(("1X2", 1))
            if open_1x2 and len(open_1x2) == 3:
                probs = dc.m_1x2(M)
                # calibration record
                for s in ("H", "D", "A"):
                    calib.append(("1X2", probs[s], 1.0 if row.ftr == s else 0.0))
                for sel in ("H", "D", "A"):
                    o = open_1x2.get(sel)
                    if not o:
                        continue
                    ev = expected_value(probs[sel], o)
                    if ev > ev_threshold:
                        cl = close_1x2.get(sel) if close_1x2 else None
                        bets.append(_mk_bet(row, league, "1X2", sel, probs[sel], o, cl,
                                            settle_1x2(sel, row.ftr), bankroll, kelly_mult, max_pct))

            # ---- Over/Under 2.5 ----
            open_ou = mo.get(("OU25", 0))
            close_ou = mo.get(("OU25", 1))
            if open_ou and len(open_ou) == 2:
                pou = dc.m_over_under(M, 2.5)
                for s in ("Over", "Under"):
                    calib.append(("OU25", pou[s], 1.0 if settle_ou(s, total) else 0.0))
                for sel in ("Over", "Under"):
                    o = open_ou.get(sel)
                    if not o:
                        continue
                    ev = expected_value(pou[sel], o)
                    if ev > ev_threshold:
                        cl = close_ou.get(sel) if close_ou else None
                        bets.append(_mk_bet(row, league, "OU25", sel, pou[sel], o, cl,
                                            settle_ou(sel, total), bankroll, kelly_mult, max_pct))

        print(f"  {league}: done ({len(bets)} cumulative bets)")

    bets_df = pd.DataFrame(bets)
    calib_df = pd.DataFrame(calib, columns=["market", "prob", "outcome"])
    report = build_report(bets_df, calib_df, ev_threshold, cfg)
    _write_outputs(bets_df, report)
    print("\n" + report)


def _mk_bet(row, league, market, sel, prob, odds_open, odds_close, won,
            bankroll, kelly_mult, max_pct):
    stake = stake_units(prob, odds_open, bankroll, kelly_mult, max_pct)
    pnl = stake * (odds_open - 1.0) if won else -stake
    clv = (odds_open / odds_close - 1.0) if odds_close else None
    return {
        "date": row.date, "league": league, "match": f"{row.home_team} v {row.away_team}",
        "market": market, "selection": sel, "model_prob": round(prob, 4),
        "odds_open": odds_open, "odds_close": odds_close,
        "stake": stake, "won": int(won), "pnl": round(pnl, 2),
        "clv": round(clv, 4) if clv is not None else None,
    }


def _max_drawdown(pnl_series: np.ndarray) -> float:
    cum = np.cumsum(pnl_series)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    return float(dd.max()) if len(dd) else 0.0


def _brier(calib_df: pd.DataFrame, market: str) -> float:
    sub = calib_df[calib_df["market"] == market]
    if sub.empty:
        return float("nan")
    return float(((sub["prob"] - sub["outcome"]) ** 2).mean())


def build_report(bets: pd.DataFrame, calib: pd.DataFrame, ev_threshold, cfg) -> str:
    L = []
    L.append("# SOCCER-VALUE-BOT — Backtest Report (Deliverable #2)\n")
    L.append(f"**Generated:** {datetime.now(timezone.utc).isoformat()}")
    L.append(f"**EV threshold:** +{ev_threshold:.0%} | **Staking:** {cfg['value']['kelly_multiplier']}x Kelly, "
             f"cap {cfg['value']['max_stake_pct']:.0%} | **Bankroll:** {cfg['bankroll']['units']} units")
    L.append("**Method:** walk-forward, monthly refit, 2-season rolling window, bet at OPENING odds, "
             "CLV vs CLOSING. No look-ahead.\n")

    if bets.empty:
        L.append("## No value bets flagged. Lower threshold or add markets.\n")
        return "\n".join(L)

    def block(df, title):
        staked = df["stake"].sum()
        pnl = df["pnl"].sum()
        roi = (pnl / staked * 100) if staked else 0
        hit = df["won"].mean() * 100
        avg_odds = df["odds_open"].mean()
        dd = _max_drawdown(df.sort_values("date")["pnl"].to_numpy())
        clv_series = df["clv"].dropna()
        clv = clv_series.mean() * 100 if len(clv_series) else float("nan")
        clv_pos = (clv_series > 0).mean() * 100 if len(clv_series) else float("nan")
        return (f"### {title}\n"
                f"- Bets: **{len(df)}** | Staked: {staked:.1f}u | P&L: **{pnl:+.1f}u** | "
                f"ROI: **{roi:+.2f}%**\n"
                f"- Hit rate: {hit:.1f}% | Avg odds: {avg_odds:.2f} | Max drawdown: {dd:.1f}u\n"
                f"- CLV avg: {clv:+.2f}% | Beat-close rate: {clv_pos:.1f}%\n")

    L.append(block(bets, "OVERALL"))
    for market in sorted(bets["market"].unique()):
        L.append(block(bets[bets["market"] == market], f"Market: {market}"))

    L.append("## Calibration (Brier — lower better, 0.25 = coin-flip baseline)")
    for m in sorted(calib["market"].unique()):
        L.append(f"- {m}: **{_brier(calib, m):.4f}**")
    L.append("")

    L.append("## By odds band (overall)")
    bands = [(1.0, 1.8), (1.8, 2.5), (2.5, 4.0), (4.0, 100)]
    for lo, hi in bands:
        b = bets[(bets["odds_open"] >= lo) & (bets["odds_open"] < hi)]
        if b.empty:
            continue
        roi = b["pnl"].sum() / b["stake"].sum() * 100 if b["stake"].sum() else 0
        L.append(f"- {lo:.1f}–{hi:.1f}: {len(b)} bets, ROI {roi:+.2f}%, hit {b['won'].mean()*100:.0f}%")
    L.append("")

    L.append("## Verdict")
    overall_roi = bets["pnl"].sum() / bets["stake"].sum() * 100 if bets["stake"].sum() else 0
    clv_all = bets["clv"].dropna()
    clv_mean = clv_all.mean() * 100 if len(clv_all) else float("nan")
    L.append(f"- Overall ROI after de-vig: **{overall_roi:+.2f}%**")
    L.append(f"- Overall CLV: **{clv_mean:+.2f}%** "
             f"({'POSITIVE — real edge signal' if clv_mean > 0 else 'NEGATIVE — no proven edge'})")
    L.append("\n**Stay skeptical:** opening-odds availability varies; sample per market matters; "
             "monthly refit is coarse; xG not yet included. Treat as a first pass, not a green light.")
    return "\n".join(L)


def _write_outputs(bets: pd.DataFrame, report: str):
    rep_dir = PROJECT_ROOT / "reports"
    rep_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    (rep_dir / f"backtest_{stamp}.md").write_text(report, encoding="utf-8")
    if not bets.empty:
        bets.to_csv(rep_dir / f"backtest_bets_{stamp}.csv", index=False)
    print(f"Report + bets written to {rep_dir}")


if __name__ == "__main__":
    run()

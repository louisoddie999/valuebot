"""
Tiered accumulator builder.

Reads SportyBet ingested selections and assembles SAFE / VALUE / LONGSHOT slips.
Correlation-aware (max one leg per match). Probability source pluggable:
  - book  : SportyBet's own book_prob (default now — slip MECHANICS, NO edge yet)
  - model : our calibrated model prob (once stat brain is wired)

Output: reports/slips_<UTC>.md  +  .json

Usage:  python -m src.punter.accumulator_builder
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, date, timedelta
from pathlib import Path

from src.db.db import connect, load_config, PROJECT_ROOT
from src.models import projector, calibration
from src.models import elo as _elo


# ---------------- date scope ----------------

def parse_scope(scope: str | None) -> tuple[str, str, str]:
    """
    Resolve a scope string to (start_date, end_date, label) as YYYY-MM-DD.
    Accepts: today | tomorrow | week (Mon-Sun) | weekend (Fri-Sun) |
             YYYY-MM-DD | YYYY-MM-DD:YYYY-MM-DD
    """
    t = date.today()
    s = (scope or "today").strip().lower()

    if s == "today":
        return t.isoformat(), t.isoformat(), "Today"
    if s == "tomorrow":
        d = t + timedelta(days=1)
        return d.isoformat(), d.isoformat(), "Tomorrow"
    if s == "week":                      # calendar Mon-Sun
        mon = t - timedelta(days=t.weekday())
        sun = mon + timedelta(days=6)
        return mon.isoformat(), sun.isoformat(), f"This week ({mon}–{sun})"
    if s == "weekend":                   # Fri-Sun of current week
        fri = t - timedelta(days=t.weekday()) + timedelta(days=4)
        sun = fri + timedelta(days=2)
        return fri.isoformat(), sun.isoformat(), f"Weekend ({fri}–{sun})"
    if s in ("ahead", "upcoming", "next", "next7"):   # ROLLING 7-day window — not Monday-locked
        d = t + timedelta(days=7)
        return t.isoformat(), d.isoformat(), f"Next 7 days ({t}–{d})"
    if ":" in s:                         # custom range
        a, b = s.split(":", 1)
        return a.strip(), b.strip(), f"{a.strip()} to {b.strip()}"
    # single explicit date
    return s, s, s


def interactive_scope() -> str:
    print("\nDate scope:")
    print("  1) Today   2) Tomorrow   3) This week (Mon-Sun)   4) Weekend (Fri-Sun)")
    print("  5) Specific date (YYYY-MM-DD)   6) Custom range (YYYY-MM-DD:YYYY-MM-DD)")
    choice = input("Choose [1-6]: ").strip()
    mapping = {"1": "today", "2": "tomorrow", "3": "week", "4": "weekend"}
    if choice in mapping:
        return mapping[choice]
    if choice == "5":
        return input("Date (YYYY-MM-DD): ").strip()
    if choice == "6":
        return input("Range (YYYY-MM-DD:YYYY-MM-DD): ").strip()
    return "today"


def load_candidate_legs(prob_source: str, min_odds: float, max_odds: float) -> list[dict]:
    """One row per active selection on an upcoming SportyBet event."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        rows = conn.execute(
            """SELECT e.event_id, e.home_team, e.away_team, e.tournament, e.kickoff_ts,
                      o.market_name, o.specifier, o.outcome_desc, o.odds, o.book_prob
               FROM sb_odds o JOIN sb_events e ON e.event_id = o.event_id
               WHERE o.odds >= ? AND o.odds <= ? AND o.book_prob IS NOT NULL
                 AND (e.kickoff_ts IS NULL OR e.kickoff_ts > ?)""",
            (min_odds, max_odds, now_iso),
        ).fetchall()

    legs = []
    for r in rows:
        prob = r["book_prob"]   # model source slots in here later
        legs.append({
            "event_id": r["event_id"],
            "match": f"{r['home_team']} v {r['away_team']}",
            "tournament": r["tournament"],
            "kickoff": r["kickoff_ts"],
            "market": r["market_name"],
            "specifier": r["specifier"],
            "selection": r["outcome_desc"],
            "odds": round(r["odds"], 2),
            "prob": prob,
        })
    return legs


def load_model_legs(min_odds: float, max_odds: float, min_conf: float,
                    start_date: str, end_date: str) -> list[dict]:
    """
    Confidence-based predictions: keep picks the stats back at >= min_conf probability,
    restricted to fixtures kicking off within [start_date, end_date]. Ranked by confidence.
    Selection is driven by DATA (model probability), not odds or edge.
    """
    with connect() as conn:
        feat_rows = {r["sb_event_id"]: dict(r)
                     for r in conn.execute("SELECT * FROM sf_features").fetchall()}
        odds_rows = conn.execute(
            """SELECT o.event_id, e.home_team, e.away_team, e.tournament, e.category, e.kickoff_ts,
                      o.market_id, o.market_name, o.specifier, o.outcome_id, o.outcome_desc,
                      o.odds, o.book_prob
               FROM sb_odds o JOIN sb_events e ON e.event_id = o.event_id
               WHERE o.odds >= ? AND o.odds <= ?
                 AND substr(e.kickoff_ts, 1, 10) BETWEEN ? AND ?
                 AND (e.kickoff_ts IS NULL OR e.kickoff_ts > ?)""",
            (min_odds, max_odds, start_date, end_date,
             datetime.now(timezone.utc).isoformat()),
        ).fetchall()
        cal = calibration.load_curve(conn, "football")   # per-sport learned correction
        _eloidx = _elo.load_index(conn)   # live Elo (top-5; absent -> no effect)
    _elo_memo = {}   # per-event cache (fuzzy match is expensive — do once per event, not per odds row)

    legs = []
    for r in odds_rows:
        f = feat_rows.get(r["event_id"])
        if not f:
            continue
        f["_market_name"] = r["market_name"]   # for card-market detection
        _ek = r["event_id"]
        if _ek not in _elo_memo:
            _elo_memo[_ek] = _elo.live_sup(r["home_team"], r["away_team"], _eloidx)
        f["elo_sup"] = _elo_memo[_ek]
        mp = projector.model_prob_for(f, r["market_id"], r["specifier"], r["outcome_desc"])
        if mp is None:
            continue
        mp = calibration.apply(mp, cal)   # self-recalibration: correct toward real hit-rate
        if mp < min_conf:
            continue
        legs.append({
            "event_id": r["event_id"],
            "match": f"{r['home_team']} v {r['away_team']}",
            "tournament": r["tournament"], "country": r["category"], "kickoff": r["kickoff_ts"],
            "market": r["market_name"], "market_id": r["market_id"],
            "specifier": r["specifier"], "outcome_id": r["outcome_id"],
            "selection": r["outcome_desc"], "odds": round(r["odds"], 2),
            "prob": mp, "confidence": round(mp, 4),
            "reason": projector.reason(f, r["market_id"], r["outcome_desc"]),
        })
    return legs


def load_basketball_legs(min_conf: float, start_date: str, end_date: str) -> list[dict]:
    """Basketball legs: project per event from bb_features, score each market via the
    basketball projector. Same leg shape as football so slips/booking are sport-agnostic."""
    from src.models import basketball_projector as bp
    from src.models import calibration
    with connect() as conn:
        feats = {r["sb_event_id"]: dict(r)
                 for r in conn.execute("SELECT * FROM bb_features").fetchall()}
        odds_rows = conn.execute(
            """SELECT o.event_id, e.home_team, e.away_team, e.tournament, e.category, e.kickoff_ts,
                      o.market_id, o.market_name, o.specifier, o.outcome_id, o.outcome_desc, o.odds
               FROM sb_odds o JOIN sb_events e ON e.event_id = o.event_id
               WHERE e.sport='Basketball' AND o.odds >= 1.20 AND o.odds <= 1.90
                 AND substr(e.kickoff_ts,1,10) BETWEEN ? AND ?
                 AND (e.kickoff_ts IS NULL OR e.kickoff_ts > ?)""",
            (start_date, end_date, datetime.now(timezone.utc).isoformat())).fetchall()
        cal = calibration.load_curve(conn, "basketball")

    legs = []
    for r in odds_rows:
        f = feats.get(r["event_id"])
        if not f:
            continue
        proj = {"exp_total": f["exp_total"], "exp_margin": f["exp_margin"],
                "pts_home": f["pts_home"], "pts_away": f["pts_away"], "poss": f["poss"]}
        mp = bp.model_prob_for(proj, r["market_id"], r["specifier"], r["outcome_desc"])
        if mp is None:
            continue
        mp = max(0.02, min(0.97, mp))   # no pick is truly 100% — credible ceiling
        mp = calibration.apply(mp, cal)
        if mp < min_conf:
            continue
        legs.append({
            "event_id": r["event_id"], "match": f"{r['home_team']} v {r['away_team']}",
            "tournament": r["tournament"], "country": r["category"], "kickoff": r["kickoff_ts"],
            "market": r["market_name"], "market_id": r["market_id"],
            "specifier": r["specifier"], "outcome_id": r["outcome_id"],
            "selection": r["outcome_desc"], "odds": round(r["odds"], 2),
            "prob": mp, "confidence": round(mp, 4),
            "reason": bp.reason(proj, r["market_id"], r["outcome_desc"]),
        })
    return legs


def build_slip(legs: list[dict], min_legs: int, max_legs: int,
               leg_min: float, leg_max: float) -> dict | None:
    """
    Stack modest, stat-confident legs into one slip.
    Tier is defined by LEG COUNT (not by chasing big single-game odds).
    Every leg odds in [leg_min, leg_max]. Legs ranked by stat confidence (edge desc) —
    strongest predictions first. One leg per match (correlation guard).
    """
    pool = [l for l in legs if leg_min <= l["odds"] <= leg_max]
    pool.sort(key=lambda l: -l["prob"])   # highest-confidence predictions first

    slip, used = [], set()
    comb_odds, comb_prob = 1.0, 1.0
    for leg in pool:
        if leg["event_id"] in used:
            continue
        if max_legs and len(slip) >= max_legs:   # max_legs None/0 => uncapped
            break
        slip.append(leg)
        used.add(leg["event_id"])
        comb_odds *= leg["odds"]
        comb_prob *= leg["prob"]

    if len(slip) < min_legs:
        return None
    return {
        "combined_odds": round(comb_odds, 2),
        "combined_prob": round(comb_prob, 8),
        "legs": slip,
    }


def build_slip_chunks(legs: list[dict], min_legs: int, leg_min: float, leg_max: float,
                      chunk_size: int, max_chunks: int | None = None) -> list[dict]:
    """
    Split the confidence-ranked, in-band, one-per-event pool into consecutive disjoint
    slips of up to chunk_size legs each. Powers numbered sub-slips (LONGSHOT 1 / 2 / ...) and
    multiple SAFE / MID tickets so a 60-leg pool becomes several individually-bookable slips
    (SportyBet betslip holds 50 selections; oversized single slips can't load).
    """
    pool = [l for l in legs if leg_min <= l["odds"] <= leg_max]
    pool.sort(key=lambda l: -l["prob"])
    seen, uniq = set(), []
    for l in pool:
        if l["event_id"] in seen:
            continue
        seen.add(l["event_id"]); uniq.append(l)

    chunks = []
    for i in range(0, len(uniq), chunk_size):
        grp = uniq[i:i + chunk_size]
        if len(grp) < min_legs:
            break
        co, cp = 1.0, 1.0
        for l in grp:
            co *= l["odds"]; cp *= l["prob"]
        chunks.append({"combined_odds": round(co, 2), "combined_prob": round(cp, 8), "legs": grp})
        if max_chunks and len(chunks) >= max_chunks:
            break
    return chunks


def run(scope: str | None = None):
    cfg = load_config()
    acc = cfg["accumulators"]
    start_d, end_d, label = parse_scope(scope)
    print(f"\nScope: {label}  [{start_d} .. {end_d}]")

    if acc["prob_source"] == "model":
        legs = load_model_legs(acc["min_leg_odds"], acc["max_leg_odds"],
                               acc.get("min_confidence", 0.65), start_d, end_d)
        print(f"high-confidence predictions in window (>= "
              f"{acc.get('min_confidence', 0.65)*100:.0f}%): {len(legs)}")
    else:
        legs = load_candidate_legs(acc["prob_source"], acc["min_leg_odds"], acc["max_leg_odds"])
        print(f"Candidate legs: {len(legs)}")

    slips = {}
    for tier, t in acc["tiers"].items():
        slip = build_slip(legs, t["min_legs"], t["max_legs"], t["leg_min"], t["leg_max"])
        slips[tier] = slip
        if slip:
            print(f"  {tier}: {len(slip['legs'])} legs, odds {slip['combined_odds']:.0f}, "
                  f"hit~{slip['combined_prob']*100:.3f}%")
        else:
            print(f"  {tier}: not enough matched legs (need {t['min_legs']}+, "
                  f"have fewer in {t['leg_min']}-{t['leg_max']} band)")

    _write(slips, acc["prob_source"], label)


def _write(slips: dict, prob_source: str, label: str = ""):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    rep = PROJECT_ROOT / "reports"
    rep.mkdir(exist_ok=True)
    (rep / f"slips_{stamp}.json").write_text(json.dumps(slips, indent=2, ensure_ascii=False),
                                             encoding="utf-8")

    L = [f"# Punter Slips — {label} — {datetime.now(timezone.utc).isoformat()}",
         f"**Prob source:** {prob_source}"
         + ("  ⚠️ book_prob = SportyBet's own number, NO edge yet — structure demo only"
            if prob_source == "book" else "  (our model)"), ""]
    for tier, slip in slips.items():
        L.append(f"## {tier}")
        if not slip:
            L.append("_No slip assembled in target band._\n")
            continue
        L.append(f"**Combined odds: {slip['combined_odds']} | "
                 f"Est. hit chance: {slip['combined_prob']*100:.2f}%** | "
                 f"{len(slip['legs'])} legs\n")
        has_conf = "confidence" in slip["legs"][0]
        if has_conf:
            L.append("| # | Match | Market | Prediction | Confidence | Odds | Why (data) |")
            L.append("|---|---|---|---|---|---|---|")
            for i, leg in enumerate(slip["legs"], 1):
                spec = f" ({leg['specifier']})" if leg["specifier"] else ""
                L.append(f"| {i} | {leg['match']} | {leg['market']}{spec} | {leg['selection']} | "
                         f"**{leg['confidence']*100:.0f}%** | {leg['odds']} | {leg['reason']} |")
        else:
            L.append("| # | Match | Market | Selection | Odds | Book prob |")
            L.append("|---|---|---|---|---|---|")
            for i, leg in enumerate(slip["legs"], 1):
                spec = f" ({leg['specifier']})" if leg["specifier"] else ""
                L.append(f"| {i} | {leg['match']} | {leg['market']}{spec} | "
                         f"{leg['selection']} | {leg['odds']} | {leg['prob']*100:.1f}% |")
        L.append("")
    (rep / f"slips_{stamp}.md").write_text("\n".join(L), encoding="utf-8")
    print(f"Slips written to {rep}")


if __name__ == "__main__":
    # scope from CLI arg (today|tomorrow|week|weekend|YYYY-MM-DD|YYYY-MM-DD:YYYY-MM-DD)
    # or interactive menu if no arg and a terminal is attached.
    if len(sys.argv) > 1:
        run(sys.argv[1])
    elif sys.stdin.isatty():
        run(interactive_scope())
    else:
        run("today")

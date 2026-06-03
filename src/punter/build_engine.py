"""
Parametric slip engine — the brain behind "build me ~300 odds for the week" and
"give me 5 different slips". Deterministic: picks from already-predicted, confidence-ranked
legs. The Gemini chat layer only translates language into these parameters; it never invents picks.

build_to_target  — stack confident legs until combined odds hit a target.
build_n_variants — produce N disjoint slips (genuinely different games).
apply_filters    — league / market / min-confidence / odds-range narrowing.
"""
from __future__ import annotations

import re

DEFAULT_TOL = 0.20      # accept combined odds within ±20% of target
HARD_MAX_LEGS = 50      # SportyBet betslip ceiling


def apply_filters(legs, league=None, market=None, min_conf=None,
                  odds_min=None, odds_max=None) -> list:
    out = legs
    if league:
        lo = league.lower()
        out = [l for l in out if lo in (l.get("tournament") or "").lower()
               or lo in (l.get("country") or "").lower()]
    if market:
        mo = market.lower()
        out = [l for l in out if mo in (l.get("market") or "").lower()]
    if min_conf is not None:
        out = [l for l in out if l["prob"] >= min_conf]
    if odds_min is not None:
        out = [l for l in out if l["odds"] >= odds_min]
    if odds_max is not None:
        out = [l for l in out if l["odds"] <= odds_max]
    return out


def _slip(legs: list) -> dict:
    odds = 1.0
    prob = 1.0
    for l in legs:
        odds *= l["odds"]
        prob *= l["prob"]
    return {"combined_odds": round(odds, 2), "hit_estimate": round(prob * 100, 4),
            "n_legs": len(legs), "legs": legs}


def build_to_target(legs, target_odds=None, target_legs=None,
                    max_legs=HARD_MAX_LEGS, tol=DEFAULT_TOL, used_events=None) -> dict | None:
    """
    Stack highest-confidence legs (one per match) toward a target.
    Provide target_odds OR target_legs. used_events lets callers keep variants disjoint.
    """
    used_events = used_events if used_events is not None else set()
    pool = sorted([l for l in legs if l["event_id"] not in used_events],
                  key=lambda l: -l["prob"])
    max_legs = min(max_legs, HARD_MAX_LEGS)
    if target_legs:
        max_legs = min(max_legs, int(target_legs))

    chosen, seen = [], set()
    odds = 1.0
    for l in pool:
        if l["event_id"] in seen:
            continue
        if len(chosen) >= max_legs:
            break
        chosen.append(l); seen.add(l["event_id"]); odds *= l["odds"]
        if target_odds and odds >= target_odds * (1 - tol):
            break
        if target_legs and len(chosen) >= int(target_legs):
            break

    if not chosen:
        return None
    if target_odds and odds < target_odds * (1 - tol) and len(chosen) < 3:
        return None
    return _slip(chosen)


def build_n_variants(legs, n: int, target_odds=None, target_legs=None,
                     max_legs=HARD_MAX_LEGS) -> list[dict]:
    """N disjoint slips — each uses different matches so they're genuinely different bets."""
    used: set = set()
    out = []
    for _ in range(max(1, int(n))):
        s = build_to_target(legs, target_odds=target_odds, target_legs=target_legs,
                            max_legs=max_legs, used_events=used)
        if not s:
            break
        out.append(s)
        used.update(l["event_id"] for l in s["legs"])
    return out


def parse_intent(text: str) -> dict:
    """Lightweight fallback NL parse (used if Gemini is not configured)."""
    t = text.lower()
    out: dict = {"scope": "today", "count": 1}
    _wd = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
           "friday": 4, "saturday": 5, "sunday": 6}
    _hit_day = next((n for n in _wd if n in t), None)
    if _hit_day:
        from datetime import date, timedelta
        td = date.today()
        out["scope"] = (td + timedelta(days=(_wd[_hit_day] - td.weekday()) % 7)).isoformat()
    else:
        for kw, sc in [("weekend", "weekend"), ("week", "week"), ("tomorrow", "tomorrow"), ("today", "today")]:
            if kw in t:
                out["scope"] = sc; break
    for _tn in ("longshot", "long shot", "mid", "safe"):
        if _tn in t:
            out["tier"] = "longshot" if "long" in _tn else _tn
            break
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:odds|odd)", t)
    if m:
        out["target_odds"] = float(m.group(1))
    m = re.search(r"(\d+)\s*(?:different|slips?|variations?|options?|tickets?)", t)
    if m:
        out["count"] = int(m.group(1))
    m = re.search(r"(\d+)\s*(?:legs?|games?|matches?|selections?|fold)", t)
    if m:
        out["target_legs"] = int(m.group(1))
    for lg in ("premier", "epl", "la liga", "serie a", "bundesliga", "ligue 1"):
        if lg in t:
            out["league"] = lg
    if "corner" in t:
        out["market"] = "corner"
    elif "over/under" in t or "over 2.5" in t or "goals" in t:
        out["market"] = "over/under"
    return out

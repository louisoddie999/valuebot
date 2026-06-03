"""
Basketball projector — pure-analysis predictions from team stats (NOT edge vs odds).

Basketball points ~ NORMAL distribution (not Poisson). Project expected total + margin from
pace + offensive/defensive efficiency, then read every market off normal CDFs.

Inputs per team (bb_features, season + last-N blended, opponent-adjusted):
  pace, off_rtg (pts/100 poss), def_rtg (pts allowed/100). Form/rest/injuries applied upstream.
"""
from __future__ import annotations

import math

LG_PACE = 100.0
LG_ORTG = 114.0
HOME_PTS = 2.6
SD_TOTAL = 11.5
SD_MARGIN = 12.0
REVERT = 0.25

SHARE = {"H1": 0.50, "H2": 0.50, "Q": 0.25}
SD_SCALE = {"H1": 0.72, "H2": 0.72, "Q": 0.52}


def _phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _revert(x, anchor):
    return (1 - REVERT) * x + REVERT * anchor


def project(home, away):
    try:
        ph, pa = float(home["pace"]), float(away["pace"])
        oh, dh = _revert(float(home["off_rtg"]), LG_ORTG), _revert(float(home["def_rtg"]), LG_ORTG)
        oa, da = _revert(float(away["off_rtg"]), LG_ORTG), _revert(float(away["def_rtg"]), LG_ORTG)
    except (KeyError, TypeError, ValueError):
        return None
    poss = (ph + pa) / 2.0
    home_per100 = (oh + da) / 2.0
    away_per100 = (oa + dh) / 2.0
    pts_home = poss / 100.0 * home_per100 + HOME_PTS
    pts_away = poss / 100.0 * away_per100
    return {"exp_total": round(pts_home + pts_away, 2), "exp_margin": round(pts_home - pts_away, 2),
            "pts_home": round(pts_home, 2), "pts_away": round(pts_away, 2), "poss": round(poss, 1)}


def _scale(period, table, full=1.0):
    return table.get(period, 1.0) if period != "FULL" else full


def prob_total_over(proj, line, period="FULL"):
    mu = proj["exp_total"] * _scale(period, SHARE)
    sd = SD_TOTAL * _scale(period, SD_SCALE)
    return 1.0 - _phi((line - mu) / sd)


def prob_team_total_over(proj, side, line, period="FULL"):
    pts = proj["pts_home"] if side == "home" else proj["pts_away"]
    mu = pts * _scale(period, SHARE)
    sd = (SD_TOTAL / math.sqrt(2)) * _scale(period, SD_SCALE)
    return 1.0 - _phi((line - mu) / sd)


def prob_home_covers(proj, hcp, period="FULL"):
    mu = proj["exp_margin"] * _scale(period, SHARE)
    sd = SD_MARGIN * _scale(period, SD_SCALE)
    return 1.0 - _phi(((-hcp) - mu) / sd)


def prob_home_win(proj, period="FULL"):
    mu = proj["exp_margin"] * _scale(period, SHARE)
    sd = SD_MARGIN * _scale(period, SD_SCALE)
    return 1.0 - _phi((0.0 - mu) / sd)


def model_prob_for(proj, market_id, specifier, outcome_desc):
    if not proj:
        return None
    mid = str(market_id)
    spec = specifier or ""
    od = (outcome_desc or "").lower()

    def _num(key):
        for part in spec.split("|"):
            if part.startswith(key + "="):
                try: return float(part.split("=", 1)[1])
                except ValueError: return None
        return None

    period = "FULL"
    if mid in ("68", "66", "69", "70", "60", "64"): period = "H1"
    elif mid in ("90", "88", "83", "86"): period = "H2"
    elif mid in ("236", "303", "756", "757", "235"): period = "Q"

    if mid in ("225", "18", "68", "90", "236"):
        line = _num("total")
        if line is None: return None
        p = prob_total_over(proj, line, period)
        return p if "over" in od else (1 - p)

    if mid in ("227", "228", "69", "70", "756", "757"):
        line = _num("total")
        if line is None: return None
        side = "home" if mid in ("227", "69", "756") else "away"
        p = prob_team_total_over(proj, side, line, period)
        return p if "over" in od else (1 - p)

    if mid in ("223", "66", "88", "303"):
        hcp = _num("hcp")
        if hcp is None: return None
        if "home" in od: return prob_home_covers(proj, hcp, period)
        if "away" in od: return 1 - prob_home_covers(proj, hcp, period)
        return None

    if mid in ("219", "1", "60", "83", "235", "11", "64", "86"):
        pw = prob_home_win(proj, period)
        if "home" in od: return pw
        if "away" in od: return 1 - pw
        return None

    return None


def reason(proj, market_id, outcome_desc):
    if not proj:
        return ""
    return (f"proj total {proj['exp_total']:.0f} - margin {proj['exp_margin']:+.0f} "
            f"(home {proj['pts_home']:.0f}-{proj['pts_away']:.0f} away - pace {proj['poss']:.0f})")


if __name__ == "__main__":
    home = {"pace": 102, "off_rtg": 118, "def_rtg": 110}
    away = {"pace": 98, "off_rtg": 112, "def_rtg": 116}
    p = project(home, away)
    print("projection:", p)
    print("Total Over 225.5 :", round(model_prob_for(p, "225", "total=225.5", "Over 225.5"), 3))
    print("Total Under 225.5:", round(model_prob_for(p, "225", "total=225.5", "Under 225.5"), 3))
    print("Home -4.5 cover  :", round(model_prob_for(p, "223", "hcp=-4.5", "Home (-4.5)"), 3))
    print("Away +4.5 cover  :", round(model_prob_for(p, "223", "hcp=-4.5", "Away (+4.5)"), 3))
    print("Home ML          :", round(model_prob_for(p, "219", None, "Home"), 3))
    print("Away ML          :", round(model_prob_for(p, "219", None, "Away"), 3))
    print("Home team Over113 :", round(model_prob_for(p, "227", "total=113.5", "Over 113.5"), 3))
    print("1H total Over 112 :", round(model_prob_for(p, "68", "total=112.5", "Over 112.5"), 3))
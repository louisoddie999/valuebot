"""
FastAPI backend — serves the prediction engine to the Next.js dashboard.

Endpoints:
  GET  /api/health
  GET  /api/fixtures?scope=today           -> fixtures in scope + top prediction each
  GET  /api/match/{event_id}               -> all modeled markets for one match
  GET  /api/slips?scope=week               -> SAFE / MID / LONGSHOT slips
  GET  /api/accuracy                        -> validated calibration stats (trust page)

Run:  uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

from collections import defaultdict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()  # load GOOGLE_AI_API_KEY from project-root .env

from src.db.db import connect, load_config
from src.models import projector
from src.punter.accumulator_builder import parse_scope, load_model_legs, build_slip, build_slip_chunks
from src.punter.build_engine import apply_filters, build_n_variants, parse_intent
from src.booking.sportybet_booking import create_booking_code
from src.results.settle import run as settle_run

app = FastAPI(title="Soccer Value Bot API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://[a-z0-9-]+\.vercel\.app",
    allow_methods=["*"], allow_headers=["*"],
)


def _cfg():
    return load_config()["accumulators"]


@app.get("/api/health")
def health():
    with connect() as c:
        ev = c.execute("SELECT COUNT(*) FROM sb_events").fetchone()[0]
        ft = c.execute("SELECT COUNT(*) FROM sf_features").fetchone()[0]
    return {"status": "ok", "events": ev, "enriched": ft}


@app.get("/api/fixtures")
def fixtures(scope: str = "today"):
    start_d, end_d, label = parse_scope(scope)
    acc = _cfg()
    legs = load_model_legs(acc["min_leg_odds"], acc["max_leg_odds"],
                           acc.get("min_confidence", 0.65), start_d, end_d)
    top = {}
    for l in legs:
        cur = top.get(l["event_id"])
        if not cur or l["prob"] > cur["confidence"]:
            top[l["event_id"]] = {"market": l["market"], "selection": l["selection"],
                                  "confidence": round(l["prob"], 4), "odds": l["odds"],
                                  "market_id": l["market_id"], "specifier": l["specifier"],
                                  "outcome_id": l["outcome_id"]}

    with connect() as c:
        rows = c.execute(
            """SELECT e.event_id, e.home_team, e.away_team, e.tournament, e.category, e.kickoff_ts,
                      (SELECT 1 FROM sf_features f WHERE f.sb_event_id=e.event_id) AS enriched
               FROM sb_events e
               WHERE substr(e.kickoff_ts,1,10) BETWEEN ? AND ?
               ORDER BY e.kickoff_ts""", (start_d, end_d)).fetchall()
        updated = c.execute("SELECT MAX(computed_at) FROM sf_features").fetchone()[0]

    out = []
    for r in rows:
        out.append({
            "event_id": r["event_id"], "home": r["home_team"], "away": r["away_team"],
            "league": r["tournament"], "country": r["category"], "kickoff": r["kickoff_ts"],
            "enriched": bool(r["enriched"]), "top_pick": top.get(r["event_id"]),
        })
    return {"scope": label, "start": start_d, "end": end_d, "count": len(out),
            "updated": updated, "fixtures": out}


@app.get("/api/match/{event_id}")
def match(event_id: str):
    with connect() as c:
        ev = c.execute("SELECT * FROM sb_events WHERE event_id=?", (event_id,)).fetchone()
        if not ev:
            raise HTTPException(404, "event not found")
        f = c.execute("SELECT * FROM sf_features WHERE sb_event_id=?", (event_id,)).fetchone()
        odds = c.execute(
            """SELECT market_id, market_name, specifier, outcome_id, outcome_desc, odds, book_prob
               FROM sb_odds WHERE event_id=? AND book_prob IS NOT NULL""", (event_id,)).fetchall()

    info = {"event_id": ev["event_id"], "home": ev["home_team"], "away": ev["away_team"],
            "league": ev["tournament"], "country": ev["category"],
            "kickoff": ev["kickoff_ts"], "enriched": bool(f)}
    if not f:
        return {**info, "predictions": [], "note": "not enriched yet"}

    fd = dict(f)
    info["context"] = {"home_missing": fd.get("home_missing"), "away_missing": fd.get("away_missing"),
                       "home_rest": fd.get("home_rest_days"), "away_rest": fd.get("away_rest_days")}
    preds = []
    for o in odds:
        fd["_market_name"] = o["market_name"]
        mp = projector.model_prob_for(fd, o["market_id"], o["specifier"], o["outcome_desc"])
        if mp is None:
            continue
        preds.append({"market": o["market_name"], "specifier": o["specifier"],
                      "selection": o["outcome_desc"], "confidence": round(mp, 4),
                      "odds": o["odds"], "reason": projector.reason(fd, o["market_id"], o["outcome_desc"]),
                      "market_id": o["market_id"], "outcome_id": o["outcome_id"]})
    preds.sort(key=lambda x: -x["confidence"])
    return {**info, "modeled": len(preds), "offered": len(odds), "predictions": preds}


@app.get("/api/slips")
def slips(scope: str = "today"):
    start_d, end_d, label = parse_scope(scope)
    cfg = load_config()
    acc = cfg["accumulators"]
    legs = load_model_legs(acc["min_leg_odds"], acc["max_leg_odds"],
                           acc.get("min_confidence", 0.65), start_d, end_d)
    BOOK_CAP = 40  # SportyBet betslip holds 50 selections; stay under so every sub-slip loads
    plan = {  # tier -> (chunk_size, max_sub_slips)  longshot = MANY legs split into bookable chunks
        "SAFE": (5, 6), "MID": (12, 4), "LONGSHOT": (BOOK_CAP, None),
    }
    result = {"scope": label, "leg_pool": len(legs), "tiers": {}}
    for tier, t in acc["tiers"].items():
        csize, maxc = plan.get(tier, (t["max_legs"] or BOOK_CAP, None))
        chunks = build_slip_chunks(legs, t["min_legs"], t["leg_min"], t["leg_max"], csize, maxc)
        result["tiers"][tier] = [
            {
                "combined_odds": s["combined_odds"],
                "hit_estimate": round(s["combined_prob"] * 100, 3),
                "legs": [{"match": l["match"], "market": l["market"], "selection": l["selection"],
                          "confidence": round(l["prob"], 4), "odds": l["odds"], "reason": l["reason"],
                          "event_id": l["event_id"], "market_id": l["market_id"],
                          "specifier": l["specifier"], "outcome_id": l["outcome_id"],
                          "league": l["tournament"], "country": l["country"], "kickoff": l["kickoff"]}
                         for l in s["legs"]],
            }
            for s in chunks
        ]
    return result


class BookingLeg(BaseModel):
    event_id: str
    market_id: str
    specifier: str | None = ""
    outcome_id: str
    odds: float


class BookingReq(BaseModel):
    legs: list[BookingLeg]


def _track_booked(slip_id: str, legs: list[dict]):
    """Enrich each booked leg from DB + log it as a pending tracked pick."""
    now = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        for lg in legs:
            eid, mid, oid = lg["event_id"], str(lg["market_id"]), str(lg["outcome_id"])
            spec = lg.get("specifier") or ""
            ev = conn.execute("SELECT home_team, away_team, tournament, kickoff_ts FROM sb_events WHERE event_id=?", (eid,)).fetchone()
            od = conn.execute(
                "SELECT market_name, outcome_desc FROM sb_odds WHERE event_id=? AND market_id=? AND outcome_id=? "
                "AND IFNULL(specifier,'')=? LIMIT 1", (eid, mid, oid, spec)).fetchone()
            f = conn.execute("SELECT * FROM sf_features WHERE sb_event_id=?", (eid,)).fetchone()
            conf = None
            if f and od:
                fd = dict(f); fd["_market_name"] = od["market_name"]
                conf = projector.model_prob_for(fd, mid, lg.get("specifier"), od["outcome_desc"])
            conn.execute(
                """INSERT INTO tracked_picks
                   (slip_id, sb_event_id, match, league, kickoff, market_id, market_name,
                    specifier, outcome_id, outcome_desc, odds, confidence, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'pending', ?)""",
                (slip_id, eid,
                 f"{ev['home_team']} v {ev['away_team']}" if ev else eid,
                 ev["tournament"] if ev else None, ev["kickoff_ts"] if ev else None,
                 mid, od["market_name"] if od else None, lg.get("specifier"), oid,
                 od["outcome_desc"] if od else None, lg["odds"],
                 round(conf, 4) if conf is not None else None, now))
        conn.commit()


@app.post("/api/booking")
def booking(req: BookingReq):
    legs = [l.model_dump() for l in req.legs]
    res = create_booking_code(legs)
    if not res.get("ok"):
        raise HTTPException(502, res.get("error", "booking failed"))
    try:
        _track_booked(res.get("shareCode", "slip"), legs)
    except Exception:
        pass  # tracking is best-effort; never block a booking
    return res


@app.get("/api/results")
def results():
    settle_run()  # settle any finished pending picks
    with connect() as conn:
        rows = conn.execute(
            "SELECT match, league, market_name, outcome_desc, odds, confidence, status, result, settled_at "
            "FROM tracked_picks WHERE status IN ('won','lost') ORDER BY settled_at DESC").fetchall()
        pend = conn.execute("SELECT COUNT(*) FROM tracked_picks WHERE status='pending'").fetchone()[0]
    settled = [dict(r) for r in rows]
    n = len(settled)
    wins = sum(r["result"] for r in settled) if n else 0
    staked = n
    pnl = sum((r["odds"] - 1) if r["result"] else -1 for r in settled)
    # calibration buckets
    buckets = [(0.5, 0.65), (0.65, 0.8), (0.8, 0.9), (0.9, 1.01)]
    calib = []
    for lo, hi in buckets:
        b = [r for r in settled if r["confidence"] is not None and lo <= r["confidence"] < hi]
        if b:
            calib.append({"bucket": f"{int(lo*100)}-{int(hi*100)}%", "n": len(b),
                          "predicted": round(sum(r["confidence"] for r in b) / len(b) * 100, 1),
                          "actual": round(sum(r["result"] for r in b) / len(b) * 100, 1)})
    return {
        "settled": n, "pending": pend, "wins": wins, "losses": n - wins,
        "hit_rate": round(wins / n * 100, 1) if n else 0,
        "roi": round(pnl / staked * 100, 2) if staked else 0,
        "pnl_units": round(pnl, 2),
        "calibration": calib,
        "recent": settled[:30],
    }


def _leg_out(l: dict) -> dict:
    return {"match": l["match"], "market": l["market"], "selection": l["selection"],
            "confidence": round(l["prob"], 4), "odds": l["odds"], "reason": l["reason"],
            "event_id": l["event_id"], "market_id": l["market_id"],
            "specifier": l["specifier"], "outcome_id": l["outcome_id"],
            "league": l.get("tournament"), "country": l.get("country"), "kickoff": l.get("kickoff")}


def _run_build(scope, target_odds=None, count=1, target_legs=None,
               league=None, market=None, min_conf=None, odds_min=None, odds_max=None):
    start_d, end_d, label = parse_scope(scope or "today")
    acc = _cfg()
    floor = max(odds_min or 0, acc.get("min_leg_odds", 1.20))   # never below the 1.20 floor
    legs = load_model_legs(floor, odds_max or acc.get("max_leg_odds", 1000),
                           min_conf if min_conf is not None else acc.get("min_confidence", 0.65),
                           start_d, end_d)
    legs = apply_filters(legs, league=league, market=market, min_conf=min_conf,
                         odds_min=odds_min, odds_max=odds_max)
    variants = build_n_variants(legs, count, target_odds=target_odds, target_legs=target_legs)
    slips = [{"combined_odds": v["combined_odds"], "hit_estimate": v["hit_estimate"],
              "n_legs": v["n_legs"], "legs": [_leg_out(l) for l in v["legs"]]} for v in variants]
    return {"scope": label, "pool": len(legs), "slips": slips}


@app.get("/api/build")
def build(scope: str = "today", target: float | None = None, count: int = 1,
          legs: int | None = None, league: str | None = None, market: str | None = None,
          min_conf: float | None = None, odds_min: float | None = None, odds_max: float | None = None):
    return _run_build(scope, target_odds=target, count=count, target_legs=legs,
                      league=league, market=market, min_conf=min_conf,
                      odds_min=odds_min, odds_max=odds_max)


def _gemini_intent(message: str) -> dict | None:
    """Use Gemini to parse a build request into params. Returns None if not configured."""
    key = os.getenv("GOOGLE_AI_API_KEY")
    if not key:
        return None
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=key)
        schema = {
            "type": "object",
            "properties": {
                "scope": {"type": "string"},
                "tier": {"type": "string", "enum": ["safe", "mid", "longshot"]},
                "target_odds": {"type": "number"},
                "count": {"type": "integer"},
                "target_legs": {"type": "integer"},
                "league": {"type": "string"},
                "market": {"type": "string"},
                "min_conf": {"type": "number"},
                "reply": {"type": "string"},
            },
        }
        from datetime import date as _date
        _t = _date.today()
        prompt = ("You translate a football punter's request into slip-builder parameters. "
                  "NEVER invent matches or odds — only extract intent. "
                  f"Today is {_t.isoformat()} ({_t.strftime('%A')}). "
                  "Fields: scope (the concrete day the user means: 'today','tomorrow','week','weekend', "
                  "a weekday name like 'saturday', or an exact YYYY-MM-DD date), "
                  "tier (safe=few legs / mid / longshot=MANY legs - NOTE longshot means MORE legs stacked, NEVER higher per-leg odds), "
                  "target_odds (desired combined odds), count (how many different slips), target_legs, "
                  "league, market (e.g. 'over/under','corner'), min_conf (0-1), and a short friendly 'reply'. "
                  f"Request: {message}")
        r = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json",
                                               response_schema=schema),
        )
        import json as _json
        return _json.loads(r.text)
    except Exception:
        return None


_TIER_LEGS = {"safe": 4, "mid": 9, "longshot": 22}
_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
             "friday": 4, "saturday": 5, "sunday": 6}


def _resolve_scope(scope: str, message: str = "") -> str:
    """Turn 'saturday'/'this sat'/weekday words into a concrete YYYY-MM-DD; pass known scopes through."""
    from datetime import date, timedelta
    import re as _re
    s = (scope or "").strip().lower()
    blob = f"{s} {message}".lower()
    if _re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s
    if s in ("today", "tomorrow", "week", "weekend") and not any(w in blob for w in _WEEKDAYS):
        return s
    t = date.today()
    for name, wd in _WEEKDAYS.items():
        if name in blob:
            delta = (wd - t.weekday()) % 7
            return (t + timedelta(days=delta)).isoformat()
    return s if s else "today"


class ChatReq(BaseModel):
    message: str


@app.post("/api/chat")
def chat(req: ChatReq):
    gi = _gemini_intent(req.message)
    params = gi or parse_intent(req.message)
    scope = _resolve_scope(params.get("scope") or "today", req.message)
    tier = (params.get("tier") or "").lower()
    target_legs = params.get("target_legs")
    if not target_legs and tier in _TIER_LEGS:
        target_legs = _TIER_LEGS[tier]
    params["scope"] = scope
    res = _run_build(
        scope,
        target_odds=params.get("target_odds"),
        count=params.get("count", 1) or 1,
        target_legs=target_legs,
        league=params.get("league"),
        market=params.get("market"),
        min_conf=params.get("min_conf"),
    )
    reply = (gi or {}).get("reply")
    if not reply:
        n = len(res["slips"])
        if n:
            reply = f"Built {n} slip{'s' if n > 1 else ''} from {res['pool']} predictions ({res['scope']})."
        else:
            reply = f"No qualifying predictions for {res['scope']} with those filters."
    return {"reply": reply, "params": params, "engine": "gemini" if gi else "fallback", **res}


@app.get("/api/accuracy")
def accuracy():
    # validated on 8,263 top-5 matches (walk-forward, no leakage)
    from src.db.db import connect as _connect
    from src.models import calibration as _cal
    try:
        with _connect() as _conn:
            live = _cal.summary(_conn)
    except Exception:
        live = {"active": False, "n_total": 0}
    return {
        "live_calibration": live,
        "validated_matches": 8263,
        "calibration": [
            {"bucket": "50-60%", "predicted": 55, "actual": 54.1, "n": 14602},
            {"bucket": "60-70%", "predicted": 65, "actual": 62.3, "n": 10607},
            {"bucket": "70-80%", "predicted": 75, "actual": 73.9, "n": 13602},
            {"bucket": "80-90%", "predicted": 84, "actual": 81.4, "n": 5821},
            {"bucket": "90%+", "predicted": 92, "actual": 85.7, "n": 453},
        ],
        "markets": [
            {"market": "Double Chance", "confidence": 78, "hit": 77.2},
            {"market": "O/U 1.5", "confidence": 77, "hit": 77.2},
            {"market": "O/U 3.5", "confidence": 68, "hit": 68.0},
            {"market": "O/U 2.5", "confidence": 60, "hit": 56.0},
            {"market": "BTTS", "confidence": 58, "hit": 54.0},
            {"market": "1X2", "confidence": 51, "hit": 50.4},
        ],
    }

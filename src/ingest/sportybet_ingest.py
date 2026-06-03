"""
SportyBet (NG) full ingest: fixtures + markets + live odds (+ SportyBet's own
margin-removed probability per outcome) into SQLite.

Endpoints (public JSON, no browser):
  - list:   /api/ng/factsCenter/pcUpcomingEvents?sportId=sr:sport:1&marketId=1&pageSize&pageNum&option=1
  - detail: /api/ng/factsCenter/event?eventId=<id>&productId=3

Each outcome carries odds AND `probability` (SportyBet's de-vigged book prob) — we store both.

Usage:  python -m src.ingest.sportybet_ingest [max_events]
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

import requests

from src.db.db import connect, init_schema

BASE = "https://www.sportybet.com/api/ng/factsCenter"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
    "Accept": "application/json",
    "Referer": "https://www.sportybet.com/ng/sport/football",
}
REQUEST_DELAY = 0.4


import os as _os
_PROXY = _os.getenv("SCRAPER_PROXY") or None
_PROXIES = {"http": _PROXY, "https": _PROXY} if _PROXY else None


def _get(url: str) -> dict | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=25, proxies=_PROXIES)
        r.raise_for_status()
        j = r.json()
        if j.get("bizCode") != 10000:
            return None
        return j.get("data")
    except (requests.RequestException, ValueError):
        return None


def _ms_to_iso(ms) -> str | None:
    if not ms:
        return None
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()


SPORT_IDS = {"football": "sr:sport:1", "basketball": "sr:sport:2"}


def list_events(max_events: int, sport_id: str = "sr:sport:1") -> list[str]:
    ids: list[str] = []
    page = 1
    while len(ids) < max_events:
        url = (f"{BASE}/pcUpcomingEvents?sportId={sport_id}&marketId=1"
               f"&pageSize=50&pageNum={page}&option=1")
        d = _get(url)
        if not d or not d.get("tournaments"):
            break
        for t in d["tournaments"]:
            for e in t.get("events", []):
                eid = e.get("eventId") or e.get("id")
                if eid:
                    ids.append(eid)
        if page * 50 >= d.get("totalNum", 0):
            break
        page += 1
        time.sleep(REQUEST_DELAY)
    return list(dict.fromkeys(ids))[:max_events]


def fetch_event(event_id: str) -> dict | None:
    return _get(f"{BASE}/event?eventId={event_id}&productId=3")


def store_event(conn, ev: dict) -> int:
    now = datetime.now(timezone.utc).isoformat()
    sport = ev.get("sport", {}) or {}
    cat = sport.get("category", {}) or {}
    tour = cat.get("tournament", {}) or {}

    conn.execute(
        """INSERT INTO sb_events
           (event_id, home_team, away_team, tournament, category, sport, kickoff_ts, status, captured_at)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(event_id) DO UPDATE SET
             status=excluded.status, captured_at=excluded.captured_at""",
        (ev.get("eventId"), ev.get("homeTeamName"), ev.get("awayTeamName"),
         tour.get("name"), cat.get("name"), sport.get("name"),
         _ms_to_iso(ev.get("estimateStartTime")), ev.get("status"), now),
    )

    rows = 0
    for m in ev.get("markets", []):
        if m.get("status") not in (0, None):   # 0 = active
            continue
        mid = str(m.get("id"))
        mname = m.get("name") or m.get("desc")
        spec = m.get("specifier")
        for o in m.get("outcomes", []):
            if not o.get("isActive", 1):
                continue
            try:
                odds = float(o.get("odds"))
            except (TypeError, ValueError):
                continue
            try:
                bp = float(o.get("probability"))
            except (TypeError, ValueError):
                bp = None
            conn.execute(
                """INSERT INTO sb_odds
                   (event_id, market_id, market_name, specifier, outcome_id,
                    outcome_desc, odds, book_prob, captured_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (ev.get("eventId"), mid, mname, spec, str(o.get("id")),
                 o.get("desc"), odds, bp, now),
            )
            rows += 1
    return rows


def run(max_events: int = 2000, sport: str = "football"):
    init_schema()
    sid = SPORT_IDS.get(sport, "sr:sport:1")
    print(f"Listing SportyBet {sport} events (cap {max_events}) ...")
    ids = list_events(max_events, sid)
    print(f"  {len(ids)} events to ingest")

    ev_count = odd_count = 0
    with connect() as conn:
        for i, eid in enumerate(ids, 1):
            ev = fetch_event(eid)
            if not ev:
                continue
            n = store_event(conn, ev)
            ev_count += 1
            odd_count += n
            if i % 10 == 0:
                conn.commit()
                print(f"  {i}/{len(ids)} events, {odd_count} odds rows")
            time.sleep(REQUEST_DELAY)
        conn.commit()
    print(f"\nDone. {ev_count} events, {odd_count} odds rows stored.")


if __name__ == "__main__":
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    run(cap)

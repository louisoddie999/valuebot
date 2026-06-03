"""
SportyBet booking-code generator.

Maps slip legs to SportyBet selections and POSTs to the public share endpoint to get a
booking code + share URL. The user opens the code/URL in the SportyBet app — the betslip
pre-loads and THEY confirm and stake. No authentication, no auto-placement, no money moved.

Endpoint: POST https://www.sportybet.com/api/ng/orders/share
"""
from __future__ import annotations

import requests

SHARE_URL = "https://www.sportybet.com/api/ng/orders/share"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://www.sportybet.com/ng/",
}


def to_selection(leg: dict) -> dict:
    """Map a slip leg to a SportyBet selection. Requires event_id, market_id, outcome_id, odds."""
    return {
        "eventId": leg["event_id"],
        "productId": 3,
        "marketId": str(leg["market_id"]),
        "specifier": leg.get("specifier") or "",
        "outcomeId": str(leg["outcome_id"]),
        "odds": str(leg["odds"]),
    }


def create_booking_code(legs: list[dict]) -> dict:
    """
    legs: list of {event_id, market_id, specifier, outcome_id, odds}.
    Returns {ok, shareCode, shareURL} or {ok: False, error}.
    """
    if not legs:
        return {"ok": False, "error": "no legs"}
    selections = [to_selection(l) for l in legs]
    try:
        r = requests.post(SHARE_URL, headers=HEADERS, json={"selections": selections}, timeout=25)
        j = r.json()
    except (requests.RequestException, ValueError) as e:
        return {"ok": False, "error": str(e)}
    if j.get("bizCode") != 10000:
        return {"ok": False, "error": j.get("message", "share failed")}
    data = j.get("data", {})
    return {"ok": True, "shareCode": data.get("shareCode"), "shareURL": data.get("shareURL")}


if __name__ == "__main__":
    import sqlite3
    c = sqlite3.connect("data/soccer_value.sqlite")
    c.row_factory = sqlite3.Row
    rows = c.execute(
        "SELECT event_id, market_id, specifier, outcome_id, odds FROM sb_odds "
        "WHERE market_id='1' AND outcome_desc='Home' LIMIT 3").fetchall()
    print(create_booking_code([dict(r) for r in rows]))

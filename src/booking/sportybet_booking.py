"""
SportyBet booking-code generator.

Maps slip legs to SportyBet selections and POSTs to the public share endpoint to get a
booking code + share URL. The user opens the code/URL in the SportyBet app — the betslip
pre-loads and THEY confirm and stake. No authentication, no auto-placement, no money moved.

Endpoint: POST https://www.sportybet.com/api/ng/orders/share

NOTE: SportyBet drops plain-`requests` calls from datacenter IPs (e.g. Render) — the WAF
returns an empty body and json() blows up. We use curl_cffi with Chrome impersonation so the
TLS/JA3 fingerprint looks like a real browser, which clears the bot filter on most hosts.
"""
from __future__ import annotations

try:
    from curl_cffi import requests as _http
    _IMPERSONATE = {"impersonate": "chrome"}
except Exception:  # fallback if curl_cffi missing
    import requests as _http  # type: ignore
    _IMPERSONATE = {}

SHARE_URL = "https://www.sportybet.com/api/ng/orders/share"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-NG,en;q=0.9",
    "Content-Type": "application/json",
    "Origin": "https://www.sportybet.com",
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
        r = _http.post(SHARE_URL, headers=HEADERS, json={"selections": selections},
                       timeout=30, **_IMPERSONATE)
    except Exception as e:
        return {"ok": False, "error": f"network: {e}"}
    body = (r.text or "").strip()
    if not body:
        return {"ok": False, "error": f"empty response (HTTP {r.status_code}) — host likely IP-blocked"}
    try:
        j = r.json()
    except Exception:
        return {"ok": False, "error": f"non-JSON (HTTP {r.status_code}): {body[:120]}"}
    if j.get("bizCode") != 10000:
        return {"ok": False, "error": j.get("message", "share failed")}
    data = j.get("data", {})
    return {"ok": True, "shareCode": data.get("shareCode"), "shareURL": data.get("shareURL")}


if __name__ == "__main__":
    import sqlite3
    c = sqlite3.connect("data/serve.sqlite")
    c.row_factory = sqlite3.Row
    rows = c.execute(
        "SELECT event_id, market_id, specifier, outcome_id, odds FROM sb_odds LIMIT 3").fetchall()
    print(create_booking_code([dict(r) for r in rows]))
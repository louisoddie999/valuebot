"""
SportyBet (NG) football market catalogue scraper.

Uses SportyBet's public JSON API (no browser needed):
  - list events:  /api/ng/factsCenter/pcUpcomingEvents
  - event detail: /api/ng/factsCenter/event?eventId=...&productId=3

Samples several events (club games carry corners/cards that friendlies don't),
unions all distinct market groups, categorises them, and writes:
  - data/sportybet_markets.json   (raw distinct markets)
  - docs/sportybet-markets.md      (human catalogue + model-coverage map)
"""
from __future__ import annotations

import json
import re
import time
from collections import OrderedDict
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE = "https://www.sportybet.com/api/ng/factsCenter"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
    "Accept": "application/json",
    "Referer": "https://www.sportybet.com/ng/sport/football",
}


def get(url: str) -> dict:
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r.json()


def list_event_ids(pages: int = 3, page_size: int = 20) -> list[str]:
    ids: list[str] = []
    for pg in range(1, pages + 1):
        url = (f"{BASE}/pcUpcomingEvents?sportId=sr:sport:1&marketId=1"
               f"&pageSize={page_size}&pageNum={pg}&option=1")
        try:
            d = get(url).get("data", {})
        except requests.RequestException:
            continue
        for t in d.get("tournaments", []):
            for e in t.get("events", []):
                eid = e.get("eventId") or e.get("id")
                if eid:
                    ids.append(eid)
        time.sleep(0.5)
    return list(OrderedDict.fromkeys(ids))


def event_markets(event_id: str) -> list[dict]:
    url = f"{BASE}/event?eventId={event_id}&productId=3"
    try:
        d = get(url).get("data", {})
    except requests.RequestException:
        return []
    return d.get("markets", [])


def normalise_name(name: str, market_id: str) -> str:
    """Strip line/specifier numbers so 'Over/Under 2.5' and '3.5' collapse to one group."""
    if not name:
        return f"(id {market_id})"
    n = re.sub(r"[-+]?\d+\.?\d*", "", name).strip(" -")
    return n or name


CATEGORY_RULES = [
    ("Result", ["1x2", "double chance", "draw no bet", "next goal", "win either half", "result"]),
    ("Goals", ["over/under", "o/u", "total goals", "goal", "gg/ng", "btts", "exact goals", "odd/even"]),
    ("Handicap", ["handicap"]),
    ("Halves", ["half", "ht/ft", "1st half", "2nd half", "early goals"]),
    ("Corners", ["corner"]),
    ("Cards/Bookings", ["card", "booking"]),
    ("Player", ["player", "scorer", "to score", "anytime", "assist"]),
    ("Specials", ["lead by", "goal bounds", "minute", "interval", "method", "clean sheet"]),
]


def categorise(name: str) -> str:
    low = name.lower()
    for cat, kws in CATEGORY_RULES:
        if any(k in low for k in kws):
            return cat
    return "Other"


def run():
    print("Listing events ...")
    ids = list_event_ids()
    print(f"  {len(ids)} events found; sampling up to 15 for market union")

    distinct: dict[str, dict] = {}
    sampled = 0
    for eid in ids:
        mks = event_markets(eid)
        if not mks:
            continue
        sampled += 1
        for m in mks:
            grp = normalise_name(m.get("name", ""), str(m.get("id", "")))
            if grp not in distinct:
                distinct[grp] = {
                    "market_id": m.get("id"),
                    "example_name": m.get("name"),
                    "outcome_count": len(m.get("outcomes", [])),
                    "outcomes_example": [o.get("desc") for o in m.get("outcomes", [])[:4]],
                    "category": categorise(grp),
                }
        time.sleep(0.4)
        if sampled >= 15:
            break

    print(f"  sampled {sampled} events, {len(distinct)} distinct market groups")

    # save raw
    (PROJECT_ROOT / "data").mkdir(exist_ok=True)
    out_json = PROJECT_ROOT / "data" / "sportybet_markets.json"
    out_json.write_text(json.dumps(distinct, indent=2, ensure_ascii=False), encoding="utf-8")

    # build markdown catalogue grouped by category
    by_cat: dict[str, list] = {}
    for name, info in sorted(distinct.items()):
        by_cat.setdefault(info["category"], []).append((name, info))

    lines = ["# SportyBet — Football Market Catalogue (scraped)\n"]
    lines.append(f"Distinct market groups: **{len(distinct)}** (sampled {sampled} live events)\n")
    cat_order = ["Result", "Goals", "Handicap", "Halves", "Corners",
                 "Cards/Bookings", "Player", "Specials", "Other"]
    for cat in cat_order:
        items = by_cat.get(cat)
        if not items:
            continue
        lines.append(f"## {cat} ({len(items)})")
        for name, info in items:
            ex = ", ".join(str(x) for x in info["outcomes_example"] if x)
            lines.append(f"- **{name}** (id {info['market_id']}, {info['outcome_count']} outcomes)"
                         + (f" — e.g. {ex}" if ex else ""))
        lines.append("")

    (PROJECT_ROOT / "docs" / "sportybet-markets.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote docs/sportybet-markets.md and data/sportybet_markets.json")

    # quick corners/cards check
    has_corner = any("corner" in n.lower() for n in distinct)
    has_card = any("card" in n.lower() or "booking" in n.lower() for n in distinct)
    print(f"  corners present: {has_corner} | cards present: {has_card}")


if __name__ == "__main__":
    run()

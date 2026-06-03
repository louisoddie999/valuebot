"""
Telegram delivery — pushes formatted daily slips to a chat via the Bot API.

Token + chat id come from the gitignored .env (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID).
No secrets in source. Sends SAFE + MID tiers for a scope (default today).

Usage:  python -m src.notify.telegram [scope]      (today|tomorrow|week|weekend|DATE)
"""
from __future__ import annotations

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

from src.db.db import load_config
from src.punter.accumulator_builder import parse_scope, load_model_legs, build_slip

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
API = f"https://api.telegram.org/bot{TOKEN}"


def send(text: str) -> dict:
    if not TOKEN or not CHAT_ID:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing in .env"}
    r = requests.post(f"{API}/sendMessage",
                      json={"chat_id": CHAT_ID, "text": text,
                            "parse_mode": "HTML", "disable_web_page_preview": True},
                      timeout=20)
    return r.json()


def _fmt_slip(tier: str, slip: dict) -> str:
    if not slip:
        return f"<b>{tier}</b>: no qualifying slip.\n"
    lines = [f"<b>{tier}</b> — <b>{slip['combined_odds']:.2f}</b> odds · "
             f"~{slip['combined_prob']*100:.1f}% · {len(slip['legs'])} legs"]
    for i, l in enumerate(slip["legs"], 1):
        conf = round(l["prob"] * 100)
        lines.append(f"{i}. {l['match']} — <b>{l['selection']}</b> "
                     f"({l['market']}) @{l['odds']:.2f} · {conf}%")
    return "\n".join(lines) + "\n"


def build_message(scope: str | None) -> str:
    start_d, end_d, label = parse_scope(scope)
    acc = load_config()["accumulators"]
    legs = load_model_legs(acc["min_leg_odds"], acc["max_leg_odds"],
                           acc.get("min_confidence", 0.65), start_d, end_d)
    parts = [f"⚽ <b>ValueBot — {label}</b>",
             f"<i>{len(legs)} predictions from data (form · xG · H2H · injuries)</i>\n"]
    for tier in ("SAFE", "MID"):
        t = acc["tiers"][tier]
        slip = build_slip(legs, t["min_legs"], t["max_legs"], t["leg_min"], t["leg_max"])
        parts.append(_fmt_slip(tier, slip))
    parts.append("<i>Not financial advice. Stake responsibly.</i>")
    return "\n".join(parts)


def run(scope: str | None = None):
    msg = build_message(scope)
    res = send(msg)
    print("sent:" if res.get("ok") else "FAILED:", res.get("ok", res))
    return res


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "today")

"""
Build data/serve.sqlite — a slim, GitHub-shippable copy for the Render-hosted API.

Keeps only what the API serves: sb_events + odds for PREDICTED events, sf_features,
tracked_picks, sf_team_cache. Drops backtest tables (matches, odds) and stale odds
snapshots. Result is a few MB instead of 140 MB.

Run on your PC after enriching, then: git add data/serve.sqlite && git push  (Render redeploys).
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "soccer_value.sqlite"
DST = ROOT / "data" / "serve.sqlite"


def main():
    if DST.exists():
        DST.unlink()
    shutil.copy(SRC, DST)
    c = sqlite3.connect(DST)
    # drop backtest-only tables
    for t in ("matches", "odds"):
        c.execute(f"DROP TABLE IF EXISTS {t}")
    # keep odds only for events that have predictions (sf_features)
    c.execute("DELETE FROM sb_odds WHERE event_id NOT IN (SELECT sb_event_id FROM sf_features)")
    # dedup: keep newest snapshot per (event, market, specifier, outcome)
    c.execute("""DELETE FROM sb_odds WHERE sb_odds_id NOT IN (
                   SELECT MAX(sb_odds_id) FROM sb_odds
                   GROUP BY event_id, market_id, IFNULL(specifier,''), outcome_id)""")
    c.commit()
    c.execute("VACUUM")
    c.commit()
    c.close()
    mb = DST.stat().st_size / 1e6
    print(f"serve.sqlite built: {mb:.1f} MB")
    if mb > 95:
        print("  WARNING: still > 95 MB (GitHub limit 100). Trim further or use Git LFS / Render disk.")


if __name__ == "__main__":
    main()

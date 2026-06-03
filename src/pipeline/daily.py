"""
Daily pipeline — one command to refresh everything the dashboard serves.

Steps:
  1. Ingest SportyBet board (fixtures + markets + odds)         [resilient]
  2. Enrich fixtures in the chosen date scope via Sofascore     [resilient]
  3. Report counts (dashboard reads the DB live — no extra step)

Scope: today | tomorrow | week | weekend | YYYY-MM-DD | YYYY-MM-DD:YYYY-MM-DD
"Core + scan": board cap covers near-term priority; widen --board to sweep more so
nothing is missed.

Usage:
  python -m src.pipeline.daily --scope today --board 200 --enrich 80
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

from src.db.db import connect, PROJECT_ROOT
from src.ingest import sportybet_ingest, sofascore
from src.punter.accumulator_builder import parse_scope


def _log(msg: str, lines: list[str]):
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line)
    lines.append(line)


def run(scope: str, board_cap: int, enrich_cap: int):
    lines: list[str] = []
    start_d, end_d, label = parse_scope(scope)
    _log(f"DAILY PIPELINE — scope={label} [{start_d}..{end_d}] board={board_cap} enrich={enrich_cap}", lines)

    # 1. SportyBet board
    try:
        _log("Step 1/2: ingesting SportyBet board ...", lines)
        sportybet_ingest.run(board_cap)
    except Exception as e:
        _log(f"  ! board ingest failed: {e}", lines)

    # 2. Sofascore enrichment for scope
    try:
        _log("Step 2/2: enriching fixtures in scope via Sofascore ...", lines)
        sofascore.run_scope(start_d, end_d, enrich_cap)
    except Exception as e:
        _log(f"  ! enrichment failed: {e}", lines)

    # summary
    with connect() as c:
        ev = c.execute("SELECT COUNT(*) FROM sb_events").fetchone()[0]
        ft = c.execute("SELECT COUNT(*) FROM sf_features").fetchone()[0]
        in_scope = c.execute(
            "SELECT COUNT(*) FROM sb_events WHERE substr(kickoff_ts,1,10) BETWEEN ? AND ?",
            (start_d, end_d)).fetchone()[0]
    _log(f"DONE. events={ev} enriched={ft} fixtures_in_scope={in_scope}. "
         f"Dashboard now live with fresh data.", lines)

    logdir = PROJECT_ROOT / "reports"
    logdir.mkdir(exist_ok=True)
    (logdir / f"daily_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.log").write_text(
        "\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="today")
    ap.add_argument("--board", type=int, default=2000)
    ap.add_argument("--enrich", type=int, default=2000)
    a = ap.parse_args()
    t0 = time.time()
    run(a.scope, a.board, a.enrich)
    print(f"\nElapsed: {time.time()-t0:.0f}s")

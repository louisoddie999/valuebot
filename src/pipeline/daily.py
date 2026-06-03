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
from src.results import settle
from src.models import calibration
from src.punter.accumulator_builder import parse_scope


def _log(msg: str, lines: list[str]):
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line)
    lines.append(line)


def run(scope: str, board_cap: int, enrich_cap: int, bball: bool = True):
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
        _log("Step 2/3: enriching fixtures in scope via Sofascore ...", lines)
        sofascore.run_scope(start_d, end_d, enrich_cap)
    except Exception as e:
        _log(f"  ! enrichment failed: {e}", lines)

    # 2b. Basketball: board ingest + per-event projection (NBA/EuroLeague/etc.)
    if bball:
        try:
            _log("Step 2b: ingesting basketball board + projecting ...", lines)
            sportybet_ingest.run(min(board_cap, 400), sport="basketball")
            from src.ingest import sofascore_basketball
            bn = sofascore_basketball.enrich_scope(start_d, end_d, enrich_cap)
            _log(f"  basketball projected: {bn}", lines)
        except Exception as e:
            _log(f"  ! basketball step failed: {e}", lines)

    # 3. settle finished picks + self-recalibrate the confidence model
    try:
        _log("Step 3/3: settling results + recalibrating model ...", lines)
        s = settle.run()
        try:
            from src.models import elo as _elo
            from src.db.db import connect as _conn
            with _conn() as _c:
                _n = _elo.build_team_table(_c)
            _log(f"  Elo ratings rebuilt: {_n} teams", lines)
        except Exception as e:
            _log(f"  ! elo rebuild failed: {e}", lines)
        cal = calibration.recalibrate()
        bits = []
        for sp, v in cal.items():
            bits.append(f"{sp}: {'ACTIVE' if v['active'] else 'learning'} ({v['n_total']} settled"
                        + ("" if v['active'] else f", need {v['need']}") + ")")
        _log(f"  settled {s.get('settled', 0)} | calibration -> " + " | ".join(bits), lines)
    except Exception as e:
        _log(f"  ! settle/recalibrate failed: {e}", lines)

    # summary
    with connect() as c:
        ev = c.execute("SELECT COUNT(*) FROM sb_events").fetchone()[0]
        ft = c.execute("SELECT COUNT(*) FROM sf_features").fetchone()[0]
        in_scope = c.execute(
            "SELECT COUNT(*) FROM sb_events WHERE substr(kickoff_ts,1,10) BETWEEN ? AND ?",
            (start_d, end_d)).fetchone()[0]
    _log(f"DONE. events={ev} enriched={ft} fixtures_in_scope={in_scope}. "
         f"Dashboard now live with fresh data.", lines)

    # 4. push top slips to Telegram (no-op if TELEGRAM_* creds not set in .env)
    try:
        from src.notify import telegram
        res = telegram.run(scope)
        _log("Telegram: sent top slips" if res.get("ok")
             else f"Telegram: skipped ({res.get('error', 'no creds')})", lines)
    except Exception as e:
        _log(f"  ! telegram push failed: {e}", lines)

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

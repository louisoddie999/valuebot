"""
Per-match analysis report.

For each fixture in the chosen date scope, iterate EVERY market that match actually offers
on SportyBet, project our stat-based probability, and report coverage + the strongest picks.
Markets we cannot model are skipped explicitly (counted, never guessed).

Usage:  python -m src.punter.match_analysis [scope]   (today|tomorrow|week|weekend|DATE|A:B)
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from src.db.db import connect, PROJECT_ROOT
from src.models import projector
from src.punter.accumulator_builder import parse_scope


def analyze(scope: str | None = None):
    start_d, end_d, label = parse_scope(scope)
    with connect() as conn:
        feats = {r["sb_event_id"]: dict(r)
                 for r in conn.execute("SELECT * FROM sf_features").fetchall()}
        events = conn.execute(
            """SELECT event_id, home_team, away_team, tournament, kickoff_ts FROM sb_events
               WHERE substr(kickoff_ts,1,10) BETWEEN ? AND ? ORDER BY kickoff_ts""",
            (start_d, end_d)).fetchall()

        blocks, tot_off, tot_mod = [], 0, 0
        for e in events:
            f = feats.get(e["event_id"])
            if not f:
                continue
            odds = conn.execute(
                """SELECT market_id, market_name, specifier, outcome_desc, odds, book_prob
                   FROM sb_odds WHERE event_id=? AND book_prob IS NOT NULL""",
                (e["event_id"],)).fetchall()

            picks, offered, modeled = [], set(), 0
            for o in odds:
                offered.add((o["market_name"], o["specifier"]))
                f["_market_name"] = o["market_name"]
                mp = projector.model_prob_for(f, o["market_id"], o["specifier"], o["outcome_desc"])
                if mp is None:
                    continue
                modeled += 1
                picks.append({
                    "market": o["market_name"], "specifier": o["specifier"],
                    "sel": o["outcome_desc"], "odds": o["odds"],
                    "model": mp, "book": o["book_prob"], "edge": mp - o["book_prob"],
                    "reason": projector.reason(f, o["market_id"], o["outcome_desc"]),
                })
            n_offered = len(odds)
            tot_off += n_offered
            tot_mod += modeled
            picks.sort(key=lambda x: -x["edge"])
            blocks.append((e, n_offered, modeled, picks[:6]))

    _write(label, blocks, tot_off, tot_mod)


def _write(label, blocks, tot_off, tot_mod):
    L = [f"# Per-Match Analysis — {label} — {datetime.now(timezone.utc).isoformat()}",
         f"Matches analyzed: **{len(blocks)}** | Selections offered: **{tot_off}** | "
         f"Modeled from stats: **{tot_mod}** ({tot_mod/tot_off*100:.0f}%)\n"]
    for e, n_off, n_mod, picks in blocks:
        L.append(f"## {e['home_team']} v {e['away_team']}  —  {e['tournament']}")
        L.append(f"_{e['kickoff_ts'][:16]} · {n_mod}/{n_off} selections modeled · "
                 f"top stat-edge picks:_\n")
        if not picks:
            L.append("_No modelable +data markets._\n"); continue
        L.append("| Market | Pick | Odds | Our | Book | Edge | Why |")
        L.append("|---|---|---|---|---|---|---|")
        for p in picks:
            spec = f" ({p['specifier']})" if p["specifier"] else ""
            L.append(f"| {p['market']}{spec} | {p['sel']} | {p['odds']} | {p['model']*100:.0f}% | "
                     f"{p['book']*100:.0f}% | {p['edge']*100:+.1f}% | {p['reason']} |")
        L.append("")
    out = PROJECT_ROOT / "reports" / f"analysis_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"Matches: {len(blocks)} | offered {tot_off} | modeled {tot_mod} "
          f"({tot_mod/tot_off*100:.0f}%)")
    print(f"Written: {out}")


if __name__ == "__main__":
    analyze(sys.argv[1] if len(sys.argv) > 1 else None)

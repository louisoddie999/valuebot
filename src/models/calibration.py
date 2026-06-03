"""
Per-sport self-recalibration.

Settled picks -> a predicted-vs-actual curve PER SPORT (football, basketball) that corrects
raw model confidence toward real hit-rate. Doctrine: learns from our OWN results only — never
from market odds. Gated by MIN_SETTLED per sport (identity until enough data).
"""
from __future__ import annotations

from datetime import datetime, timezone
from src.db.db import connect, init_schema

BINS = [(0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 1.0001)]
MIN_SETTLED = 150
K = 25.0
MAX_OFFSET = 0.15
SPORTS = ("football", "basketball")


def _bin_index(p):
    for i, (lo, hi) in enumerate(BINS):
        if lo <= p < hi:
            return i
    return -1


def _ensure_schema(conn):
    """Self-migrate: add sport everywhere; rebuild calibration caches with sport key."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(tracked_picks)")]
    if "sport" not in cols:
        conn.execute("ALTER TABLE tracked_picks ADD COLUMN sport TEXT")
    cc = [r[1] for r in conn.execute("PRAGMA table_info(calibration_curve)")]
    if "sport" not in cc:
        conn.execute("DROP TABLE IF EXISTS calibration_curve")
        conn.execute("CREATE TABLE calibration_curve (sport TEXT, lo REAL, hi REAL, mid REAL, "
                     "n INTEGER, actual REAL, offset REAL, updated_at TEXT)")
    cm = [r[1] for r in conn.execute("PRAGMA table_info(calibration_meta)")]
    if "sport" not in cm:
        conn.execute("DROP TABLE IF EXISTS calibration_meta")
        conn.execute("CREATE TABLE calibration_meta (sport TEXT PRIMARY KEY, n_total INTEGER, "
                     "active INTEGER, updated_at TEXT)")
    conn.commit()


def tag_sports(conn):
    """Backfill tracked_picks.sport from bb_features membership (basketball) else football."""
    bb = {r[0] for r in conn.execute("SELECT sb_event_id FROM bb_features")}
    for r in conn.execute("SELECT pick_id, sb_event_id FROM tracked_picks WHERE sport IS NULL").fetchall():
        conn.execute("UPDATE tracked_picks SET sport=? WHERE pick_id=?",
                     ("basketball" if r[1] in bb else "football", r[0]))
    conn.commit()


def recalibrate(conn=None):
    """Rebuild per-sport curves. Returns {sport: {n_total, active, need}}."""
    own = conn is None
    if own:
        init_schema(); conn = connect()
    try:
        _ensure_schema(conn); tag_sports(conn)
        now = datetime.now(timezone.utc).isoformat()
        out = {}
        for sport in SPORTS:
            rows = conn.execute(
                "SELECT confidence, result FROM tracked_picks WHERE sport=? AND status IN "
                "('won','lost') AND result IS NOT NULL AND confidence IS NOT NULL", (sport,)).fetchall()
            n_total = len(rows)
            active = 1 if n_total >= MIN_SETTLED else 0
            buckets = [{"lo": lo, "hi": hi, "mid": round((lo + min(hi, 1.0)) / 2, 4), "n": 0, "wins": 0}
                       for lo, hi in BINS]
            for r in rows:
                i = _bin_index(float(r["confidence"]))
                if i >= 0:
                    buckets[i]["n"] += 1; buckets[i]["wins"] += int(r["result"])
            conn.execute("DELETE FROM calibration_curve WHERE sport=?", (sport,))
            for b in buckets:
                if b["n"]:
                    actual = b["wins"] / b["n"]
                    cal = (b["n"] * actual + K * b["mid"]) / (b["n"] + K)
                else:
                    actual, cal = None, b["mid"]
                off = max(-MAX_OFFSET, min(MAX_OFFSET, cal - b["mid"]))
                conn.execute("INSERT INTO calibration_curve(sport,lo,hi,mid,n,actual,offset,updated_at) "
                             "VALUES (?,?,?,?,?,?,?,?)",
                             (sport, b["lo"], b["hi"], b["mid"], b["n"],
                              round(actual, 4) if actual is not None else None, round(off, 4), now))
            conn.execute("INSERT INTO calibration_meta(sport,n_total,active,updated_at) VALUES (?,?,?,?) "
                         "ON CONFLICT(sport) DO UPDATE SET n_total=excluded.n_total, "
                         "active=excluded.active, updated_at=excluded.updated_at",
                         (sport, n_total, active, now))
            out[sport] = {"n_total": n_total, "active": bool(active), "need": max(0, MIN_SETTLED - n_total)}
        conn.commit()
        return out
    finally:
        if own:
            conn.close()


def load_curve(conn, sport="football"):
    try:
        _ensure_schema(conn)
        meta = conn.execute("SELECT active, n_total FROM calibration_meta WHERE sport=?", (sport,)).fetchone()
        if not meta or not meta["active"]:
            return {"active": False, "offsets": [], "n_total": meta["n_total"] if meta else 0}
        rows = conn.execute("SELECT lo,hi,offset FROM calibration_curve WHERE sport=? ORDER BY lo",
                            (sport,)).fetchall()
        return {"active": True, "n_total": meta["n_total"],
                "offsets": [(r["lo"], r["hi"], r["offset"]) for r in rows]}
    except Exception:
        return {"active": False, "offsets": [], "n_total": 0}


def apply(prob, curve):
    if prob is None or not curve or not curve.get("active"):
        return prob
    for lo, hi, off in curve["offsets"]:
        if lo <= prob < hi:
            return max(0.01, min(0.99, prob + (off or 0.0)))
    return prob


def summary(conn, sport="football"):
    _ensure_schema(conn)
    meta = conn.execute("SELECT active,n_total,updated_at FROM calibration_meta WHERE sport=?", (sport,)).fetchone()
    rows = conn.execute("SELECT lo,hi,mid,n,actual,offset FROM calibration_curve WHERE sport=? ORDER BY lo",
                        (sport,)).fetchall()
    return {"sport": sport, "active": bool(meta["active"]) if meta else False,
            "n_total": meta["n_total"] if meta else 0, "min_required": MIN_SETTLED,
            "updated_at": meta["updated_at"] if meta else None,
            "buckets": [{"range": f"{int(r['lo']*100)}-{int(min(r['hi'],1.0)*100)}%",
                         "predicted": round(r["mid"]*100, 1),
                         "actual": round(r["actual"]*100, 1) if r["actual"] is not None else None,
                         "n": r["n"], "offset": r["offset"]} for r in rows]}


if __name__ == "__main__":
    print(recalibrate())

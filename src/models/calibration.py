"""
Self-recalibration loop.

Closes the feedback loop: settled picks (tracked_picks.result) -> a calibration curve
that corrects the model's raw confidence so published numbers match real hit-rates.

- recalibrate(): rebuild the curve from settled picks. Gated by MIN_SETTLED — below that
  the curve stays INACTIVE (apply() is identity) so we never "learn" from noise.
- load_curve()/apply(): used by the slip/fixtures builder to correct each prob.
- summary(): live calibration table for /api/accuracy.

Method: bucket settled picks by predicted confidence, compute actual hit-rate per bucket,
shrink toward the predicted mid by sample size (Bayesian), and apply the resulting
offset to any raw prob in that bucket. Monotonic-ish, continuous, conservative.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.db.db import connect, init_schema

BINS = [(0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 1.0001)]
MIN_SETTLED = 150     # need this many settled picks before the curve goes active
K = 25.0              # shrinkage strength toward the predicted mid (per bucket)
MAX_OFFSET = 0.15     # never shift a prob by more than this (safety clamp)


def _bin_index(p: float) -> int:
    for i, (lo, hi) in enumerate(BINS):
        if lo <= p < hi:
            return i
    return -1


def recalibrate(conn=None) -> dict:
    """Rebuild calibration_curve from settled picks. Returns a summary dict."""
    own = conn is None
    if own:
        init_schema()
        conn = connect().__enter__() if False else connect()
    try:
        rows = conn.execute(
            "SELECT confidence, result FROM tracked_picks "
            "WHERE status IN ('won','lost') AND result IS NOT NULL AND confidence IS NOT NULL"
        ).fetchall()
        n_total = len(rows)
        active = 1 if n_total >= MIN_SETTLED else 0
        now = datetime.now(timezone.utc).isoformat()

        buckets = [{"lo": lo, "hi": hi, "mid": round((lo + min(hi, 1.0)) / 2, 4),
                    "n": 0, "wins": 0} for lo, hi in BINS]
        for r in rows:
            i = _bin_index(float(r["confidence"]))
            if i < 0:
                continue
            buckets[i]["n"] += 1
            buckets[i]["wins"] += int(r["result"])

        conn.execute("DELETE FROM calibration_curve")
        for b in buckets:
            if b["n"]:
                actual = b["wins"] / b["n"]
                # shrink actual toward predicted mid by sample size
                cal = (b["n"] * actual + K * b["mid"]) / (b["n"] + K)
            else:
                actual, cal = None, b["mid"]
            offset = max(-MAX_OFFSET, min(MAX_OFFSET, cal - b["mid"]))
            conn.execute(
                "INSERT INTO calibration_curve(lo,hi,mid,n,actual,offset,updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (b["lo"], b["hi"], b["mid"], b["n"],
                 round(actual, 4) if actual is not None else None,
                 round(offset, 4), now),
            )
        conn.execute(
            "INSERT INTO calibration_meta(id,n_total,active,updated_at) VALUES (1,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET n_total=excluded.n_total, active=excluded.active, "
            "updated_at=excluded.updated_at",
            (n_total, active, now),
        )
        conn.commit()
        return {"n_total": n_total, "active": bool(active),
                "need": max(0, MIN_SETTLED - n_total)}
    finally:
        if own:
            conn.close()


def load_curve(conn) -> dict:
    """Read the active curve once (cheap). Returns {'active': bool, 'offsets': [..]}"""
    try:
        meta = conn.execute("SELECT active, n_total FROM calibration_meta WHERE id=1").fetchone()
        if not meta or not meta["active"]:
            return {"active": False, "offsets": [], "n_total": meta["n_total"] if meta else 0}
        rows = conn.execute("SELECT lo,hi,offset FROM calibration_curve ORDER BY lo").fetchall()
        return {"active": True, "n_total": meta["n_total"],
                "offsets": [(r["lo"], r["hi"], r["offset"]) for r in rows]}
    except Exception:
        return {"active": False, "offsets": [], "n_total": 0}


def apply(prob: float, curve: dict) -> float:
    """Correct a raw model prob using the calibration curve. Identity if inactive."""
    if prob is None or not curve or not curve.get("active"):
        return prob
    for lo, hi, off in curve["offsets"]:
        if lo <= prob < hi:
            return max(0.01, min(0.99, prob + (off or 0.0)))
    return prob


def summary(conn) -> dict:
    """Live calibration state for the API."""
    meta = conn.execute("SELECT active, n_total, updated_at FROM calibration_meta WHERE id=1").fetchone()
    rows = conn.execute(
        "SELECT lo,hi,mid,n,actual,offset FROM calibration_curve ORDER BY lo").fetchall()
    return {
        "active": bool(meta["active"]) if meta else False,
        "n_total": meta["n_total"] if meta else 0,
        "min_required": MIN_SETTLED,
        "updated_at": meta["updated_at"] if meta else None,
        "buckets": [{"range": f"{int(r['lo']*100)}-{int(min(r['hi'],1.0)*100)}%",
                     "predicted": round(r["mid"]*100, 1),
                     "actual": round(r["actual"]*100, 1) if r["actual"] is not None else None,
                     "n": r["n"], "offset": r["offset"]} for r in rows],
    }


if __name__ == "__main__":
    print(recalibrate())

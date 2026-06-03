"""
Results settlement — grades tracked picks against real Sofascore outcomes.

For each pending pick whose match has finished, fetch the final score + half-time + corners
from Sofascore (via the sf_event_id mapping), evaluate the market outcome, and mark won/lost.
Powers the Results / live-calibration page.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from src.db.db import connect, init_schema
from src.ingest import sofascore as sf


def _line(spec, desc):
    if spec:
        m = re.search(r"=\s*([0-9]+\.?[0-9]*)", spec)
        if m:
            return float(m.group(1))
    m = re.search(r"([0-9]+\.?[0-9]*)", desc or "")
    return float(m.group(1)) if m else None


def fetch_result(sf_event_id: int) -> dict | None:
    ev = sf._get(f"/event/{sf_event_id}")
    if not ev:
        return None
    e = ev.get("event") or ev
    if (e.get("status", {}) or {}).get("type") != "finished":
        return None
    hs, as_ = e.get("homeScore", {}), e.get("awayScore", {})
    h, a = hs.get("current"), as_.get("current")
    if h is None or a is None:
        return None
    R = {"h": h, "a": a, "hh": hs.get("period1", 0) or 0, "ha": as_.get("period1", 0) or 0,
         "ch": None, "ca": None}
    ms = sf._match_stats(sf_event_id)
    if ms and "home_corners" in ms:
        R["ch"], R["ca"] = ms["home_corners"], ms["away_corners"]
    return R


def settle_market(mid: str, spec, desc, R) -> bool | None:
    d = (desc or "").lower().strip()
    h, a = R["h"], R["a"]
    total = h + a
    httotal = R["hh"] + R["ha"]
    res = "home" if h > a else ("draw" if h == a else "away")
    line = _line(spec, desc)
    mid = str(mid)

    if mid == "1":
        return res == d
    if mid == "10":
        if "draw" in d and "away" in d: return res in ("draw", "away")
        if "home" in d and "away" in d: return res in ("home", "away")
        if "home" in d and "draw" in d: return res in ("home", "draw")
        return None
    if mid == "11":
        if res == "draw": return None
        return res == ("home" if "home" in d else "away")
    if mid == "12":  # home no bet (draw/away)
        return (res == "draw") if "draw" in d else (res == "away")
    if mid == "13":  # away no bet (home/draw)
        return (res == "home") if "home" in d else (res == "draw")
    if mid == "18":
        if line is None: return None
        return (total > line) if "over" in d else (total < line)
    if mid in ("19", "20"):
        if line is None: return None
        v = h if mid == "19" else a
        return (v > line) if "over" in d else (v < line)
    if mid == "29":
        yes = h > 0 and a > 0
        return yes if "yes" in d else not yes
    if mid in ("26", "27", "28"):
        v = total if mid == "26" else (h if mid == "27" else a)
        odd = v % 2 == 1
        return odd if "odd" in d else not odd
    if mid == "21":
        if "+" in d: k = int(re.search(r"\d+", d).group()); return total >= k
        m = re.search(r"\d+", d); return total == int(m.group()) if m else None
    if mid == "25":
        if "+" in d: k = int(re.search(r"\d+", d).group()); return total >= k
        m = re.findall(r"\d+", d); return (int(m[0]) <= total <= int(m[1])) if len(m) == 2 else None
    if mid == "30":
        if "none" in d: return total == 0
        if "only home" in d: return h > 0 and a == 0
        if "only away" in d: return a > 0 and h == 0
        if "both" in d: return h > 0 and a > 0
        return None
    if mid == "31":  # home clean sheet
        cs = a == 0; return cs if "yes" in d else not cs
    if mid == "32":
        cs = h == 0; return cs if "yes" in d else not cs
    if mid == "33":  # home win to nil
        wtn = h > a and a == 0; return wtn if "yes" in d else not wtn
    if mid == "34":
        wtn = a > h and h == 0; return wtn if "yes" in d else not wtn
    if mid == "15":  # winning margin
        diff = h - a
        if "draw" in d: return diff == 0
        k = _line(None, desc)
        if k is None: return None
        k = int(k)
        if "home" in d: return (diff >= k) if "+" in d else (diff == k)
        if "away" in d: return (-diff >= k) if "+" in d else (-diff == k)
        return None
    if mid == "166":
        if R["ch"] is None: return None
        return ((R["ch"] + R["ca"]) > line) if "over" in d else ((R["ch"] + R["ca"]) < line)
    if mid in ("900300", "900301"):
        if R["ch"] is None: return None
        v = R["ch"] if mid == "900300" else R["ca"]
        return (v > line) if "over" in d else (v < line)
    if mid == "68":  # 1st half O/U
        if line is None: return None
        return (httotal > line) if "over" in d else (httotal < line)
    if mid == "90":  # 2nd half O/U
        if line is None: return None
        sh = total - httotal
        return (sh > line) if "over" in d else (sh < line)
    if mid == "60":  # 1st half 1X2
        r2 = "home" if R["hh"] > R["ha"] else ("draw" if R["hh"] == R["ha"] else "away")
        return r2 == d
    if mid == "63":  # 1st half DC
        r2 = "home" if R["hh"] > R["ha"] else ("draw" if R["hh"] == R["ha"] else "away")
        if "draw" in d and "away" in d: return r2 in ("draw", "away")
        if "home" in d and "away" in d: return r2 in ("home", "away")
        if "home" in d and "draw" in d: return r2 in ("home", "draw")
        return None
    if mid == "47":  # HT/FT
        parts = re.split(r"[\/]", d)
        if len(parts) != 2: return None
        m2 = {"home": "home", "draw": "draw", "away": "away", "1": "home", "x": "draw", "2": "away"}
        htr = "home" if R["hh"] > R["ha"] else ("draw" if R["hh"] == R["ha"] else "away")
        want_ht = m2.get(parts[0].strip()); want_ft = m2.get(parts[1].strip())
        return want_ht == htr and want_ft == res if want_ht and want_ft else None
    if mid in ("548", "549", "550"):
        v = total if mid == "548" else (h if mid == "549" else a)
        if "+" in d: return v >= int(re.search(r"\d+", d).group())
        m = re.findall(r"\d+", d); return (int(m[0]) <= v <= int(m[1])) if len(m) == 2 else None
    return None


def run() -> dict:
    init_schema()
    now = datetime.now(timezone.utc).isoformat()
    settled = 0
    with connect() as conn:
        feat = {r["sb_event_id"]: r["sf_event_id"]
                for r in conn.execute("SELECT sb_event_id, sf_event_id FROM sf_features").fetchall()}
        pend = conn.execute(
            "SELECT * FROM tracked_picks WHERE status='pending' AND (kickoff IS NULL OR kickoff < ?)",
            (now,)).fetchall()
        cache: dict = {}
        for p in pend:
            sfid = feat.get(p["sb_event_id"])
            if not sfid:
                continue
            R = cache.get(sfid)
            if R is None and sfid not in cache:
                R = fetch_result(sfid); cache[sfid] = R
            if not R:
                continue
            w = settle_market(p["market_id"], p["specifier"], p["outcome_desc"], R)
            if w is None:
                status, result = "unknown", None
            else:
                status, result = ("won", 1) if w else ("lost", 0)
            conn.execute("UPDATE tracked_picks SET status=?, result=?, settled_at=? WHERE pick_id=?",
                         (status, result, now, p["pick_id"]))
            settled += 1
        conn.commit()
    return {"settled": settled}


if __name__ == "__main__":
    print(run())

"""
Sofascore stat-brain ingest (free, via curl_cffi Chrome-impersonation to bypass Cloudflare).

For each upcoming SportyBet fixture:
  1. find the Sofascore event (same date, fuzzy team-name match)
  2. pull both teams' recent finished matches -> compute market features
     (goals for/against avg, Over2.5 rate, BTTS rate, form points, win rate)
  3. pull H2H record
  4. store one feature row per fixture in sf_features

These features are the analysis fuel for the punter engine (form/goals -> market leanings).

Usage:  python -m src.ingest.sofascore [max_fixtures]
"""
from __future__ import annotations

import json
import sys
import time
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher

from curl_cffi import requests as cr

from src.db.db import connect, init_schema

API = "https://api.sofascore.com/api/v1"
LAST_N = 10          # recent matches per team for form/goal rates
CORNER_N = 3         # recent matches per team for corners/xG (per-match stat calls = costly)
TEAM_TTL_H = 18      # reuse a team's computed features for this many hours (form barely moves)
REQUEST_DELAY = 0.7                   # politer pacing to avoid Cloudflare bot block
_STAT_CACHE: dict[int, dict] = {}    # event_id -> {home_corners, away_corners, home_id}


import os as _os
_PROXY = _os.getenv("SCRAPER_PROXY") or None
_PROXIES = {"http": _PROXY, "https": _PROXY} if _PROXY else None


def _get(path: str, retries: int = 4) -> dict | None:
    """GET with backoff on 403/429 (Cloudflare rate-limit). Returns None on hard fail.
    Routes through SCRAPER_PROXY (residential) when set; direct otherwise."""
    for i in range(retries):
        try:
            r = cr.get(API + path, impersonate="chrome", timeout=20, proxies=_PROXIES)
        except Exception:
            time.sleep(2 * (i + 1))
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code in (403, 429):
            time.sleep(min(60, 8 * (i + 1)))   # escalating cooldown: 8,16,24,32s
            continue
        return None
    return None


# club abbreviations + state/region codes SportyBet appends that Sofascore omits
_NOISE = {
    "fc", "cf", "afc", "sc", "ac", "ec", "cd", "ca", "cr", "sad", "ad", "fk", "sk",
    "bk", "if", "ff", "kf", "sv", "us", "ud", "cp", "gd", "club", "clube", "de", "do", "da",
    # Brazil states
    "mg", "ba", "rj", "sp", "rs", "pr", "go", "ce", "pe", "pa", "df", "ma", "pb", "rn",
    "al", "se", "pi", "to", "mt", "ms", "ro", "am", "ap", "rr", "es",
}


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = "".join(c if (c.isalnum() or c == " ") else " " for c in s)
    toks = [t for t in s.split() if t and t not in _NOISE]
    return " ".join(toks).strip() or s.strip()


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


_DATE_CACHE: dict[str, dict] = {}    # date -> scheduled-events (avoid refetch per fixture)


def find_event(home: str, away: str, date_iso: str) -> tuple[dict | None, float]:
    """Find the Sofascore event matching a SportyBet fixture by date + team names."""
    if not date_iso:
        return None, 0.0
    date = date_iso[:10]
    data = _DATE_CACHE.get(date)
    if data is None:
        data = _get(f"/sport/football/scheduled-events/{date}") or {}
        _DATE_CACHE[date] = data
    if not data:
        return None, 0.0
    best, best_score = None, 0.0
    for e in data.get("events", []):
        h = e.get("homeTeam", {}).get("name", "")
        a = e.get("awayTeam", {}).get("name", "")
        score = (_sim(home, h) + _sim(away, a)) / 2
        if score > best_score:
            best, best_score = e, score
    return (best, best_score) if best_score >= 0.6 else (None, best_score)


def _match_stats(event_id: int) -> dict | None:
    """Per-match stats for a finished game: corners, yellow, red, fouls (home/away)."""
    if event_id in _STAT_CACHE:
        return _STAT_CACHE[event_id]
    st = _get(f"/event/{event_id}/statistics")
    res: dict = {}
    if st:
        for grp in st.get("statistics", []):
            if grp.get("period") != "ALL":
                continue
            for cat in grp.get("groups", []):
                for item in cat.get("statisticsItems", []):
                    nm = item.get("name", "").lower()
                    key = ("xg" if "expected goal" in nm else
                           "corners" if "corner" in nm else
                           "yellow" if "yellow" in nm else
                           "red" if "red card" in nm or nm == "red cards" else
                           "fouls" if nm == "fouls" else None)
                    if key:
                        try:
                            res[f"home_{key}"] = float(item.get("home"))
                            res[f"away_{key}"] = float(item.get("away"))
                        except (TypeError, ValueError):
                            pass
    res = res or None
    _STAT_CACHE[event_id] = res
    return res


def team_features(team_id: int) -> dict | None:
    """Compute goal/form/corner features from a team's recent finished matches."""
    data = _get(f"/team/{team_id}/events/last/0")
    if not data:
        return None
    evs = [e for e in data.get("events", [])
           if e.get("status", {}).get("type") == "finished"][-LAST_N:]
    if not evs:
        return None

    gf = ga = over25 = btts = pts = wins = 0
    htgf = htga = 0.0
    n = 0
    for e in evs:
        hs = e.get("homeScore", {}).get("current")
        as_ = e.get("awayScore", {}).get("current")
        if hs is None or as_ is None:
            continue
        is_home = e.get("homeTeam", {}).get("id") == team_id
        for_, against = (hs, as_) if is_home else (as_, hs)
        gf += for_
        ga += against
        over25 += 1 if (hs + as_) > 2.5 else 0
        btts += 1 if (hs > 0 and as_ > 0) else 0
        if for_ > against:
            pts += 3; wins += 1
        elif for_ == against:
            pts += 1
        # half-time goals (period1)
        h1 = e.get("homeScore", {}).get("period1")
        a1 = e.get("awayScore", {}).get("period1")
        if h1 is not None and a1 is not None:
            htgf += h1 if is_home else a1
            htga += a1 if is_home else h1
        n += 1
    if n == 0:
        return None

    # corners + cards + fouls + xG from last CORNER_N matches (per-match stat calls)
    cf = ca = cards = fouls = xgf = xga = 0.0
    cn = sn = xn = 0
    for e in evs[-CORNER_N:]:
        ms = _match_stats(e["id"])
        time.sleep(REQUEST_DELAY)
        if not ms:
            continue
        is_home = e.get("homeTeam", {}).get("id") == team_id
        if "home_corners" in ms:
            cf += ms["home_corners"] if is_home else ms["away_corners"]
            ca += ms["away_corners"] if is_home else ms["home_corners"]
            cn += 1
        if "home_xg" in ms:
            xgf += ms["home_xg"] if is_home else ms["away_xg"]
            xga += ms["away_xg"] if is_home else ms["home_xg"]
            xn += 1
        y = ms.get("home_yellow" if is_home else "away_yellow", 0)
        r = ms.get("home_red" if is_home else "away_red", 0)
        fo = ms.get("home_fouls" if is_home else "away_fouls", 0)
        cards += (y + r)
        fouls += fo
        sn += 1

    last_ts = evs[-1].get("startTimestamp") if evs else None
    return {
        "gf": round(gf / n, 3), "ga": round(ga / n, 3),
        "over25": round(over25 / n, 3), "btts": round(btts / n, 3),
        "form": round(pts / (3 * n), 3), "winrate": round(wins / n, 3), "n": n,
        "htgf": round(htgf / n, 3), "htga": round(htga / n, 3),
        "cf": round(cf / cn, 2) if cn else None,
        "ca": round(ca / cn, 2) if cn else None,
        "cards": round(cards / sn, 2) if sn else None,
        "fouls": round(fouls / sn, 2) if sn else None,
        "xgf": round(xgf / xn, 3) if xn else None,
        "xga": round(xga / xn, 3) if xn else None,
        "last_ts": last_ts,
    }


def cached_team_features(team_id: int) -> dict | None:
    """team_features with a persistent TTL cache — re-runs + shared teams skip the API entirely."""
    now = datetime.now(timezone.utc)
    try:
        with connect() as c:
            c.execute("CREATE TABLE IF NOT EXISTS sf_team_cache "
                      "(team_id INTEGER PRIMARY KEY, features TEXT, computed_at TEXT)")
            row = c.execute("SELECT features, computed_at FROM sf_team_cache WHERE team_id=?",
                            (team_id,)).fetchone()
        if row:
            age_h = (now - datetime.fromisoformat(row[1])).total_seconds() / 3600
            if age_h < TEAM_TTL_H:
                return json.loads(row[0])
    except Exception:
        pass
    feats = team_features(team_id)
    if feats:
        try:
            with connect() as c:
                c.execute("INSERT OR REPLACE INTO sf_team_cache VALUES (?,?,?)",
                          (team_id, json.dumps(feats), now.isoformat()))
                c.commit()
        except Exception:
            pass
    return feats


# position weights for availability impact
_ATK_W = {"F": 1.0, "M": 0.4, "D": 0.0, "G": 0.0}
_DEF_W = {"D": 1.0, "G": 0.8, "M": 0.2, "F": 0.0}
_VALUE_SCALE = 120_000_000   # market value at which loss saturates


def availability(sf_event_id: int) -> dict:
    """Missing players -> value-weighted attack_loss / def_weak per side + names."""
    lu = _get(f"/event/{sf_event_id}/lineups")
    out = {"home": {"al": 0.0, "dw": 0.0, "txt": ""},
           "away": {"al": 0.0, "dw": 0.0, "txt": ""}}
    if not lu:
        return out
    reasons = {0: "inj", 1: "susp", 2: "doubt"}
    for side in ("home", "away"):
        atk = dfn = 0.0
        names = []
        for mp in (lu.get(side, {}).get("missingPlayers") or []):
            pl = mp.get("player", {})
            pos = pl.get("position", "M")
            val = (pl.get("proposedMarketValueRaw") or {}).get("value") or 0
            atk += val * _ATK_W.get(pos, 0.3)
            dfn += val * _DEF_W.get(pos, 0.2)
            names.append(f"{pl.get('shortName', pl.get('name', '?'))}({pos},{reasons.get(mp.get('reason'), '?')})")
        out[side]["al"] = round(min(0.30, atk / _VALUE_SCALE), 4)
        out[side]["dw"] = round(min(0.30, dfn / _VALUE_SCALE), 4)
        out[side]["txt"] = ", ".join(names[:5])
    return out


def h2h(event_id: int) -> tuple[int, int, int]:
    data = _get(f"/event/{event_id}/h2h")
    if not data:
        return 0, 0, 0
    duel = data.get("teamDuel") or {}
    return (duel.get("homeWins", 0) or 0,
            duel.get("draws", 0) or 0,
            duel.get("awayWins", 0) or 0)


def enrich_fixture(conn, sb_event_id, home, away, kickoff) -> bool:
    ev, score = find_event(home, away, kickoff)
    if not ev:
        return False
    hf = cached_team_features(ev["homeTeam"]["id"])
    af = cached_team_features(ev["awayTeam"]["id"])
    if not hf or not af:
        return False
    time.sleep(REQUEST_DELAY)
    hw, dr, aw = h2h(ev["id"])
    time.sleep(REQUEST_DELAY)
    av = availability(ev["id"])

    # rest/congestion days from each team's last finished match
    ko = ev.get("startTimestamp")
    def rest(side_ts):
        if ko and side_ts:
            return int(max(0, (ko - side_ts) / 86400))
        return None
    h_rest, a_rest = rest(hf.get("last_ts")), rest(af.get("last_ts"))

    conn.execute(
        """INSERT OR REPLACE INTO sf_features
           (sb_event_id, sf_event_id, match_score,
            home_gf,home_ga,home_over25,home_btts,home_form,home_winrate,home_n,home_cf,home_ca,
            home_htgf,home_htga,home_cards,home_fouls,home_xgf,home_xga,
            away_gf,away_ga,away_over25,away_btts,away_form,away_winrate,away_n,away_cf,away_ca,
            away_htgf,away_htga,away_cards,away_fouls,away_xgf,away_xga,
            h2h_home_wins,h2h_draws,h2h_away_wins,
            home_attack_loss,home_def_weak,home_rest_days,home_missing,
            away_attack_loss,away_def_weak,away_rest_days,away_missing,
            computed_at)
           VALUES (?,?,?, ?,?,?,?,?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?,?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,
                   ?,?,?,?, ?,?,?,?, ?)""",
        (sb_event_id, ev["id"], round(score, 3),
         hf["gf"], hf["ga"], hf["over25"], hf["btts"], hf["form"], hf["winrate"], hf["n"], hf["cf"], hf["ca"],
         hf["htgf"], hf["htga"], hf["cards"], hf["fouls"], hf["xgf"], hf["xga"],
         af["gf"], af["ga"], af["over25"], af["btts"], af["form"], af["winrate"], af["n"], af["cf"], af["ca"],
         af["htgf"], af["htga"], af["cards"], af["fouls"], af["xgf"], af["xga"],
         hw, dr, aw,
         av["home"]["al"], av["home"]["dw"], h_rest, av["home"]["txt"],
         av["away"]["al"], av["away"]["dw"], a_rest, av["away"]["txt"],
         datetime.now(timezone.utc).isoformat()),
    )
    return True


def run(max_fixtures: int = 30):
    init_schema()
    now_iso = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        fixtures = conn.execute(
            """SELECT event_id, home_team, away_team, kickoff_ts FROM sb_events
               WHERE kickoff_ts > ? ORDER BY kickoff_ts LIMIT ?""",
            (now_iso, max_fixtures),
        ).fetchall()
        print(f"Enriching {len(fixtures)} SportyBet fixtures via Sofascore ...")
        ok = 0
        for i, f in enumerate(fixtures, 1):
            if enrich_fixture(conn, f["event_id"], f["home_team"], f["away_team"], f["kickoff_ts"]):
                ok += 1
            if i % 5 == 0:
                conn.commit()
                print(f"  {i}/{len(fixtures)} processed, {ok} matched+enriched")
            time.sleep(REQUEST_DELAY)
        conn.commit()
    print(f"\nDone. {ok}/{len(fixtures)} fixtures enriched with Sofascore stats.")


def run_scope(start_date: str, end_date: str, max_fixtures: int = 2000, skip_existing: bool = True):
    """Enrich SportyBet fixtures kicking off within [start_date, end_date] (YYYY-MM-DD)."""
    init_schema()
    q = ("SELECT event_id, home_team, away_team, kickoff_ts FROM sb_events "
         "WHERE substr(kickoff_ts,1,10) BETWEEN ? AND ?")
    if skip_existing:
        q += " AND event_id NOT IN (SELECT sb_event_id FROM sf_features)"
    q += " ORDER BY kickoff_ts LIMIT ?"
    with connect() as conn:
        fixtures = conn.execute(q, (start_date, end_date, max_fixtures)).fetchall()
        print(f"Enriching {len(fixtures)} fixtures in {start_date}..{end_date} ...")
        ok = 0
        for i, f in enumerate(fixtures, 1):
            try:
                if enrich_fixture(conn, f["event_id"], f["home_team"], f["away_team"], f["kickoff_ts"]):
                    ok += 1
            except Exception as e:
                print(f"  ! {f['home_team']} v {f['away_team']}: {e}")
            if i % 5 == 0:
                conn.commit()
                print(f"  {i}/{len(fixtures)}, {ok} enriched")
            if i % 40 == 0:            # periodic cool-down to avoid Cloudflare bot block
                time.sleep(25)
            time.sleep(REQUEST_DELAY)
        conn.commit()
    print(f"Scope enrichment done: {ok}/{len(fixtures)}")
    return ok


if __name__ == "__main__":
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    run(cap)

"""
Sofascore basketball enrichment — last-N scoring profile per team (points-for/against),
form, and rest, matched to SportyBet fixtures by team name + date. Same client/backoff as the
football ingest (curl_cffi Chrome impersonation, polite pacing). Feeds basketball_projector.
"""
from __future__ import annotations

import os
import time
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher

from curl_cffi import requests as cr

API = "https://api.sofascore.com/api/v1"
LAST_N = 12          # recent games for scoring averages
REQUEST_DELAY = 0.6
_PROXY = os.getenv("SCRAPER_PROXY") or None
_PROXIES = {"http": _PROXY, "https": _PROXY} if _PROXY else None
_DATE_CACHE: dict = {}
_TEAM_CACHE: dict = {}


def _get(path, retries=4):
    for i in range(retries):
        try:
            r = cr.get(API + path, impersonate="chrome", timeout=20, proxies=_PROXIES)
        except Exception:
            time.sleep(2 * (i + 1)); continue
        if r.status_code == 200:
            return r.json()
        if r.status_code in (403, 429):
            time.sleep(min(60, 8 * (i + 1))); continue
        return None
    return None


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return "".join(c if c.isalnum() or c == " " else " " for c in s).strip()


def _sim(a, b):
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def find_event(home, away, date_iso):
    if not date_iso:
        return None, 0.0
    date = date_iso[:10]
    if date not in _DATE_CACHE:
        d = _get(f"/sport/basketball/scheduled-events/{date}")
        _DATE_CACHE[date] = (d or {}).get("events", [])
        time.sleep(REQUEST_DELAY)
    best, score = None, 0.0
    for e in _DATE_CACHE[date]:
        h = e.get("homeTeam", {}).get("name", ""); a = e.get("awayTeam", {}).get("name", "")
        s = (_sim(home, h) + _sim(away, a)) / 2
        if s > score:
            best, score = e, s
    return (best, score) if score >= 0.6 else (None, score)


def team_profile(team_id, before_ts=None):
    """Last-N finished games -> avg points for/against, n, last game timestamp (for rest)."""
    if team_id in _TEAM_CACHE:
        return _TEAM_CACHE[team_id]
    d = _get(f"/team/{team_id}/events/last/0")
    time.sleep(REQUEST_DELAY)
    evs = [e for e in (d or {}).get("events", []) if e.get("status", {}).get("type") == "finished"]
    pf, pa, last_ts = [], [], None
    for e in evs[-LAST_N:]:
        hs = e.get("homeScore", {}).get("current"); as_ = e.get("awayScore", {}).get("current")
        if hs is None or as_ is None:
            continue
        is_home = e.get("homeTeam", {}).get("id") == team_id
        pf.append(hs if is_home else as_); pa.append(as_ if is_home else hs)
        last_ts = e.get("startTimestamp") or last_ts
    if len(pf) < 3:
        return None
    prof = {"pts_for": round(sum(pf) / len(pf), 2), "pts_against": round(sum(pa) / len(pa), 2),
            "n": len(pf), "last_ts": last_ts}
    _TEAM_CACHE[team_id] = prof
    return prof


def features_for(home_name, away_name, date_iso, kickoff_ts=None):
    """Return {home:{pts_for,pts_against,n,rest_adj}, away:{...}} or None if unmatched."""
    ev, sc = find_event(home_name, away_name, date_iso)
    if not ev:
        return None
    hid = ev.get("homeTeam", {}).get("id"); aid = ev.get("awayTeam", {}).get("id")
    hp = team_profile(hid); ap = team_profile(aid)
    if not hp or not ap:
        return None
    # rest adjustment: back-to-back (<=1 day rest) costs ~ -1.5 pts
    def rest_adj(prof):
        ko = kickoff_ts or ev.get("startTimestamp")
        if not ko or not prof.get("last_ts"):
            return 0.0
        days = (ko - prof["last_ts"]) / 86400.0
        return -1.5 if days <= 1.3 else (0.5 if days >= 3 else 0.0)
    hp = {**hp, "rest_adj": rest_adj(hp)}
    ap = {**ap, "rest_adj": rest_adj(ap)}
    return {"home": hp, "away": ap, "match_score": round(sc, 2),
            "sofa_event": ev.get("id")}


if __name__ == "__main__":
    # live end-to-end test on a real upcoming NBA game
    d = _get("/sport/basketball/scheduled-events/2026-06-04") or {}
    nba = [e for e in d.get("events", []) if "NBA" in (e.get("tournament", {}).get("name", ""))]
    e = nba[0] if nba else d.get("events", [])[0]
    h = e["homeTeam"]["name"]; a = e["awayTeam"]["name"]
    print("GAME:", h, "vs", a, "|", e.get("tournament", {}).get("name"))
    feat = features_for(h, a, "2026-06-04", e.get("startTimestamp"))
    print("features:", feat)
    if feat:
        from src.models import basketball_projector as bp
        proj = bp.project_from_scores(feat["home"], feat["away"])
        print("projection:", proj)
        print("  Total O/U ~", proj["exp_total"], "-> Over 220.5:", round(bp.model_prob_for(proj,"225","total=220.5","Over 220.5"),3))
        print("  Margin", proj["exp_margin"], "-> Home ML:", round(bp.model_prob_for(proj,"219",None,"Home"),3))
        print("  why:", bp.reason(proj, "225", "Over"))
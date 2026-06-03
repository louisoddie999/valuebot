"""
football-data.co.uk loader.

Downloads per-league/per-season CSVs, normalises, and loads into SQLite:
  - matches (results + match stats)
  - odds    (Bet365 1X2 open+close, Over/Under 2.5 open+close)

CSV reference: https://www.football-data.co.uk/notes.txt
URL pattern:   {base}/{season}/{leaguecode}.csv   e.g. .../2324/E0.csv
"""
from __future__ import annotations

import io
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from src.db.db import connect, load_config, init_schema
from src.ingest.team_mapping import canonical

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SoccerValueBot/1.0"}

# football-data column -> our match column
STAT_COLS = {
    "FTHG": "fthg", "FTAG": "ftag", "FTR": "ftr",
    "HTHG": "hthg", "HTAG": "htag", "HTR": "htr",
    "HS": "home_shots", "AS": "away_shots",
    "HST": "home_sot", "AST": "away_sot",
    "HC": "home_corners", "AC": "away_corners",
    "HF": "home_fouls", "AF": "away_fouls",
    "HY": "home_yellow", "AY": "away_yellow",
    "HR": "home_red", "AR": "away_red",
    "Referee": "referee",
}

# (bookmaker, market, selection, csv_col, is_closing)
ODDS_MAP = [
    ("Bet365", "1X2", "H", "B365H", 0),
    ("Bet365", "1X2", "D", "B365D", 0),
    ("Bet365", "1X2", "A", "B365A", 0),
    ("Bet365", "1X2", "H", "B365CH", 1),
    ("Bet365", "1X2", "D", "B365CD", 1),
    ("Bet365", "1X2", "A", "B365CA", 1),
    ("Bet365", "OU25", "Over", "B365>2.5", 0),
    ("Bet365", "OU25", "Under", "B365<2.5", 0),
    ("Bet365", "OU25", "Over", "B365C>2.5", 1),
    ("Bet365", "OU25", "Under", "B365C<2.5", 1),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def download_csv(base: str, season: str, league_code: str) -> pd.DataFrame | None:
    url = f"{base}/{season}/{league_code}.csv"
    try:
        r = requests.get(url, headers=UA, timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  ! download failed {url}: {e}")
        return None
    # football-data CSVs sometimes have trailing empty columns / encoding quirks
    df = pd.read_csv(io.StringIO(r.text), encoding="latin-1", on_bad_lines="skip")
    df.columns = [c.strip() for c in df.columns]
    return df


def _parse_date(val) -> str | None:
    dt = pd.to_datetime(val, dayfirst=True, errors="coerce")
    return None if pd.isna(dt) else dt.strftime("%Y-%m-%d")


def _to_int(val):
    try:
        if pd.isna(val):
            return None
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _to_float(val):
    try:
        if pd.isna(val):
            return None
        return float(val)
    except (ValueError, TypeError):
        return None


def load_league_season(conn, base, season, league_code, league_name) -> int:
    df = download_csv(base, season, league_code)
    if df is None or df.empty or "HomeTeam" not in df.columns:
        return 0

    inserted = 0
    for _, row in df.iterrows():
        date = _parse_date(row.get("Date"))
        home = canonical(str(row.get("HomeTeam", "")).strip())
        away = canonical(str(row.get("AwayTeam", "")).strip())
        if not date or not home or not away:
            continue

        match = {
            "date": date, "league": league_name, "season": season,
            "home_team": home, "away_team": away,
        }
        for csv_col, db_col in STAT_COLS.items():
            v = row.get(csv_col)
            match[db_col] = (str(v).strip() if db_col in ("ftr", "htr", "referee")
                             else _to_int(v)) if v is not None else None

        cols = ", ".join(match.keys())
        ph = ", ".join("?" for _ in match)
        cur = conn.execute(
            f"INSERT OR IGNORE INTO matches ({cols}) VALUES ({ph})",
            list(match.values()),
        )
        # fetch match_id (whether newly inserted or pre-existing)
        mid_row = conn.execute(
            "SELECT match_id FROM matches WHERE date=? AND home_team=? AND away_team=?",
            (date, home, away),
        ).fetchone()
        if not mid_row:
            continue
        match_id = mid_row["match_id"]
        if cur.rowcount:
            inserted += 1

        # odds
        for bookmaker, market, selection, csv_col, is_closing in ODDS_MAP:
            odd = _to_float(row.get(csv_col))
            if odd is None or odd < 1.01:
                continue
            conn.execute(
                """INSERT OR IGNORE INTO odds
                   (match_id, bookmaker, market, selection, odds_decimal, is_closing, captured_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (match_id, bookmaker, market, selection, odd, is_closing, _now()),
            )
    conn.commit()
    return inserted


def run() -> None:
    cfg = load_config()
    init_schema()
    base = cfg["football_data"]["base_url"]
    delay = cfg["football_data"].get("request_delay_sec", 1.0)
    leagues = cfg["leagues"]
    seasons = cfg["seasons"]

    total = 0
    with connect() as conn:
        for season in seasons:
            for code, name in leagues.items():
                print(f"Loading {name} {season} ({code}) ...")
                n = load_league_season(conn, base, season, code, name)
                print(f"  + {n} new matches")
                total += n
                time.sleep(delay)
    print(f"\nDone. {total} new matches loaded into SQLite.")


if __name__ == "__main__":
    run()

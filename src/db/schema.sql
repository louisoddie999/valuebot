-- SOCCER-VALUE-BOT SQLite schema

CREATE TABLE IF NOT EXISTS teams (
    team_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT UNIQUE NOT NULL,
    league         TEXT
);

-- maps every raw source alias -> canonical team
CREATE TABLE IF NOT EXISTS team_aliases (
    alias          TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    source         TEXT
);

CREATE TABLE IF NOT EXISTS matches (
    match_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT NOT NULL,          -- ISO YYYY-MM-DD
    league       TEXT NOT NULL,
    season       TEXT NOT NULL,          -- e.g. 2324
    home_team    TEXT NOT NULL,
    away_team    TEXT NOT NULL,
    fthg         INTEGER,                -- full time home goals
    ftag         INTEGER,
    ftr          TEXT,                   -- H / D / A
    hthg         INTEGER,                -- half time home goals
    htag         INTEGER,
    htr          TEXT,
    home_shots   INTEGER,
    away_shots   INTEGER,
    home_sot     INTEGER,                -- shots on target
    away_sot     INTEGER,
    home_corners INTEGER,
    away_corners INTEGER,
    home_fouls   INTEGER,
    away_fouls   INTEGER,
    home_yellow  INTEGER,
    away_yellow  INTEGER,
    home_red     INTEGER,
    away_red     INTEGER,
    referee      TEXT,
    UNIQUE(date, home_team, away_team)
);

-- long-format odds: one row per match/bookmaker/market/selection
CREATE TABLE IF NOT EXISTS odds (
    odds_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id     INTEGER NOT NULL REFERENCES matches(match_id),
    bookmaker    TEXT NOT NULL,
    market       TEXT NOT NULL,          -- 1X2 / OU25 / AH ...
    selection    TEXT NOT NULL,          -- H/D/A, Over/Under, line
    odds_decimal REAL NOT NULL,
    is_closing   INTEGER DEFAULT 0,      -- 1 if closing line
    captured_at  TEXT,
    UNIQUE(match_id, bookmaker, market, selection, is_closing)
);

CREATE TABLE IF NOT EXISTS features (
    match_id     INTEGER NOT NULL REFERENCES matches(match_id),
    feature_name TEXT NOT NULL,
    feature_value REAL,
    computed_at  TEXT,
    PRIMARY KEY (match_id, feature_name)
);

CREATE TABLE IF NOT EXISTS predictions (
    pred_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id      INTEGER NOT NULL REFERENCES matches(match_id),
    market        TEXT NOT NULL,
    selection     TEXT NOT NULL,
    model_prob    REAL NOT NULL,
    fair_odds     REAL,
    model_version TEXT,
    generated_at  TEXT
);

CREATE TABLE IF NOT EXISTS value_bets (
    bet_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id      INTEGER NOT NULL REFERENCES matches(match_id),
    market        TEXT NOT NULL,
    selection     TEXT NOT NULL,
    bookmaker     TEXT,
    book_odds     REAL,
    model_prob    REAL,
    implied_prob  REAL,
    ev            REAL,
    kelly_fraction REAL,
    stake_units   REAL,
    flagged_at    TEXT
);

CREATE TABLE IF NOT EXISTS ledger (
    ledger_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    bet_id        INTEGER REFERENCES value_bets(bet_id),
    stake_actual  REAL,
    result        TEXT,                  -- win / lose / void
    pnl           REAL,
    closing_odds  REAL,
    clv           REAL,
    settled_at    TEXT
);

-- ---- SportyBet live ingest (separate from historical football-data matches) ----
CREATE TABLE IF NOT EXISTS sb_events (
    event_id    TEXT PRIMARY KEY,        -- sr:match:xxxx
    home_team   TEXT,
    away_team   TEXT,
    tournament  TEXT,
    category    TEXT,                     -- country / International
    sport       TEXT,
    kickoff_ts  TEXT,                     -- ISO UTC
    status      INTEGER,
    captured_at TEXT
);

CREATE TABLE IF NOT EXISTS sb_odds (
    sb_odds_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id     TEXT NOT NULL,
    market_id    TEXT,
    market_name  TEXT,
    specifier    TEXT,                    -- e.g. total=2.5, hcp=-1
    outcome_id   TEXT,
    outcome_desc TEXT,                    -- Home, Over 2.5, Yes ...
    odds         REAL,
    book_prob    REAL,                    -- SportyBet's own (margin-removed) probability
    captured_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_sbodds_event ON sb_odds(event_id);
CREATE INDEX IF NOT EXISTS idx_sbodds_market ON sb_odds(event_id, market_id, specifier);
CREATE INDEX IF NOT EXISTS idx_sbevents_kick ON sb_events(kickoff_ts);

-- Sofascore stat-brain features per SportyBet fixture (one row per matched event)
CREATE TABLE IF NOT EXISTS sf_features (
    sb_event_id   TEXT PRIMARY KEY,
    sf_event_id   INTEGER,
    match_score   REAL,                 -- fuzzy name-match confidence 0-1
    home_gf       REAL, home_ga REAL, home_over25 REAL, home_btts REAL,
    home_form     REAL, home_winrate REAL, home_n INTEGER,
    home_cf       REAL, home_ca REAL,        -- corners for / against avg
    home_htgf     REAL, home_htga REAL,      -- 1st-half goals for / against avg
    home_cards    REAL, home_fouls REAL,     -- cards (Y+R) / fouls avg
    home_xgf      REAL, home_xga REAL,        -- xG for / against avg (true xG)
    away_gf       REAL, away_ga REAL, away_over25 REAL, away_btts REAL,
    away_form     REAL, away_winrate REAL, away_n INTEGER,
    away_cf       REAL, away_ca REAL,
    away_htgf     REAL, away_htga REAL,
    away_cards    REAL, away_fouls REAL,
    away_xgf      REAL, away_xga REAL,
    h2h_home_wins INTEGER, h2h_draws INTEGER, h2h_away_wins INTEGER,
    -- availability / context layer
    home_attack_loss REAL, home_def_weak REAL, home_rest_days INTEGER, home_missing TEXT,
    away_attack_loss REAL, away_def_weak REAL, away_rest_days INTEGER, away_missing TEXT,
    computed_at   TEXT
);

-- Tracked picks (booked slips) for results/settlement
CREATE TABLE IF NOT EXISTS tracked_picks (
    pick_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    slip_id     TEXT,
    sb_event_id TEXT, match TEXT, league TEXT, kickoff TEXT,
    market_id   TEXT, market_name TEXT, specifier TEXT, outcome_id TEXT, outcome_desc TEXT,
    odds REAL, confidence REAL,
    status      TEXT DEFAULT 'pending',   -- pending | won | lost | void | unknown
    result      INTEGER,                   -- 1 win, 0 loss, NULL otherwise
    settled_at  TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tp_status ON tracked_picks(status);
CREATE INDEX IF NOT EXISTS idx_tp_event ON tracked_picks(sb_event_id);

-- self-recalibration: predicted-vs-actual curve learned from settled picks
CREATE TABLE IF NOT EXISTS calibration_curve (
    lo REAL, hi REAL, mid REAL, n INTEGER, actual REAL, offset REAL, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS calibration_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    n_total INTEGER DEFAULT 0, active INTEGER DEFAULT 0, updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);
CREATE INDEX IF NOT EXISTS idx_matches_league_season ON matches(league, season);
CREATE INDEX IF NOT EXISTS idx_odds_match ON odds(match_id);

-- basketball per-event projection (parallel to sf_features for football)
CREATE TABLE IF NOT EXISTS bb_features (
    sb_event_id TEXT PRIMARY KEY,
    sofa_event  INTEGER,
    match_score REAL,
    exp_total   REAL, exp_margin REAL, pts_home REAL, pts_away REAL,
    home_pf REAL, home_pa REAL, away_pf REAL, away_pa REAL, poss REAL,
    computed_at TEXT
);
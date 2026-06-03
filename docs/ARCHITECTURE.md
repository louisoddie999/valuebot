# SOCCER-VALUE-BOT — System Architecture & Technical Specification

**Version:** 1.0
**Date:** 2026-06-02
**Author:** Quant Analyst + 25yr Punter (acting)
**Status:** Architecture phase — approved scope, pre-build

---

## 0. Executive summary

This is **not** a "predict every game correctly" bot. No such thing exists. Bookmakers
employ teams of quants and still only win because of the margin (vig) they bake into odds.

This system is a **value-detection engine**. Its single job:

> Estimate the *true* probability of every match outcome from real data, compare it to the
> probability implied by Stake.com / SportyBet odds, and flag **only** the bets where our
> estimate says the odds are mispriced in our favour (positive expected value).

Profit comes from **selective betting on mispriced odds + disciplined staking**, proven by
**backtest before any real money moves**. If the backtest doesn't show a positive edge after
the bookmaker margin, we do not bet. That honesty is the whole product.

### Locked decisions (from kickoff)
| Decision | Choice |
|---|---|
| League scope | Top 5 EU leagues (EPL, La Liga, Serie A, Bundesliga, Ligue 1) |
| Data budget | Paid API — API-Football (~$15–30/mo) + free historical (football-data.co.uk, Understat) |
| Bet placement | **Manual** — bot outputs picks + stakes, human places them |
| First deliverables | (1) This architecture doc → (2) Backtest report proving edge on paper |

---

## 1. Goals & non-goals

### Goals
- Calibrated probabilities for all major markets offered by Stake + SportyBet.
- EV + Kelly stake per market; recommend only EV > threshold.
- Every pick cites the data factors that drove it (no black-box, no generic).
- Full walk-forward backtest: ROI, hit-rate, drawdown, Brier/calibration, P&L by market.
- Daily pipeline: fixtures → features → predict → compare odds → ranked value report.

### Non-goals (v1)
- No automated bet placement (ToS + ban risk; explicitly rejected).
- No live in-play betting (separate, harder problem — phase 2+).
- No "guaranteed wins" claims. Ever.
- No markets that fail the backtest (we cut them).

---

## 2. Markets covered

| Market | Model approach | Backtest priority |
|---|---|---|
| 1X2 (Home/Draw/Away) | Dixon-Coles (bivariate Poisson) | P0 |
| Double Chance | Derived from 1X2 distribution | P0 |
| Over/Under 0.5–4.5 goals | Poisson goal totals | P0 |
| BTTS (both teams to score) | Poisson independence-adjusted | P0 |
| Asian Handicap | Goal-supremacy distribution | P1 |
| Correct Score | Bivariate Poisson grid | P1 |
| HT/FT | Conditional Poisson (split-half scoring rates) | P2 |
| Total Corners O/U | Negative binomial / XGBoost | P2 |
| Total Cards O/U | Poisson + referee strictness feature | P2 |

**Rule:** A market ships to the live report ONLY after it clears the vig in backtest.
P0 first — they are the most liquid, best-modelled, and where Dixon-Coles is proven.

---

## 3. System architecture

```
                          ┌──────────────────────────────────────┐
                          │          DATA SOURCES                 │
                          │  • football-data.co.uk (CSV history)  │
                          │  • Understat / FBref (xG)             │
                          │  • API-Football (fixtures/lineups/    │
                          │    injuries/odds — live)              │
                          │  • Stake + SportyBet odds (scrape)    │
                          └──────────────────┬───────────────────┘
                                             │ ingest
                          ┌──────────────────▼───────────────────┐
                          │      INGESTION LAYER (src/ingest)     │
                          │  loaders + scrapers → raw tables      │
                          └──────────────────┬───────────────────┘
                                             │ clean/validate
                          ┌──────────────────▼───────────────────┐
                          │   STORAGE (SQLite v1 → Postgres v2)   │
                          │  matches · teams · odds · features    │
                          └──────────────────┬───────────────────┘
                                             │
                          ┌──────────────────▼───────────────────┐
                          │   FEATURE ENGINE (src/features)       │
                          │  form · xG · home/away · rest · H2H   │
                          │  injuries · lineup strength · referee │
                          └──────────────────┬───────────────────┘
                                             │
                          ┌──────────────────▼───────────────────┐
                          │   MODEL LAYER (src/models)            │
                          │  Dixon-Coles core + XGBoost overlay   │
                          │  → calibrated probabilities/market    │
                          └──────────────────┬───────────────────┘
                                             │
              ┌──────────────────────────────┴─────────────────────────────┐
              │                                                             │
   ┌──────────▼──────────┐                                  ┌──────────────▼─────────────┐
   │  VALUE ENGINE       │                                  │   BACKTEST ENGINE          │
   │  (src/value)        │                                  │   (src/backtest)           │
   │  vig strip → implied │                                  │   walk-forward 3+ seasons  │
   │  prob → EV → Kelly  │                                  │   ROI/hit/DD/Brier/P&L     │
   └──────────┬──────────┘                                  └──────────────┬─────────────┘
              │                                                             │
   ┌──────────▼──────────┐                                  ┌──────────────▼─────────────┐
   │  DAILY REPORT       │                                  │   BACKTEST REPORT          │
   │  reports/*.md/.csv  │                                  │   reports/backtest_*.md    │
   │  picks+stake+reason │                                  │   (Deliverable #2)         │
   └──────────┬──────────┘                                  └────────────────────────────┘
              │ optional
   ┌──────────▼──────────┐
   │  P&L LEDGER         │  tracked bets, CLV, running ROI
   │  data/ledger.sqlite │
   └─────────────────────┘
```

---

## 4. Data layer (60% of the work — get this right)

### 4.1 Sources
| Source | Use | Cost | Notes |
|---|---|---|---|
| football-data.co.uk | Historical results + closing odds, 20+ seasons, all top-5 | Free | CSV per league/season. Backbone of backtest. |
| Understat | Shot-level xG, per match | Free (scrape) | Best free xG. EPL/La Liga/Serie A/Bund/Ligue1 all covered. |
| FBref | Advanced stats, lineups | Free (scrape, rate-limited) | Backup / enrichment. |
| API-Football | Live fixtures, lineups, injuries, in-running odds | ~$15–30/mo | Powers the *daily* pipeline. |
| Stake.com | Live odds (our benchmark) | Free (scrape) | Crypto book, sharp-ish. Playwright. |
| SportyBet | Live odds (our benchmark) | Free (scrape) | Softer Nigerian/African book → more edges. Playwright. |

### 4.2 Closing-line value (CLV) — the truth serum
We log the **closing odds** for every flagged bet. If our picks consistently beat the closing
line (CLV > 0), the model has a real edge even before P&L confirms it. CLV is the fastest,
lowest-variance proof an edge is real. This is a non-negotiable tracked metric.

### 4.3 Schema (SQLite v1)
```sql
teams(team_id PK, name, league, fbref_id, understat_id, api_football_id)

matches(match_id PK, date, league, season, home_id FK, away_id FK,
        home_goals, away_goals, home_xg, away_xg, ht_home, ht_away,
        corners_home, corners_away, cards_home, cards_away, referee, status)

odds(odds_id PK, match_id FK, bookmaker, market, selection,
     odds_decimal, captured_at, is_closing BOOL)

features(match_id FK, feature_name, feature_value, computed_at)

predictions(pred_id PK, match_id FK, market, selection,
            model_prob, fair_odds, generated_at, model_version)

value_bets(bet_id PK, match_id FK, market, selection, bookmaker,
           book_odds, model_prob, implied_prob, ev, kelly_fraction,
           stake_units, flagged_at)

ledger(ledger_id PK, bet_id FK, stake_actual, result, pnl,
       closing_odds, clv, settled_at)
```

### 4.4 Data quality checklist (per ingest)
- [ ] Team-name normalisation across sources (Man Utd = Manchester United = ManU) via mapping table
- [ ] Duplicate match dedup (date + home + away key)
- [ ] Null policy: drop matches missing goals; flag (not drop) missing xG
- [ ] Odds sanity: decimal odds in [1.01, 1000]; flag arbitrage/stale captures
- [ ] Timezone normalised to UTC
- [ ] Rate limiting on all scrapers (respect robots; randomised delays)
- [ ] ToS reviewed per scraped site

---

## 5. Feature engineering

| Feature group | Examples |
|---|---|
| Form | Points/goals last 5 & 10, weighted-recency |
| Attack/Defence strength | Dixon-Coles α (attack), β (defence) per team, time-decayed |
| Expected goals | Rolling xG for/against, xG over/under-performance |
| Home/Away splits | Separate home vs away strength |
| Rest & congestion | Days since last match, games in last 14 days, travel |
| Head-to-head | Recent H2H goals/results (lightly weighted — small sample) |
| Lineup/Injury | Starting XI strength vs season baseline (API-Football) |
| Context | League position gap, motivation (relegation/title/dead rubber) |
| Referee | Cards/match average (for cards market) |
| Set-piece / corners | Corners for/against rolling (for corners market) |

**Time-decay:** Dixon-Coles ξ (xi) parameter down-weights old matches. Recent form > last season.
**Leakage guard:** every feature computed using **only data available before kickoff**. Enforced in code + verified in backtest (walk-forward, no peeking).

---

## 6. Model layer

### 6.1 Core — Dixon-Coles
The proven football model. Models home & away goals as (correlated) Poisson processes:
- Team attack & defence strengths + home advantage.
- Dixon-Coles low-score correction (fixes Poisson's under-estimation of 0-0, 1-0, 0-1, 1-1).
- Time-decay weighting.
- Output: full **scoreline probability matrix** → derive 1X2, O/U, BTTS, correct score, AH, DC.

### 6.2 Overlay — XGBoost (gradient boosting)
For markets where raw goal-Poisson is weak (corners, cards, complex contexts) and to blend
extra features. Trained per market, **probability-calibrated** (isotonic / Platt) so output
probabilities are honest — critical, because EV math is only as good as calibration.

### 6.3 Calibration is mandatory
A model that says "70%" must win ~70% of the time. We measure with **reliability curves +
Brier score**. Uncalibrated probabilities = fake EV = losing money. No model ships uncalibrated.

### 6.4 Model registry
Every trained model versioned (`model_version` in DB) with its training window, features,
and calibration stats, so every historical pick is reproducible.

---

## 7. Value & staking engine

### 7.1 Strip the vig
Bookmaker odds imply probabilities that sum to >100% (the margin). To get the book's *true*
implied probability we remove the margin (proportional / Shin / power methods — we'll test which
de-vig method best matches closing lines).

```
implied_prob_raw   = 1 / decimal_odds
overround          = Σ implied_prob_raw over all selections
implied_prob_fair  = implied_prob_raw / overround   (proportional de-vig)
```

### 7.2 Expected value
```
EV_per_unit = (model_prob × decimal_odds) − 1
Flag bet IF EV_per_unit > EV_THRESHOLD          (start at +0.03 = +3%)
AND model is calibrated for that market
AND liquidity/limits acceptable
```

### 7.3 Staking — fractional Kelly
```
kelly_fraction = (model_prob × (odds − 1) − (1 − model_prob)) / (odds − 1)
stake          = BANKROLL × KELLY_MULTIPLIER × kelly_fraction
KELLY_MULTIPLIER = 0.25   (quarter-Kelly — full Kelly ruins bankrolls on model error)
Cap any single stake at MAX_STAKE_PCT (e.g. 2% bankroll).
```

Quarter-Kelly + per-bet cap = survives model error and variance. This is how pros avoid ruin.

---

## 8. Backtest engine (Deliverable #2 — the proof)

### 8.1 Method — walk-forward, no look-ahead
```
For each season S in [S-3, S-2, S-1, current]:
  For each gameweek W in S:
     train model on ALL matches strictly before W
     predict markets for W
     de-vig the ACTUAL historical odds (football-data.co.uk closing odds)
     flag value bets (EV > threshold)
     settle vs real results, apply quarter-Kelly staking
     record P&L, CLV, calibration
```
No future data ever touches a prediction. This is the difference between a real edge and a
curve-fitted fantasy.

### 8.2 Metrics reported (per market + overall)
| Metric | Meaning | Pass bar |
|---|---|---|
| ROI % | Profit / total staked | > 0 after vig, ideally > 3% |
| Hit rate | % bets won | Context vs avg odds |
| Yield by odds band | ROI in 1.5–2.0, 2.0–3.0, 3.0+ | Spot where edge lives |
| Max drawdown | Worst peak-to-trough | Survivable at chosen stake |
| Brier score | Calibration quality | Lower = better |
| CLV % | Beat closing line | > 0 = real edge |
| Sample size | # bets | Enough to trust (>300/market ideal) |

### 8.3 Honesty gates
- Market with negative ROI after vig → **cut from live**, documented.
- Suspiciously high ROI → investigate leakage before celebrating.
- Out-of-sample only; report includes a "why you should still be skeptical" section.

---

## 9. Daily pipeline (after backtest passes)

```
06:00 UTC  pull today's fixtures (API-Football)
           → compute features (only pre-kickoff data)
           → run models → calibrated probabilities
           → scrape Stake + SportyBet odds
           → de-vig → EV → Kelly stake
           → rank value bets, attach reasoning + factor breakdown
           → write reports/value_YYYY-MM-DD.md + .csv
           → (optional) Telegram/email alert
Human reviews, places bets manually, logs into ledger.
Post-match: settle ledger, update CLV + running ROI.
```

### Sample daily report row
```
⚽ Arsenal vs Brighton — EPL — Sat 18:30 UTC
Market: Over 2.5 Goals
Model prob: 61%  | Fair odds: 1.64 | Stake odds (SportyBet): 1.85
De-vig book prob: 52% | EV: +12.9% | Quarter-Kelly stake: 1.4u
WHY: Arsenal xGF 2.3 (home), Brighton xGA 1.7 (away), both top-6 in BTTS%,
     ref avg high tempo, no key absences. H2H last 4: 3 went over.
Confidence: HIGH (calibrated, large sample market)
```

---

## 10. Tech stack

| Layer | Tool |
|---|---|
| Language | Python 3.11 |
| Data | pandas, numpy |
| Models | statsmodels (Poisson), custom Dixon-Coles, XGBoost, scikit-learn (calibration) |
| Scraping | Playwright (Stake/SportyBet/Understat), requests+BeautifulSoup (static) |
| API | API-Football (requests) |
| Storage | SQLite v1 → Postgres v2 |
| Scheduling | APScheduler / Windows Task Scheduler (cron-style) |
| Reports | Markdown + CSV → (v2) Streamlit dashboard |
| Alerts | Telegram bot / SMTP email (optional) |
| Orchestration | Ruflo (claude-flow) for multi-agent build |

---

## 11. Project structure
```
SOCCER-VALUE-BOT/
├── docs/
│   ├── ARCHITECTURE.md        ← this file
│   ├── PRD.md                 ← product requirements (next)
│   ├── DATA-SOURCES.md        ← source contracts + scrape notes
│   └── SKILL-LEDGER.md        ← skill invocation log
├── src/
│   ├── ingest/                ← loaders + scrapers
│   ├── features/              ← feature engine
│   ├── models/                ← dixon_coles.py, xgb_markets.py, calibrate.py
│   ├── value/                 ← devig.py, ev.py, kelly.py
│   ├── backtest/              ← walkforward.py, metrics.py
│   ├── report/                ← daily_report.py
│   └── db/                    ← schema.sql, db.py
├── data/                      ← sqlite db, raw csv cache
├── notebooks/                 ← exploration, model dev
├── reports/                   ← daily + backtest outputs
├── config.yaml                ← thresholds, bankroll, kelly mult, leagues
├── requirements.txt
└── README.md
```

---

## 12. Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| No real edge exists after vig | HIGH | Backtest FIRST. If no edge, don't bet. Honest gate. |
| Data leakage inflates backtest | HIGH | Strict walk-forward, pre-kickoff-only features, code review |
| Top-5 odds too sharp to beat | MED | SportyBet softer than Stake; focus edges where book is weakest; CLV check |
| Scraper breakage (site changes) | MED | Modular scrapers, fail-loud, API-Football fallback for odds |
| Overfitting markets to history | MED | Out-of-sample only, penalise complexity, min sample sizes |
| Bookmaker limits/bans winners | MED | Manual placement, stake discipline, spread across both books |
| Variance / drawdown panic | MED | Quarter-Kelly, documented max-DD, bankroll rules |
| API cost creep | LOW | Single paid API, cache aggressively |

---

## 13. Phased roadmap

| Phase | Deliverable | Gate to next |
|---|---|---|
| **0** | This architecture doc + PRD | User approval ✅ in progress |
| **1** | Data layer: schema + football-data.co.uk loader + Understat xG + team-name mapping | Clean 3-season dataset in SQLite |
| **2** | Dixon-Coles model + calibration on P0 markets (1X2/O-U/BTTS/DC) | Calibrated probs, Brier reported |
| **3** | Value engine (de-vig/EV/Kelly) + **Backtest report** (Deliverable #2) | Positive CLV/ROI after vig on ≥1 market |
| **4** | API-Football integration + Stake/SportyBet odds scrapers | Live odds flowing |
| **5** | Daily pipeline + report + ledger | End-to-end daily run |
| **6** | P1/P2 markets (AH, correct score, corners, cards) — each gated by backtest | Markets that pass ship |
| **7** | Dashboard + alerts (optional) | — |

**Hard rule:** No real money until Phase 3 backtest shows positive expected value after the
bookmaker margin on at least one market. If it doesn't, we iterate or we stop. That's the deal.

---

## 14. Legal / responsible-gambling note
- Betting is legal-age only; check local jurisdiction.
- This tool informs decisions; it does not guarantee profit. Variance is real; losing runs happen.
- Bankroll = money you can afford to lose. Bot enforces stake caps but discipline is human.
- No automated placement (ToS compliance + account safety).

---

*End of architecture spec. Next: PRD.md, then begin Phase 1 build.*

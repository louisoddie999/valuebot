# Data Sources

| Source | Role | URL | Fields | Cost |
|---|---|---|---|---|
| **football-data.co.uk** | Backbone | https://www.football-data.co.uk | Results, match stats (shots/corners/cards/fouls), Bet365 1X2 open+close, O/U 2.5 open+close, AH | Free |
| **Understat** | xG features | https://understat.com | Shot-level xG, per-team xG for/against | Free (scrape) |
| **API-Football** | Live daily pipeline | https://www.api-football.com | Fixtures, lineups, injuries, live odds | ~$15–30/mo |
| **Stake.com** | Live odds benchmark | https://stake.com | Live odds (sharp-ish) | Free (scrape) |
| **SportyBet** | Live odds benchmark | https://sportybet.com | Live odds (softer → more edges) | Free (scrape) |
| **openfootball/football.json** | Supplement only | https://github.com/openfootball/football.json | Scores + fixtures ONLY (no odds, no xG) | Free |

## openfootball verdict
Confirmed structure: `{round, date, team1, team2, score:{ft:[h,a]}}`. Scores + fixtures only.
No odds → unusable for backtest as a primary. No xG. **Supplementary** use: clean fixture
lists, name cross-checks, leagues football-data.co.uk misses. Not the backbone.

## football-data.co.uk codes
League: E0=Premier League, SP1=La Liga, I1=Serie A, D1=Bundesliga, F1=Ligue 1.
Season: `2324` = 2023/24. URL: `{base}/{season}/{code}.csv`.
Column reference: https://www.football-data.co.uk/notes.txt

## Ingest status
- [x] Loader built: `src/ingest/football_data_loader.py`
- [x] Schema: `src/db/schema.sql`
- [x] Team mapping: `src/ingest/team_mapping.py`
- [ ] Understat xG loader (Phase 1 next)
- [ ] API-Football (Phase 4)
- [ ] Stake/SportyBet scrapers (Phase 4)

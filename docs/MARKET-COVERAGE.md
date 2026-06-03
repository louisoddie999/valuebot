# Market Coverage Map — SportyBet markets → our models

SportyBet football carries **157+ distinct market groups** (scraped, see `sportybet-markets.md`).
This maps each family to HOW we model it and WHAT data it needs. Corners ✅ and cards ✅ are
already in our DB (`home_corners`/`away_corners`, `home_yellow`/`away_yellow`/`home_red`/`away_red`
— 8,906 matches each).

## Tier A — derived directly from Dixon-Coles scoreline matrix (BUILT)
One model → all of these. No extra data.
- 1X2, Double Chance, Draw No Bet, Home/Away No Bet
- Over/Under (every line 0.5–6.5), Home O/U, Away O/U
- BTTS (GG/NG), Odd/Even, Team Odd/Even
- Correct Score, Goal Range, Multigoals, Exact Goals, Winning Margin
- Clean Sheet (home/away), Win to Nil, Which Team to Score
- Combos: O/U & GG/NG, 1X2 & O/U, DC & Total, etc. (joint probs from matrix)
- Asian/European Handicap (from goal-supremacy distribution)

## Tier B — needs half-split scoring model (DATA READY: HTHG/HTAG stored)
Fit a second Poisson on first-half goals; second half = FT − HT.
- Halftime/Fulltime (HT/FT), HT/FT & Total, HT/FT correct score
- 1st Half / 2nd Half: O/U, X, DC, DNB, GG/NG, Correct Score, Odd/Even, Multigoals
- Highest Scoring Half, Score in Both Halves, Both Halves Over/Under

## Tier C — separate count models (DATA READY in our DB)
- **Corners** (SportyBet: Total Corners, Home/Away Corners, 1st-Half Corners)
  → Negative-Binomial or Poisson on `home_corners`/`away_corners`. Backtestable on history.
- **Cards / Bookings** (SportyBet club games carry these)
  → Poisson on yellows+reds, with **referee strictness** feature. We store `*_yellow`/`*_red`.

## Tier D — NOT modelable from current data (needs event/player feeds)
Defer to API-Football (Phase 4) or skip — these are noise/low-edge for us:
- Player to score / anytime scorer / assists (no player data yet)
- Xth-goal timing, minute-interval markets, "Next Goal", "Last Goal" (live/in-play)
- "Match Result after X minutes", interval-specific goal windows

## Build order (gated by backtest each step)
1. **Tier A** — DONE (model built). Backtest 1X2 + O/U2.5 now → expand to DC/BTTS/AH.
2. **Tier C corners** — high value, SportyBet/Stake offer it, data ready. Add after Tier A proof.
3. **Tier B halves** — HT/FT etc. Data ready.
4. **Tier C cards** — referee feature needed.
5. **Tier D** — only if API-Football added and edge proven.

## Honesty note
Having 157 markets ≠ betting 157 markets. Most are derivatives of the same goal model and are
**highly correlated** — betting many at once is NOT diversification, it's the same bet repeated.
We bet only the few markets that (a) clear the vig in backtest and (b) where SportyBet/Stake odds
are soft. Quality of edge > quantity of markets.

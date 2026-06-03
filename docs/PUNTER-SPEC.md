# Punter Engine Spec — tiered accumulators from the full SportyBet market

**Persona:** 25-year professional punter + quant. Not generic H2H. Uses the FULL SportyBet
market spread (193 markets) and builds tiered accumulators, each leg stat-justified.

## Probability sources (3 layers compared per selection)
1. `model_prob` — OUR calibrated estimate from stats/form/xG (the brain; needs API-Football).
2. `book_prob` — SportyBet's own margin-removed probability (already ingested per outcome).
3. `implied = 1/odds` — raw market price.

**Edge per leg = `model_prob − book_prob`.** Positive edge = we think it's more likely than
SportyBet does. Until the stat model is wired, the builder runs on `book_prob` (slip MECHANICS
work, but there is NO edge yet — these are not profitable picks, just structure).

## Accumulator tiers — defined by LEG COUNT (not big single-game odds)
Combined odds emerge from STACKING many modest, stat-backed legs. NO long-odds singles —
every leg is a confident pick in the 1.20-1.90 range. One leg per match.

| Tier | Legs | Per-leg odds | Typical combined |
|---|---|---|---|
| SAFE | 3 – 5 | 1.20 – 1.60 | 3 – 10 |
| MID | 6 – 12 | 1.20 – 1.90 | 20 – 150 |
| LONGSHOT | 15 – 30 | 1.20 – 1.90 | 500 – 30,000 |

Example: 20 legs × ~1.5 avg ≈ 3,000 combined — but each leg is a solid prediction, not a punt.
Legs ranked by **stat confidence** (edge + form/H2H agreement) — strongest predictions fill
the slip first. Analysis-first: a leg must be EARNED by the stats, not chosen for its odds.

## Hard rules
- **Correlation guard:** max ONE leg per match per slip. (Over2.5 + BTTS + Home on the same game
  is one bet 3×, not three — banned in the same slip. Cross-match legs only.)
- **Leg must have a reason:** every leg carries a stat narrative (form/xG/injuries/H2H/motivation)
  once the stat brain is live.
- **Longshots are lottery:** expect most to lose; size tiny. Sustainable money = SAFE/VALUE tiers.
- **Each leg ideally +EV:** accas only beat the book long-term if individual legs beat book_prob.
  Stacking -EV legs with big odds = donating. The builder prefers +edge legs once model is live.

## Output — the punter slip
Per slip: tier · combined odds · combined model prob · per-leg {match, market, selection,
SportyBet odds, book_prob, our edge, stat reasoning, confidence}.

## Build order
1. Accumulator builder framework (THIS step) — runs on `book_prob` now.
2. Fixture join: SportyBet `sr:match` ID ↔ API-Football fixture.
3. Stat ingest (API-Football + Understat) → features.
4. Multi-market calibrated model → `model_prob` per selection.
5. Swap builder prob source book→model, switch on edge filter + narrative.
6. Backtest leg selection on top-5 history before trusting.

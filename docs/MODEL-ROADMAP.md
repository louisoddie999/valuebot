# ValueBot — Model Upgrade Roadmap

Goal: push the prediction model from ~7/10 toward 9/10. Doctrine holds throughout —
**predict from sports data, never from odds/edge.** Market prices are NOT blended in.

## Buildable now (no paid API)
- [x] Self-recalibration loop (settled results → confidence correction)
- [ ] **Per-sport calibration** — separate curve for football vs basketball
- [x] **Elo strength prior** — backtest-validated (ELO_W=0.30; acc +0.3pp, Brier -0.003). LIVE wiring needs a team-name bridge or API-SPORTS results graph (top-5 leagues only until then).
- [ ] **Richer stat features** — schedule congestion, home/away splits depth, recent-form weighting
- [ ] **Multi-model ensemble (data only)** — Poisson/Normal + Elo + form, weighted; NO odds

## Needs API-SPORTS key (saved for purchase)
- [ ] Lineups + injury depth (starters out → big swing) — football & basketball
- [ ] Player-level models → unlock player props (huge basketball market volume)
- [ ] 24/7 server enrichment (key-based, no IP ban) — replaces Sofascore residential dependency

## Maturity (automatic over time)
- [ ] Calibration tightens as settled-pick volume grows (≥150/sport activates correction)

## Explicitly NOT doing (violates doctrine)
- Market-implied blending / de-vig / beating the book — we rank likelihood, not value.

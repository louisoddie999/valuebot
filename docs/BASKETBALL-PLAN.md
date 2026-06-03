# ValueBot — Basketball Expansion Plan

Add Basketball as a second sport. ~60% of the stack is reused; the **prediction model** is
net-new. Same philosophy as football: predict from data, rank by calibrated confidence,
all legs ≤1.9, stack into bookable SAFE/MID/LONGSHOT slips.

---

## 1. Architecture — make ValueBot multi-sport

Introduce a `sport` dimension end-to-end. Football stays the default; basketball is additive.

```
ingest (sportId param) ─┐
                        ├─ sb_events.sport  ('football' | 'basketball')
                        ├─ sb_odds          (already keyed by event)
enrich (sport-specific) ┤
                        ├─ sf_features      (football stats)
                        └─ bb_features      (basketball stats)  ← NEW table
                                  │
              projector.py (football)   basketball_projector.py (NEW)
                                  │            │
                          accumulator_builder  (sport-agnostic — routes by sport)
                                  │
                       API /api/fixtures?sport=basketball  · dashboard sport tabs
```

**Key principle:** the *plumbing* (ingest, slips, booking, calibration, telegram, pipeline,
dashboard shell) is shared. Only the **feature schema + projector + market settlement** fork
per sport.

### Schema changes
- `sb_events`: add `sport TEXT DEFAULT 'football'`.
- NEW `bb_features` (parallel to `sf_features`): pace, off_rating, def_rating, pts_for,
  pts_against, pace_opp, rest_days, b2b (back-to-back flag), home/away splits, recent form.
- `tracked_picks`: add `sport` (calibration can stay global OR split per sport — recommend
  **per-sport calibration_curve** since basketball totals calibrate differently).
- `calibration_curve` / `calibration_meta`: add `sport` column (curve learned per sport).

---

## 2. The basketball model (`src/models/basketball_projector.py`)

Football uses Poisson on goals. **Basketball is different math:**

### Core engine — expected points
- **Expected total** = `pace × (off_rtg_home + off_rtg_away) / 100`, adjusted for opponent
  def rating and home-court (+~2.5 pts home). Pace = avg possessions/game.
- **Expected margin** = `exp_pts_home − exp_pts_away` (from each team's net rating vs pace).
- Points are ~**Normally distributed** (not Poisson). Game total σ ≈ 10–12 pts;
  margin σ ≈ 11–13 pts. Use a normal CDF for line probabilities.

### Market math (maps to the catalog markets)
| Market | Formula |
|--------|---------|
| **Total O/U** (225/18) | `P(Over) = 1 − Φ((line − exp_total)/σ_total)` |
| **Spread** (223) | `P(Home covers −x) = 1 − Φ((x − exp_margin)/σ_margin)` |
| **Moneyline** (219) | `P(Home win) = 1 − Φ((0 − exp_margin)/σ_margin)` |
| **Team total** (227/228) | normal around each team's expected points |
| **Half / quarter totals** | scale exp_total by period share (~Q≈24%, H1≈50%) + wider σ |

### Inputs (from `bb_features`, via Sofascore basketball)
- Team off/def rating, pace, points for/against (season + last-N)
- Rest days, back-to-back (huge in NBA — fatigue), home/away splits
- Injuries (star-out swings totals/margins materially)

### Calibration
The existing self-recalibration loop works **unchanged** — just per-sport. Basketball totals
will calibrate to their own curve (basketball is generally more model-predictable than soccer).

### Confidence philosophy (unchanged)
Rank by calibrated probability, only surface picks above min-confidence, every leg odds ≤1.9,
split into SAFE/MID/LONGSHOT by leg count.

---

## 3. Ingest + enrichment
- `sportybet_ingest.py`: parameterize `sportId` (football `sr:sport:1`, basketball `sr:sport:2`);
  write `sport` on each event. Basketball market parsing reuses the same outcome loop.
- NEW `src/ingest/sofascore_basketball.py`: pull basketball team stats (pace, ratings, form,
  rest) → `bb_features`. Sofascore covers NBA/EuroLeague/etc.
- `settle.py`: add basketball market settlement (totals, spread, ML, team totals, halves/quarters).
  Each market_id needs a settle rule from final + period scores.

## 4. Slip builder
`accumulator_builder.load_model_legs` becomes sport-aware: route to `projector` (football) or
`basketball_projector`. Everything downstream (bands ≤1.9, chunking, SAFE/MID/LONGSHOT) is shared.
Mixed-sport slips allowed (SportyBet supports cross-sport accumulators) — or keep per-sport.

## 5. API + dashboard
- `/api/fixtures?sport=basketball`, `/api/slips?sport=basketball`, chat `sport` intent.
- Dashboard: **sport toggle** (Football / Basketball) in the header; same Fixtures/Slips/
  Results/Accuracy pages, filtered by sport. Per-sport calibration shown on Accuracy.

## 6. Pipeline
`daily.py` gains a sport loop: ingest+enrich+settle+recalibrate **per sport**. Telegram sends
top slips per sport. `valuebot.bat` unchanged (runs the whole pipeline).

---

## Build phases (suggested order)
1. **Schema + ingest** — `sport` column, basketball event/odds ingest, market catalog wired (catalog ✅ done — `BASKETBALL-MARKET-COVERAGE.md`).
2. **Enrichment** — `sofascore_basketball.py` → `bb_features`.
3. **Model** — `basketball_projector.py` (totals → spread → ML → team totals → halves → quarters).
4. **Settlement** — basketball market settle rules in `settle.py`.
5. **Slip routing + per-sport calibration**.
6. **API + dashboard sport tabs**.
7. **Pipeline + Telegram per-sport**, validate, ship.

## Effort & risk
- ~2–3 focused sessions. Phases 1–2 are mechanical (reuse football). Phase 3 (model) is the
  real work + needs a backtest to set σ values and validate calibration.
- **Risk:** basketball totals/spreads are sharply priced; as a *prediction* tool (not edge)
  it's fine, but expect the model to need a few hundred settled picks before calibration tightens.
- **Data check first:** confirm Sofascore basketball coverage for the leagues SportyBet lists
  (NBA/EuroLeague solid; obscure leagues will have the same gaps as football).

## What's reused as-is
SportyBet ingest shell · booking (curl_cffi) · slips/chunking · calibration loop · Telegram ·
pipeline · `valuebot.bat` · tunnel · dashboard shell · ROI/Results · mobile nav.

## What's net-new
`bb_features` schema · `sofascore_basketball.py` · `basketball_projector.py` · basketball
settlement rules · sport routing · sport tabs.

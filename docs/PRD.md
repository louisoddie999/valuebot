# ValueBot — Product Requirements Document

*Status: v1 (supersedes Phase-0 PRD) · 2026-06-02*

## Problem Statement
Punters bet football on gut + scattered stats, with no single tool that turns real match data
(form, goals, H2H, corners, half-time, injuries, rest) into **honest, calibrated predictions**
across the many markets a bookmaker offers. "Prediction" sites hide accuracy and push fake "sure
odds". The cost: bad bets, no transparency, no way to build reasoned accumulators.

## Evidence
- Owner is an active SportyBet punter wanting stat-driven picks, not generic 3-odds tips.
- Validation: odds-chasing loses (−8.9% ROI vs closing) BUT predictions are **calibrated**
  (80% picks land 81%, n=8,263). Value = accurate prediction, not edge.
- SportyBet exposes 193 markets/match; no consumer tool models more than a few with reasoning.

## Proposed Solution
Local-first web app: ingest SportyBet (fixtures/odds/markets) + Sofascore (stats/form/injuries),
run a transparent per-match model across 22+ markets, present **calibrated predictions with the
data behind each**. Build tiered accumulators (SAFE/MID/LONGSHOT) by stacking confident legs,
generate a SportyBet **booking code** so the user places the bet himself, and add a **Gemini
read-only explainer**. Deterministic math; LLM never predicts.

## Key Hypothesis
A calibrated, transparent multi-market predictor with reasoning helps a punter pick and stack
confident bets. Right when **predicted confidence ≈ realized hit-rate** on live fixtures and the
owner uses slips weekly.

## What We're NOT Building
- **Auto-placing bets** — no automated stake/money movement (ToS, ban, financial risk). Booking codes only; human confirms.
- **LLM-generated predictions** — Gemini explains, never invents probabilities/odds.
- **Edge/value-vs-bookmaker system** — no edge vs sharp closing odds; out of scope.
- **Player-prop markets** — no free player data wired.

## Success Metrics
| Metric | Target | How Measured |
|---|---|---|
| Live calibration | \|predicted − actual\| ≤ 6%/band | weekly settle vs results |
| Market coverage | ≥ 20 families/match | `/match` endpoint |
| Fixture coverage (scope) | ≥ 90% enriched | pipeline summary |
| Pipeline runtime (today) | < 8 min | daily log |
| Owner weekly use | ≥ 3×/wk | usage |

---

## Users & Context
**Primary user** — owner: stats-literate SportyBet punter (Nigeria), builds accas, wants reasoning
+ confidence, controls his money.
- Current: checks form/news manually, places accas.
- Trigger: "what should I stack today / this weekend?"
- Success: ranked, reasoned slip he trusts + one-tap into SportyBet.

**JTBD:** *When planning bets for a day/week, I want calibrated stat-based predictions across
markets with reasoning, so I can build accumulators I trust.*

**Non-users:** edge-seeking arbers; casual "magic 2-odds" seekers.

---

## Solution Detail — MoSCoW
| Priority | Capability | Rationale |
|---|---|---|
| Must | Board: **country · league · real date/time** + scope tabs + **date picker** | Identify games (current gap) |
| Must | Per-match all-markets analysis (confidence + reasoning + injuries) | Core value |
| Must | Tiered accumulator builder (SAFE/MID/LONGSHOT, leg-count, scope) | Punter output |
| Must | Accuracy/calibration page | Trust |
| Must | Daily pipeline + scheduler | Fresh data |
| Should | **SportyBet booking-code** per slip | One-tap to bet (human confirms) |
| Should | **Gemini explainer/chat** (read-only) | NL explain / filtering |
| Could | Telegram morning delivery | Convenience |
| Could | Vercel deploy (frontend) | Access anywhere |
| Won't | Auto-place · LLM predictions · player props | Risk / data / trust |

### MVP
Board (country/league/date) → match analysis → SAFE/MID/LONGSHOT slips → accuracy page, fed by
daily pipeline. (Built; fixes pending.)

### Critical flow
Open → pick scope/date → scan fixtures (country·league·time + top pick) → match (markets +
reasoning) → builder → tier → slip + **booking code** → place on SportyBet.

---

## Technical Approach
**Feasibility: HIGH** — engine, API, dashboard, pipeline built + validated.

**Architecture:** ingest (`sportybet_ingest`, `sofascore`/curl_cffi) → SQLite → `projector`
(deterministic Poisson + HT + corners + cards + form/H2H + injury/rest) → FastAPI → Next.js.
Pipeline `daily.py` + Task Scheduler.

**Data model:** `sb_events`(event_id, home, away, **tournament=league**, **category=country**,
kickoff_ts); `sf_features`(per-team stats + injuries + rest + H2H).

**Risks**
| Risk | L | Mitigation |
|---|---|---|
| Sofascore Cloudflare block | M | curl_cffi; cache; degrade |
| Booking-code needs auth | M | probe; fallback deep-link |
| Vercel serverless scrape-blocked | H | ingest/API local or VPS; deploy frontend + read-only API |
| Model overconfidence | M | min-history gate; calibration monitor |
| Gemini hallucinating numbers | M | strict read-only prompt over supplied JSON |

---

## Implementation Phases
| # | Phase | Status | Depends |
|---|---|---|---|
| 1 | Engine + model + validation | complete | - |
| 2 | API + dashboard (4 pages) | complete | 1 |
| 3 | Daily pipeline + scheduler | complete | 1 |
| 4 | **UI fixes** — country·league·real date·date-picker | pending | 2 |
| 5 | **Booking codes** — SportyBet share-code (probe→build/fallback) | pending | 2 |
| 6 | **Gemini explainer** — read-only chat over data | pending | 2 |
| 7 | Telegram delivery | pending | 3 |
| 8 | Vercel deploy (frontend + read-only API) | pending | 4 |

**Phase 4 (next):** show `country · league` + formatted kickoff on board & match; real date
display; calendar date-picker → `YYYY-MM-DD` scope. Done when every row shows country/league/time
and any date is selectable.

**Phase 5:** probe SportyBet share/booking endpoint; reachable → POST selections → code + "open in
SportyBet"; fallback per-leg deep links. No auto-place.

**Phase 6:** `/explain` → Gemini given match/slip JSON → plain-English preview / Q&A. Hard rule:
only supplied numbers; never generate picks/odds.

---

## Decisions Log
| Decision | Choice | Alternatives | Rationale |
|---|---|---|---|
| Selection metric | Confidence (calibrated) | Edge vs odds | Edge absent; user wants prediction |
| Betting | Booking codes only | Auto-place / deep-link | Human controls money |
| LLM role | Gemini explainer only | Gemini predicts | LLM hallucinates numbers |
| Stats source | Sofascore + Understat (free) | API-Football (paid) | Free, rich; paid later |
| Deploy | Local → Vercel frontend | Full cloud | Scrape blocked on serverless |

## Open Questions
- [ ] SportyBet booking-code without full auth? (probe Phase 5)
- [ ] Gemini API key + model — owner to provide.
- [ ] Vercel: read-only API host (Render/VPS) vs static snapshots?
- [ ] Live-results settlement source for ongoing calibration.

---
*Next: Phase 4 UI fixes → booking-code probe → Gemini explainer.*

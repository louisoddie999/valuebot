# SportyBet Basketball — Market Coverage

Live-probed from SportyBet NG (`sportId=sr:sport:2`, `/event?eventId=…&productId=3`).
**74 unique markets** across 56 sampled events (NBA, EuroLeague, etc.). Same concept as the
football catalog: market_id → name → specifier → outcomes, tagged by whether ValueBot's
basketball model can/should predict it.

Legend: ✅ model target (v1) · 🟡 v2 (needs player/possession model) · ⛔ skip (exotic/luck)

## Core — game (incl. overtime)
| id | market | specifier | outcomes | model |
|----|--------|-----------|----------|-------|
| 219 | Winner (incl. OT) | — | Home / Away | ✅ moneyline |
| 1 | 1X2 | — | Home / Draw / Away | ✅ (reg time; draw rare) |
| 11 / 18? | DNB | — | Home / Away | ✅ |
| 223 | Handicap (incl. OT) | hcp=-17.5 | Home (-x) / Away (+x) | ✅ **spread — core** |
| 14 | Handicap (3-way) | hcp=0:4 | Home / Draw / Away | 🟡 |
| 225 | Over/Under (incl. OT) | total=205.5 | Over / Under | ✅ **total — core** |
| 18 | Over/Under (reg) | total=215.5 | Over / Under | ✅ |
| 297 | Total (over-exact-under) | total=218 | Under / Exact / Over | 🟡 |
| 229 | Odd/Even (incl. OT) | — | Odd / Even | ⛔ ~coinflip |
| 220 | Will there be overtime | — | Yes / No | 🟡 (close-game signal) |
| 292 | Winner & Total | total=218.5 | H&O / A&O / H&U / A&U | 🟡 combo |
| 37 | 1X2 & Total | total=217.5 | combo | 🟡 |
| 290 | Winning margin (incl. OT) | variant | Home by 6+ / Away by 6+ / other | 🟡 |
| 849 | Any team win margin | variant | 1-5 / 6-10 / 11-15 / 16-20 | 🟡 |
| 47 | Halftime/Fulltime | — | H/H, H/A, … | 🟡 |

## Team totals
| id | market | spec | model |
|----|--------|------|-------|
| 227 | Home O/U (incl. OT) | total=109.5 | ✅ team total |
| 228 | Away O/U (incl. OT) | total=105.5 | ✅ team total |

## Halves
| id | market | spec | model |
|----|--------|------|-------|
| 60 | 1st half - 1X2 | — | ✅ |
| 64 / 66 / 68 | 1st half DNB / Handicap / Total | hcp,total | ✅ |
| 69 / 70 | 1st half Home/Away O/U | total | ✅ |
| 83 / 86 / 88 / 90 | 2nd half 1X2 / DNB / Handicap / Total | | ✅ |
| 74 / 94 | 1st/2nd half odd-even | — | ⛔ |
| 52 | Highest scoring half | — | 🟡 |

## Quarters (specifier carries quarternr)
| id | market | spec | model |
|----|--------|------|-------|
| 235 | xth quarter - 1X2 | quarternr=1 | ✅ |
| 303 | xth quarter - handicap | hcp,quarternr | ✅ |
| 236 | xth quarter - total | total,quarternr | ✅ |
| 756 / 757 | xth quarter - team1/team2 total | total,quarternr | ✅ |
| 302 / 304 / 301 / 960 | quarter DNB / odd-even / margin / last point | | 🟡/⛔ |
| 234 | Highest scoring quarter | — | 🟡 |
| 1193 / 1195 | Highest/Lowest scoring quarter total | total | 🟡 |
| 1175-1178 | quarter/half (1X2&Total / Handicap&Total) combos | | 🟡 |
| 1174 | Handicap & Total (incl OT) | total,hcp | 🟡 |

## Player props (need player-level model = v2)
| id | market | spec |
|----|--------|------|
| 921 / 923 / 922 / 924 | Player total points / rebounds / assists / 3PT | total, player |
| 768 / 770 / 772 / 774 | Player points / assists / rebounds / 3PT (ladder) | variant, player |
| 1237 / 1238 | Double-double / Triple-double | player |
| 1236 | 1st point scorer | player |
All 🟡 v2 — require per-player projections (minutes, usage, role). Out of v1 scope.

## Exotic / luck-driven (skip)
| id | market |
|----|--------|
| 230 Race to x points · 965/966/967 lead-by-x · 961 free-throw · 962-964 max consecutive points · 48/49/1197-1203/1313/1314 win-both-halves/all-quarters |
→ ⛔ high-variance / luck; not predictable from team stats.

## v1 model targets (what the basketball projector will predict)
**Core, highest-confidence first:**
1. **Totals** (225/18) — Over/Under game points  ← strongest (pace+ratings → expected total)
2. **Spread / Handicap** (223) — margin vs line
3. **Moneyline / Winner** (219) — win prob
4. **Team totals** (227/228)
5. **Halves totals + spreads** (66/68/88/90)
6. **Quarter totals** (236) — noisier, lower confidence

Everything else = v2 (player props) or skip (exotic). Same philosophy as football:
predict from data, rank by calibrated confidence, all legs ≤1.9 odds, stack into slips.

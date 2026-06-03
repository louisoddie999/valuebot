# Dashboard Design System (locked via ui-ux-pro-max)

**Pattern:** Real-Time / Operations dashboard — data-dense but scannable, status colors, trust signals.
**Style:** Data-Dense Dashboard — KPI cards, tables, grid, minimal padding, max data visibility. Light + Dark.

## Colors
| Role | Hex |
|---|---|
| Primary (blue) | `#1E40AF` |
| Secondary | `#3B82F6` |
| Accent/CTA (amber) | `#D97706` |
| Background (light) | `#F8FAFC` |
| Foreground | `#1E3A8A` |
| Muted | `#E9EEF6` |
| Border | `#DBEAFE` |
| Destructive | `#DC2626` |
| Success (confidence high) | `#16A34A` |
| Warning (mid) | `#D97706` |

Confidence scale: ≥80% green · 65-80% blue · 50-65% amber · <50% muted.

## Typography
- Headings / numbers: **Fira Code** (tabular figures for data)
- Body: **Fira Sans**
- Import: `Fira+Code:wght@400;500;600;700` + `Fira+Sans:wght@300;400;500;600;700`

## Effects
Hover tooltips · row highlight on hover · smooth filter transitions (150-300ms) · skeleton loaders · chart zoom.

## UX rules (from UUPM)
- Tabular figures for all odds/confidence/stats (no layout shift).
- Confidence shown by color + number (never color alone).
- Filters mandatory (league / market / confidence / date scope).
- Reduced-motion respected. Focus rings. 4.5:1 contrast. Responsive 375/768/1024/1440.
- One primary CTA per view (Build Slip).

## Pages
1. **Fixtures board** — date-scope selector, league filter, list of matches + top prediction + confidence.
2. **Match detail** — all modeled markets, prediction, confidence, data reasoning, injuries.
3. **Accumulator builder** — tier (SAFE/MID/LONGSHOT), scope, generated slip with legs + confidence.
4. **Accuracy / trust page** — calibration table, market hit-rates (the validation proof).

## Stack
Next.js + React + Tailwind + shadcn/ui · FastAPI backend serving JSON · local first → Vercel.

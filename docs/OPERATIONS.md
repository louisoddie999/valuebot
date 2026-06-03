# Operations — run & schedule

## Daily refresh (one command)
```
python -m src.pipeline.daily --scope today --board 200 --enrich 80
```
- `--scope`  today | tomorrow | week | weekend | YYYY-MM-DD | A:B
- `--board`  how many SportyBet fixtures to pull (core + scan; raise to sweep more)
- `--enrich` how many in-scope fixtures to enrich via Sofascore (skips already-enriched)

Writes a log to `reports/daily_*.log`. Dashboard reads the DB live — no rebuild needed.

## Start the app (local)
```
scripts\serve.bat
```
API → http://localhost:8000 · Dashboard → http://localhost:3000

Or manually:
```
python -m uvicorn api.main:app --port 8000
cd dashboard && npm run dev
```

## Schedule the daily refresh (Windows Task Scheduler)
Register a 7:00 AM daily job:
```
schtasks /Create /SC DAILY /ST 07:00 /TN "ValueBot Daily" ^
  /TR "C:\Users\FX\claude-workspace\projects\SOCCER-VALUE-BOT\scripts\run-daily.bat"
```
Check / remove:
```
schtasks /Query /TN "ValueBot Daily"
schtasks /Delete /TN "ValueBot Daily" /F
```
`run-daily.bat` refreshes tomorrow (deep) + today (top-up) and appends to `reports/daily_cron.log`.

## "Core + scan so nothing is missed"
- Core: default `--board 200` covers near-term priority fixtures fast.
- Scan: run a wide sweep when you want full coverage, e.g.
  ```
  python -m src.pipeline.daily --scope week --board 600 --enrich 250
  ```
  Heavier + slower (more Sofascore calls) but catches lower-league games.

## Notes
- Enrichment skips fixtures already enriched (idempotent) — safe to re-run.
- Sofascore via curl_cffi (Cloudflare bypass); if it starts 403'ing, the lib may need an update.
- Telegram delivery + Vercel deploy: see roadmap (not yet wired).

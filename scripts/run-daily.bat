@echo off
REM Daily prediction refresh — ingest SportyBet board + enrich today/tomorrow.
cd /d "%~dp0.."
python -m src.pipeline.daily --scope tomorrow --board 250 --enrich 120 >> reports\daily_cron.log 2>&1
python -m src.pipeline.daily --scope today   --board 60  --enrich 80  >> reports\daily_cron.log 2>&1

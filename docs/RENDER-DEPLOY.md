# Deploy the API to Render (always-on, no PC needed)

Render hosts the FastAPI **read** layer — predictions, slips, chat, booking codes — served from
the committed SQLite DB. Enrichment (Sofascore) still runs **locally** on your mobile IP; you
refresh the DB and `git push` to redeploy.

## What's already prepped
- `requirements-api.txt` — lean deps (no playwright/training libs)
- `render.yaml` — Blueprint (web service, build/start commands, health check)
- `.gitignore` — `data/soccer_value.sqlite` is now committed (ships the DB)

## One-time setup
1. **Push to GitHub** (private repo is fine):
   ```bash
   cd C:/Users/FX/claude-workspace/projects/SOCCER-VALUE-BOT
   git init            # if not already a repo
   git add -A
   git commit -m "ValueBot API for Render"
   gh repo create valuebot --private --source=. --push   # or push to an existing remote
   ```
   The DB (`data/soccer_value.sqlite`) commits too — that's the data Render serves.

2. **Render → New → Blueprint** → connect the repo → it reads `render.yaml`.
3. **Set the secret env var** in Render dashboard: `GOOGLE_AI_API_KEY` = your Gemini key.
   (`GEMINI_MODEL` + `PYTHON_VERSION` come from render.yaml.)
4. Deploy. Render gives a URL like `https://valuebot-api.onrender.com`.
5. **Point the frontend at it** — set Vercel env + redeploy:
   ```bash
   cd dashboard
   printf "https://valuebot-api.onrender.com" | vercel env add NEXT_PUBLIC_API_BASE production --force
   vercel --prod --yes
   ```

## Refresh data (when you re-enrich locally)
```bash
# on your PC, mobile IP:
python -m src.pipeline.daily --scope 2026-06-02:2026-12-31
git add data/soccer_value.sqlite && git commit -m "refresh predictions" && git push
# Render auto-redeploys with the new DB
```

## Free-tier caveats (honest)
- **Spins down after 15 min idle** → first request after sleep is a ~50s cold start. Fine for personal use; pay $7/mo for always-warm.
- **Ephemeral disk** → booking-tracking writes (`tracked_picks`) reset on restart. Predictions are read-only so unaffected. For persistent results, add a Render disk ($) or external DB later.
- **No Sofascore on Render** (datacenter IP blocked) → `/api/results` settlement is best-effort there; run settlement locally.
- **512 MB RAM** — numpy/scipy fit; fine.

## Net
Phone-accessible, always-on (modulo cold start), no PC required for serving. Data freshness =
how often you re-enrich locally + push.

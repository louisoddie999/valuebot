# Deploy ValueBot 24/7 — VPS + residential proxy (Path B)

Fully automatic, always-on, no PC. The catch SportyBet/Sofascore impose: datacenter IPs are
blocked, so the two scraping/booking calls route through a **residential proxy** (everything
else runs normally on the cheap VPS).

## 1. Get a VPS (~$4–6/mo)
Any Ubuntu 22.04+ box: Hetzner CX22, Contabo, DigitalOcean, Vultr. 1 vCPU / 2GB is plenty.
SSH in, install Docker:
```
curl -fsSL https://get.docker.com | sh
```

## 2. Get a residential proxy (~$2–10/mo)
Providers: IPRoyal, Smartproxy, Bright Data, Proxy-Cheap. 
- Pick **Nigeria** geo if available (matches SportyBet NG; best success).
- You get a string like `http://user:pass@geo.iproyal.com:12321`.
- Residential (not datacenter) is what beats the block.

## 3. Pull + configure
```
git clone https://github.com/louisoddie999/valuebot.git
cd valuebot
cp .env.vps.example .env
nano .env          # paste GOOGLE_AI_API_KEY + SCRAPER_PROXY
```

## 4. Run (forever)
```
docker compose up -d --build
```
That's it. The container:
- refreshes data on boot (via proxy), then **every REFRESH_HOURS**,
- serves the API on :8000,
- `restart: unless-stopped` → survives crashes + VPS reboots.
Check: `docker compose logs -f valuebot`  ·  `curl localhost:8000/api/health`

## 5. HTTPS (so the Vercel site can call it)
Vercel is https; browsers block https→http. Two options:
- **Caddy (auto Let's Encrypt)** — point a domain's A-record at the VPS IP, set `DOMAIN` in `.env`, then:
  `docker compose --profile tls up -d`  → API live at `https://api.yourdomain.com`
- **Cloudflare Tunnel** — run `cloudflared` on the VPS (no open ports, no domain math). 

## 6. Point the frontend at it (once)
Vercel → Project → Settings → Environment Variables:
`NEXT_PUBLIC_API_BASE = https://api.yourdomain.com` → redeploy.
Done — site works 24/7, predictions refresh themselves, booking works through the proxy.

## Verify the proxy actually beats the block
On the VPS: `docker compose exec valuebot python -m src.booking.sportybet_booking`
→ should print `{'ok': True, 'shareCode': ...}`. If `IP-blocked`/empty, the proxy isn't
residential enough — switch geo/provider.

## Cost summary
VPS ~$5/mo + proxy ~$2–10/mo. ~$7–15/mo total for hands-off 24/7.

## Notes
- DB seeds from `data/serve.sqlite` (committed) and grows in the mounted `./data` volume.
- API + Gemini do NOT use the proxy (no need) — only Sofascore + SportyBet calls do.
- To change cadence/scope: edit `.env` (`REFRESH_HOURS`, `SCOPE`) → `docker compose up -d`.

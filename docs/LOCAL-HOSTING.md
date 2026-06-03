# Local Hosting (run ValueBot on your own machine)

Booking codes + Sofascore enrichment both need a **residential IP** (datacenter IPs get
WAF-blocked by SportyBet/Sofascore). Running the API on your PC = both work, full 135MB DB,
no cold start. Trade-off: the public site only answers while your PC is on.

## Start it
Double-click **`run.bat`** (project root).
It launches the API on `127.0.0.1:8000` and opens a tunnel, then prints the **PUBLIC API URL**.

## Tunnel modes (auto-picked, best available first)
| Mode | Setup | URL |
|------|-------|-----|
| **ngrok permanent** (recommended) | `ngrok config add-authtoken <token>` then set env `NGROK_DOMAIN=yourname.ngrok-free.app` | fixed, never changes |
| Cloudflare named | set env `CF_TUNNEL_TOKEN` (Cloudflare Zero Trust; needs a domain on CF) | fixed |
| Cloudflare quick | nothing | `https://xxxx.trycloudflare.com` — **rotates each run** |

### One-time: permanent URL via ngrok (free, no domain needed)
1. Sign up at ngrok.com, copy your authtoken.
2. `winget install ngrok`  (or download ngrok.exe)
3. `ngrok config add-authtoken <YOUR_TOKEN>`
4. Dashboard → Domains → claim your free static domain (e.g. `valuebot.ngrok-free.app`).
5. Set a persistent env var (PowerShell, once):
   `setx NGROK_DOMAIN "valuebot.ngrok-free.app"`
6. In **Vercel** → Project → Settings → Environment Variables:
   `NEXT_PUBLIC_API_BASE = https://valuebot.ngrok-free.app` → redeploy.
Done. From now on: double-click `run.bat`, the public site works whenever your PC is on.

## Quick-tunnel users (no ngrok)
The URL changes each run. To point the live site at the new URL, the launcher prints the
exact `vercel env` command — paste it, or just use the local dashboard (`cd dashboard && npm run dev`).

## Refresh predictions
Run your Sofascore enrichment as before (mobile IP), then restart `run.bat`. The API serves
the full local DB directly — no git push, no Render.
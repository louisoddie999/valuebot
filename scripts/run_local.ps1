# ValueBot local launcher — runs the API on your machine (residential IP = booking + Sofascore work)
# and exposes it through a tunnel so the Vercel frontend can reach it.
#
# Tunnel auto-pick (best first):
#   1. ngrok PERMANENT  -> set env NGROK_DOMAIN (e.g. valuebot.ngrok-free.app) + `ngrok config add-authtoken <t>`
#   2. cloudflare named  -> set env CF_TUNNEL_TOKEN (from Cloudflare Zero Trust; needs a domain on CF)
#   3. cloudflare quick  -> no setup; prints a fresh https://*.trycloudflare.com each run (URL rotates)
#
# Usage:  double-click run.bat   (or)   powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1

$ErrorActionPreference = 'Stop'
$proj = Split-Path -Parent $PSScriptRoot
Set-Location $proj

$PORT = 8000
$cf   = Join-Path $proj 'cloudflared.exe'
$log  = Join-Path $env:TEMP 'valuebot_tunnel.log'
if (Test-Path $log) { Remove-Item $log -Force }

function Stop-All {
  Write-Host "`nShutting down..." -ForegroundColor Yellow
  Get-Job | Stop-Job -ErrorAction SilentlyContinue
  Get-Job | Remove-Job -Force -ErrorAction SilentlyContinue
  Get-Process cloudflared,ngrok -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

try {
  Write-Host "==> Starting ValueBot API on http://127.0.0.1:$PORT (full DB)" -ForegroundColor Cyan
  $api = Start-Process -PassThru -WindowStyle Minimized python `
         -ArgumentList '-m','uvicorn','api.main:app','--host','127.0.0.1','--port',"$PORT"
  Start-Sleep -Seconds 5

  # health probe
  try { $null = Invoke-RestMethod "http://127.0.0.1:$PORT/api/health" -TimeoutSec 10; Write-Host "API healthy." -ForegroundColor Green }
  catch { Write-Host "WARN: API not responding yet — continuing (it may still be loading)." -ForegroundColor Yellow }

  $publicUrl = $null

  if ($env:NGROK_DOMAIN -and (Get-Command ngrok -ErrorAction SilentlyContinue)) {
    Write-Host "==> Tunnel: ngrok PERMANENT -> https://$($env:NGROK_DOMAIN)" -ForegroundColor Cyan
    $publicUrl = "https://$($env:NGROK_DOMAIN)"
    Start-Process -WindowStyle Minimized ngrok -ArgumentList 'http',"$PORT","--domain=$($env:NGROK_DOMAIN)"
  }
  elseif ($env:CF_TUNNEL_TOKEN) {
    Write-Host "==> Tunnel: Cloudflare named (token)" -ForegroundColor Cyan
    Start-Process -WindowStyle Minimized $cf -ArgumentList 'tunnel','run','--token',"$($env:CF_TUNNEL_TOKEN)"
    Write-Host "Permanent URL = the hostname you mapped in Cloudflare Zero Trust." -ForegroundColor Green
  }
  else {
    Write-Host "==> Tunnel: Cloudflare QUICK (no setup; URL rotates each run)" -ForegroundColor Cyan
    Start-Process -WindowStyle Minimized -RedirectStandardError $log $cf `
      -ArgumentList 'tunnel','--url',"http://127.0.0.1:$PORT"
    Write-Host "Waiting for tunnel URL..." -NoNewline
    for ($i=0; $i -lt 30 -and -not $publicUrl; $i++) {
      Start-Sleep -Seconds 1; Write-Host "." -NoNewline
      if (Test-Path $log) {
        $m = Select-String -Path $log -Pattern 'https://[a-z0-9]+(-[a-z0-9]+)+\.trycloudflare\.com' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($m) { $publicUrl = $m.Matches[0].Value }
      }
    }
    Write-Host ""
  }

  if ($publicUrl) {
    # write local dev env so a local `next dev` hits the tunnel too (optional)
    $envFile = Join-Path $proj 'dashboard\.env.local'
    "NEXT_PUBLIC_API_BASE=$publicUrl" | Set-Content $envFile -NoNewline
    Write-Host "`n==============================================================" -ForegroundColor Green
    Write-Host " PUBLIC API URL:  $publicUrl" -ForegroundColor Green
    Write-Host "==============================================================" -ForegroundColor Green
    if (-not $env:NGROK_DOMAIN -and -not $env:CF_TUNNEL_TOKEN) {
      Write-Host " (quick tunnel — this URL changes each run)" -ForegroundColor Yellow
      Write-Host " To make the LIVE Vercel site use it now, run:" -ForegroundColor Yellow
      Write-Host "   vercel env rm NEXT_PUBLIC_API_BASE production -y; echo $publicUrl | vercel env add NEXT_PUBLIC_API_BASE production; vercel --prod" -ForegroundColor DarkGray
    } else {
      Write-Host " Set this ONCE in Vercel -> Project -> Settings -> Env -> NEXT_PUBLIC_API_BASE -> redeploy." -ForegroundColor Green
    }
  } else {
    Write-Host "Could not capture tunnel URL — check $log" -ForegroundColor Red
  }

  Write-Host "`nAPI + tunnel running. Press Ctrl+C to stop." -ForegroundColor Cyan
  while ($true) { Start-Sleep -Seconds 3600 }
}
finally {
  Stop-All
  if ($api -and -not $api.HasExited) { $api | Stop-Process -Force -ErrorAction SilentlyContinue }
}
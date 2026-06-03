param([string]$Scope = "ahead", [int]$RefreshHours = 12, [int]$Board = 2000, [int]$Enrich = 2000)
$ErrorActionPreference = 'Stop'
$proj = Split-Path -Parent $PSScriptRoot
Set-Location $proj
$PORT = 8000
$cf   = Join-Path $proj 'cloudflared.exe'
$tlog = Join-Path $env:TEMP 'valuebot_tunnel.log'

function Stop-All {
  Write-Host "`nShutting down ValueBot..." -ForegroundColor Yellow
  Get-Job | Stop-Job -EA SilentlyContinue; Get-Job | Remove-Job -Force -EA SilentlyContinue
  Get-Process cloudflared,ngrok -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue
  Get-NetTCPConnection -LocalPort $PORT -State Listen -EA SilentlyContinue |
    Select-Object -Expand OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -EA SilentlyContinue }
}
function Invoke-Refresh([string]$why) {
  Write-Host "`n[$(Get-Date -Format HH:mm)] Refreshing ($why): scope=$Scope ..." -ForegroundColor Cyan
  python -m src.pipeline.daily --scope $Scope --board $Board --enrich $Enrich
  Write-Host "[$(Get-Date -Format HH:mm)] Refresh done." -ForegroundColor Green
}
try {
  Write-Host "============ ValueBot (single command) ============" -ForegroundColor Cyan
  Write-Host " scope=$Scope  auto-refresh ${RefreshHours}h  port=$PORT" -ForegroundColor DarkGray
  Invoke-Refresh "startup"
  Get-NetTCPConnection -LocalPort $PORT -State Listen -EA SilentlyContinue |
    Select-Object -Expand OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -EA SilentlyContinue }
  Write-Host "==> API on http://127.0.0.1:$PORT (full DB)" -ForegroundColor Cyan
  $api = Start-Process -PassThru -WindowStyle Minimized python -ArgumentList '-m','uvicorn','api.main:app','--host','127.0.0.1','--port',"$PORT"
  Start-Sleep 5
  try { $null = Invoke-RestMethod "http://127.0.0.1:$PORT/api/health" -TimeoutSec 10; Write-Host "API healthy." -ForegroundColor Green } catch { Write-Host "WARN: API slow." -ForegroundColor Yellow }
  $publicUrl = $null
  if ($env:NGROK_DOMAIN -and (Get-Command ngrok -EA SilentlyContinue)) {
    $publicUrl = "https://$($env:NGROK_DOMAIN)"
    Start-Process -WindowStyle Minimized ngrok -ArgumentList 'http',"$PORT","--domain=$($env:NGROK_DOMAIN)"
    Write-Host "==> Tunnel ngrok PERMANENT -> $publicUrl" -ForegroundColor Cyan
  } elseif ($env:CF_TUNNEL_TOKEN) {
    Start-Process -WindowStyle Minimized $cf -ArgumentList 'tunnel','run','--token',"$($env:CF_TUNNEL_TOKEN)"
    Write-Host "==> Tunnel Cloudflare named (token)" -ForegroundColor Cyan
  } else {
    if (Test-Path $tlog) { Remove-Item $tlog -Force }
    Start-Process -WindowStyle Minimized -RedirectStandardError $tlog $cf -ArgumentList 'tunnel','--url',"http://127.0.0.1:$PORT"
    Write-Host "==> Tunnel Cloudflare quick (URL rotates). Waiting..." -NoNewline
    for ($i=0; $i -lt 30 -and -not $publicUrl; $i++){ Start-Sleep 1; Write-Host "." -NoNewline
      if (Test-Path $tlog){ $m=Select-String -Path $tlog -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -EA SilentlyContinue | Select-Object -First 1; if($m){$publicUrl=$m.Matches[0].Value} } }
    Write-Host ""
  }
  if ($publicUrl) {
    "NEXT_PUBLIC_API_BASE=$publicUrl" | Set-Content (Join-Path $proj 'dashboard\.env.local') -NoNewline
    Write-Host "`n=====================================================" -ForegroundColor Green
    Write-Host " PUBLIC API URL:  $publicUrl" -ForegroundColor Green
    Write-Host "=====================================================" -ForegroundColor Green
  }
  Write-Host "`nValueBot LIVE. Auto-refresh every ${RefreshHours}h. Ctrl+C to stop." -ForegroundColor Cyan
  $next = (Get-Date).AddHours($RefreshHours)
  while ($true) { Start-Sleep -Seconds 60; if ((Get-Date) -ge $next) { Invoke-Refresh "scheduled"; $next = (Get-Date).AddHours($RefreshHours) } }
}
finally { Stop-All; if ($api -and -not $api.HasExited) { $api | Stop-Process -Force -EA SilentlyContinue } }
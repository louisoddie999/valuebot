# ValueBot data refresh — fresh SportyBet board + Sofascore enrichment for a scope.
# Updates sf_features.computed_at -> resets the dashboard "updated" stamp.
param([string]$Scope = "weekend", [int]$Board = 2000, [int]$Enrich = 2000)
$ErrorActionPreference = 'Stop'
$proj = Split-Path -Parent $PSScriptRoot
Set-Location $proj
Write-Host "==> Refreshing ValueBot data  scope=$Scope  board=$Board  enrich=$Enrich" -ForegroundColor Cyan
Write-Host "    (live Sofascore + SportyBet calls — run on a residential/mobile IP)" -ForegroundColor DarkGray
python -m src.pipeline.daily --scope $Scope --board $Board --enrich $Enrich
Write-Host "`n==> Done. Dashboard 'updated' stamp is now 'just now'." -ForegroundColor Green
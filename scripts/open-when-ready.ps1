#Requires -Version 5.1
<#
  Waits for the API and the Vite dev server, prints every URL that works
  (including the LAN address for testing on a phone), then opens the browser.
#>

$ErrorActionPreference = 'Stop'
$ProgressPreference     = 'SilentlyContinue'

$ApiHealth   = 'http://127.0.0.1:8000/health'
$ApiDocs     = 'http://localhost:8000/docs'
$FrontendUrl = 'http://localhost:5173'
$TimeoutSec  = 120

function Wait-ForUrl {
    param([string]$Url, [string]$Label, [int]$Seconds)

    Write-Host "Waiting for $Label ..." -NoNewline
    for ($i = 0; $i -lt $Seconds; $i++) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null
            Write-Host " ready" -ForegroundColor Green
            return $true
        } catch {
            Start-Sleep -Seconds 1
            if ($i % 5 -eq 4) { Write-Host '.' -NoNewline }
        }
    }
    Write-Host " TIMED OUT" -ForegroundColor Red
    return $false
}

function Get-LanAddress {
    try {
        $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
              Where-Object {
                  $_.IPAddress -notlike '127.*' -and
                  $_.IPAddress -notlike '169.254.*' -and
                  $_.PrefixOrigin -ne 'WellKnown'
              } |
              Select-Object -First 1 -ExpandProperty IPAddress
        return $ip
    } catch { return $null }
}

Write-Host ''
Write-Host '  PGDesk' -ForegroundColor Cyan
Write-Host '  ------' -ForegroundColor Cyan

$apiOk = Wait-ForUrl -Url $ApiHealth   -Label 'API (port 8000)'      -Seconds $TimeoutSec
$feOk  = Wait-ForUrl -Url $FrontendUrl -Label 'frontend (port 5173)' -Seconds $TimeoutSec

Write-Host ''

if (-not $apiOk) {
    Write-Host '  The API never answered on port 8000.' -ForegroundColor Yellow
    Write-Host '  Check the backend terminal tab for a traceback.' -ForegroundColor Yellow
    Write-Host '  Most common cause: PostgreSQL is not running, or the'   -ForegroundColor Yellow
    Write-Host '  password in backend\.env does not match the pgdesk role.' -ForegroundColor Yellow
    Write-Host ''
}

if (-not $feOk) {
    Write-Host '  Vite never answered on port 5173.'                   -ForegroundColor Yellow
    Write-Host '  If you have never run it here: PGDesk: First-time Setup' -ForegroundColor Yellow
    Write-Host ''
    exit 1
}

$lan = Get-LanAddress

Write-Host '  App        ' -NoNewline; Write-Host $FrontendUrl -ForegroundColor Cyan
Write-Host '  API docs   ' -NoNewline; Write-Host $ApiDocs     -ForegroundColor Cyan
if ($lan) {
    Write-Host '  On phone   ' -NoNewline; Write-Host "http://${lan}:5173" -ForegroundColor Cyan
    Write-Host '             (same Wi-Fi; see note in README-DEV.md if it refuses)' -ForegroundColor DarkGray
}

Write-Host ''
Write-Host '  Sign in with' -ForegroundColor DarkGray
Write-Host '    Owner     owner@sunrise.local     Owner@2024'
Write-Host '    Master    master@pgdesk.local     Master@2024'
Write-Host '    Manager   manager@sunrise.local   Manager@2024'
Write-Host '    Resident  customer@sunrise.local  Customer@2024'
Write-Host ''

Start-Process $FrontendUrl
Write-Host '  Browser opened. Leave this window; closing it stops nothing.' -ForegroundColor DarkGray
Write-Host ''

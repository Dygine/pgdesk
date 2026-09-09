#Requires -Version 5.1
<#
  Frees ports 8000 and 5173. Useful after a crash leaves an orphan
  uvicorn or node holding the port, which shows up as
  "address already in use" on the next start.
#>

$ErrorActionPreference = 'SilentlyContinue'

foreach ($port in 8000, 5173) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen
    if (-not $conns) {
        Write-Host "  Port $port  already free"
        continue
    }
    # NB: not $pid - that is a read-only automatic variable in PowerShell.
    foreach ($procId in ($conns.OwningProcess | Select-Object -Unique)) {
        $proc = Get-Process -Id $procId
        $name = if ($proc) { $proc.ProcessName } else { 'unknown' }
        Stop-Process -Id $procId -Force
        Write-Host "  Port $port  stopped $name (pid $procId)" -ForegroundColor Yellow
    }
}

Write-Host ''
Write-Host '  Done. PostgreSQL was not touched.' -ForegroundColor DarkGray
Write-Host ''

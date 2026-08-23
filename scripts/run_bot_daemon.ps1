Write-Host '===============================================================================' -ForegroundColor Cyan
Write-Host ' KALSHI 24/7 TRADING BOT DAEMON (POWERSHELL AUTO-RESTART)' -ForegroundColor Cyan
Write-Host '===============================================================================' -ForegroundColor Cyan

while ($true) {
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Write-Host "[ $timestamp ] Starting Kalshi Bot in Demo API mode..." -ForegroundColor Green
    try {
        python scripts/run_bot.py --mode live --env demo --poll-interval 15 --scan-interval 180
    } catch {
        Write-Host "[ ERROR ] Bot process stopped: $_" -ForegroundColor Red
    }
    Write-Host "[ 2026-08-23 12:43:12 ] Bot stopped. Restarting in 10 seconds..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
}

@echo off
title Kalshi High-Probability Trading Bot (24/7 Server Daemon)
color 0A

echo ===============================================================================
echo  KALSHI 24/7 TRADING BOT DAEMON (AUTO-RESTART PROTECTED)
echo ===============================================================================
echo  Target: Kalshi Demo API (Set KALSHI_ENV=prod in .env for real money)
echo  Active Monitoring: Every 15 seconds
echo  Scanner Cadence: Every 3 minutes
echo  Dynamic Stop-Loss: Active (Anti-Whipsaw + Depth Sanity + Limit Floor)
echo ===============================================================================

:loop
echo [%date% %time%] Starting Kalshi Trading Bot...
python scripts/run_bot.py --mode live --env demo --poll-interval 15 --scan-interval 180

echo.
echo [%date% %time%] Bot process stopped or encountered error. Auto-restarting in 10s (Ctrl+C to abort)...
timeout /t 10 /nobreak >nul
goto loop

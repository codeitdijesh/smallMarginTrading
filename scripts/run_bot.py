"""
CLI Script: Kalshi Trading Bot (Demo & Live).
Runs 24/7 automated active monitoring and scanning with:
- Sub-minute active position price polling (every 15s)
- Dynamic stop-loss execution with multi-tick persistence filter
- Market settlement tracking & automatic recovery on restart
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import (
    BANKROLL_START,
    PROD_API_URL,
    DEMO_API_URL,
    KALSHI_ENV,
    MIN_PROBABILITY,
    MAX_PROBABILITY,
    MAX_HOURS_TO_EXPIRY,
    MAX_BID_ASK_SPREAD,
    MIN_OPEN_INTEREST,
    MAX_POSITIONS_PER_EVENT,
    ENABLE_STOP_LOSS,
    STOP_LOSS_TYPE,
    STOP_LOSS_BASE_DROP,
    STOP_LOSS_MIN_DROP,
    STOP_LOSS_MAX_DROP,
    STOP_LOSS_LIMIT_FLOOR,
    STOP_LOSS_PERSISTENCE_TICKS,
    POSITION_CHECK_INTERVAL,
    SCAN_INTERVAL
)
from src.bot.engine import TradingBot
from src.strategy.scanner import MarketScanner
from src.strategy.risk import RiskManager
from src.api.kalshi_client import KalshiClient
from src.utils.logger import logger

def main():
    parser = argparse.ArgumentParser(description="Kalshi High-Probability Trading Bot with Active Dynamic Stop-Loss")
    parser.add_argument("--mode", choices=["live", "paper"], default="live", help="Execution mode: 'live' (Demo/Prod API) or 'paper' (simulated locally)")
    parser.add_argument("--env", choices=["demo", "prod"], default=KALSHI_ENV, help=f"Kalshi account API environment (default: {KALSHI_ENV})")
    parser.add_argument("--bankroll", type=float, default=BANKROLL_START, help="Initial bankroll for fallback ($)")
    parser.add_argument("--max-hours", type=float, default=MAX_HOURS_TO_EXPIRY, help=f"Max hours to settlement (default: {MAX_HOURS_TO_EXPIRY})")
    parser.add_argument("--min-prob", type=float, default=MIN_PROBABILITY, help=f"Min probability (default: {MIN_PROBABILITY})")
    parser.add_argument("--max-prob", type=float, default=MAX_PROBABILITY, help=f"Max probability (default: {MAX_PROBABILITY})")
    parser.add_argument("--max-per-event", type=int, default=MAX_POSITIONS_PER_EVENT, help=f"Max positions allowed per event (default: {MAX_POSITIONS_PER_EVENT})")
    parser.add_argument("--stop-loss", action="store_true", default=ENABLE_STOP_LOSS, help="Enable dynamic stop loss")
    parser.add_argument("--stop-type", choices=["dynamic", "static"], default=STOP_LOSS_TYPE, help=f"Stop loss mode (default: {STOP_LOSS_TYPE})")
    parser.add_argument("--base-drop", type=float, default=STOP_LOSS_BASE_DROP, help=f"Base stop drop in dollars (default: {STOP_LOSS_BASE_DROP})")
    parser.add_argument("--limit-floor", type=float, default=STOP_LOSS_LIMIT_FLOOR, help=f"Hard stop limit floor (default: {STOP_LOSS_LIMIT_FLOOR})")
    parser.add_argument("--persistence", type=int, default=STOP_LOSS_PERSISTENCE_TICKS, help=f"Ticks to confirm breach (default: {STOP_LOSS_PERSISTENCE_TICKS})")
    parser.add_argument("--poll-interval", type=int, default=POSITION_CHECK_INTERVAL, help=f"Interval in seconds to monitor active positions (default: {POSITION_CHECK_INTERVAL}s)")
    parser.add_argument("--scan-interval", type=int, default=SCAN_INTERVAL, help=f"Interval in seconds between full market scan cycles (default: {SCAN_INTERVAL}s)")
    parser.add_argument("--once", action="store_true", help="Run one scan cycle and exit (do not loop 24/7)")
    args = parser.parse_args()

    order_api_url = DEMO_API_URL if args.env == "demo" else PROD_API_URL
    scanner_api_url = PROD_API_URL  # Real-time liquid production orderbooks

    client = KalshiClient(base_url=order_api_url)
    scanner = MarketScanner(
        base_url=scanner_api_url,
        min_prob=args.min_prob,
        max_prob=args.max_prob,
        max_hours=args.max_hours,
        max_spread=MAX_BID_ASK_SPREAD,
        min_oi=MIN_OPEN_INTEREST
    )
    risk_manager = RiskManager(
        max_positions_per_event=args.max_per_event,
        enable_stop_loss=args.stop_loss,
        stop_loss_type=args.stop_type,
        stop_loss_base_drop=args.base_drop,
        stop_loss_min_drop=STOP_LOSS_MIN_DROP,
        stop_loss_max_drop=STOP_LOSS_MAX_DROP,
        stop_loss_limit_floor=args.limit_floor,
        stop_loss_persistence_ticks=args.persistence
    )
    bot = TradingBot(
        mode=args.mode,
        bankroll=args.bankroll,
        scanner=scanner,
        risk_manager=risk_manager,
        client=client
    )

    print("\n" + "="*85)
    print(f" KALSHI HIGH-PROBABILITY TRADING BOT [{args.mode.upper()} MODE - {args.env.upper()} API]")
    print(f" Strategy: {args.min_prob*100:.0f}%-{args.max_prob*100:.0f}% Win Chance | <{args.max_hours:.0f}h Expiry | Max {args.max_per_event} Bet/Event")
    print(f" Risk Defense: Stop-Loss: {args.stop_loss} ({args.stop_type.upper()}) | Base Drop: -${args.base_drop:.2f} | Floor: ${args.limit_floor:.2f} | Persistence: {args.persistence} ticks")
    print(f" Cadence: Active Monitor every {args.poll_interval}s | Market Scanner every {args.scan_interval}s")
    print("="*85)

    if args.once:
        bot.monitor_active_positions()
        trades = bot.execute_scan_cycle()
        summary = bot.get_summary()
        print(f"\n[SINGLE RUN COMPLETED] Placed {len(trades)} trade(s). Current Bankroll: ${summary['current_bankroll']:.2f}")
        return

    last_scan_time = 0.0
    iteration = 0

    try:
        while True:
            iteration += 1
            now_ts = time.time()

            try:
                # 1. Active Position & Stop-Loss Monitoring (High Frequency: every 15s)
                monitor_stats = bot.monitor_active_positions()

                # 2. Opportunity Scanner & Trade Entry (Cadence: every scan_interval or when cash frees up)
                time_since_scan = now_ts - last_scan_time
                should_scan = (last_scan_time == 0.0) or (time_since_scan >= args.scan_interval) or (monitor_stats["exits"] > 0) or (monitor_stats["settled"] > 0)

                if should_scan:
                    trades = bot.execute_scan_cycle()
                    last_scan_time = now_ts
                    summary = bot.get_summary()

                    print(f"\n--- PORTFOLIO SUMMARY ({args.mode.upper()} - {args.env.upper()}) [{datetime.now().strftime('%H:%M:%S')}] ---")
                    print(f" Current Bankroll: ${summary['current_bankroll']:.2f} (Start: ${summary['initial_bankroll']:.2f})")
                    print(f" Available Cash:   ${summary['available_cash']:.2f}")
                    print(f" Active Exposure:  ${summary['active_exposure']:.2f} across {summary['active_positions_count']} open position(s)")
                    print(f" Closed Trades:    {summary['closed_trades_count']} | Realized PnL: ${summary['total_pnl']:.2f} (ROI: {summary['roi_percent']}%)")
                    print(f" New Trades Entered This Scan: {len(trades)}")
                    print("="*85)
                elif iteration % 4 == 0:
                    # Periodic heartbeat summary
                    summary = bot.get_summary()
                    logger.info(f"[HEARTBEAT] Bankroll: ${summary['current_bankroll']:.2f} | Active: {summary['active_positions_count']} | Next scan in {int(args.scan_interval - time_since_scan)}s")

            except Exception as e:
                logger.error(f"Unexpected error in trading loop: {e}", exc_info=True)

            # Sleep poll_interval seconds before next position check
            time.sleep(args.poll_interval)

    except KeyboardInterrupt:
        logger.info("Bot execution halted by user.")

if __name__ == "__main__":
    main()


"""
CLI Script: Kalshi Trading Bot (Paper & Live).
Runs automated trading cycles with risk management, state persistence, and performance tracking.
"""

import argparse
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import (
    BANKROLL_START,
    API_BASE_URL,
    PROD_API_URL,
    DEMO_API_URL,
    KALSHI_ENV,
    MIN_PROBABILITY,
    MAX_PROBABILITY,
    MAX_HOURS_TO_EXPIRY,
    MAX_BID_ASK_SPREAD,
    MIN_OPEN_INTEREST,
    MAX_POSITIONS_PER_EVENT
)
from src.bot.engine import TradingBot
from src.strategy.scanner import MarketScanner
from src.strategy.risk import RiskManager
from src.api.kalshi_client import KalshiClient
from src.utils.logger import logger

def main():
    parser = argparse.ArgumentParser(description="Kalshi High-Probability Trading Bot")
    parser.add_argument("--mode", choices=["paper", "live"], default="live", help="Execution mode: 'live' (places orders on Kalshi demo/prod API) or 'paper' (simulated locally)")
    parser.add_argument("--env", choices=["demo", "prod"], default=KALSHI_ENV, help=f"Kalshi account API environment (default: {KALSHI_ENV})")
    parser.add_argument("--bankroll", type=float, default=BANKROLL_START, help="Initial bankroll for paper trading ($)")
    parser.add_argument("--max-hours", type=float, default=MAX_HOURS_TO_EXPIRY, help=f"Max hours to settlement (default: {MAX_HOURS_TO_EXPIRY})")
    parser.add_argument("--min-prob", type=float, default=MIN_PROBABILITY, help=f"Min probability (default: {MIN_PROBABILITY})")
    parser.add_argument("--max-prob", type=float, default=MAX_PROBABILITY, help=f"Max probability (default: {MAX_PROBABILITY})")
    parser.add_argument("--max-per-event", type=int, default=MAX_POSITIONS_PER_EVENT, help=f"Max positions allowed per event (default: {MAX_POSITIONS_PER_EVENT})")
    parser.add_argument("--loop", action="store_true", help="Run continuously in a loop")
    parser.add_argument("--interval", type=int, default=300, help="Interval in seconds between cycles when looping (default: 300s)")
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
        max_positions_per_event=args.max_per_event
    )
    bot = TradingBot(
        mode=args.mode,
        bankroll=args.bankroll,
        scanner=scanner,
        risk_manager=risk_manager,
        client=client
    )

    print("\n" + "="*80)
    print(f" KALSHI HIGH-PROBABILITY TRADING BOT [{args.mode.upper()} MODE - {args.env.upper()} API]")
    print(f" Strategy: {args.min_prob*100:.0f}%-{args.max_prob*100:.0f}% Win Chance, <{args.max_hours:.0f}h Expiry, Max {args.max_per_event} Bet/Event")
    print("="*80)

    try:
        while True:
            trades = bot.execute_scan_cycle()
            summary = bot.get_summary()

            print(f"\n--- PORTFOLIO SUMMARY ({args.mode.upper()}) ---")
            print(f" Current Bankroll: ${summary['current_bankroll']:.2f} (Start: ${summary['initial_bankroll']:.2f})")
            print(f" Available Cash:   ${summary['available_cash']:.2f}")
            print(f" Active Exposure:  ${summary['active_exposure']:.2f} across {summary['active_positions_count']} positions")
            print(f" New Trades Placed This Cycle: {len(trades)}")
            print(f" Total Realized PnL: ${summary['total_pnl']:.2f} (ROI: {summary['roi_percent']}%)")
            print("="*80)

            if not args.loop:
                break

            logger.info(f"Sleeping for {args.interval} seconds before next cycle (Press Ctrl+C to stop)...")
            time.sleep(args.interval)

    except KeyboardInterrupt:
        logger.info("Bot execution halted by user.")

if __name__ == "__main__":
    main()

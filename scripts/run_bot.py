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

from config.settings import BANKROLL_START, API_BASE_URL
from src.bot.engine import TradingBot
from src.strategy.scanner import MarketScanner
from src.api.kalshi_client import KalshiClient
from src.utils.logger import logger

def main():
    parser = argparse.ArgumentParser(description="Kalshi High-Probability Trading Bot")
    parser.add_argument("--mode", choices=["paper", "live"], default="paper", help="Execution mode: 'paper' (simulated) or 'live' (real orders)")
    parser.add_argument("--bankroll", type=float, default=BANKROLL_START, help="Initial bankroll for paper trading ($)")
    parser.add_argument("--loop", action="store_true", help="Run continuously in a loop")
    parser.add_argument("--interval", type=int, default=300, help="Interval in seconds between cycles when looping (default: 300s)")
    args = parser.parse_args()

    client = KalshiClient(base_url=API_BASE_URL)
    scanner = MarketScanner(base_url=API_BASE_URL)
    bot = TradingBot(mode=args.mode, bankroll=args.bankroll, scanner=scanner, client=client)

    print("\n" + "="*80)
    print(f" KALSHI HIGH-PROBABILITY TRADING BOT [{args.mode.upper()} MODE]")
    print(f" Strategy: >90% Win Chance, <24h Expiry, 5% Bankroll Sizing, 75% Exposure Cap")
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

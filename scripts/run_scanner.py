"""
CLI Script: Kalshi Market Scanner.
Runs high-probability intraday scanning and outputs clean formatted results.
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import PROD_API_URL, DEMO_API_URL, MIN_PROBABILITY, MAX_PROBABILITY, MAX_HOURS_TO_EXPIRY
from src.strategy.scanner import MarketScanner

def main():
    parser = argparse.ArgumentParser(description="Kalshi Intraday High-Probability Scanner (<24h)")
    parser.add_argument("--env", choices=["prod", "demo"], default="prod", help="API environment (default: prod)")
    parser.add_argument("--max-hours", type=float, default=MAX_HOURS_TO_EXPIRY, help="Max hours to settlement (default: 24.0)")
    parser.add_argument("--min-prob", type=float, default=MIN_PROBABILITY, help=f"Min probability (default: {MIN_PROBABILITY})")
    parser.add_argument("--max-prob", type=float, default=MAX_PROBABILITY, help=f"Max probability (default: {MAX_PROBABILITY})")
    parser.add_argument("--all-strikes", action="store_true", help="Show all qualifying strike brackets rather than top 1 per event")
    parser.add_argument("--top", type=int, default=20, help="Number of top candidates to display (default: 20)")
    args = parser.parse_args()

    api_url = PROD_API_URL if args.env == "prod" else DEMO_API_URL

    mode_text = "ALL STRIKES" if args.all_strikes else "1 BEST STRIKE PER EVENT"
    print(f"\n" + "="*80)
    print(f" KALSHI SAME-DAY (<{args.max_hours:.0f}h) HIGH-PROBABILITY SCANNER ({args.env.upper()} API)")
    print(f" Filter: Win Probability {args.min_prob*100:.0f}% - {args.max_prob*100:.0f}% | Mode: {mode_text}")
    print("="*80)

    scanner = MarketScanner(
        base_url=api_url,
        min_prob=args.min_prob,
        max_prob=args.max_prob,
        max_hours=args.max_hours
    )

    candidates = scanner.scan_all_opportunities(dedup_by_event=not args.all_strikes)

    if not candidates:
        print("\nNo qualifying same-day markets found with current criteria.")
        return

    print(f"\nFound {len(candidates)} qualifying opportunities (Showing top {min(len(candidates), args.top)}):")
    for i, c in enumerate(candidates[:args.top], 1):
        print(f"\n[{i:02d}] {c['ticker']} ({c.get('event_ticker', '')}) -> {c['action']} @ ${c['ask_price']:.2f} ({c['implied_prob']} Prob)")
        print(f"     Title: {c['title']}")
        print(f"     Settlement: In {c['hours_left']} hours (Closes {c['close_time']})")
        print(f"     Economics: Net +${c['net_profit']:.3f}/contract (ROI: +{c['roi_percent']}% | Fee: -${c['fee']:.3f})")
        print(f"     Liquidity: Open Interest: {c['oi']:,.0f} contracts | Bid: ${c['bid_price']:.2f} / Ask: ${c['ask_price']:.2f} (Spread: ${c['spread']:.2f})")

    print("\n" + "="*80)

if __name__ == "__main__":
    main()

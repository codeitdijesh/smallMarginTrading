"""
AutoBetTool / SmallMarginTrading - Main Entry Point.
Provides unified CLI access for running the scanner or the automated paper trading bot.
"""

import argparse
import sys
from scripts.run_scanner import main as run_scanner_main
from scripts.run_bot import main as run_bot_main

def main():
    parser = argparse.ArgumentParser(
        description="Kalshi High-Probability Trading Bot CLI",
        usage="python main.py [scan|bot] [options]"
    )
    parser.add_argument("mode", choices=["scan", "bot"], help="Execution mode: 'scan' to inspect opportunities, 'bot' to run paper trading")
    
    # Check if a sub-command is called or forward arguments
    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(1)

    mode = sys.argv[1].lower()
    # Shift sys.argv so sub-parsers can parse remaining flags
    sys.argv = [sys.argv[0]] + sys.argv[2:]

    if mode == "scan":
        run_scanner_main()
    elif mode == "bot":
        run_bot_main()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

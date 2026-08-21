"""
Configuration settings for Kalshi High-Probability Trading Bot (AutoBetTool).
Loads environment variables and sets core strategy thresholds.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv(BASE_DIR / ".env")

# API Configuration
KALSHI_ENV = os.getenv("KALSHI_ENV", "prod").lower()
DEMO_API_URL = "https://demo-api.kalshi.co/trade-api/v2"
PROD_API_URL = "https://api.elections.kalshi.com/trade-api/v2"

API_BASE_URL = DEMO_API_URL if KALSHI_ENV == "demo" else PROD_API_URL

# Credentials (for authenticated live/demo trading)
KALSHI_API_KEY_ID = os.getenv("KALSHI_API_KEY_ID", os.getenv("KALSHI_API", "")).strip()
KALSHI_PRIVATE_KEY = os.getenv("KALSHI_PRIVATE_KEY", "").strip()
KALSHI_PRIVATE_KEY_PATH = os.getenv("KALSHI_PRIVATE_KEY_PATH", "").strip()

# ---------------- Strategy Parameters (Per PRD) ---------------- #
# 1. Target Probability (>90% win chance, capped at 98% to guarantee margin)
MIN_PROBABILITY = 0.90
MAX_PROBABILITY = 0.98

# 2. Time to Settlement (<24 Hours for rapid compounding)
MAX_HOURS_TO_EXPIRY = 24.0

# 3. Market Filter & Liquidity
MAX_BID_ASK_SPREAD = 0.08   # Max 8 cents spread to prevent slippage
MIN_OPEN_INTEREST = 50.0    # Minimum contracts of open interest
MIN_VOLUME_24H = 0.0        # Volume threshold

# 4. Risk Management
BANKROLL_START = 1000.0                # Initial virtual bankroll for paper trading ($)
MAX_POSITION_SIZE_PERCENT = 0.05       # Risk fixed 5% of total bankroll per trade
MAX_TOTAL_EXPOSURE_PERCENT = 0.75      # Never exceed 75% total active allocation
STOP_LOSS_PRICE_DROP = 0.15            # Exit if contract price drops > 15 cents below entry

# 5. Kalshi Fee Model Parameters
KALSHI_FEE_MULTIPLIER = 0.07           # Kalshi formula: 0.07 * price * (1 - price)
MIN_FEE_PER_CONTRACT = 0.01            # Kalshi min $0.01 fee

# 6. High-Volume Daily / Intraday Series
DAILY_SERIES = [
    # Weather Daily Highs/Lows
    "KXHIGHDEN", "KXHIGHPHIL", "KXHIGHMIA", "KXHIGHCHI", "KXHIGHAUS",
    "KXHIGHNY", "KXLOWTLFPG", "KXHIGHTRKSI", "KXHIGHLAX", "KXHIGHSFO", "KXHIGHBOS",
    # Financial / Crypto Daily Closes
    "KXBTCD", "KXETHD", "INXD", "NASDAQ100D",
    # Sports Daily
    "KXMLBGAME", "KXNBAGAME", "KXSOCCER", "KXCSGOGAME", "KXLOL"
]

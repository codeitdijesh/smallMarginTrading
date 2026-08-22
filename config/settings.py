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
KALSHI_ENV = os.getenv("KALSHI_ENV", "demo").lower()
DEMO_API_URL = "https://demo-api.kalshi.co/trade-api/v2"
PROD_API_URL = os.getenv("KALSHI_PROD_URL", "https://external-api.kalshi.com/trade-api/v2")

# Market scanner reads live production orderbooks for accurate price discovery
SCANNER_API_URL = os.getenv("KALSHI_SCANNER_URL", PROD_API_URL)
API_BASE_URL = SCANNER_API_URL
AUTH_API_URL = DEMO_API_URL if KALSHI_ENV == "demo" else PROD_API_URL

# Credentials (for authenticated live/demo trading with multiple alias support)
KALSHI_API_KEY_ID = (
    os.getenv("KALSHI_API_KEY_ID") or
    os.getenv("KALSHI_API_KEY") or
    os.getenv("KALSHI_KEY_ID") or
    os.getenv("KALSHI_API") or
    ""
).strip()

KALSHI_PRIVATE_KEY = (
    os.getenv("KALSHI_PRIVATE_KEY") or
    os.getenv("KALSHI_RSA_PRIVATE_KEY") or
    os.getenv("KALSHI_SECRET_KEY") or
    ""
).strip()

KALSHI_PRIVATE_KEY_PATH = os.getenv("KALSHI_PRIVATE_KEY_PATH", "").strip()

# ---------------- Strategy Parameters (Per PRD) ---------------- #
# 1. Target Probability (High win chance, configurable via env or CLI)
MIN_PROBABILITY = float(os.getenv("MIN_PROBABILITY", "0.85"))
MAX_PROBABILITY = float(os.getenv("MAX_PROBABILITY", "0.98"))

# 2. Time to Settlement (<24 Hours for rapid compounding)
MAX_HOURS_TO_EXPIRY = float(os.getenv("MAX_HOURS_TO_EXPIRY", "24.0"))

# 3. Market Filter & Liquidity
MAX_BID_ASK_SPREAD = float(os.getenv("MAX_BID_ASK_SPREAD", "0.08"))   # Max 8 cents spread to prevent slippage
MIN_OPEN_INTEREST = float(os.getenv("MIN_OPEN_INTEREST", "25.0"))     # Minimum contracts of open interest
MIN_VOLUME_24H = float(os.getenv("MIN_VOLUME_24H", "0.0"))           # Volume threshold

# 4. Risk Management & Diversification (Anti-Overexposure)
BANKROLL_START = 1000.0                                               # Initial virtual bankroll for paper trading ($)
MAX_POSITION_SIZE_PERCENT = 0.05                                      # Risk fixed 5% of total bankroll per trade
MAX_TOTAL_EXPOSURE_PERCENT = 0.75                                     # Never exceed 75% total active allocation
MAX_POSITIONS_PER_EVENT = int(os.getenv("MAX_POSITIONS_PER_EVENT", "1"))           # Max 1 trade per underlying event (prevents betting on same event 10 times)
MAX_EVENT_EXPOSURE_PERCENT = float(os.getenv("MAX_EVENT_EXPOSURE_PERCENT", "0.05"))# Max 5% bankroll exposure on any single event
MAX_POSITIONS_PER_SERIES = int(os.getenv("MAX_POSITIONS_PER_SERIES", "3"))         # Max 3 trades across the same series
MAX_SERIES_EXPOSURE_PERCENT = float(os.getenv("MAX_SERIES_EXPOSURE_PERCENT", "0.15")) # Max 15% exposure in one series
STOP_LOSS_PRICE_DROP = 0.15                                           # Exit if contract price drops > 15 cents below entry

# 5. Kalshi Fee Model Parameters
KALSHI_FEE_MULTIPLIER = 0.07                                          # Kalshi formula: 0.07 * price * (1 - price)
MIN_FEE_PER_CONTRACT = 0.01                                           # Kalshi min $0.01 fee

# 6. High-Volume Daily / Intraday Series
DAILY_SERIES = [
    # Weather Daily Highs & Lows
    "KXHIGHDEN", "KXHIGHPHIL", "KXHIGHMIA", "KXHIGHCHI", "KXHIGHAUS",
    "KXHIGHNY", "KXHIGHLAX", "KXHIGHTSFO", "KXHIGHTSEA", "KXHIGHTLV",
    "KXHIGHTPHX", "KXLOWTSEA", "KXLOWTLAX", "KXLOWTPHX", "KXLOWTSATX",
    "KXLOWTOKC", "KXLOWTMIN", "KXRAIN", "KXRAINWKND",
    # Financial / Crypto Daily Closes
    "KXBTCD", "KXETHD", "KXSOL", "KXBTCDAILY", "KXETHDAILY",
    # Sports Daily & Fast Turnover Matches
    "KXMLBGAME", "KXNBAGAME", "KXNFLGAME", "KXCLUBFTOTAL", "KXCLUBFSPREAD", "KXCLUBFGAME", "KXCLUBFBTTS",
    # Fast Weekly / Daily Entertainment & Events
    "KXALBUMEQUIV", "KXTRUMPNOMNUM"
]

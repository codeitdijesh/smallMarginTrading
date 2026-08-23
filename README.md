# Small Margin Trading Bot (AutoBetTool)

An automated, high-probability, low-margin compounding trading bot and scanner for **Kalshi** prediction markets.

## 1. Strategy Overview

Based on the [Product Requirements Document (PRD)](file:///C:/Users/DSU%20Student/Desktop/autoBetTool/PRD.md):
- **High Win Probability:** Targets contracts priced between **$0.90 - $0.98** (>90% implied probability).
- **Fast Capital Turnover (<24 Hours):** Focuses exclusively on markets settling within 24 hours (weather brackets, daily crypto/index closes, sports).
- **Strict Liquidity & Spread Filter:** Enforces maximum bid-ask spread ($\le \$0.08$) and minimum open interest to avoid slippage.
- **Dynamic Fee Calculation:** Accounts for Kalshi maker/taker fee model to guarantee net positive EV before placing orders.
- **Strict Risk Management:**
  - Fixed **5% bankroll** sizing per trade.
  - **75% max portfolio exposure** cap.
  - **Stop-Loss strategy** against drastic market moves.
- **Strict Limit Orders (Kalshi V2 API):** Uses single-book limit orders (`/portfolio/events/orders`) with RSA cryptographic authentication. Never submits market orders.

---

## 2. Project Directory Structure

```text
smallMarginTrading/
├── .github/
│   └── workflows/
│       └── trading_bot.yml  # GitHub Actions cron scheduler (every 10 minutes)
├── config/
│   ├── __init__.py
│   └── settings.py          # Environment settings, thresholds, API endpoints, series tickers
├── src/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── kalshi_client.py # Kalshi V2 RSA API client (public queries & order execution)
│   ├── bot/
│   │   ├── __init__.py
│   │   └── engine.py        # Automated paper & live trading engine & risk manager
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── fees.py          # Kalshi fee formula & net return economics
│   │   ├── risk.py          # Bankroll sizing (5%), max exposure (75%), and stop-loss logic
│   │   └── scanner.py       # Market scanning & filtering engine (<24h, >90% prob, spread limit)
│   └── utils/
│       ├── __init__.py
│       └── logger.py        # Centralized logger
├── scripts/
│   ├── run_scanner.py       # Standalone CLI scanner
│   └── run_bot.py           # Standalone CLI paper & live bot
├── tests/
│   ├── __init__.py
│   ├── test_fees.py         # Unit tests for fee & profit economics
│   ├── test_risk.py         # Unit tests for risk management
│   └── test_scanner.py      # Unit tests for filtering & candidate discovery
├── .env.example             # Template for API credentials and environment mode
├── .gitignore               # Clean git ignore configuration
├── main.py                  # Primary unified CLI entry point
├── PRD.md                   # Product Requirements Document
├── requirements.txt         # Python dependencies
└── README.md                # Documentation
```

---

## 3. Quick Start

### Installation

```bash
git clone https://github.com/codeitdijesh/smallMarginTrading.git
cd smallMarginTrading
python -m pip install -r requirements.txt
```

### Configuration (`.env`)

```env
KALSHI_API_KEY_ID=your-api-key-id-uuid
KALSHI_PRIVATE_KEY_PATH=kalshi.pem
KALSHI_ENV=demo # or prod
```

---

## 4. Usage & 24/7 Server Execution

### Run 24/7 Dedicated Server Daemon (Recommended)

Run the bot as a continuous background daemon on your server or dedicated laptop:

```bash
# Windows Batch (Auto-Restarts if closed or on error)
.\scripts\run_bot_daemon.bat

# Or PowerShell
.\scripts\run_bot_daemon.ps1

# Or Direct Python CLI
python scripts/run_bot.py --mode live --env demo --poll-interval 15 --scan-interval 180
```

### Strategy & 4-Layer Stop-Loss Defense
1. **Dynamic Time-Decay Stop:**
   - Adapts buffer based on hours to settlement ($24\text{h} \to \$0.55\text{ stop}, 1\text{h} \to \$0.75\text{ stop}$).
2. **Multi-Tick Persistence Filter:**
   - Price must stay below threshold for 2 consecutive ticks (30s) to avoid whipsaws / momentary flash dips.
3. **Spread & Depth Sanity:**
   - Ignores artificial spreads ($> \$0.15$) and 1-contract phantom bids.
4. **Limit Floor Protection:**
   - Hard floor at \$0.40 prevents panic dumping into illiquid pennies ($<\$0.40$).
5. **Startup Auto-Reconciliation:**
   - If server reboots or is offline, the bot automatically checks settled positions and reconciles balances upon startup.

---

## 5. Running Tests

```bash
python -m pytest
```
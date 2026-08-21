# AutoBetTool - Product Requirements Document (PRD)

## 1. Overview
The goal of this project is to build an automated trading bot for Kalshi (starting on the Demo/Sandbox API) that executes a high-probability, low-margin trading strategy. The bot will run continuously for a 2-week paper trading period to evaluate actual profitability before any real capital is deployed.

## 2. Core Strategy
- **Target Probability:** >90% win chance. The bot targets markets where implied probability is extremely high (e.g., 'Yes' contract $\ge \$0.90$, or 'No' contract $\ge \$0.90$).
- **Time to Settlement (<24 Hours):** To enable rapid compounding of small margins and prevent long capital lockups, the bot will strictly target markets closing within **24 hours** (same-day / intraday turnover, such as daily weather brackets, index closes, crypto prices, sports).
- **Market Filter ("Whale Money" & Liquidity):** Markets must exhibit real trading volume, open interest, and tight bid-ask spreads ($\le \$0.05 - \$0.08$) to avoid slippage.
- **Profit Objective:** Accumulate small margins (e.g., 2-8 cents net per contract) over rapid, continuous repeat trades.

## 3. Risk Management & Capital Allocation
- **Position Sizing:** The bot will risk a fixed **5% of total account bankroll** per trade. 
- **Maximum Exposure:** The bot will never allocate more than **75% of total bankroll** across all active trades simultaneously.
- **Stop-Loss Strategy:** **Strict Stop-Loss** to exit if a market moves drastically against the position before resolution.

## 4. Execution Details
- **Order Types:** **Strict Limit Orders** exclusively (never Market Orders).
- **Fee Calculation:** Dynamically deducts Kalshi maker/taker fee before placing an order to guarantee net-positive EV.

## 5. Technical Architecture
- **API Environment:** Kalshi Demo / Sandbox API (`demo-api.kalshi.co`) with fallback / monitoring on Live API.
- **Execution Frequency:** Polling REST API every 1-5 minutes via GitHub Actions `cron`.
- **Language:** Python 3.x (`requests`, `kalshi-python`, `cryptography`, `python-dotenv`).

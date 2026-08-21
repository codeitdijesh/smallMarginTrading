"""
Trading Bot Engine (Paper & Live).
Executes the high-probability, low-margin compounding strategy.
Simulates paper trading portfolio or submits strict limit orders to Kalshi API.
"""

from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import json
from pathlib import Path

from config.settings import (
    BANKROLL_START,
    MAX_POSITION_SIZE_PERCENT,
    MAX_TOTAL_EXPOSURE_PERCENT,
    STOP_LOSS_PRICE_DROP,
    BASE_DIR
)
from src.strategy.scanner import MarketScanner
from src.strategy.risk import RiskManager
from src.strategy.fees import calculate_contract_economics
from src.api.kalshi_client import KalshiClient
from src.utils.logger import logger

class TradingBot:
    def __init__(
        self,
        mode: str = "paper", # "paper" or "live"
        bankroll: float = BANKROLL_START,
        scanner: Optional[MarketScanner] = None,
        risk_manager: Optional[RiskManager] = None,
        client: Optional[KalshiClient] = None,
        state_file: Optional[Path] = None
    ):
        self.mode = mode.lower()
        self.client = client or KalshiClient()
        self.scanner = scanner or MarketScanner(base_url=self.client.base_url)
        self.risk_manager = risk_manager or RiskManager(
            max_position_pct=MAX_POSITION_SIZE_PERCENT,
            max_exposure_pct=MAX_TOTAL_EXPOSURE_PERCENT,
            stop_loss_drop=STOP_LOSS_PRICE_DROP
        )
        self.state_file = state_file or (BASE_DIR / "paper_trading_state.json")
        self.active_positions: Dict[str, Dict[str, Any]] = {}
        self.closed_positions: List[Dict[str, Any]] = []

        if self.mode == "live":
            if not self.client.is_authenticated:
                logger.error("Live mode requires valid Kalshi RSA credentials (KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY).")
            else:
                live_bal = self.client.get_balance()
                if live_bal and "balance_dollars" in live_bal:
                    bankroll = live_bal["balance_dollars"]
                    logger.info(f"Retrieved Live Kalshi Balance: ${bankroll:.2f}")

        self.bankroll = bankroll
        self.initial_bankroll = bankroll
        self.load_state()

    @property
    def total_exposure(self) -> float:
        """Total capital currently locked in active positions."""
        return sum(pos["total_cost"] for pos in self.active_positions.values())

    @property
    def available_cash(self) -> float:
        """Cash available for new trades."""
        return max(0.0, self.bankroll - self.total_exposure)

    def execute_scan_cycle(self) -> List[Dict[str, Any]]:
        """
        Executes one full scan & trade cycle:
        1. Query live balance if in live mode
        2. Scan opportunities
        3. Filter and size positions (5% bankroll, 75% max exposure)
        4. Enter orders (paper simulated or live API)
        """
        if self.mode == "live" and self.client.is_authenticated:
            live_bal = self.client.get_balance()
            if live_bal and "balance_dollars" in live_bal:
                self.bankroll = live_bal["balance_dollars"]

        logger.info(f"--- Starting {self.mode.upper()} Cycle | Bankroll: ${self.bankroll:.2f} | Active Exposure: ${self.total_exposure:.2f} ---")
        opportunities = self.scanner.scan_all_opportunities()

        entered_trades = []

        for opp in opportunities:
            ticker = opp["ticker"]
            side = opp["side"]
            pos_key = f"{ticker}_{side}"

            # Skip if already holding position in this market & side
            if pos_key in self.active_positions:
                continue

            price = opp["ask_price"]
            # Sizing: 5% of total bankroll
            contracts = self.risk_manager.calculate_position_size(self.bankroll, price)
            if contracts <= 0:
                continue

            total_cost = round(contracts * price, 2)

            # Exposure check: Max 75% total exposure
            approved, reason = self.risk_manager.validate_exposure(
                self.bankroll,
                self.total_exposure,
                total_cost
            )

            if not approved:
                logger.info(f"Skipping {ticker} ({side}): {reason}")
                continue

            order_response = None
            if self.mode == "live":
                if not self.client.is_authenticated:
                    logger.error(f"Cannot place live order for {ticker}: Client is not authenticated.")
                    continue
                # Submit strict LIMIT order to Kalshi
                order_response = self.client.place_limit_order(
                    ticker=ticker,
                    action="buy",
                    side=side,
                    count=contracts,
                    price_dollars=price
                )
                if not order_response:
                    logger.warning(f"Live order placement failed for {ticker}")
                    continue

            # Record Position
            econ = calculate_contract_economics(price)
            pos = {
                "ticker": ticker,
                "title": opp["title"],
                "side": side,
                "entry_price": price,
                "contracts": contracts,
                "total_cost": total_cost,
                "est_fee": round(econ["fee"] * contracts, 3),
                "est_net_profit": round(econ["net_profit"] * contracts, 3),
                "roi_percent": opp["roi_percent"],
                "hours_left": opp["hours_left"],
                "close_time": opp["close_time"],
                "mode": self.mode,
                "order_id": order_response.get("order_id") if order_response else None,
                "entered_at": datetime.now(timezone.utc).isoformat()
            }

            self.active_positions[pos_key] = pos
            entered_trades.append(pos)
            logger.info(
                f"[{self.mode.upper()} ORDER PLACED] {ticker} -> {opp['action']} | {contracts} contracts @ ${price:.2f} "
                f"(Cost: ${total_cost:.2f}, Est Net: +${pos['est_net_profit']:.2f})"
            )

        self.save_state()
        return entered_trades

    def evaluate_settlements(self, current_market_prices: Optional[Dict[str, float]] = None):
        """
        Simulates / updates position resolutions and stop loss exits.
        """
        now = datetime.now(timezone.utc)
        resolved_keys = []

        for key, pos in self.active_positions.items():
            if current_market_prices and pos["ticker"] in current_market_prices:
                cur_price = current_market_prices[pos["ticker"]]
                if self.risk_manager.check_stop_loss(pos["entry_price"], cur_price):
                    loss = pos["total_cost"] - (cur_price * pos["contracts"])
                    self.bankroll -= loss
                    pos["outcome"] = "STOP_LOSS"
                    pos["realized_pnl"] = -round(loss, 2)
                    pos["resolved_at"] = now.isoformat()
                    self.closed_positions.append(pos)
                    resolved_keys.append(key)
                    logger.warning(f"[STOP LOSS EXIT] {pos['ticker']} exit @ ${cur_price:.2f}. Loss: -${loss:.2f}")

        for key in resolved_keys:
            del self.active_positions[key]

        self.save_state()

    def get_summary(self) -> Dict[str, Any]:
        """Returns portfolio performance metrics."""
        total_pnl = self.bankroll - self.initial_bankroll
        roi = (total_pnl / self.initial_bankroll) * 100 if self.initial_bankroll > 0 else 0.0
        return {
            "mode": self.mode,
            "initial_bankroll": self.initial_bankroll,
            "current_bankroll": round(self.bankroll, 2),
            "active_exposure": round(self.total_exposure, 2),
            "available_cash": round(self.available_cash, 2),
            "active_positions_count": len(self.active_positions),
            "closed_trades_count": len(self.closed_positions),
            "total_pnl": round(total_pnl, 2),
            "roi_percent": round(roi, 2)
        }

    def save_state(self):
        """Persists trading state to JSON file."""
        state = {
            "mode": self.mode,
            "bankroll": self.bankroll,
            "initial_bankroll": self.initial_bankroll,
            "active_positions": self.active_positions,
            "closed_positions": self.closed_positions,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving state: {e}")

    def load_state(self):
        """Loads state from JSON file if available."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.bankroll = data.get("bankroll", self.bankroll)
                    self.initial_bankroll = data.get("initial_bankroll", self.initial_bankroll)
                    self.active_positions = data.get("active_positions", {})
                    self.closed_positions = data.get("closed_positions", [])
                    logger.info(f"Loaded existing trading state from {self.state_file}")
            except Exception as e:
                logger.error(f"Error loading state from {self.state_file}: {e}")

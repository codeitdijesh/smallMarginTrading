"""
Trading Bot Engine (Demo & Live API).
Executes the high-probability, low-margin compounding strategy.
Features:
- Active real-time position monitoring
- Dynamic time-decay stop-loss execution
- Multi-tick persistence filter (anti-whipsaw noise defense)
- Bid depth and spread sanity filters (anti-ghost bid defense)
- Limit floor rule (anti-penny panic dump defense)
- Automatic startup reconciliation and state recovery
"""

from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import json
import time
from pathlib import Path

from config.settings import (
    BANKROLL_START,
    MAX_POSITION_SIZE_PERCENT,
    MAX_TOTAL_EXPOSURE_PERCENT,
    STOP_LOSS_PRICE_DROP,
    ENABLE_STOP_LOSS,
    STOP_LOSS_TYPE,
    STOP_LOSS_BASE_DROP,
    STOP_LOSS_MIN_DROP,
    STOP_LOSS_MAX_DROP,
    STOP_LOSS_LIMIT_FLOOR,
    STOP_LOSS_PERSISTENCE_TICKS,
    STOP_LOSS_MAX_SPREAD,
    STOP_LOSS_MIN_BID_DEPTH,
    POSITION_CHECK_INTERVAL,
    SCAN_INTERVAL,
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
        mode: str = "live", # "live" (Demo or Prod via KalshiClient) or "paper"
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
            stop_loss_drop=STOP_LOSS_PRICE_DROP,
            enable_stop_loss=ENABLE_STOP_LOSS,
            stop_loss_type=STOP_LOSS_TYPE,
            stop_loss_base_drop=STOP_LOSS_BASE_DROP,
            stop_loss_min_drop=STOP_LOSS_MIN_DROP,
            stop_loss_max_drop=STOP_LOSS_MAX_DROP,
            stop_loss_limit_floor=STOP_LOSS_LIMIT_FLOOR,
            stop_loss_persistence_ticks=STOP_LOSS_PERSISTENCE_TICKS,
            stop_loss_max_spread=STOP_LOSS_MAX_SPREAD,
            stop_loss_min_bid_depth=STOP_LOSS_MIN_BID_DEPTH
        )
        self.state_file = state_file or (BASE_DIR / f"{self.mode}_trading_state.json")
        self.active_positions: Dict[str, Dict[str, Any]] = {}
        self.closed_positions: List[Dict[str, Any]] = []

        self.live_balance_loaded = False
        self.live_portfolio_value = 0.0
        self.live_total_equity = bankroll
        self.bankroll = bankroll
        self.initial_bankroll = bankroll

        if self.mode == "live":
            if not self.client.is_authenticated:
                logger.error("Live mode requires valid Kalshi RSA credentials (KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY). Defaulting to fallback bankroll.")
            else:
                self.refresh_live_balance()

        self.load_state()

        if self.mode == "live" and self.client.is_authenticated:
            self.sync_live_positions()

        # Reconcile on startup to handle any trades resolved during offline periods
        self.reconcile_positions_on_startup()

    def refresh_live_balance(self) -> Optional[Dict[str, Any]]:
        """Refreshes live account balance, available cash, portfolio value, and equity from Kalshi API."""
        if self.mode != "live" or not self.client.is_authenticated:
            return None

        live_bal = self.client.get_balance()
        if live_bal and "available_cash" in live_bal:
            self.bankroll = live_bal["available_cash"]
            self.live_portfolio_value = live_bal.get("portfolio_value", 0.0)
            self.live_total_equity = live_bal.get("total_equity", round(self.bankroll + self.live_portfolio_value, 2))
            self.live_balance_loaded = True
            logger.info(
                f"Retrieved Live Kalshi Account -> Total Equity: ${self.live_total_equity:.2f} | "
                f"Available Cash: ${self.bankroll:.2f} | Open Positions Value: ${self.live_portfolio_value:.2f}"
            )
            return live_bal
        else:
            logger.warning(f"Could not retrieve live balance from Kalshi API. Using current bankroll: ${self.bankroll:.2f}")
            return None

    @property
    def total_exposure(self) -> float:
        """Total capital currently locked in active positions."""
        return sum(pos["total_cost"] for pos in self.active_positions.values())

    @property
    def total_equity(self) -> float:
        """Total account equity = Available Cash + Capital deployed in open positions."""
        if self.mode == "live" and self.live_balance_loaded:
            return round(self.bankroll + (self.live_portfolio_value if self.live_portfolio_value > 0 else self.total_exposure), 2)
        return self.bankroll

    @property
    def available_cash(self) -> float:
        """Cash available for new trades."""
        if self.mode == "live" and self.live_balance_loaded:
            return max(0.0, self.bankroll)
        return max(0.0, self.bankroll - self.total_exposure)

    def sync_live_positions(self):
        """Syncs active positions and resting orders from Kalshi API when authenticated in live mode."""
        if self.mode != "live" or not self.client.is_authenticated:
            return

        try:
            positions_data = self.client.get_positions(status="open")
            if positions_data is not None:
                market_positions = positions_data.get("market_positions", [])
                live_pos_keys = set()
                for mp in market_positions:
                    ticker = mp.get("ticker")
                    pos_count = int(float(mp.get("position_fp") or mp.get("position") or 0))
                    if not ticker or pos_count == 0:
                        continue
                    side = "yes" if pos_count > 0 else "no"
                    pos_key = f"{ticker}_{side}"
                    live_pos_keys.add(pos_key)
                    exposure = float(mp.get("market_exposure_dollars") or (float(mp.get("market_exposure", 0)) / 100.0) or 0.0)
                    entry_price = exposure / max(1, abs(pos_count)) if abs(pos_count) > 0 else 0.90

                    if pos_key not in self.active_positions:
                        event_ticker = ticker.rsplit("-", 1)[0] if "-" in ticker else ticker
                        series_ticker = ticker.split("-")[0] if "-" in ticker else ticker
                        self.active_positions[pos_key] = {
                            "ticker": ticker,
                            "event_ticker": event_ticker,
                            "series_ticker": series_ticker,
                            "title": ticker,
                            "side": side,
                            "entry_price": round(entry_price, 4),
                            "contracts": abs(pos_count),
                            "total_cost": round(exposure, 2),
                            "est_fee": 0.0,
                            "est_net_profit": 0.0,
                            "roi_percent": 0.0,
                            "hours_left": 24.0,
                            "initial_hours": 24.0,
                            "breach_count": 0,
                            "close_time": "Live Position",
                            "mode": "live",
                            "synced_from_api": True,
                            "entered_at": datetime.now(timezone.utc).isoformat()
                        }
                    else:
                        self.active_positions[pos_key]["contracts"] = abs(pos_count)
                        if exposure > 0:
                            self.active_positions[pos_key]["total_cost"] = round(exposure, 2)

                # Reconcile any positions in active_positions that are no longer open on Kalshi
                stale_keys = [k for k, v in self.active_positions.items() if v.get("mode") == "live" and k not in live_pos_keys]
                for k in stale_keys:
                    logger.info(f"Reconciling stale live position not found on Kalshi: {k}")
                    pos = self.active_positions.pop(k)
                    pos["outcome"] = "CLOSED_ON_KALSHI"
                    pos["resolved_at"] = datetime.now(timezone.utc).isoformat()
                    self.closed_positions.append(pos)

                if stale_keys:
                    self.save_state()
        except Exception as e:
            logger.warning(f"Could not sync live positions from API: {e}")

    def reconcile_positions_on_startup(self):
        """
        Reconciles portfolio state on startup.
        Checks if any active positions were settled or resolved while the bot was offline.
        """
        if not self.active_positions:
            return

        logger.info(f"Reconciling {len(self.active_positions)} active position(s) on startup...")
        resolved_keys = []
        now = datetime.now(timezone.utc)

        for pos_key, pos in list(self.active_positions.items()):
            ticker = pos["ticker"]
            side = pos["side"]
            quote = self.client.get_market_quote(ticker, side)

            if not quote:
                continue

            status = quote.get("status", "").lower()
            result = quote.get("result", "").lower()

            if status in ("finalized", "closed", "settled") or result in ("yes", "no"):
                # Market finalized while offline
                if result == side:
                    gross_payout = pos["contracts"] * 1.0
                    fee = pos.get("est_fee", 0.0)
                    realized_pnl = gross_payout - pos["total_cost"] - fee
                    pos["outcome"] = "WIN"
                    pos["realized_pnl"] = round(realized_pnl, 2)
                    if not (self.mode == "live" and self.live_balance_loaded):
                        self.bankroll += (gross_payout - fee)
                    logger.info(f"[RECONCILE WIN] {ticker} ({side.upper()}) resolved as WIN while offline. Realized: +${realized_pnl:.2f}")
                else:
                    realized_pnl = -pos["total_cost"]
                    pos["outcome"] = "LOSS"
                    pos["realized_pnl"] = round(realized_pnl, 2)
                    logger.warning(f"[RECONCILE LOSS] {ticker} ({side.upper()}) resolved as LOSS while offline. Realized: ${realized_pnl:.2f}")

                pos["resolved_at"] = now.isoformat()
                self.closed_positions.append(pos)
                resolved_keys.append(pos_key)

        for k in resolved_keys:
            if k in self.active_positions:
                del self.active_positions[k]

        if resolved_keys:
            self.save_state()
            logger.info(f"Reconciliation complete: {len(resolved_keys)} position(s) settled.")

    def monitor_active_positions(self) -> Dict[str, Any]:
        """
        Active real-time monitoring loop for all open positions:
        1. Checks for market resolution / final settlement.
        2. Evaluates dynamic stop-loss condition (time-decay adjusted, spread/depth filtered).
        3. Applies multi-tick persistence filter to eliminate whipsaws.
        4. Submits sell limit order to Kalshi API when hard stop conditions are satisfied.
        """
        if not self.active_positions:
            return {"active_count": 0, "exits": 0, "warnings": 0, "settled": 0}

        now = datetime.now(timezone.utc)
        resolved_keys = []
        stats = {"active_count": len(self.active_positions), "exits": 0, "warnings": 0, "settled": 0}

        for pos_key, pos in list(self.active_positions.items()):
            ticker = pos["ticker"]
            side = pos["side"]
            entry_price = pos["entry_price"]
            contracts = pos["contracts"]
            total_cost = pos["total_cost"]

            quote = self.client.get_market_quote(ticker, side)
            if not quote:
                continue

            status = quote.get("status", "").lower()
            result = quote.get("result", "").lower()

            # 1. Check for Market Resolution
            if status in ("finalized", "closed", "settled") or result in ("yes", "no"):
                if result == side:
                    gross_payout = contracts * 1.0
                    fee = pos.get("est_fee", 0.0)
                    realized_pnl = gross_payout - total_cost - fee
                    pos["outcome"] = "WIN"
                    pos["realized_pnl"] = round(realized_pnl, 2)
                    if not (self.mode == "live" and self.live_balance_loaded):
                        self.bankroll += (gross_payout - fee)
                    logger.info(f"[SETTLEMENT WIN] {ticker} ({side.upper()}) resolved as WIN! Realized PnL: +${realized_pnl:.2f}")
                else:
                    realized_pnl = -total_cost
                    pos["outcome"] = "LOSS"
                    pos["realized_pnl"] = round(realized_pnl, 2)
                    logger.warning(f"[SETTLEMENT LOSS] {ticker} ({side.upper()}) resolved as LOSS. Realized PnL: ${realized_pnl:.2f}")

                pos["resolved_at"] = now.isoformat()
                self.closed_positions.append(pos)
                resolved_keys.append(pos_key)
                stats["settled"] += 1
                continue

            # 2. Evaluate Dynamic Stop-Loss
            bid_price = quote["bid_price"]
            ask_price = quote["ask_price"]
            bid_depth = quote["bid_depth"]

            # Calculate remaining hours
            hours_left = pos.get("hours_left", 24.0)
            if quote.get("close_time"):
                try:
                    close_dt = datetime.fromisoformat(quote["close_time"].replace("Z", "+00:00"))
                    hours_left = max(0.0, (close_dt - now).total_seconds() / 3600.0)
                except Exception:
                    pass

            initial_hours = pos.get("initial_hours") or pos.get("hours_left") or 24.0
            pos["hours_left"] = round(hours_left, 2)
            pos["last_bid"] = bid_price

            should_exit, target_stop, reason = self.risk_manager.evaluate_stop_loss_condition(
                entry_price=entry_price,
                current_bid=bid_price,
                current_ask=ask_price,
                bid_depth=bid_depth,
                hours_left=hours_left,
                total_hours=initial_hours
            )

            pos["target_stop"] = target_stop

            if should_exit:
                pos["breach_count"] = pos.get("breach_count", 0) + 1
                stats["warnings"] += 1
                logger.warning(
                    f"[STOP LOSS WARNING] {ticker} ({side.upper()}) | Entry: ${entry_price:.2f} | Bid: ${bid_price:.2f} <= Dynamic Stop: ${target_stop:.2f} "
                    f"| Breach: {pos['breach_count']}/{self.risk_manager.stop_loss_persistence_ticks} | {reason}"
                )

                # 3. Check Multi-Tick Persistence Filter
                if pos["breach_count"] >= self.risk_manager.stop_loss_persistence_ticks:
                    logger.warning(f"[STOP LOSS TRIGGERED] Breach persisted for {pos['breach_count']} ticks. Executing sell exit for {ticker} ({side.upper()}) @ ${bid_price:.2f}...")

                    # Execute Live Limit Sell on Kalshi
                    order_response = None
                    if self.mode == "live" and self.client.is_authenticated:
                        order_response = self.client.place_limit_order(
                            ticker=ticker,
                            action="sell",
                            side=side,
                            count=contracts,
                            price_dollars=bid_price
                        )
                        if not order_response:
                            logger.error(f"Failed to place live stop-loss sell order for {ticker}. Retrying next cycle.")
                            continue

                    # Calculate Realized Loss with Exit Fee
                    exit_proceeds = round(bid_price * contracts, 2)
                    econ = calculate_contract_economics(bid_price)
                    exit_fee = round(econ["fee"] * contracts, 3)
                    realized_pnl = round(exit_proceeds - total_cost - exit_fee, 2)

                    if not (self.mode == "live" and self.live_balance_loaded):
                        self.bankroll += (exit_proceeds - exit_fee)

                    pos["outcome"] = "STOP_LOSS"
                    pos["exit_price"] = bid_price
                    pos["exit_proceeds"] = exit_proceeds
                    pos["exit_fee"] = exit_fee
                    pos["realized_pnl"] = realized_pnl
                    pos["resolved_at"] = now.isoformat()
                    pos["exit_order_id"] = order_response.get("order_id") if order_response else None

                    self.closed_positions.append(pos)
                    resolved_keys.append(pos_key)
                    stats["exits"] += 1
                    logger.warning(
                        f"[STOP LOSS EXECUTED] Closed {contracts}x {ticker} ({side.upper()}) @ ${bid_price:.2f}. "
                        f"Proceeds: ${exit_proceeds:.2f}, Fee: ${exit_fee:.2f}, Realized Loss: -${abs(realized_pnl):.2f} "
                        f"(Saved: +${total_cost - exit_proceeds:.2f} vs total loss)"
                    )
            else:
                # Price recovered or noise check failed - reset breach counter
                if pos.get("breach_count", 0) > 0:
                    logger.info(f"[STOP LOSS RECOVERED] {ticker} ({side.upper()}) bid recovered to ${bid_price:.2f} > ${target_stop:.2f}. Persistence filter reset.")
                    pos["breach_count"] = 0

        for k in resolved_keys:
            if k in self.active_positions:
                del self.active_positions[k]

        if resolved_keys or stats["warnings"] > 0:
            self.save_state()

        return stats

    def execute_scan_cycle(self) -> List[Dict[str, Any]]:
        """
        Executes one full scan & trade entry cycle:
        1. Query live balance and sync positions if in live mode
        2. Scan opportunities (with native time windowing and event-level deduplication)
        3. Validate against strict risk controls (5% position size, 1 position/5% per event, 75% max exposure)
        4. Enter orders (Demo/Live API limit order)
        """
        if self.mode == "live" and self.client.is_authenticated:
            self.refresh_live_balance()
            self.sync_live_positions()

        logger.info(f"--- Starting {self.mode.upper()} Scan Cycle | Equity: ${self.total_equity:.2f} | Available Cash: ${self.available_cash:.2f} | Active Exposure: ${self.total_exposure:.2f} ---")
        opportunities = self.scanner.scan_all_opportunities(dedup_by_event=True)

        entered_trades = []

        for opp in opportunities:
            ticker = opp["ticker"]
            side = opp["side"]
            event_ticker = opp.get("event_ticker") or (ticker.rsplit("-", 1)[0] if "-" in ticker else ticker)
            pos_key = f"{ticker}_{side}"

            price = opp["ask_price"]
            # Sizing: 5% of total account equity
            contracts = self.risk_manager.calculate_position_size(self.total_equity, price)
            if contracts <= 0:
                continue

            total_cost = round(contracts * price, 2)

            # Check available cash buffer
            if total_cost > (self.available_cash + 0.01):
                logger.info(f"Skipping {ticker} ({side}): Insufficient available cash (${self.available_cash:.2f} < ${total_cost:.2f})")
                continue

            # Multi-layer risk validation
            approved, reason = self.risk_manager.validate_candidate_trade(
                self.total_equity,
                self.active_positions,
                opp,
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
            hours_left = opp.get("hours_left", 24.0)
            pos = {
                "ticker": ticker,
                "event_ticker": event_ticker,
                "series_ticker": opp.get("series_ticker"),
                "title": opp["title"],
                "side": side,
                "entry_price": price,
                "contracts": contracts,
                "total_cost": total_cost,
                "est_fee": round(econ["fee"] * contracts, 3),
                "est_net_profit": round(econ["net_profit"] * contracts, 3),
                "roi_percent": opp["roi_percent"],
                "hours_left": hours_left,
                "initial_hours": hours_left,
                "breach_count": 0,
                "target_stop": self.risk_manager.calculate_dynamic_stop_price(price, hours_left, hours_left),
                "close_time": opp["close_time"],
                "mode": self.mode,
                "order_id": order_response.get("order_id") if order_response else None,
                "entered_at": datetime.now(timezone.utc).isoformat()
            }

            self.active_positions[pos_key] = pos
            entered_trades.append(pos)
            logger.info(
                f"[{self.mode.upper()} ORDER PLACED] {ticker} ({event_ticker}) -> {opp['action']} | {contracts} contracts @ ${price:.2f} "
                f"(Cost: ${total_cost:.2f}, Est Net: +${pos['est_net_profit']:.2f}, Dynamic Stop: ${pos['target_stop']:.2f})"
            )

        self.save_state()
        return entered_trades

    def evaluate_settlements(self, current_market_prices: Optional[Dict[str, float]] = None):
        """Bridge method maintaining backwards compatibility."""
        return self.monitor_active_positions()

    def get_summary(self) -> Dict[str, Any]:
        """Returns portfolio performance metrics."""
        realized_pnl = sum(pos.get("realized_pnl", 0.0) for pos in self.closed_positions)
        total_pnl = self.total_equity - self.initial_bankroll
        roi = (total_pnl / self.initial_bankroll) * 100 if self.initial_bankroll > 0 else 0.0
        return {
            "mode": self.mode,
            "initial_bankroll": self.initial_bankroll,
            "total_equity": round(self.total_equity, 2),
            "current_bankroll": round(self.total_equity, 2),
            "available_cash": round(self.available_cash, 2),
            "active_exposure": round(self.total_exposure, 2),
            "active_positions_count": len(self.active_positions),
            "closed_trades_count": len(self.closed_positions),
            "realized_pnl": round(realized_pnl, 2),
            "total_pnl": round(total_pnl, 2),
            "roi_percent": round(roi, 2)
        }

    def save_state(self):
        """Persists trading state to JSON file."""
        state = {
            "mode": self.mode,
            "bankroll": self.bankroll,
            "initial_bankroll": self.initial_bankroll,
            "total_equity": round(self.total_equity, 2),
            "available_cash": round(self.available_cash, 2),
            "active_exposure": round(self.total_exposure, 2),
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
                    if not (self.mode == "live" and self.live_balance_loaded):
                        self.bankroll = data.get("bankroll", self.bankroll)
                    saved_initial = data.get("initial_bankroll")
                    if saved_initial and saved_initial > 0:
                        self.initial_bankroll = saved_initial
                    else:
                        self.initial_bankroll = self.total_equity if (self.mode == "live" and self.live_balance_loaded) else self.bankroll
                    self.active_positions = data.get("active_positions", {})
                    self.closed_positions = data.get("closed_positions", [])
                    logger.info(f"Loaded existing trading state from {self.state_file}")
            except Exception as e:
                logger.error(f"Error loading state from {self.state_file}: {e}")


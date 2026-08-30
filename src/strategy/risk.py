"""
Risk Management and Capital Allocation Module.
Enforces the 5% bankroll position limit, 75% max portfolio exposure,
strict event/series diversification to avoid multi-strike correlation risk,
and stop-loss logic.
"""

from typing import Tuple, Dict, Any, Optional, List
from config.settings import (
    MAX_POSITION_SIZE_PERCENT,
    MAX_ORDER_NOTIONAL_DOLLARS,
    MAX_CONTRACTS_PER_ORDER,
    MAX_TOTAL_EXPOSURE_PERCENT,
    MAX_POSITIONS_PER_EVENT,
    MAX_EVENT_EXPOSURE_PERCENT,
    MAX_POSITIONS_PER_SERIES,
    MAX_SERIES_EXPOSURE_PERCENT,
    STOP_LOSS_PRICE_DROP,
    ENABLE_STOP_LOSS,
    STOP_LOSS_TYPE,
    STOP_LOSS_BASE_DROP,
    STOP_LOSS_MIN_DROP,
    STOP_LOSS_MAX_DROP,
    STOP_LOSS_LIMIT_FLOOR,
    STOP_LOSS_PERSISTENCE_TICKS,
    STOP_LOSS_MAX_SPREAD,
    STOP_LOSS_MIN_BID_DEPTH
)

class RiskManager:
    def __init__(
        self,
        max_position_pct: float = MAX_POSITION_SIZE_PERCENT,
        max_order_notional: float = MAX_ORDER_NOTIONAL_DOLLARS,
        max_contracts_per_order: int = MAX_CONTRACTS_PER_ORDER,
        max_exposure_pct: float = MAX_TOTAL_EXPOSURE_PERCENT,
        max_positions_per_event: int = MAX_POSITIONS_PER_EVENT,
        max_event_exposure_pct: float = MAX_EVENT_EXPOSURE_PERCENT,
        max_positions_per_series: int = MAX_POSITIONS_PER_SERIES,
        max_series_exposure_pct: float = MAX_SERIES_EXPOSURE_PERCENT,
        stop_loss_drop: float = STOP_LOSS_PRICE_DROP,
        enable_stop_loss: bool = ENABLE_STOP_LOSS,
        stop_loss_type: str = STOP_LOSS_TYPE,
        stop_loss_base_drop: float = STOP_LOSS_BASE_DROP,
        stop_loss_min_drop: float = STOP_LOSS_MIN_DROP,
        stop_loss_max_drop: float = STOP_LOSS_MAX_DROP,
        stop_loss_limit_floor: float = STOP_LOSS_LIMIT_FLOOR,
        stop_loss_persistence_ticks: int = STOP_LOSS_PERSISTENCE_TICKS,
        stop_loss_max_spread: float = STOP_LOSS_MAX_SPREAD,
        stop_loss_min_bid_depth: int = STOP_LOSS_MIN_BID_DEPTH
    ):
        self.max_position_pct = max_position_pct
        self.max_order_notional = max_order_notional
        self.max_contracts_per_order = max_contracts_per_order
        self.max_exposure_pct = max_exposure_pct
        self.max_positions_per_event = max_positions_per_event
        self.max_event_exposure_pct = max_event_exposure_pct
        self.max_positions_per_series = max_positions_per_series
        self.max_series_exposure_pct = max_series_exposure_pct
        self.stop_loss_drop = stop_loss_drop
        self.enable_stop_loss = enable_stop_loss
        self.stop_loss_type = stop_loss_type.lower()
        self.stop_loss_base_drop = stop_loss_base_drop
        self.stop_loss_min_drop = stop_loss_min_drop
        self.stop_loss_max_drop = stop_loss_max_drop
        self.stop_loss_limit_floor = stop_loss_limit_floor
        self.stop_loss_persistence_ticks = stop_loss_persistence_ticks
        self.stop_loss_max_spread = stop_loss_max_spread
        self.stop_loss_min_bid_depth = stop_loss_min_bid_depth

    def calculate_position_size(self, current_bankroll: float, contract_price: float) -> int:
        """
        Calculates maximum contracts to buy ensuring total cost does not exceed
        5% of total bankroll.
        """
        if current_bankroll <= 0 or contract_price <= 0:
            return 0
        
        max_capital_to_risk = min(
            current_bankroll * self.max_position_pct,
            self.max_order_notional
        )
        # Number of contracts allowed
        contracts = int(max_capital_to_risk // contract_price)
        if self.max_contracts_per_order > 0:
            contracts = min(contracts, self.max_contracts_per_order)
        return max(0, contracts)

    def validate_candidate_trade(
        self,
        current_bankroll: float,
        active_positions: Dict[str, Dict[str, Any]],
        candidate: Dict[str, Any],
        new_trade_cost: float
    ) -> Tuple[bool, str]:
        """
        Validates if a candidate opportunity satisfies all portfolio risk constraints:
        1. Ticker duplicate check: Cannot hold multiple positions on the same market ticker.
        2. Event-level limit: Cannot exceed max positions or max exposure for the same underlying event
           (prevents betting on 10 strike brackets for the same weather/crypto/sports event).
        3. Series-level limit: Cannot over-concentrate across a single series.
        4. Total portfolio exposure: Overall capital allocation cannot exceed 75%.
        """
        if current_bankroll <= 0:
            return False, "Bankroll is zero or negative."

        ticker = candidate.get("ticker", "")
        event_ticker = candidate.get("event_ticker") or ticker.rsplit("-", 1)[0]
        series_ticker = candidate.get("series_ticker") or (ticker.split("-")[0] if "-" in ticker else ticker)

        total_active_exposure = sum(pos.get("total_cost", 0.0) for pos in active_positions.values())

        if self.max_order_notional > 0 and new_trade_cost > (self.max_order_notional + 0.01):
            return False, (
                f"Trade cost ${new_trade_cost:.2f} exceeds hard per-order cap "
                f"(${self.max_order_notional:.2f})"
            )

        # 1. Ticker duplication check
        for pos in active_positions.values():
            if pos.get("ticker") == ticker:
                return False, f"Already holding active position in market ticker: {ticker}"

        # 2. Event-level limits (Crucial fix for correlated strike betting)
        event_positions = [
            pos for pos in active_positions.values()
            if (pos.get("event_ticker") == event_ticker or pos.get("ticker", "").startswith(event_ticker))
        ]
        if len(event_positions) >= self.max_positions_per_event:
            return False, (
                f"Event {event_ticker} already has {len(event_positions)} active position(s) "
                f"(Max allowed per event: {self.max_positions_per_event})"
            )

        event_exposure = sum(pos.get("total_cost", 0.0) for pos in event_positions)
        max_allowed_event_exposure = current_bankroll * self.max_event_exposure_pct
        if (event_exposure + new_trade_cost) > (max_allowed_event_exposure + 0.01):
            return False, (
                f"Event {event_ticker} projected exposure (${event_exposure + new_trade_cost:.2f}) "
                f"exceeds event limit (${max_allowed_event_exposure:.2f})"
            )

        # 3. Series-level limits
        series_positions = [
            pos for pos in active_positions.values()
            if (pos.get("series_ticker") == series_ticker or pos.get("ticker", "").startswith(series_ticker))
        ]
        if len(series_positions) >= self.max_positions_per_series:
            return False, (
                f"Series {series_ticker} already has {len(series_positions)} active position(s) "
                f"(Max allowed per series: {self.max_positions_per_series})"
            )

        series_exposure = sum(pos.get("total_cost", 0.0) for pos in series_positions)
        max_allowed_series_exposure = current_bankroll * self.max_series_exposure_pct
        if (series_exposure + new_trade_cost) > (max_allowed_series_exposure + 0.01):
            return False, (
                f"Series {series_ticker} projected exposure (${series_exposure + new_trade_cost:.2f}) "
                f"exceeds series limit (${max_allowed_series_exposure:.2f})"
            )

        # 4. Total Portfolio Exposure Limit
        projected_total = total_active_exposure + new_trade_cost
        max_allowed_total = current_bankroll * self.max_exposure_pct
        if projected_total > (max_allowed_total + 0.01):
            return False, (
                f"Exceeds max portfolio exposure: ${projected_total:.2f} > ${max_allowed_total:.2f} "
                f"({self.max_exposure_pct*100:.0f}% limit)"
            )

        return True, "Approved"

    def audit_active_positions(
        self,
        current_bankroll: float,
        active_positions: Dict[str, Dict[str, Any]]
    ) -> Tuple[bool, List[str]]:
        """
        Audits already-open positions against the same portfolio constraints used for
        new entries. This catches synced/manual/legacy exposure that bypassed entry checks.
        """
        violations = []
        if current_bankroll <= 0:
            return False, ["Bankroll is zero or negative."]

        total_active_exposure = sum(pos.get("total_cost", 0.0) for pos in active_positions.values())
        max_allowed_total = current_bankroll * self.max_exposure_pct
        if total_active_exposure > (max_allowed_total + 0.01):
            violations.append(
                f"Total active exposure ${total_active_exposure:.2f} exceeds "
                f"portfolio limit ${max_allowed_total:.2f}"
            )

        event_groups: Dict[str, List[Dict[str, Any]]] = {}
        series_groups: Dict[str, List[Dict[str, Any]]] = {}

        for pos_key, pos in active_positions.items():
            ticker = pos.get("ticker", pos_key)
            event_ticker = pos.get("event_ticker") or (ticker.rsplit("-", 1)[0] if "-" in ticker else ticker)
            series_ticker = pos.get("series_ticker") or (ticker.split("-")[0] if "-" in ticker else ticker)
            total_cost = float(pos.get("total_cost", 0.0) or 0.0)
            contracts = int(float(pos.get("contracts", 0) or 0))

            if self.max_order_notional > 0 and total_cost > (self.max_order_notional + 0.01):
                violations.append(
                    f"{ticker} position cost ${total_cost:.2f} exceeds per-order cap "
                    f"${self.max_order_notional:.2f}"
                )

            if self.max_contracts_per_order > 0 and contracts > self.max_contracts_per_order:
                violations.append(
                    f"{ticker} contract count {contracts} exceeds per-order contract cap "
                    f"{self.max_contracts_per_order}"
                )

            event_groups.setdefault(event_ticker, []).append(pos)
            series_groups.setdefault(series_ticker, []).append(pos)

        for event_ticker, positions in event_groups.items():
            event_exposure = sum(pos.get("total_cost", 0.0) for pos in positions)
            max_allowed_event_exposure = current_bankroll * self.max_event_exposure_pct
            if len(positions) > self.max_positions_per_event:
                tickers = ", ".join(pos.get("ticker", "") for pos in positions)
                violations.append(
                    f"Event {event_ticker} has {len(positions)} active positions "
                    f"(max {self.max_positions_per_event}): {tickers}"
                )
            if event_exposure > (max_allowed_event_exposure + 0.01):
                violations.append(
                    f"Event {event_ticker} exposure ${event_exposure:.2f} exceeds "
                    f"event limit ${max_allowed_event_exposure:.2f}"
                )

        for series_ticker, positions in series_groups.items():
            series_exposure = sum(pos.get("total_cost", 0.0) for pos in positions)
            max_allowed_series_exposure = current_bankroll * self.max_series_exposure_pct
            if len(positions) > self.max_positions_per_series:
                violations.append(
                    f"Series {series_ticker} has {len(positions)} active positions "
                    f"(max {self.max_positions_per_series})"
                )
            if series_exposure > (max_allowed_series_exposure + 0.01):
                violations.append(
                    f"Series {series_ticker} exposure ${series_exposure:.2f} exceeds "
                    f"series limit ${max_allowed_series_exposure:.2f}"
                )

        return len(violations) == 0, violations

    def validate_exposure(self, current_bankroll: float, active_exposure: float, new_trade_cost: float) -> Tuple[bool, str]:
        """
        Validates if adding new_trade_cost violates the maximum exposure ceiling (75% of bankroll).
        """
        projected_exposure = active_exposure + new_trade_cost
        max_allowed_exposure = current_bankroll * self.max_exposure_pct

        if projected_exposure > max_allowed_exposure:
            return (
                False,
                f"Exceeds max exposure: ${projected_exposure:.2f} > ${max_allowed_exposure:.2f} (75% limit)"
            )
        return True, "Approved"

    def calculate_dynamic_stop_price(self, entry_price: float, hours_left: float, total_hours: float = 24.0) -> float:
        """
        Calculates the stop-loss price threshold for a position.
        If 'dynamic', adjusts threshold based on time remaining until settlement:
          - High time left (e.g. 18-24h): Wider buffer (allows normal intraday mean-reversion, e.g. down to 55c).
          - Low time left (e.g. <2h): Tighter buffer (cuts loss rapidly before expiry, e.g. down to 75c).
        Guaranteed to never go below stop_loss_limit_floor (e.g. 40c).
        """
        if not self.enable_stop_loss:
            return 0.0

        if self.stop_loss_type == "static":
            stop_price = entry_price - self.stop_loss_base_drop
        else: # "dynamic"
            # Time factor between 0.0 and 1.0 (with square root damping for natural decay curve)
            time_factor = max(0.0, min(1.0, hours_left / max(1.0, total_hours)))
            drop = self.stop_loss_min_drop + (self.stop_loss_max_drop - self.stop_loss_min_drop) * (time_factor ** 0.5)
            stop_price = entry_price - drop

        # Apply limit floor
        return max(self.stop_loss_limit_floor, round(stop_price, 2))

    def evaluate_stop_loss_condition(
        self,
        entry_price: float,
        current_bid: float,
        current_ask: float,
        bid_depth: int,
        hours_left: float,
        total_hours: float = 24.0
    ) -> Tuple[bool, float, str]:
        """
        Evaluates whether a position breach meets all sanity checks:
        1. Checks if stop loss is enabled
        2. Checks limit floor: avoids panic dumping at 5-10c pennies
        3. Checks spread sanity: avoids exiting when bid is artificially depressed due to wide spread
        4. Checks bid depth: avoids exiting into a single 1-contract phantom bid
        5. Compares current_bid with target dynamic stop price
        """
        if not self.enable_stop_loss:
            return False, 0.0, "Stop loss disabled in configuration."

        target_stop = self.calculate_dynamic_stop_price(entry_price, hours_left, total_hours)

        if current_bid <= 0:
            return False, target_stop, "Zero bid / No liquidity in orderbook."

        # Filter 1: Limit Floor (prevent selling at 5-10 cents)
        if current_bid < self.stop_loss_limit_floor:
            return False, target_stop, (
                f"Bid ${current_bid:.2f} is below limit floor ${self.stop_loss_limit_floor:.2f} "
                f"(refusing to panic-dump at pennies; preserving recovery optionality)"
            )

        # Filter 2: Spread Sanity (detect ghost / illiquid spreads)
        if current_ask > 0:
            spread = current_ask - current_bid
            if spread > self.stop_loss_max_spread:
                return False, target_stop, (
                    f"Spread ${spread:.2f} exceeds max allowable spread (${self.stop_loss_max_spread:.2f}); "
                    f"ignoring temporary orderbook illiquidity"
                )

        # Filter 3: Bid Depth Sanity (ensure real volume exists at bid)
        if bid_depth < self.stop_loss_min_bid_depth:
            return False, target_stop, (
                f"Bid depth ({bid_depth} contracts) < minimum required depth ({self.stop_loss_min_bid_depth}); "
                f"ignoring single-contract flash dip"
            )

        # Filter 4: Trigger comparison
        if current_bid <= target_stop:
            return True, target_stop, f"Bid ${current_bid:.2f} <= dynamic stop threshold ${target_stop:.2f}"

        return False, target_stop, f"Bid ${current_bid:.2f} > dynamic stop threshold ${target_stop:.2f}"

    def check_stop_loss(self, entry_price: float, current_market_price: float) -> bool:
        """
        Returns True if current price has dropped by more than the stop loss threshold.
        (Maintained for legacy/simple checks).
        """
        if current_market_price <= 0:
            return True
        price_drop = entry_price - current_market_price
        return price_drop >= self.stop_loss_drop

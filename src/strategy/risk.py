"""
Risk Management and Capital Allocation Module.
Enforces the 5% bankroll position limit, 75% max portfolio exposure,
strict event/series diversification to avoid multi-strike correlation risk,
and stop-loss logic.
"""

from typing import Tuple, Dict, Any, Optional
from config.settings import (
    MAX_POSITION_SIZE_PERCENT,
    MAX_TOTAL_EXPOSURE_PERCENT,
    MAX_POSITIONS_PER_EVENT,
    MAX_EVENT_EXPOSURE_PERCENT,
    MAX_POSITIONS_PER_SERIES,
    MAX_SERIES_EXPOSURE_PERCENT,
    STOP_LOSS_PRICE_DROP
)

class RiskManager:
    def __init__(
        self,
        max_position_pct: float = MAX_POSITION_SIZE_PERCENT,
        max_exposure_pct: float = MAX_TOTAL_EXPOSURE_PERCENT,
        max_positions_per_event: int = MAX_POSITIONS_PER_EVENT,
        max_event_exposure_pct: float = MAX_EVENT_EXPOSURE_PERCENT,
        max_positions_per_series: int = MAX_POSITIONS_PER_SERIES,
        max_series_exposure_pct: float = MAX_SERIES_EXPOSURE_PERCENT,
        stop_loss_drop: float = STOP_LOSS_PRICE_DROP
    ):
        self.max_position_pct = max_position_pct
        self.max_exposure_pct = max_exposure_pct
        self.max_positions_per_event = max_positions_per_event
        self.max_event_exposure_pct = max_event_exposure_pct
        self.max_positions_per_series = max_positions_per_series
        self.max_series_exposure_pct = max_series_exposure_pct
        self.stop_loss_drop = stop_loss_drop

    def calculate_position_size(self, current_bankroll: float, contract_price: float) -> int:
        """
        Calculates maximum contracts to buy ensuring total cost does not exceed
        5% of total bankroll.
        """
        if current_bankroll <= 0 or contract_price <= 0:
            return 0
        
        max_capital_to_risk = current_bankroll * self.max_position_pct
        # Number of contracts allowed
        contracts = int(max_capital_to_risk // contract_price)
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

    def check_stop_loss(self, entry_price: float, current_market_price: float) -> bool:
        """
        Returns True if current price has dropped by more than the stop loss threshold.
        """
        if current_market_price <= 0:
            return True
        price_drop = entry_price - current_market_price
        return price_drop >= self.stop_loss_drop

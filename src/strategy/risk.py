"""
Risk Management and Capital Allocation Module.
Enforces the 5% bankroll position limit, 75% max portfolio exposure, and stop-loss logic.
"""

from typing import Tuple
from config.settings import (
    MAX_POSITION_SIZE_PERCENT,
    MAX_TOTAL_EXPOSURE_PERCENT,
    STOP_LOSS_PRICE_DROP
)

class RiskManager:
    def __init__(
        self,
        max_position_pct: float = MAX_POSITION_SIZE_PERCENT,
        max_exposure_pct: float = MAX_TOTAL_EXPOSURE_PERCENT,
        stop_loss_drop: float = STOP_LOSS_PRICE_DROP
    ):
        self.max_position_pct = max_position_pct
        self.max_exposure_pct = max_exposure_pct
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

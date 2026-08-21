"""
Kalshi Fee and Expected Value Calculation Module.
Calculates dynamic maker/taker transaction costs and net expected return.
"""

from typing import Dict
from config.settings import KALSHI_FEE_MULTIPLIER, MIN_FEE_PER_CONTRACT

def calculate_kalshi_fee(price: float) -> float:
    """
    Computes Kalshi variable fee per contract:
    Formula: 0.07 * price * (1.0 - price), minimum $0.01.
    """
    if price <= 0.0 or price >= 1.0:
        return MIN_FEE_PER_CONTRACT
    
    fee = KALSHI_FEE_MULTIPLIER * price * (1.0 - price)
    return max(MIN_FEE_PER_CONTRACT, round(fee, 3))

def calculate_contract_economics(price: float) -> Dict[str, float]:
    """
    Given a contract purchase price (e.g., $0.94):
    - gross_profit = $1.00 - price = $0.06
    - fee = calculate_kalshi_fee(price)
    - net_profit = gross_profit - fee
    - roi_percent = (net_profit / price) * 100
    """
    gross_profit = round(1.0 - price, 4)
    fee = calculate_kalshi_fee(price)
    net_profit = round(gross_profit - fee, 4)
    roi_percent = round((net_profit / price) * 100.0, 2) if price > 0 else 0.0

    return {
        "price": price,
        "gross_profit": gross_profit,
        "fee": fee,
        "net_profit": net_profit,
        "roi_percent": roi_percent,
        "is_profitable": net_profit > 0
    }

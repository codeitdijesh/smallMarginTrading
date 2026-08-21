import pytest
from src.strategy.fees import calculate_kalshi_fee, calculate_contract_economics

def test_calculate_kalshi_fee():
    # Min fee floor check: 0.07 * 0.90 * 0.10 = 0.0063 -> clamps to min $0.01
    assert calculate_kalshi_fee(0.90) == 0.01
    assert calculate_kalshi_fee(0.95) == 0.01
    
    # Mid probability fee: 0.07 * 0.50 * 0.50 = 0.0175 -> rounds to 0.018 (> 0.01)
    mid_fee = calculate_kalshi_fee(0.50)
    assert mid_fee == 0.018

def test_contract_economics():
    # Buy contract at $0.92
    econ = calculate_contract_economics(0.92)
    assert econ["gross_profit"] == pytest.approx(0.08, abs=1e-4)
    assert econ["fee"] >= 0.01
    assert econ["net_profit"] > 0
    assert econ["is_profitable"] is True
    assert econ["roi_percent"] > 0

def test_unprofitable_contract():
    # Extremely expensive contract with negligible return
    econ = calculate_contract_economics(0.995)
    # Gross profit is 0.005, fee is 0.01 -> Net is negative
    assert econ["net_profit"] < 0
    assert econ["is_profitable"] is False

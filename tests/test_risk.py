from src.strategy.risk import RiskManager

def test_position_sizing():
    risk = RiskManager(max_position_pct=0.05)
    bankroll = 1000.0
    price = 0.95
    # 5% of 1000 = $50. $50 // 0.95 = 52 contracts ($49.40)
    contracts = risk.calculate_position_size(bankroll, price)
    assert contracts == 52
    assert contracts * price <= 50.0

def test_validate_exposure():
    risk = RiskManager(max_exposure_pct=0.75)
    bankroll = 1000.0
    
    # 700 already exposed + 40 new = 740 <= 750 (Allowed)
    approved, _ = risk.validate_exposure(bankroll, 700.0, 40.0)
    assert approved is True
    
    # 720 already exposed + 50 new = 770 > 750 (Blocked)
    blocked, reason = risk.validate_exposure(bankroll, 720.0, 50.0)
    assert blocked is False
    assert "Exceeds max exposure" in reason

def test_stop_loss():
    risk = RiskManager(stop_loss_drop=0.15)
    entry_price = 0.92
    
    # Drops to 0.85 (drop of 0.07 -> not triggered)
    assert risk.check_stop_loss(entry_price, 0.85) is False
    
    # Drops to 0.75 (drop of 0.17 -> triggered)
    assert risk.check_stop_loss(entry_price, 0.75) is True

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

def test_validate_candidate_trade_prevents_duplicate_ticker():
    risk = RiskManager()
    bankroll = 1000.0
    active_positions = {
        "TICKER-A_yes": {
            "ticker": "TICKER-A",
            "event_ticker": "EVENT-1",
            "total_cost": 49.0
        }
    }
    candidate = {
        "ticker": "TICKER-A",
        "event_ticker": "EVENT-1",
        "side": "no"
    }
    approved, reason = risk.validate_candidate_trade(bankroll, active_positions, candidate, 49.0)
    assert approved is False
    assert "Already holding active position" in reason

def test_validate_candidate_trade_prevents_multi_strike_same_event():
    # Strict 1 bet per event
    risk = RiskManager(max_positions_per_event=1, max_event_exposure_pct=0.05)
    bankroll = 1000.0
    active_positions = {
        "KXHIGHDEN-26AUG21-B88.5_no": {
            "ticker": "KXHIGHDEN-26AUG21-B88.5",
            "event_ticker": "KXHIGHDEN-26AUG21",
            "series_ticker": "KXHIGHDEN",
            "total_cost": 49.0
        }
    }
    # Second strike for the SAME Denver weather event
    candidate = {
        "ticker": "KXHIGHDEN-26AUG21-B90.5",
        "event_ticker": "KXHIGHDEN-26AUG21",
        "series_ticker": "KXHIGHDEN",
        "side": "no"
    }
    approved, reason = risk.validate_candidate_trade(bankroll, active_positions, candidate, 49.0)
    assert approved is False
    assert "already has 1 active position" in reason

def test_validate_candidate_trade_allows_different_events():
    risk = RiskManager(max_positions_per_event=1, max_event_exposure_pct=0.05)
    bankroll = 1000.0
    active_positions = {
        "KXHIGHDEN-26AUG21-B88.5_no": {
            "ticker": "KXHIGHDEN-26AUG21-B88.5",
            "event_ticker": "KXHIGHDEN-26AUG21",
            "series_ticker": "KXHIGHDEN",
            "total_cost": 49.0
        }
    }
    # Distinct NY event -> Allowed
    candidate = {
        "ticker": "KXHIGHNY-26AUG21-B75.5",
        "event_ticker": "KXHIGHNY-26AUG21",
        "series_ticker": "KXHIGHNY",
        "side": "no"
    }
    approved, reason = risk.validate_candidate_trade(bankroll, active_positions, candidate, 49.0)
    assert approved is True
    assert reason == "Approved"

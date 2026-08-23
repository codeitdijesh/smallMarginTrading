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

def test_dynamic_stop_loss_time_decay():
    risk = RiskManager(
        enable_stop_loss=True,
        stop_loss_type="dynamic",
        stop_loss_min_drop=0.15,
        stop_loss_max_drop=0.35,
        stop_loss_limit_floor=0.40
    )
    entry_price = 0.90

    # 24h left -> maximum drop allowance (0.35 drop -> stop at 0.55)
    stop_24h = risk.calculate_dynamic_stop_price(entry_price, hours_left=24.0, total_hours=24.0)
    assert stop_24h == 0.55

    # 0h left (at expiry) -> minimum drop allowance (0.15 drop -> stop at 0.75)
    stop_0h = risk.calculate_dynamic_stop_price(entry_price, hours_left=0.0, total_hours=24.0)
    assert stop_0h == 0.75

    # 6h left -> intermediate drop
    stop_6h = risk.calculate_dynamic_stop_price(entry_price, hours_left=6.0, total_hours=24.0)
    assert 0.55 < stop_6h < 0.75

def test_stop_loss_evaluation_filters():
    risk = RiskManager(
        enable_stop_loss=True,
        stop_loss_type="dynamic",
        stop_loss_min_drop=0.15,
        stop_loss_max_drop=0.35,
        stop_loss_limit_floor=0.40,
        stop_loss_max_spread=0.15,
        stop_loss_min_bid_depth=5
    )
    entry_price = 0.90

    # 1. Valid breach: 24h left (stop is 0.55), bid is 0.50, ask is 0.58 (spread 0.08 <= 0.15), depth 10 >= 5
    should_exit, target_stop, reason = risk.evaluate_stop_loss_condition(
        entry_price=entry_price,
        current_bid=0.50,
        current_ask=0.58,
        bid_depth=10,
        hours_left=24.0
    )
    assert should_exit is True
    assert target_stop == 0.55

    # 2. Limit Floor filter: Bid dropped to 0.20 (< 0.40 floor) -> DO NOT panic dump
    should_exit, target_stop, reason = risk.evaluate_stop_loss_condition(
        entry_price=entry_price,
        current_bid=0.20,
        current_ask=0.25,
        bid_depth=10,
        hours_left=24.0
    )
    assert should_exit is False
    assert "below limit floor" in reason

    # 3. Spread filter: Bid is 0.50, but Ask is 0.85 (spread 0.35 > 0.15) -> Illiquid spread, ignore
    should_exit, target_stop, reason = risk.evaluate_stop_loss_condition(
        entry_price=entry_price,
        current_bid=0.50,
        current_ask=0.85,
        bid_depth=10,
        hours_left=24.0
    )
    assert should_exit is False
    assert "exceeds max allowable spread" in reason

    # 4. Bid Depth filter: Bid is 0.50, but depth is only 1 contract (< 5 min) -> Ghost bid, ignore
    should_exit, target_stop, reason = risk.evaluate_stop_loss_condition(
        entry_price=entry_price,
        current_bid=0.50,
        current_ask=0.56,
        bid_depth=1,
        hours_left=24.0
    )
    assert should_exit is False
    assert "Bid depth" in reason and "minimum required depth" in reason


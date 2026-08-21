from datetime import datetime, timezone, timedelta
from src.strategy.scanner import MarketScanner

def test_evaluate_market_yes_opportunity():
    scanner = MarketScanner(min_prob=0.90, max_prob=0.98, max_hours=24.0, max_spread=0.08, min_oi=50.0)
    now = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
    
    mock_market = {
        "ticker": "TEST-YES-OPP",
        "title": "Will Temperature Exceed 80F?",
        "close_time": (now + timedelta(hours=6)).isoformat(),
        "open_interest": 1000,
        "volume_24h": 500,
        "yes_bid_dollars": "0.92",
        "yes_ask_dollars": "0.95",
        "no_bid_dollars": "0.05",
        "no_ask_dollars": "0.08"
    }
    
    results = scanner.evaluate_market(mock_market, now=now)
    assert len(results) == 1
    assert results[0]["side"] == "yes"
    assert results[0]["ask_price"] == 0.95
    assert results[0]["hours_left"] == 6.0
    assert results[0]["net_profit"] > 0

def test_evaluate_market_no_opportunity():
    scanner = MarketScanner(min_prob=0.90, max_prob=0.98, max_hours=24.0, max_spread=0.08, min_oi=50.0)
    now = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
    
    mock_market = {
        "ticker": "TEST-NO-OPP",
        "title": "Will Temperature Exceed 110F?",
        "close_time": (now + timedelta(hours=10)).isoformat(),
        "open_interest": 200,
        "volume_24h": 100,
        "yes_bid_dollars": "0.04",
        "yes_ask_dollars": "0.07",
        "no_bid_dollars": "0.93",
        "no_ask_dollars": "0.96"
    }
    
    results = scanner.evaluate_market(mock_market, now=now)
    assert len(results) == 1
    assert results[0]["side"] == "no"
    assert results[0]["ask_price"] == 0.96

def test_evaluate_market_filters_out_long_dated():
    scanner = MarketScanner(max_hours=24.0)
    now = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
    
    # 48 hours away
    mock_market = {
        "ticker": "TEST-FAR",
        "title": "Far Expiry Event",
        "close_time": (now + timedelta(hours=48)).isoformat(),
        "open_interest": 1000,
        "yes_bid_dollars": "0.92",
        "yes_ask_dollars": "0.94"
    }
    results = scanner.evaluate_market(mock_market, now=now)
    assert len(results) == 0

def test_evaluate_market_filters_wide_spread():
    scanner = MarketScanner(max_spread=0.08)
    now = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
    
    # Spread is 0.15 (0.80 to 0.95) -> Too wide
    mock_market = {
        "ticker": "TEST-WIDE-SPREAD",
        "title": "Wide Spread Event",
        "close_time": (now + timedelta(hours=5)).isoformat(),
        "open_interest": 1000,
        "yes_bid_dollars": "0.80",
        "yes_ask_dollars": "0.95"
    }
    results = scanner.evaluate_market(mock_market, now=now)
    assert len(results) == 0

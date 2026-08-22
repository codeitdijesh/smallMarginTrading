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

def test_event_deduplication():
    scanner = MarketScanner(min_prob=0.90, max_prob=0.98, max_hours=24.0, max_spread=0.08, min_oi=50.0)
    now = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)

    # 3 strikes of the same event (KXHIGHDEN-26AUG21)
    market_1 = {
        "ticker": "KXHIGHDEN-26AUG21-B88.5",
        "event_ticker": "KXHIGHDEN-26AUG21",
        "series_ticker": "KXHIGHDEN",
        "title": "Denver High 88-89",
        "close_time": (now + timedelta(hours=10)).isoformat(),
        "open_interest": 1000,
        "no_bid_dollars": "0.93",
        "no_ask_dollars": "0.95"  # ROI lower
    }
    market_2 = {
        "ticker": "KXHIGHDEN-26AUG21-B90.5",
        "event_ticker": "KXHIGHDEN-26AUG21",
        "series_ticker": "KXHIGHDEN",
        "title": "Denver High 90-91",
        "close_time": (now + timedelta(hours=10)).isoformat(),
        "open_interest": 2000,
        "no_bid_dollars": "0.90",
        "no_ask_dollars": "0.91"  # ROI higher (+8.79%)
    }
    market_3 = {
        "ticker": "KXHIGHNY-26AUG21-B75.5",
        "event_ticker": "KXHIGHNY-26AUG21",
        "series_ticker": "KXHIGHNY",
        "title": "NY High 75-76",
        "close_time": (now + timedelta(hours=12)).isoformat(),
        "open_interest": 500,
        "no_bid_dollars": "0.92",
        "no_ask_dollars": "0.94"
    }

    # Mock fetch_open_markets
    scanner.fetch_open_markets = lambda max_pages=20: [market_1, market_2, market_3]

    # Without event dedup -> 3 opportunities
    all_opps = scanner.scan_all_opportunities(include_targeted_series=False, dedup_by_event=False, now=now)
    assert len(all_opps) == 3

    # With event dedup -> only 2 opportunities (1 for Denver, 1 for NY)
    deduped_opps = scanner.scan_all_opportunities(include_targeted_series=False, dedup_by_event=True, now=now)
    assert len(deduped_opps) == 2
    denver_opp = next(o for o in deduped_opps if o["event_ticker"] == "KXHIGHDEN-26AUG21")
    # Best ROI strike should be selected (B90.5 @ $0.91)
    assert denver_opp["ticker"] == "KXHIGHDEN-26AUG21-B90.5"
    assert denver_opp["ask_price"] == 0.91

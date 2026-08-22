import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from src.bot.engine import TradingBot
from src.strategy.scanner import MarketScanner
from src.strategy.risk import RiskManager

def test_bot_cycle_prevents_multiple_bets_on_same_event():
    now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
    
    # 5 different strikes for the same event (e.g. Phoenix High temperature)
    markets = [
        {
            "ticker": f"KXHIGHTPHX-26AUG22-B{strike}",
            "event_ticker": "KXHIGHTPHX-26AUG22",
            "series_ticker": "KXHIGHTPHX",
            "title": f"Phoenix High {strike}",
            "close_time": (now + timedelta(hours=6)).isoformat(),
            "open_interest": 1000 + i * 100,
            "no_bid_dollars": "0.92",
            "no_ask_dollars": f"0.9{4 - i if i < 3 else 5}"
        }
        for i, strike in enumerate(["106.5", "108.5", "110.5", "112.5", "114.5"])
    ]
    # Another independent event (LAX)
    markets.append({
        "ticker": "KXHIGHLAX-26AUG22-B78.5",
        "event_ticker": "KXHIGHLAX-26AUG22",
        "series_ticker": "KXHIGHLAX",
        "title": "LAX High 78-79",
        "close_time": (now + timedelta(hours=8)).isoformat(),
        "open_interest": 2000,
        "no_bid_dollars": "0.93",
        "no_ask_dollars": "0.95"
    })

    scanner = MarketScanner(min_prob=0.90, max_prob=0.98, max_hours=24.0, max_spread=0.08, min_oi=50.0)
    scanner.fetch_open_markets = lambda max_pages=20: markets

    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "paper_test_state.json"
        risk_manager = RiskManager(max_positions_per_event=1, max_event_exposure_pct=0.05)
        
        bot = TradingBot(
            mode="paper",
            bankroll=1000.0,
            scanner=scanner,
            risk_manager=risk_manager,
            state_file=state_file
        )

        # Override now in scan_all_opportunities
        original_scan = bot.scanner.scan_all_opportunities
        bot.scanner.scan_all_opportunities = lambda **kwargs: original_scan(include_targeted_series=False, now=now, **kwargs)

        entered = bot.execute_scan_cycle()

        # Even though 5 Phoenix strikes were available, exactly 1 Phoenix bet and 1 LAX bet placed!
        assert len(entered) == 2
        event_tickers = [pos["event_ticker"] for pos in entered]
        assert event_tickers == ["KXHIGHTPHX-26AUG22", "KXHIGHLAX-26AUG22"]
        assert len(bot.active_positions) == 2

        # Run cycle again: should place 0 new trades since both events are already active
        second_cycle = bot.execute_scan_cycle()
        assert len(second_cycle) == 0

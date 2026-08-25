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

def test_bot_active_monitoring_stop_loss_persistence():
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "test_state.json"
        risk_manager = RiskManager(
            enable_stop_loss=True,
            stop_loss_type="dynamic",
            stop_loss_min_drop=0.15,
            stop_loss_max_drop=0.35,
            stop_loss_limit_floor=0.40,
            stop_loss_persistence_ticks=2
        )
        bot = TradingBot(
            mode="paper",
            bankroll=1000.0,
            risk_manager=risk_manager,
            state_file=state_file
        )

        pos_key = "KXTEST-26AUG22_yes"
        bot.active_positions[pos_key] = {
            "ticker": "KXTEST-26AUG22",
            "event_ticker": "KXTEST",
            "side": "yes",
            "entry_price": 0.90,
            "contracts": 50,
            "total_cost": 45.0,
            "est_fee": 0.50,
            "est_net_profit": 4.50,
            "hours_left": 24.0,
            "initial_hours": 24.0,
            "breach_count": 0,
            "target_stop": 0.55
        }

        # Mock quote: bid is 0.50 (< 0.55 stop), spread is 0.06, depth is 10
        bot.client.get_market_quote = lambda ticker, side: {
            "ticker": ticker,
            "side": side,
            "bid_price": 0.50,
            "ask_price": 0.56,
            "spread": 0.06,
            "bid_depth": 10,
            "status": "open",
            "result": "",
            "close_time": None
        }

        # Tick 1: First breach -> breach_count becomes 1, no exit yet (whipsaw filter)
        stats1 = bot.monitor_active_positions()
        assert stats1["warnings"] == 1
        assert stats1["exits"] == 0
        assert pos_key in bot.active_positions
        assert bot.active_positions[pos_key]["breach_count"] == 1

        # Tick 2: Second consecutive breach -> triggers stop loss!
        stats2 = bot.monitor_active_positions()
        assert stats2["exits"] == 1
        assert pos_key not in bot.active_positions
        assert len(bot.closed_positions) == 1
        closed = bot.closed_positions[0]
        assert closed["outcome"] == "STOP_LOSS"
        assert closed["exit_price"] == 0.50

def test_bot_active_monitoring_recovers_from_noise():
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "test_state.json"
        risk_manager = RiskManager(
            enable_stop_loss=True,
            stop_loss_persistence_ticks=2
        )
        bot = TradingBot(
            mode="paper",
            bankroll=1000.0,
            risk_manager=risk_manager,
            state_file=state_file
        )

        pos_key = "KXTEST-26AUG22_yes"
        bot.active_positions[pos_key] = {
            "ticker": "KXTEST-26AUG22",
            "event_ticker": "KXTEST",
            "side": "yes",
            "entry_price": 0.90,
            "contracts": 50,
            "total_cost": 45.0,
            "est_fee": 0.50,
            "est_net_profit": 4.50,
            "hours_left": 24.0,
            "initial_hours": 24.0,
            "breach_count": 0,
            "target_stop": 0.55
        }

        # Tick 1: momentary dip to 0.50
        bot.client.get_market_quote = lambda ticker, side: {
            "ticker": ticker,
            "side": side,
            "bid_price": 0.50,
            "ask_price": 0.56,
            "spread": 0.06,
            "bid_depth": 10,
            "status": "open",
            "result": "",
            "close_time": None
        }
        bot.monitor_active_positions()
        assert bot.active_positions[pos_key]["breach_count"] == 1

        # Tick 2: price recovers back to 0.88 -> breach_count resets to 0!
        bot.client.get_market_quote = lambda ticker, side: {
            "ticker": ticker,
            "side": side,
            "bid_price": 0.88,
            "ask_price": 0.92,
            "spread": 0.04,
            "bid_depth": 20,
            "status": "open",
            "result": "",
            "close_time": None
        }
        stats2 = bot.monitor_active_positions()
        assert stats2["exits"] == 0
        assert pos_key in bot.active_positions
        assert bot.active_positions[pos_key]["breach_count"] == 0

def test_bot_startup_reconciliation_settled():
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "test_state.json"
        
        # Write state file containing an unresolved position
        initial_state = {
            "mode": "paper",
            "bankroll": 1000.0,
            "initial_bankroll": 1000.0,
            "active_positions": {
                "KXWIN-26AUG22_yes": {
                    "ticker": "KXWIN-26AUG22",
                    "side": "yes",
                    "entry_price": 0.90,
                    "contracts": 50,
                    "total_cost": 45.0,
                    "est_fee": 0.50
                }
            },
            "closed_positions": []
        }
        import json
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(initial_state, f)

        bot = TradingBot(
            mode="paper",
            bankroll=1000.0,
            state_file=state_file
        )

        # Mock quote showing the market finalized as "yes" while the bot was booting up
        bot.client.get_market_quote = lambda ticker, side: {
            "ticker": ticker,
            "side": side,
            "bid_price": 1.0,
            "ask_price": 1.0,
            "spread": 0.0,
            "bid_depth": 0,
            "status": "finalized",
            "result": "yes",
            "close_time": None
        }

        bot.reconcile_positions_on_startup()
        assert len(bot.active_positions) == 0
        assert len(bot.closed_positions) == 1
        assert bot.closed_positions[0]["outcome"] == "WIN"

def test_live_balance_refresh_and_equity_accuracy():
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "live_test_state.json"
        
        bot = TradingBot(
            mode="live",
            bankroll=500.0,
            state_file=state_file
        )

        # Mock authenticated client methods
        bot.client.key_id = "test_key"
        bot.client.private_key = object()
        bot.client.get_balance = lambda: {
            "balance_cents": 215053,
            "balance_dollars": 2150.53,
            "available_cash": 2150.53,
            "portfolio_value": 0.0,
            "total_equity": 2150.53
        }
        bot.client.get_positions = lambda status="open": {
            "market_positions": []
        }

        # Add a mock stale position in local state
        bot.active_positions["KXSTALE-26AUG22_yes"] = {
            "ticker": "KXSTALE-26AUG22",
            "side": "yes",
            "entry_price": 0.90,
            "contracts": 50,
            "total_cost": 45.0,
            "mode": "live"
        }

        # Refresh balance and sync positions
        bot.refresh_live_balance()
        bot.sync_live_positions()

        # Stale position should have been reconciled and removed from active
        assert "KXSTALE-26AUG22_yes" not in bot.active_positions
        # Equity should match the exact Kalshi live balance without ghost positions
        assert bot.total_equity == 2150.53
        assert bot.available_cash == 2150.53



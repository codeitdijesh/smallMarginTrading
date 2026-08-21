"""
Market Scanner Module.
Scans Kalshi markets for high-probability (>90%), short-dated (<24h) intraday opportunities
with tight spreads and net positive expected value.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import requests

from config.settings import (
    API_BASE_URL,
    MIN_PROBABILITY,
    MAX_PROBABILITY,
    MAX_HOURS_TO_EXPIRY,
    MAX_BID_ASK_SPREAD,
    MIN_OPEN_INTEREST,
    DAILY_SERIES
)
from src.strategy.fees import calculate_contract_economics
from src.utils.logger import logger


class MarketScanner:
    def __init__(
        self,
        base_url: str = API_BASE_URL,
        min_prob: float = MIN_PROBABILITY,
        max_prob: float = MAX_PROBABILITY,
        max_hours: float = MAX_HOURS_TO_EXPIRY,
        max_spread: float = MAX_BID_ASK_SPREAD,
        min_oi: float = MIN_OPEN_INTEREST
    ):
        self.base_url = base_url.rstrip("/")
        self.min_prob = min_prob
        self.max_prob = max_prob
        self.max_hours = max_hours
        self.max_spread = max_spread
        self.min_oi = min_oi

    def fetch_open_markets(self, max_pages: int = 15) -> List[Dict[str, Any]]:
        """Fetches active open markets with pagination."""
        markets = []
        cursor = ""
        for _ in range(max_pages):
            url = f"{self.base_url}/markets?limit=200&status=open"
            if cursor:
                url += f"&cursor={cursor}"
            try:
                resp = requests.get(url, timeout=12)
                if resp.status_code != 200:
                    logger.warning(f"Failed to fetch markets: HTTP {resp.status_code}")
                    break
                data = resp.json()
                batch = data.get("markets", [])
                markets.extend(batch)
                cursor = data.get("cursor")
                if not cursor or not batch:
                    break
            except Exception as e:
                logger.error(f"Error querying {url}: {e}")
                break
        return markets

    def fetch_series_markets(self, series_ticker: str) -> List[Dict[str, Any]]:
        """Fetches all open markets for a specific series ticker."""
        url = f"{self.base_url}/markets?series_ticker={series_ticker}&status=open"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("markets", [])
        except Exception as e:
            logger.debug(f"Error fetching series {series_ticker}: {e}")
        return []

    def evaluate_market(self, market: Dict[str, Any], now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Evaluates a single market dictionary against strategy criteria.
        Returns candidate opportunities (YES or NO side) if valid.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        ticker = market.get("ticker", "")
        if not ticker or "CROSSCATEGORY" in ticker:
            return []

        close_time_str = market.get("close_time") or market.get("expiration_time")
        if not close_time_str:
            return []

        try:
            close_dt = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
            hours_left = (close_dt - now).total_seconds() / 3600.0
        except Exception:
            return []

        # Must resolve within window (0 < hours <= max_hours)
        if hours_left <= 0 or hours_left > self.max_hours:
            return []

        oi = float(market.get("open_interest_fp") or market.get("open_interest") or 0)
        vol = float(market.get("volume_24h_fp") or market.get("volume_24h") or 0)

        if oi < self.min_oi:
            return []

        yes_bid = float(market.get("yes_bid_dollars") or 0)
        yes_ask = float(market.get("yes_ask_dollars") or 0)
        no_bid = float(market.get("no_bid_dollars") or 0)
        no_ask = float(market.get("no_ask_dollars") or 0)

        title = market.get("title", ticker)
        results = []

        # Evaluate YES side
        if self.min_prob <= yes_ask <= self.max_prob and (yes_ask - yes_bid) <= self.max_spread:
            econ = calculate_contract_economics(yes_ask)
            if econ["is_profitable"]:
                results.append({
                    "ticker": ticker,
                    "title": title,
                    "side": "yes",
                    "action": "BUY YES",
                    "ask_price": yes_ask,
                    "bid_price": yes_bid,
                    "spread": round(yes_ask - yes_bid, 3),
                    "implied_prob": f"{yes_ask * 100:.1f}%",
                    "net_profit": econ["net_profit"],
                    "gross_profit": econ["gross_profit"],
                    "fee": econ["fee"],
                    "roi_percent": econ["roi_percent"],
                    "oi": oi,
                    "vol_24h": vol,
                    "hours_left": round(hours_left, 1),
                    "close_time": close_dt.strftime("%H:%M UTC (%Y-%m-%d)"),
                    "close_dt": close_dt
                })

        # Evaluate NO side
        if self.min_prob <= no_ask <= self.max_prob and (no_ask - no_bid) <= self.max_spread:
            econ = calculate_contract_economics(no_ask)
            if econ["is_profitable"]:
                results.append({
                    "ticker": ticker,
                    "title": title,
                    "side": "no",
                    "action": "BUY NO",
                    "ask_price": no_ask,
                    "bid_price": no_bid,
                    "spread": round(no_ask - no_bid, 3),
                    "implied_prob": f"{no_ask * 100:.1f}%",
                    "net_profit": econ["net_profit"],
                    "gross_profit": econ["gross_profit"],
                    "fee": econ["fee"],
                    "roi_percent": econ["roi_percent"],
                    "oi": oi,
                    "vol_24h": vol,
                    "hours_left": round(hours_left, 1),
                    "close_time": close_dt.strftime("%H:%M UTC (%Y-%m-%d)"),
                    "close_dt": close_dt
                })

        return results

    def scan_all_opportunities(self, max_pages: int = 15, include_targeted_series: bool = True) -> List[Dict[str, Any]]:
        """Scans all open markets via pagination and optionally queries high-volume daily series."""
        logger.info(f"Scanning open markets from {self.base_url}...")
        markets = self.fetch_open_markets(max_pages=max_pages)
        now = datetime.now(timezone.utc)
        candidates = []
        seen_keys = set()

        for m in markets:
            for opp in self.evaluate_market(m, now):
                key = (opp["ticker"], opp["side"])
                if key not in seen_keys:
                    seen_keys.add(key)
                    candidates.append(opp)

        if include_targeted_series:
            logger.info(f"Scanning {len(DAILY_SERIES)} high-volume targeted daily series...")
            for s in DAILY_SERIES:
                for m in self.fetch_series_markets(s):
                    for opp in self.evaluate_market(m, now):
                        key = (opp["ticker"], opp["side"])
                        if key not in seen_keys:
                            seen_keys.add(key)
                            candidates.append(opp)

        # Sort primarily by time to expiry (fastest turnover), secondarily by open interest
        candidates.sort(key=lambda x: (x["hours_left"], -x["oi"]))
        logger.info(f"Scan complete: {len(candidates)} high-probability intraday opportunities found.")
        return candidates

    def scan_targeted_series(self, series_list: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Scans specific high-turnover daily series (Weather, Crypto, Sports, Indices)."""
        series = series_list or DAILY_SERIES
        logger.info(f"Scanning {len(series)} targeted daily series...")
        now = datetime.now(timezone.utc)
        candidates = []
        seen_keys = set()

        for s in series:
            markets = self.fetch_series_markets(s)
            for m in markets:
                for opp in self.evaluate_market(m, now):
                    key = (opp["ticker"], opp["side"])
                    if key not in seen_keys:
                        seen_keys.add(key)
                        candidates.append(opp)

        candidates.sort(key=lambda x: (x["hours_left"], -x["oi"]))
        return candidates

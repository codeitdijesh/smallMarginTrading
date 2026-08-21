"""
Kalshi API Client.
Wrapper for Kalshi v2 REST API supporting both public market queries
and authenticated trading actions (Demo & Prod) using RSA-PSS signing.
"""

import base64
import time
import uuid
from urllib.parse import urlparse
from typing import Dict, Any, Optional
from pathlib import Path
import requests

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

from config.settings import (
    API_BASE_URL,
    KALSHI_API_KEY_ID,
    KALSHI_PRIVATE_KEY,
    KALSHI_PRIVATE_KEY_PATH
)
from src.utils.logger import logger

class KalshiClient:
    def __init__(
        self,
        base_url: str = API_BASE_URL,
        key_id: Optional[str] = KALSHI_API_KEY_ID,
        private_key_pem: Optional[str] = KALSHI_PRIVATE_KEY,
        private_key_path: Optional[str] = KALSHI_PRIVATE_KEY_PATH
    ):
        self.base_url = base_url.rstrip("/")
        self.key_id = key_id.strip() if key_id else None
        self.private_key = None
        self.session = requests.Session()

        self._load_private_key(private_key_pem, private_key_path)

    def _load_private_key(self, pem_str: Optional[str], path_str: Optional[str]):
        """Loads RSA private key from PEM string or file path."""
        try:
            # 1. Try from inline PEM string
            if pem_str and "-----BEGIN" in pem_str:
                self.private_key = serialization.load_pem_private_key(
                    pem_str.encode("utf-8"),
                    password=None,
                    backend=default_backend()
                )
                logger.info("Loaded Kalshi RSA private key from environment variable.")
                return

            # 2. Try from file path
            if path_str:
                key_path = Path(path_str)
                if key_path.exists():
                    with open(key_path, "rb") as f:
                        self.private_key = serialization.load_pem_private_key(
                            f.read(),
                            password=None,
                            backend=default_backend()
                        )
                    logger.info(f"Loaded Kalshi RSA private key from file: {key_path}")
                    return

            # 3. Check default locations (e.g. kalshi.pem in base dir)
            default_pem = Path("kalshi.pem")
            if default_pem.exists():
                with open(default_pem, "rb") as f:
                    self.private_key = serialization.load_pem_private_key(
                        f.read(),
                        password=None,
                        backend=default_backend()
                    )
                logger.info(f"Loaded Kalshi RSA private key from default: {default_pem}")
                return

        except Exception as e:
            logger.error(f"Error loading Kalshi private key: {e}")

    @property
    def is_authenticated(self) -> bool:
        """Returns True if API Key ID and RSA private key are loaded."""
        return bool(self.key_id and self.private_key)

    def _get_auth_headers(self, method: str, full_url: str) -> Dict[str, str]:
        """
        Generates Kalshi API v2 RSA-PSS SHA256 authentication headers.
        Headers:
          KALSHI-ACCESS-KEY: key_id
          KALSHI-ACCESS-SIGNATURE: base64(RSA_PSS_SHA256(timestamp + method + path))
          KALSHI-ACCESS-TIMESTAMP: timestamp in milliseconds
        """
        if not self.is_authenticated:
            return {}

        now_ms = int(time.time() * 1000)
        timestamp_str = str(now_ms)
        path = urlparse(full_url).path

        msg_string = timestamp_str + method.upper() + path
        signature = self.private_key.sign(
            msg_string.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH
            ),
            hashes.SHA256()
        )
        signature_b64 = base64.b64encode(signature).decode("utf-8")

        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": signature_b64,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_str,
            "Content-Type": "application/json"
        }

    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, json_data: Optional[Dict] = None, auth_required: bool = False) -> Optional[requests.Response]:
        """Performs HTTP request with optional RSA authentication."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {}
        if auth_required or self.is_authenticated:
            headers.update(self._get_auth_headers(method, url))

        try:
            resp = self.session.request(method, url, params=params, json=json_data, headers=headers, timeout=12)
            return resp
        except Exception as e:
            logger.error(f"HTTP request error for {method} {url}: {e}")
            return None

    # Public Market Queries
    def get_market(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Retrieves market details for a single ticker."""
        resp = self._request("GET", f"markets/{ticker}")
        if resp and resp.status_code == 200:
            return resp.json().get("market")
        return None

    def get_orderbook(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Retrieves orderbook depth for a ticker."""
        resp = self._request("GET", f"markets/{ticker}/orderbook")
        if resp and resp.status_code == 200:
            return resp.json().get("orderbook")
        return None

    # Authenticated Portfolio & Order Management
    def get_balance(self) -> Optional[Dict[str, Any]]:
        """Retrieves account balance and available cash."""
        resp = self._request("GET", "portfolio/balance", auth_required=True)
        if resp and resp.status_code == 200:
            data = resp.json()
            balance_cents = data.get("balance", 0)
            return {
                "balance_cents": balance_cents,
                "balance_dollars": round(balance_cents / 100.0, 2),
                "raw": data
            }
        elif resp:
            logger.error(f"Failed to fetch balance ({resp.status_code}): {resp.text}")
        return None

    def get_positions(self, status: str = "open") -> Optional[Dict[str, Any]]:
        """Retrieves open portfolio positions."""
        resp = self._request("GET", f"portfolio/positions?status={status}", auth_required=True)
        if resp and resp.status_code == 200:
            return resp.json()
        return None

    def get_orders(self, status: str = "resting") -> Optional[Dict[str, Any]]:
        """Retrieves resting orders."""
        resp = self._request("GET", f"portfolio/orders?status={status}", auth_required=True)
        if resp and resp.status_code == 200:
            return resp.json()
        return None

    def cancel_order(self, order_id: str) -> bool:
        """Cancels an existing resting order."""
        resp = self._request("DELETE", f"portfolio/orders/{order_id}", auth_required=True)
        if resp and resp.status_code in (200, 204):
            logger.info(f"Successfully cancelled order {order_id}")
            return True
        return False

    def place_limit_order(
        self,
        ticker: str,
        action: str, # "buy" or "sell"
        side: str,   # "yes" or "no"
        count: int,
        price_dollars: float,
        client_order_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Places a strict LIMIT order on Kalshi using the V2 events/orders endpoint.
        Single-book model:
          - Buy YES at $P -> side="bid", price=P
          - Buy NO at $P (where P is implied NO win prob) -> side="ask", price=(1.0 - P)
        """
        if not self.is_authenticated:
            logger.error("Cannot place order: Client is not authenticated with RSA keypair.")
            return None

        side_lower = side.lower()
        # Single-book side and pricing
        if side_lower == "yes":
            api_side = "bid" if action.lower() == "buy" else "ask"
            api_price = price_dollars
        else: # NO side
            api_side = "ask" if action.lower() == "buy" else "bid"
            api_price = round(1.0 - price_dollars, 4)

        payload = {
            "ticker": ticker,
            "client_order_id": client_order_id or str(uuid.uuid4()),
            "side": api_side,
            "count": f"{float(count):.2f}",
            "price": f"{api_price:.4f}",
            "time_in_force": "good_till_canceled",
            "self_trade_prevention_type": "taker_at_cross"
        }

        logger.info(f"Placing V2 LIMIT order: {action.upper()} {count}x {ticker} ({side_lower.upper()}) @ ${price_dollars:.2f} [API side: {api_side} @ ${api_price:.4f}]")
        resp = self._request("POST", "portfolio/events/orders", json_data=payload, auth_required=True)

        if resp and resp.status_code in (200, 201):
            order = resp.json()
            order_id = order.get("order_id", payload["client_order_id"])
            logger.info(f"Order successfully placed and confirmed! Order ID: {order_id}")
            return order
        elif resp:
            logger.error(f"Order placement rejected (HTTP {resp.status_code}): {resp.text}")
        return None

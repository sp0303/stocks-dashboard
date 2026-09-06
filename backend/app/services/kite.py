"""Zerodha Kite API integration — trades, holdings, cash balance, orders.

Kite uses session-based auth. Supports two methods:
1. Token-based auth: User manually logs in via browser, provides access_token
2. Programmatic auth: Automated login with credentials (requires solving CAPTCHA)

For best experience: Use token-based auth to avoid CAPTCHA.
"""
from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse, parse_qs

log = logging.getLogger("kite")


def authenticate(creds: dict) -> tuple[str, dict] | None:
    """Authenticate with Kite programmatically using PIN (4-digit Kite security PIN).
    Automates form submission to get request_token, then exchanges for access_token.
    creds: {api_key, api_secret, user_id, password, pin}
    """
    try:
        import requests
        import json as json_lib
        from kiteconnect import KiteConnect

        api_key = creds.get("api_key", "")
        api_secret = creds.get("api_secret", "")
        user_id = creds.get("user_id", "")
        password = creds.get("password", "")
        totp_secret = creds.get("totp_secret", "")

        if not all([api_key, api_secret, user_id, password, totp_secret]):
            log.warning("Kite auth: missing credentials")
            return None

        # Initialize session
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })

        # Step 1: Submit credentials (user_id + password)
        try:
            login_data = {
                "user_id": user_id,
                "password": password
            }
            r = session.post(
                "https://kite.zerodha.com/api/login",
                data=login_data,
                timeout=10
            )
            log.info(f"Login submission status: {r.status_code}")

            login_response = r.json()
            log.info(f"Login response: {login_response.get('status')}")

            if login_response.get("status") != "success":
                log.error(f"Login failed: {login_response.get('message')}")
                return None

            request_id = login_response.get("data", {}).get("request_id")
            if not request_id:
                log.error("No request_id in login response")
                return None

            log.info(f"Login successful. request_id: {request_id}")

        except Exception as e:
            log.error(f"Login submission error: {e}")
            return None

        # Step 2: Submit 2FA (TOTP)
        try:
            # Generate TOTP code using pyotp
            try:
                import pyotp
                if totp_secret:
                    totp = pyotp.TOTP(totp_secret)
                    twofa_value = totp.now()
                    log.info(f"Generated TOTP code: {twofa_value}")
                else:
                    log.error("No TOTP secret provided")
                    return None
            except ImportError:
                log.error("pyotp not installed: pip install pyotp")
                return None
            except Exception as e:
                log.error(f"TOTP generation error: {e}")
                return None

            twofa_data = {
                "user_id": user_id,
                "request_id": request_id,
                "twofa_value": twofa_value
            }
            r = session.post(
                "https://kite.zerodha.com/api/twofa",
                data=twofa_data,
                timeout=10
            )
            log.info(f"2FA submission status: {r.status_code}")

            twofa_response = r.json()
            log.info(f"2FA response: {twofa_response.get('status')}")

            if twofa_response.get("status") != "success":
                log.error(f"2FA failed: {twofa_response.get('message')}")
                return None

            request_token = twofa_response.get("data", {}).get("request_token")
            if not request_token:
                log.error("No request_token in 2FA response")
                return None

            log.info(f"2FA successful. request_token: {request_token[:20]}...")

        except Exception as e:
            log.error(f"2FA submission error: {e}")
            return None

        # Step 3: Exchange request_token for access_token
        try:
            kite = KiteConnect(api_key=api_key)
            response = kite.generate_session(request_token, api_secret)

            if response and isinstance(response, dict) and response.get("status") == "success":
                access_token = response.get("data", {}).get("access_token")
                if access_token:
                    kite.access_token = access_token
                    user = kite.profile()
                    log.info(f"Kite authenticated for user {user.get('user_id')}")
                    return access_token, user

            log.error(f"Kite session generation failed: {response}")
            return None

        except Exception as exc:
            log.error(f"Kite generate_session error: {exc}")
            return None

    except ImportError as e:
        log.error(f"Missing library: {e}. Install: pip install kiteconnect requests")
        return None
    except Exception as exc:
        log.error(f"Kite auth error: {exc}")
        return None


def validate_access_token(access_token: str, api_key: str) -> dict | None:
    """Validate an access token by fetching user profile.

    This is the token-based auth approach: User manually logs in via browser,
    copies access_token, and provides it here. No CAPTCHA needed.

    Returns user profile if token is valid, None otherwise.
    """
    try:
        from kiteconnect import KiteConnect

        if not access_token or not api_key:
            log.warning("validate_access_token: missing token or api_key")
            return None

        kite = KiteConnect(api_key=api_key)
        kite.access_token = access_token

        # Try to fetch user profile - will fail if token is invalid/expired
        profile = kite.user_profile()

        if not profile:
            log.error("validate_access_token: no profile returned")
            return None

        # Extract relevant fields
        user_data = profile.get("user", {})
        result = {
            "user_name": user_data.get("user_name", ""),
            "user_id": user_data.get("user_id", ""),
            "email": user_data.get("email", ""),
            "phone": user_data.get("phone", ""),
            "broker": user_data.get("broker", ""),
        }

        # Get account details
        account_data = profile.get("data", {})
        result.update({
            "account_type": account_data.get("account_type", ""),
            "exchanges": account_data.get("exchanges", []),
            "products": account_data.get("products", []),
        })

        log.info(f"validate_access_token: SUCCESS for {result.get('user_name')}")
        return result

    except Exception as e:
        log.error(f"validate_access_token error: {e}")
        return None


def trades(access_token: str, api_key: str) -> list[dict] | None:
    """Fetch all executed trades from Kite account."""
    try:
        from kiteconnect import KiteConnect

        kite = KiteConnect(api_key=api_key)
        kite.access_token = access_token

        # Get all orders (includes executed trades)
        orders = kite.orders()
        if not orders:
            return []

        trades_list = []
        for order in orders:
            # Only include fully executed orders
            if order.get("status") != "COMPLETE":
                continue

            # Convert Kite trade format to our internal format
            trade = {
                "symbol": order.get("tradingsymbol", ""),
                "exchange": order.get("exchange", "NSE"),
                "action": order.get("transaction_type", "").upper(),  # BUY or SELL
                "quantity": int(order.get("filled_quantity", 0)),
                "price": float(order.get("average_price", 0)),
                "trade_date": order.get("order_timestamp", "")[:10],  # YYYY-MM-DD
                "order_id": order.get("order_id", ""),
                "broker_id": "kite",
            }
            if trade["quantity"] > 0:
                trades_list.append(trade)

        log.info(f"fetched {len(trades_list)} trades from Kite")
        return trades_list

    except Exception as exc:
        log.error(f"kite trades error: {exc}")
        return None


def holdings(access_token: str, api_key: str) -> list[dict] | None:
    """Fetch current holdings (positions) from Kite account."""
    try:
        from kiteconnect import KiteConnect

        kite = KiteConnect(api_key=api_key)
        kite.access_token = access_token

        positions = kite.positions()
        if not positions or "net" not in positions:
            return []

        holdings_list = []
        for pos in positions.get("net", []):
            holding = {
                "symbol": pos.get("tradingsymbol", ""),
                "quantity": int(pos.get("quantity", 0)),
                "avg_cost": float(pos.get("average_price", 0)),
                "ltp": float(pos.get("last_price", 0)),
                "value": float(pos.get("value", 0)),
            }
            if holding["quantity"] != 0:
                holdings_list.append(holding)

        log.info(f"fetched {len(holdings_list)} holdings from Kite")
        return holdings_list

    except Exception as exc:
        log.error(f"kite holdings error: {exc}")
        return None


def cash_balance(access_token: str, api_key: str) -> dict | None:
    """Fetch account cash, balance, and margin details."""
    try:
        from kiteconnect import KiteConnect

        kite = KiteConnect(api_key=api_key)
        kite.access_token = access_token

        margins = kite.margins()
        equity = margins.get("equity", {})

        return {
            "cash": float(equity.get("cash", 0)),
            "available_balance": float(equity.get("available", 0)),
            "utilised": float(equity.get("utilised", 0)),
            "net_worth": float(equity.get("net", 0)),
        }

    except Exception as exc:
        log.error(f"kite cash_balance error: {exc}")
        return None


def account_summary(access_token: str, api_key: str) -> dict | None:
    """Comprehensive account summary: trades, holdings, cash."""
    trades_list = trades(access_token, api_key)
    holdings_list = holdings(access_token, api_key)
    cash = cash_balance(access_token, api_key)

    return {
        "trades": trades_list or [],
        "holdings": holdings_list or [],
        "cash": cash or {},
    }


def user_profile(access_token: str, api_key: str) -> dict | None:
    """Fetch user profile: name, email, phone, account type, segment."""
    try:
        import requests
        headers = {
            "Authorization": f"token {api_key}:{access_token}",
            "User-Agent": "Mozilla/5.0",
        }
        r = requests.get(
            "https://api.kite.trade/user/profile",
            headers=headers,
            timeout=10
        )
        if r.status_code != 200:
            log.warning(f"Profile fetch failed: {r.status_code} {r.text}")
            return None

        data = r.json().get("data", {})
        return {
            "user_id": data.get("user_id"),
            "user_name": data.get("user_name"),
            "email": data.get("email"),
            "phone": data.get("phone"),
            "broker": data.get("broker"),
            "account_type": data.get("account_type"),
            "segment": data.get("segment", []),
            "exchanges": data.get("exchanges", []),
            "products": data.get("products", []),
        }
    except Exception as e:
        log.error(f"Profile fetch error: {e}")
        return None

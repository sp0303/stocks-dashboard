"""Watchlist email alerts.

Two triggers, evaluated across every manager and client watchlist:
  * target price — live price at/above the entry's alert_price
  * alert date   — the entry's alert_date has arrived (today or past)

Each threshold notifies exactly once: after emailing we stamp alert_price_notified /
alert_date_notified on the entry. Editing the target/date clears the stamp (see the
watchlists router), so a new threshold can fire again.

Recipient is the *owning manager's* email — for a manager watchlist that's the manager
themselves; for a client watchlist it's the client's portfolio manager. Entries whose
owner has no email on file are skipped.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from app.config import settings
from app.services.mailer import MailNotConfigured, send_email
from app.services.market_data import get_quote_details

log = logging.getLogger("alerts")


async def _owner_email(store, owner_type: str, owner_id: str) -> tuple[str | None, str]:
    """Return (email, label) for whoever should receive alerts for this watchlist."""
    if owner_type == "MANAGER":
        m = await store.get_manager(owner_id)
        return (m.get("email") if m else None), (m.get("name") if m else owner_id)
    c = await store.get_client(owner_id)
    if not c:
        return None, owner_id
    m = await store.get_manager(c.get("portfolio_manager_id"))
    label = f"{c.get('name', owner_id)} (client)"
    return (m.get("email") if m else None), label


def _target_body(symbol: str, price: float, target: float, owner_label: str) -> str:
    return (
        f"Watchlist alert for {owner_label}\n\n"
        f"{symbol} has reached your target price.\n"
        f"  Target : ₹{target:,.2f}\n"
        f"  Current: ₹{price:,.2f}\n\n"
        f"— Portfolio Intelligence"
    )


def _date_body(symbol: str, alert_date: str, price: float | None, owner_label: str) -> str:
    px = f"₹{price:,.2f}" if price is not None else "—"
    return (
        f"Watchlist alert for {owner_label}\n\n"
        f"Your alert date for {symbol} ({alert_date}) has arrived.\n"
        f"  Current price: {px}\n\n"
        f"— Portfolio Intelligence"
    )


async def _send(to: str, subject: str, body: str) -> bool:
    try:
        await asyncio.to_thread(send_email, to, subject, body)
        log.info("alert email sent to %s: %s", to, subject)
        return True
    except MailNotConfigured:
        raise
    except Exception as exc:  # transport/auth — log and move on, don't mark notified
        log.warning("alert email FAILED to %s (%s): %s", to, subject, exc)
        return False


async def _check_watchlist(store, owner_type: str, owner_id: str) -> int:
    lists = await store.get_watchlists(owner_type, owner_id)
    if not any(l["entries"] for l in lists):
        return 0
    email, label = await _owner_email(store, owner_type, owner_id)
    if not email:
        return 0

    # one quote fetch covers every symbol across all of the owner's lists
    symbols = sorted({e["symbol"] for l in lists for e in l["entries"]})
    quotes = get_quote_details(symbols)
    today = date.today().isoformat()
    sent = 0

    for wl in lists:
        for e in wl["entries"]:
            s = e["symbol"]
            price = quotes.get(s, {}).get("price")

            # target price reached — notify once per distinct target value
            target = e.get("alert_price")
            if target is not None and price is not None and price >= target and e.get("alert_price_notified") != target:
                if await _send(email, f"🎯 {s} hit target ₹{target:g}", _target_body(s, price, target, label)):
                    await store.update_watchlist_entry(owner_type, owner_id, s, {"alert_price_notified": target}, watchlist_id=wl["id"])
                    sent += 1

            # alert date arrived — notify once per distinct date
            adate = e.get("alert_date")
            if adate and adate <= today and e.get("alert_date_notified") != adate:
                if await _send(email, f"📅 {s} alert date {adate}", _date_body(s, adate, price, label)):
                    await store.update_watchlist_entry(owner_type, owner_id, s, {"alert_date_notified": adate}, watchlist_id=wl["id"])
                    sent += 1

    return sent


async def check_owner(store, owner_type: str, owner_id: str) -> int:
    """Evaluate just one watchlist now — used to fire an alert the instant a matching
    target/alert-date is set, instead of waiting for the next background sweep."""
    if not settings.alerts_ready:
        return 0
    try:
        return await _check_watchlist(store, owner_type, owner_id)
    except MailNotConfigured:
        return 0
    except Exception as exc:
        log.warning("check_owner error for %s/%s: %s", owner_type, owner_id, exc)
        return 0


async def check_and_send(store) -> dict:
    """Evaluate every watchlist once. Returns a small summary dict."""
    if not settings.alerts_ready:
        return {"sent": 0, "skipped": "alerts not configured (set alert_smtp_password)"}
    sent = 0
    for m in await store.list_managers():
        sent += await _check_watchlist(store, "MANAGER", m["id"])
    for c in await store.list_clients():
        sent += await _check_watchlist(store, "CLIENT", c["id"])
    return {"sent": sent}


async def run_alert_loop(store) -> None:
    """Background heartbeat started from the app lifespan. Cheap and quiet when
    alerts aren't configured; cancelled on shutdown."""
    interval = max(60, settings.alert_check_interval_seconds)
    while True:
        try:
            if settings.alerts_ready:
                await check_and_send(store)
        except MailNotConfigured:
            pass  # configured flag flipped mid-flight; try again next tick
        except Exception as exc:
            log.warning("alert loop error: %s", exc)
        await asyncio.sleep(interval)

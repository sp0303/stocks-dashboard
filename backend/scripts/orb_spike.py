#!/usr/bin/env python
"""Phase 0 — the four questions that everything downstream assumes an answer to.

Run this on a machine with live Angel credentials in backend/.env. It writes nothing to
the database and places no orders; it only asks Angel things and prints what came back.

    python scripts/orb_spike.py                  # all checks
    python scripts/orb_spike.py --only ws        # one check
    python scripts/orb_spike.py --symbol SBIN

Checks 4 and 5 are best run *during market hours*; the rest work any time.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings                                    # noqa: E402
from app.services import angel                                     # noqa: E402
from app.services.orb.session import IST, MARKET_CLOSE, MARKET_OPEN, hhmm  # noqa: E402
from app.services.orb.universe import (INDEX_TOKENS, equity_candidates)    # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")

OK, BAD, WARN = "PASS", "FAIL", "CHECK"
results: list[tuple[str, str, str]] = []


def say(check: str, verdict: str, detail: str = "") -> None:
    results.append((check, verdict, detail))
    print(f"  [{verdict:5}] {detail}")


def head(n: int, title: str) -> None:
    print(f"\n{n}. {title}\n" + "-" * 68)


def _fmt(d: date, m: int) -> str:
    return f"{d.isoformat()} {m // 60:02d}:{m % 60:02d}"


def find(symbol: str):
    for i in equity_candidates():
        if i.symbol == symbol:
            return i
    raise SystemExit(f"{symbol} is not in the NSE EQ list")


# ── 1 ─────────────────────────────────────────────────────────────
def check_credentials():
    head(1, "Credentials and session")
    st = angel.status()
    if not st["enabled"]:
        say("creds", BAD, "ANGEL_* not set in backend/.env — nothing else can run")
        raise SystemExit(1)
    if not st["authenticated"]:
        say("creds", BAD, f"login failed: {st['error']}")
        raise SystemExit(1)
    say("creds", OK, "TOTP login succeeded")


# ── 2 ─────────────────────────────────────────────────────────────
def check_minute_history(symbol: str):
    head(2, "1-minute REST candles over a 30-day window")
    inst = find(symbol)
    end = date.today()
    start = end - timedelta(days=28)
    t0 = time.time()
    rows = angel.get_candles(inst.token, "NSE", "1m", _fmt(start, MARKET_OPEN),
                             _fmt(end, MARKET_CLOSE))
    if rows is None:
        say("history", BAD, "call failed or the budget was exhausted")
        return
    days = {r[0][:10] for r in rows}
    say("history", OK, f"{len(rows)} candles over {len(days)} sessions "
                       f"in {time.time() - t0:.1f}s")
    if rows:
        print(f"         first: {rows[0]}")
        print(f"         last : {rows[-1]}")
        print(f"         -> prices are RUPEES here (the websocket sends paise)")


# ── 3 ─────────────────────────────────────────────────────────────
def check_gap_handling(symbol: str):
    head(3, "Does REST omit minutes that had no trades?")
    print("     This decides how reconciliation aligns the two series. If Angel omits")
    print("     quiet minutes, aligning positionally would compare unrelated bars.")
    inst = find(symbol)
    day = _recent_session()
    rows = angel.get_candles(inst.token, "NSE", "1m", _fmt(day, MARKET_OPEN),
                             _fmt(day, MARKET_CLOSE))
    if not rows:
        say("gaps", WARN, f"no candles for {day} — try another date")
        return
    full = MARKET_CLOSE - MARKET_OPEN
    minutes = sorted({datetime.fromisoformat(r[0]).hour * 60
                      + datetime.fromisoformat(r[0]).minute for r in rows})
    missing = full - len(minutes)
    zero_vol = sum(1 for r in rows if not r[5])
    if missing > 0:
        say("gaps", OK, f"{len(minutes)}/{full} minutes present — Angel OMITS "
                        f"{missing} quiet minutes. Align on the minute key.")
    else:
        say("gaps", OK, f"all {full} minutes present ({zero_vol} with zero volume) — "
                        f"Angel pads quiet minutes itself.")


# ── 4 ─────────────────────────────────────────────────────────────
def check_todays_session(symbol: str):
    head(4, "Does the running session return candles, and how far behind?")
    inst = find(symbol)
    now = datetime.now(IST)
    minute = now.hour * 60 + now.minute
    if not (MARKET_OPEN < minute < MARKET_CLOSE):
        say("live-candles", WARN, "outside market hours — re-run during a session")
        return
    rows = angel.get_candles(inst.token, "NSE", "1m", _fmt(date.today(), MARKET_OPEN),
                             _fmt(date.today(), minute))
    if not rows:
        say("live-candles", BAD, "no candles for the running session")
        return
    last = datetime.fromisoformat(rows[-1][0])
    lag = (now - last).total_seconds()
    verdict = OK if lag < 180 else WARN
    say("live-candles", verdict,
        f"{len(rows)} candles, last at {last:%H:%M:%S}, {lag:.0f}s behind now")
    print("         -> this lag is exactly why the live path builds bars from ticks")


# ── 5 ─────────────────────────────────────────────────────────────
def check_index_candles():
    head(5, "Index candles — do they carry volume?")
    print("     If index volume is zero, a sector index has no VWAP and gate D5 must")
    print("     align on percentage return instead.")
    day = _recent_session()
    for name in ("NIFTY 50", "NIFTY BANK"):
        token = INDEX_TOKENS[name]
        rows = angel.get_candles(token, "NSE", "1m", _fmt(day, MARKET_OPEN),
                                 _fmt(day, MARKET_OPEN + 30))
        if not rows:
            say(f"index:{name}", WARN, "no candles returned")
            continue
        vols = [r[5] for r in rows]
        say(f"index:{name}", OK,
            f"{len(rows)} candles, volume {'all zero' if not any(vols) else max(vols)}")


# ── 6 ─────────────────────────────────────────────────────────────
def check_websocket(symbol: str, seconds: int = 25):
    head(6, "WebSocket: connect, subscribe, parse, and the paise scaling")
    inst = find(symbol)
    from app.services.orb.feed import Feed, MODE_QUOTE

    seen: list = []
    feed = Feed(on_tick=lambda t: seen.append(t), mode=MODE_QUOTE)
    feed.start([inst.token])
    print(f"     listening {seconds}s on {inst.symbol} (token {inst.token})…")
    for _ in range(seconds):
        time.sleep(1)
        if len(seen) >= 3:
            break
    feed.stop()

    if not seen:
        say("websocket", WARN if _outside_hours() else BAD,
            "no ticks — outside market hours?" if _outside_hours()
            else "connected but silent; check the feed token and subscription")
        print(f"         status: {feed.status.as_dict()}")
        return
    t = seen[-1]
    say("websocket", OK, f"{len(seen)} ticks; last LTP {t.ltp} paise "
                         f"= Rs {t.ltp / 100:,.2f}")
    print(f"         cumulative volume : {t.cum_volume}")
    print(f"         average_traded_price (the exchange's session VWAP): "
          f"{t.avg_price} = Rs {(t.avg_price or 0) / 100:,.2f}")
    print(f"         previous close    : Rs {(t.prev_close or 0) / 100:,.2f}")
    if t.cum_volume is None:
        say("ws-volume", BAD, "no volume field — QUOTE mode is required, not LTP")
    else:
        say("ws-volume", OK, "volume_trade_for_the_day present (bar volume is its delta)")


# ── 7 ─────────────────────────────────────────────────────────────
def check_second_login(symbol: str):
    head(7, "Does a second Angel login kill the live socket?")
    print("     angel.py documents AG8001: a login elsewhere invalidates this process's")
    print("     token. If it also drops the feed, the dashboard and the engine cannot")
    print("     share one session and the engine needs its own credentials.")
    inst = find(symbol)
    from app.services.orb.feed import Feed

    seen = []
    feed = Feed(on_tick=lambda t: seen.append(t))
    feed.start([inst.token])
    time.sleep(10)
    before = len(seen)
    if before == 0:
        say("second-login", WARN, "no ticks before the test — re-run during market hours")
        feed.stop()
        return
    print("     forcing a fresh login in this process…")
    angel._invalidate_session()
    angel._ensure_session()
    time.sleep(15)
    after = len(seen) - before
    feed.stop()
    if after > 0:
        say("second-login", OK, f"feed survived ({after} ticks after re-login)")
    else:
        say("second-login", WARN,
            "feed went silent after a re-login — give the engine its own Angel account, "
            "or make angel.py's session single-owner")


def _outside_hours() -> bool:
    n = datetime.now(IST)
    return not (MARKET_OPEN <= n.hour * 60 + n.minute <= MARKET_CLOSE) or n.weekday() >= 5


def _recent_session() -> date:
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


CHECKS = {
    "creds": lambda a: check_credentials(),
    "history": lambda a: check_minute_history(a.symbol),
    "gaps": lambda a: check_gap_handling(a.symbol),
    "live": lambda a: check_todays_session(a.symbol),
    "index": lambda a: check_index_candles(),
    "ws": lambda a: check_websocket(a.symbol, a.seconds),
    "relogin": lambda a: check_second_login(a.symbol),
}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", default="SBIN")
    p.add_argument("--seconds", type=int, default=25)
    p.add_argument("--only", choices=list(CHECKS), action="append")
    args = p.parse_args()

    print("=" * 68)
    print("ORB Phase 0 spike — asking Angel the four questions the plan assumes")
    print(f"symbol {args.symbol} · {datetime.now(IST):%Y-%m-%d %H:%M:%S IST}"
          f" · market hours: {'no' if _outside_hours() else 'yes'}")
    print("=" * 68)

    check_credentials()
    for name in (args.only or [k for k in CHECKS if k != "creds"]):
        if name == "creds":
            continue
        try:
            CHECKS[name](args)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            say(name, BAD, f"{type(exc).__name__}: {exc}")

    print("\n" + "=" * 68)
    print("SUMMARY")
    for check, verdict, detail in results:
        print(f"  {verdict:5}  {check:16} {detail[:60]}")
    failed = [r for r in results if r[1] == BAD]
    print("=" * 68)
    print(f"{len(results) - len(failed)} of {len(results)} checks passed.")
    if failed:
        print("Resolve the failures above before starting Segment B.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

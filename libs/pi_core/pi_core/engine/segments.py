"""Segment separation rule R9: Delivery equity, intraday, and derivatives."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from pi_core.models import Segment, Side, Trade


def separate_segments(trades: list[Trade]) -> tuple[list[Trade], list[Trade], list[Trade]]:
    """Separate trades into Delivery Equity, Intraday, and Derivatives pools per Rule R9.

    Returns:
        Tuple of (delivery_equity_trades, intraday_trades, derivative_trades)
    """
    delivery_trades: list[Trade] = []
    intraday_trades: list[Trade] = []
    derivative_trades: list[Trade] = []

    # Step 1: Separate derivatives first (FO, FUT, OPT, NRML)
    equity_pool: list[Trade] = []
    for t in trades:
        if t.segment == Segment.DERIVATIVE:
            derivative_trades.append(t)
        else:
            equity_pool.append(t)

    # Step 2: In equity pool, group by (symbol, trade_date) to detect intraday round-trips
    day_symbol_map = defaultdict(lambda: {Side.BUY: 0.0, Side.SELL: 0.0, "buys": [], "sells": []})

    for t in equity_pool:
        # Same stock, same day, either exchange (Section 43(5); v1 split_intraday)
        key = (t.symbol, t.trade_date)
        day_symbol_map[key][t.side] += t.quantity
        if t.side == Side.BUY:
            day_symbol_map[key]["buys"].append(t)
        else:
            day_symbol_map[key]["sells"].append(t)

    for group in day_symbol_map.values():
        total_buy_qty = group[Side.BUY]
        total_sell_qty = group[Side.SELL]

        # Overlapping quantity on the same day is intraday
        intraday_qty = min(total_buy_qty, total_sell_qty)

        if intraday_qty == 0.0:
            # All trades on this day for this symbol are delivery
            delivery_trades.extend(group["buys"])
            delivery_trades.extend(group["sells"])
            continue

        # Split buys between intraday and delivery
        rem_intraday_buy = intraday_qty
        for t in group["buys"]:
            if rem_intraday_buy <= 0:
                delivery_trades.append(t)
            elif t.quantity <= rem_intraday_buy:
                intraday_trades.append(replace(t, segment=Segment.INTRADAY))
                rem_intraday_buy -= t.quantity
            else:
                # Trade is partially intraday, partially delivery
                intra_part = replace(t, quantity=rem_intraday_buy, segment=Segment.INTRADAY)
                deliv_part = replace(
                    t, quantity=t.quantity - rem_intraday_buy, segment=Segment.EQUITY
                )
                intraday_trades.append(intra_part)
                delivery_trades.append(deliv_part)
                rem_intraday_buy = 0.0

        # Split sells between intraday and delivery
        rem_intraday_sell = intraday_qty
        for t in group["sells"]:
            if rem_intraday_sell <= 0:
                delivery_trades.append(t)
            elif t.quantity <= rem_intraday_sell:
                intraday_trades.append(replace(t, segment=Segment.INTRADAY))
                rem_intraday_sell -= t.quantity
            else:
                intra_part = replace(t, quantity=rem_intraday_sell, segment=Segment.INTRADAY)
                deliv_part = replace(
                    t, quantity=t.quantity - rem_intraday_sell, segment=Segment.EQUITY
                )
                intraday_trades.append(intra_part)
                delivery_trades.append(deliv_part)
                rem_intraday_sell = 0.0

    # Sort outputs deterministically by trade_date, trade_id
    delivery_trades.sort(key=lambda t: (t.trade_date, t.trade_id))
    intraday_trades.sort(key=lambda t: (t.trade_date, t.trade_id))
    derivative_trades.sort(key=lambda t: (t.trade_date, t.trade_id))

    return delivery_trades, intraday_trades, derivative_trades

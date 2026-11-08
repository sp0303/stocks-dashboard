"""FIFO trade matching adhering to Rule R7."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, List, Tuple

from pi_core.models import Lot, MatchedTrade, Side, Trade, UnmatchedSell


def match_trades_fifo(
    trades: List[Trade],
) -> Tuple[List[MatchedTrade], List[UnmatchedSell], Dict[Tuple[str, str], List[Lot]]]:
    """Matches buy and sell trades strictly using FIFO per (symbol, exchange).

    Returns:
        (matched_trades, unmatched_sells, open_lots_by_symbol_and_exchange)
    """
    matched: List[MatchedTrade] = []
    unmatched: List[UnmatchedSell] = []
    open_lots: Dict[Tuple[str, str], deque[Lot]] = defaultdict(deque)

    # Sort trades chronologically: BUYS processed before SELLS on same day
    sorted_trades = sorted(
        trades,
        key=lambda t: (t.trade_date, 0 if t.side == Side.BUY else 1, t.trade_id),
    )

    for t in sorted_trades:
        key = (t.symbol, t.exchange)
        chg = t.charges if t.charges is not None else 0.0
        chg_per_unit = chg / t.quantity if t.quantity > 0 else 0.0

        if t.side == Side.BUY:
            lot = Lot(
                lot_id=t.trade_id,
                buy_date=t.trade_date,
                symbol=t.symbol,
                exchange=t.exchange,
                quantity=t.quantity,
                original_quantity=t.quantity,
                price=t.price,
                charges_per_unit=chg_per_unit,
            )
            open_lots[key].append(lot)
        else:
            # Side == SELL: exhaust open lots in FIFO order
            rem_sell_qty = t.quantity

            while rem_sell_qty > 0 and open_lots[key]:
                earliest_lot = open_lots[key][0]
                matched_qty = min(earliest_lot.quantity, rem_sell_qty)

                # Prorate charges for matched slice
                buy_chg_slice = matched_qty * earliest_lot.charges_per_unit
                sell_chg_slice = matched_qty * chg_per_unit

                matched.append(
                    MatchedTrade(
                        sell_trade_id=t.trade_id,
                        buy_trade_id=earliest_lot.lot_id,
                        symbol=t.symbol,
                        exchange=t.exchange,
                        buy_date=earliest_lot.buy_date,
                        sell_date=t.trade_date,
                        quantity=matched_qty,
                        buy_price=earliest_lot.price,
                        sell_price=t.price,
                        buy_charges=buy_chg_slice,
                        sell_charges=sell_chg_slice,
                    )
                )

                earliest_lot.quantity -= matched_qty
                rem_sell_qty -= matched_qty

                if earliest_lot.quantity <= 1e-6:
                    open_lots[key].popleft()

            # If there's still unmatched sell quantity, record as UnmatchedSell (Rule R7)
            if rem_sell_qty > 1e-6:
                unmatched.append(
                    UnmatchedSell(
                        trade_id=t.trade_id,
                        trade_date=t.trade_date,
                        symbol=t.symbol,
                        exchange=t.exchange,
                        quantity=rem_sell_qty,
                        sell_price=t.price,
                        proceeds=rem_sell_qty * t.price,
                    )
                )

    remaining_lots: Dict[Tuple[str, str], List[Lot]] = {
        k: list(v) for k, v in open_lots.items() if v
    }

    return matched, unmatched, remaining_lots

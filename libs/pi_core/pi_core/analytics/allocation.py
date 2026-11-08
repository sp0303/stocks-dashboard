"""Symbol capital allocation adhering to Rule R5."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List

from pi_core.models import Side, Trade


@dataclass(frozen=True)
class SymbolAllocation:
    symbol: str
    exchange: str
    peak_capital: float
    current_cost: float
    allocation_pct: float  # Fraction of total book capital


def calculate_symbol_allocation(
    trades: List[Trade],
    total_book_capital_deployed: float,
) -> List[SymbolAllocation]:
    """Computes capital allocation per symbol using peak capital deployed per symbol (Rule R5).

    Never sums opposing legs (buys + sells).
    """
    trades_by_sym = defaultdict(list)
    for t in trades:
        trades_by_sym[(t.symbol, t.exchange)].append(t)

    allocations: List[SymbolAllocation] = []

    for (sym, exch), sym_trades in trades_by_sym.items():
        # Sort chronologically
        sorted_trades = sorted(sym_trades, key=lambda t: (t.trade_date, 0 if t.side == Side.BUY else 1))

        open_qty = 0.0
        open_cost = 0.0
        peak_cap = 0.0

        for t in sorted_trades:
            chg = t.charges if t.charges is not None else 0.0
            if t.side == Side.BUY:
                open_qty += t.quantity
                open_cost += (t.quantity * t.price) + chg
            else:
                cost_slice = (t.quantity / open_qty * open_cost) if open_qty > 0 else 0.0
                open_qty = max(0.0, open_qty - t.quantity)
                open_cost = max(0.0, open_cost - cost_slice)

            if open_cost > peak_cap:
                peak_cap = open_cost

        pct = (peak_cap / total_book_capital_deployed) if total_book_capital_deployed > 0 else 0.0

        allocations.append(
            SymbolAllocation(
                symbol=sym,
                exchange=exch,
                peak_capital=peak_cap,
                current_cost=open_cost if open_qty > 1e-5 else 0.0,
                allocation_pct=pct,
            )
        )

    allocations.sort(key=lambda a: a.peak_capital, reverse=True)
    return allocations

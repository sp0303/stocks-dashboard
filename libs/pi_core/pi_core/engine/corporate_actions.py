"""Corporate actions engine module adhering to Rule R8."""

from __future__ import annotations

from collections import deque

from pi_core.models import ActionType, CorporateAction, Lot


def apply_corporate_actions(
    open_lots: dict[tuple[str, str], deque[Lot]],
    actions: list[CorporateAction],
) -> list[str]:
    """Applies corporate action scaling to open lots in-place.

    Returns:
        List of human-readable warnings (e.g., demerger / merger cost apportionment needed).
    """
    warnings: list[str] = []

    for ca in actions:
        if ca.action_type in (ActionType.SPLIT, ActionType.BONUS):
            m = ca.multiplier
            if m <= 0.0 or m == 1.0:
                continue

            # Scale open lots for all exchanges of this symbol
            scaled_any = False
            for (sym, exch), lots in open_lots.items():
                if sym == ca.symbol:
                    for lot in lots:
                        lot.quantity *= m
                        lot.price /= m
                        lot.charges_per_unit /= m
                    scaled_any = True

            if not scaled_any:
                warnings.append(
                    f"Corporate action {ca.action_type.value} on {ca.symbol} (ex-date {ca.ex_date}): "
                    f"no open lots held at ex-date."
                )

        elif ca.action_type in (
            ActionType.DEMERGER,
            ActionType.MERGER,
            ActionType.RIGHTS,
            ActionType.BUYBACK,
            ActionType.OTHER,
        ):
            warnings.append(
                f"Action {ca.action_type.value} for {ca.symbol} on {ca.ex_date}: "
                f"cost apportionment manual review required (Rule R8)."
            )

    return warnings

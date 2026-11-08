# 0009. Value a lot at the other exchange's close when its own exchange has none

* **Status**: **Accepted** (chosen by the project owner, 2026-11-08). Amends [DOMAIN-RULES](../v2/DOMAIN-RULES.md) R6.1.
* **Date**: 2026-11-08
* **Deciders**: Project Owner

## 1. Context

R6.1 said a BSE holding is never valued at the NSE price. v2 applied it strictly: a lot bought on the BSE with no BSE close was **unpriced** and left out of market value and current invested (R6.4).

A local end-to-end test on four real books (7,623 trades, prices to 6 Nov 2026) showed the cost of that strictness: BSE-bought lots left out of value ranged from about 2 % to about 20 % of a client's book (the largest was roughly a fifth of one client's holdings). v1 values the same lots at the NSE price, so v2's market value, unrealised P&L, allocation and concentration all disagreed with v1 and, more importantly, with the investor's own broker. Shares are fungible across exchanges in the demat account; the engine already matches sells to buys across exchanges for that reason.

R6.1 existed to stop v1's real defect: a symbol-keyed cache that let whichever exchange loaded first price every holding, with no way to see it.

## 2. Decision

* Keep prices keyed `(symbol, exchange)`. **A lot is valued at its own exchange's close whenever that exchange has a usable close.**
* If it has none, use the same symbol's close on the other exchange (NSE, else BSE). One close, from one place; never an average or a blend.
* The same freshness limit applies (`MAX_PRICE_CARRY_DAYS`, 10 days, `pi_core.pricing`). A stale fallback is no better than a stale own close: the lot becomes unpriced.
* The fallback is **never silent**: `portfolio.client_overview.priced_on_other_exchange` lists the lots, the overview carries a warning, the positions and manager-holdings APIs return `priced_on`, and the UI shows "NSE price" beside the figure.
* A lot with no usable close on either exchange stays unpriced (R6.4): excluded from both cost and value.

## 3. Consequences

* BSE-bought lots of NSE-listed stocks now count in value, P&L, allocation and risk, and v2 agrees with v1 on them.
* The engine price lookup, the client positions query and the manager holdings query share one rule. The analytics worker uses the same lookup, so the Performance tab, allocation and concentration follow it automatically.
* For a stock that is genuinely far more illiquid on one exchange, the fallback price can differ from what that exchange would show. That is why it is flagged, and why own-exchange prices always win.
* Tests: `tests/unit/workers/test_portfolio_compute.py` (lookup), `tests/golden/test_engine_fixes.py::test_bse_lot_is_valued_at_nse_close_and_flagged_adr_0009`.

## 4. Alternatives rejected

* **Keep R6.1 strictly.** Leaves up to a fifth of a client's book unvalued and disagrees with v1 and the broker.
* **Always price by symbol on the NSE.** Brings back v1's defect: it hides real differences between listings.
* **Average the two exchanges.** Invents a price that never traded.

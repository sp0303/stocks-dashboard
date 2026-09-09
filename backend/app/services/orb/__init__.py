"""Opening Range Breakout engine.

Three segments that do not depend on each other's internals:

  A · data   — REST backfill of 1-minute candles into Mongo (history.py, store.py),
               with the trading calendar derived from the data itself (calendar.py).
  B · live   — WebSocket ticks assembled into 1-minute bars (feed.py, bars.py), written
               by a wall-clock scheduler (scheduler.py, engine.py), verified nightly
               against Angel's own candles (recon.py). The strategy (strategy.py) sits
               on top and only reads bars that have already been proven.
  C · backtest — deliberately absent. It will be a replay driver over the same store
               calling the same strategy.decide(); nothing here anticipates it beyond
               keeping strategy.py pure.

The single-core rule: strategy.decide() takes a SessionContext and returns a Decision.
It performs no I/O, reads no clock, and imports nothing from this package's I/O modules.
That is what lets the future backtest and the live engine share one implementation.
"""

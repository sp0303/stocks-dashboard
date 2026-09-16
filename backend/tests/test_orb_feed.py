"""Multi-connection feed fan-out (whole-NSE recording). Pins the token slicing and the
status aggregation — the pure logic that decides how ~2,676 symbols spread across 3
websocket connections. No sockets, no Angel."""
from app.services.orb import feed as FE


def test_slice_covers_whole_nse_balanced_across_three_connections():
    toks = [str(i) for i in range(2678)]
    chunks = FE.slice_tokens(toks, per_conn=1000, max_conn=3)
    assert [len(c) for c in chunks] == [893, 893, 892]      # balanced, all under the 1000 cap
    assert max(len(c) for c in chunks) < 1000               # headroom on every connection
    # every token placed exactly once, order preserved
    assert [t for c in chunks for t in c] == toks


def test_slice_single_connection_when_small():
    assert FE.slice_tokens([str(i) for i in range(500)], 1000, 3) == [[str(i) for i in range(500)]]


def test_slice_truncates_beyond_capacity():
    chunks = FE.slice_tokens([str(i) for i in range(3500)], 1000, 3)
    assert [len(c) for c in chunks] == [1000, 1000, 1000]     # capped at 3x1000, extras dropped


def test_slice_empty_is_one_empty_chunk():
    assert FE.slice_tokens([], 1000, 3) == [[]]


def test_agg_status_sums_across_connections():
    mf = FE.MultiFeed(lambda t: None)
    f1, f2, f3 = FE.Feed(lambda t: None), FE.Feed(lambda t: None), FE.Feed(lambda t: None)
    f1.status = FE.FeedStatus(connected=True, subscribed=1000, ticks=500)
    f2.status = FE.FeedStatus(connected=True, subscribed=1000, ticks=400)
    f3.status = FE.FeedStatus(connected=False, subscribed=676, ticks=0, last_error="down")
    mf.feeds = [f1, f2, f3]
    d = mf.status.as_dict()
    assert d["connections"] == 3 and d["connections_up"] == 2
    assert d["connected"] is True                    # any connection up
    assert d["subscribed"] == 2676 and d["ticks"] == 900
    assert d["last_error"] == "down"


def test_agg_status_empty_before_start():
    d = FE.MultiFeed(lambda t: None).status.as_dict()
    assert d["connections"] == 0 and d["connected"] is False and d["subscribed"] == 0


def test_feed_routes_to_the_recorder_prep_rebuilds():
    """Regression: job_prep replaces self.recorder every morning. The feed must dispatch to
    the CURRENT recorder, not the one bound at construction — else every tick is dropped."""
    from app.services.orb.engine import Engine
    from app.services.orb.recorder import Recorder

    eng = Engine()
    eng.recorder = Recorder()                 # what job_prep does at 08:45
    eng.recorder.register("TESTSYM", "999")
    eng.feed.on_tick(FE.Tick(token="999", ltp=10000, cum_volume=100, avg_price=None,
                             prev_close=None, exchange_ts_ms=0))
    assert eng.recorder.by_token["999"].ticks == 1     # reached the rebuilt recorder
    assert eng.recorder.dropped_unknown_token == 0

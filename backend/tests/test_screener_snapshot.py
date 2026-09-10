"""The screener snapshot must (1) never block the event loop during its heavy compute,
and (2) collapse concurrent cold misses into a single compute (single-flight). Both are
verified here with a mocked compute — no network."""
import asyncio
import time

import pytest

from app.routers import screener


def _reset():
    screener._SNAPSHOT["data"] = None
    screener._SNAPSHOT["computed_at"] = 0.0


@pytest.mark.asyncio
async def test_single_flight_collapses_concurrent_cold_misses(monkeypatch):
    calls = {"n": 0}

    def fake_compute():
        calls["n"] += 1
        time.sleep(0.2)  # simulate the slow, blocking provider fetch
        return {"generated_at": "x", "count": 1, "stocks": [{"ticker": "T"}], "sectors": {}}

    monkeypatch.setattr(screener, "_compute_screener", fake_compute)
    _reset()

    results = await asyncio.gather(*[screener.screener() for _ in range(5)])

    assert calls["n"] == 1, "concurrent cold requests must share one compute"
    assert all(r["data"]["count"] == 1 for r in results)


@pytest.mark.asyncio
async def test_compute_does_not_block_the_event_loop(monkeypatch):
    def slow_compute():
        time.sleep(0.5)  # blocking work — must run off the loop
        return {"generated_at": "x", "count": 0, "stocks": [], "sectors": {}}

    monkeypatch.setattr(screener, "_compute_screener", slow_compute)
    _reset()

    task = asyncio.create_task(screener.screener())
    ticks = 0
    while not task.done():
        await asyncio.sleep(0.01)  # the loop must be free to tick while compute runs
        ticks += 1
    await task

    assert ticks > 5, "event loop was blocked during the compute (ticks too few)"


@pytest.mark.asyncio
async def test_fresh_snapshot_served_without_recompute(monkeypatch):
    calls = {"n": 0}

    def fake_compute():
        calls["n"] += 1
        return {"generated_at": "x", "count": 2, "stocks": [], "sectors": {}}

    monkeypatch.setattr(screener, "_compute_screener", fake_compute)
    _reset()

    await screener.screener()            # cold → computes once
    await screener.screener()            # fresh → served from cache, no recompute
    assert calls["n"] == 1

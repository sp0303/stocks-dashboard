"""Heatmap response models (OpenAPI source for the web client). Returns are decimals (R12)."""

from __future__ import annotations

from pydantic import BaseModel


class _Held(BaseModel):
    symbol: str
    exchange: str | None = None  # exchange whose closes were used
    qty: float
    invested: float
    clients: int
    entry_date: str | None = None  # tracking day: oldest open lot
    suspect: bool = (
        False  # a move >= 40 % with no split/bonus behind it: check the data
    )


class HeatmapTile(_Held):
    ret: float | None = None  # None = no close that day, never 0
    close: float | None = None
    prev_close: float | None = None
    prev_date: str | None = None


class HeatmapColumn(BaseModel):
    key: str
    last_date: str


class HeatmapRow(_Held):
    start: str | None = None
    start_close: float | None = None
    end_close: float | None = None
    cells: dict[str, float] = {}
    total: float | None = None


class HeatmapResponse(BaseModel):
    mode: str
    day: str | None = None
    latest: str | None = None
    end: str | None = None
    grain: str | None = None
    tiles: list[HeatmapTile] = []
    columns: list[HeatmapColumn] = []
    rows: list[HeatmapRow] = []
    no_history: list[str] = []

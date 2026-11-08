"""Pure transforms for the v1 (Mongo) -> v2 (Postgres) market-data sync.

No I/O here: the DB/Mongo side lives in ``v1_sync_db``. Everything in this
module is deterministic so it can be unit-tested without a database.

Rules: R6 (prices keyed (symbol, exchange), carry source, stale/frozen rows
rejected at ingest), R11 (trading calendar), R17 (as-traded prices).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

EOD_SOURCE = "orb_rollup"
BENCHMARK_SOURCE = "v1_benchmark_prices"
CALENDAR_NOTE_OPEN = "derived: v1 orb_candles_1d"
CALENDAR_NOTE_CLOSED = "derived: weekday without v1 daily rows (holiday?)"
# A date is a session only if at least this many symbols traded on it. Guards
# against a stray row (e.g. a bad Sunday print) opening a non-trading day.
MIN_SYMBOLS_PER_SESSION = 50

_PAISE = Decimal(100)
_CENT = Decimal("0.01")


def paise_to_rupees(paise: float | str) -> Decimal:
    """v1 orb_candles_1d stores integer paise; market.eod_prices is NUMERIC rupees."""
    return (Decimal(str(paise)) / _PAISE).quantize(_CENT, rounding=ROUND_HALF_UP)


def parse_iso_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


@dataclass
class EodRow:
    price_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None


@dataclass
class TransformStats:
    accepted: int = 0
    rejects: Counter = field(default_factory=Counter)

    def merge(self, other: TransformStats) -> None:
        self.accepted += other.accepted
        self.rejects.update(other.rejects)


def _reject_reason(o: Decimal, h: Decimal, l: Decimal, c: Decimal) -> str | None:
    if min(o, h, l, c) <= 0:
        return "non_positive"
    if l > h or c > h or c < l or o > h or o < l:
        return "ohlc_inconsistent"
    return None


def transform_daily_rows(
    rows: Sequence[Mapping], since: date | None = None
) -> tuple[list[EodRow], TransformStats]:
    """Validate and convert one symbol's v1 daily rows (paise) to rupee rows.

    Rejects (counted, never loaded): unparseable, non-positive, OHLC-inconsistent,
    duplicate dates, and *frozen* bars (R6): zero volume with O=H=L=C equal to the
    previous close, which is how a dead feed forward-fills.
    """
    stats = TransformStats()
    parsed: dict[date, Mapping] = {}
    for r in rows:
        try:
            d = parse_iso_date(r["date"])
        except (KeyError, TypeError, ValueError):
            stats.rejects["bad_date"] += 1
            continue
        if d in parsed:
            stats.rejects["duplicate_date"] += 1
        parsed[d] = r

    out: list[EodRow] = []
    prev_close: Decimal | None = None
    for d in sorted(parsed):
        r = parsed[d]
        try:
            o, h, l, c = (paise_to_rupees(r[k]) for k in ("o", "h", "l", "c"))
        except (KeyError, TypeError, ArithmeticError, ValueError):
            stats.rejects["bad_number"] += 1
            continue
        vol = r.get("v")
        vol_i = int(vol) if vol is not None else None
        reason = _reject_reason(o, h, l, c)
        if reason is None and vol_i == 0 and o == h == l == c and c == prev_close:
            reason = "frozen"
        in_window = since is None or d >= since
        if reason:
            if in_window:
                stats.rejects[reason] += 1
            continue
        prev_close = c
        if not in_window:
            continue
        out.append(EodRow(d, o, h, l, c, vol_i))
    stats.accepted = len(out)
    return out, stats


def derive_calendar(
    symbols_per_date: Mapping[date, int],
    min_symbols: int = MIN_SYMBOLS_PER_SESSION,
) -> list[tuple[date, bool, str]]:
    """Trading calendar from the dates that actually carry daily rows (R11).

    Open: a date with >= ``min_symbols`` symbols. Closed: any weekday between
    the first and last open date with no (or too few) rows -- e.g. 2026-10-02.
    Weekends are never opened by this function, whatever v1's probe said.
    """
    open_days = sorted(
        d for d, n in symbols_per_date.items() if n >= min_symbols and d.weekday() < 5
    )
    if not open_days:
        return []
    open_set = set(open_days)
    out: list[tuple[date, bool, str]] = []
    d = open_days[0]
    while d <= open_days[-1]:
        if d in open_set:
            out.append((d, True, CALENDAR_NOTE_OPEN))
        elif d.weekday() < 5:
            out.append((d, False, CALENDAR_NOTE_CLOSED))
        d += timedelta(days=1)
    return out


def transform_benchmark_docs(
    docs: Iterable[Mapping],
    after: date | None,
    last_value: Decimal | None,
) -> tuple[list[tuple[date, Decimal]], TransformStats]:
    """Benchmark closes (rupees) strictly after ``after``; frozen repeats rejected.

    An index printing the exact same close on consecutive sessions is a dead
    ticker being forward-filled (R10: ^CRSMID flatlined for two months). Those
    rows are dropped so the health check sees the gap and alarms.
    """
    stats = TransformStats()
    by_date: dict[date, Decimal] = {}
    for doc in docs:
        try:
            d = parse_iso_date(doc["date"])
            v = Decimal(str(doc["close"])).quantize(Decimal("0.0001"))
        except (KeyError, TypeError, ValueError, ArithmeticError):
            stats.rejects["bad_row"] += 1
            continue
        if after is not None and d <= after:
            continue
        if v <= 0:
            stats.rejects["non_positive"] += 1
            continue
        by_date[d] = v
    out: list[tuple[date, Decimal]] = []
    prev = last_value
    for d in sorted(by_date):
        v = by_date[d]
        if prev is not None and v == prev:
            stats.rejects["frozen"] += 1
            continue
        out.append((d, v))
        prev = v
    stats.accepted = len(out)
    return out, stats


def build_upsert_sql(
    target: str,
    staging: str,
    columns: Sequence[str],
    key_columns: Sequence[str],
    update_columns: Sequence[str] = (),
    update_guard: str | None = None,
) -> str:
    """INSERT .. SELECT FROM staging ON CONFLICT .. (AGENTS §3.8: COPY -> staging -> merge).

    Idempotent: an update only fires when a value actually changed
    (``IS DISTINCT FROM``), so re-running the same load updates zero rows.
    ``RETURNING (xmax = 0)`` lets the caller count inserts vs updates.
    """
    for name in (*columns, *key_columns, *update_columns):
        if not name.replace("_", "").isalnum():
            raise ValueError(f"unsafe column name: {name!r}")
    cols = ", ".join(columns)
    keys = ", ".join(key_columns)
    head = f"INSERT INTO {target} AS t ({cols})\nSELECT {cols} FROM {staging}\n"
    if not update_columns:
        return (
            head + f"ON CONFLICT ({keys}) DO NOTHING\nRETURNING (xmax = 0) AS inserted"
        )
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_columns)
    changed = " OR ".join(
        f"t.{c} IS DISTINCT FROM EXCLUDED.{c}" for c in update_columns
    )
    where = f"({changed})" if not update_guard else f"({update_guard}) AND ({changed})"
    return (
        head
        + f"ON CONFLICT ({keys}) DO UPDATE SET {sets}\nWHERE {where}\n"
        + "RETURNING (xmax = 0) AS inserted"
    )


def map_symbols_to_securities(
    securities: Mapping[str, int],
    aliases: Iterable[tuple[str, str]],
) -> dict[str, list[int]]:
    """v1 NSE symbol -> v2 NSE security_ids.

    Direct match on symbol, plus renames: if a held security still carries an
    old symbol (``old -> new`` in market.symbol_aliases), the new symbol's v1
    rows are loaded against the old security too.
    """
    out: dict[str, list[int]] = {sym: [sid] for sym, sid in securities.items()}
    for old, new in aliases:
        sid = securities.get(old)
        if sid is not None and sid not in out.setdefault(new, []):
            out[new].append(sid)
    return out

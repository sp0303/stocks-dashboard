"""SQL for the ledger resync: staging DDL and MERGE statements (AGENTS §3.8).

Pure string builders over constant specs; nothing here touches a connection. Every write
goes COPY -> temp staging (ON COMMIT DROP) -> ``MERGE``. Updates fire only when a value
actually changed (``IS DISTINCT FROM``), so re-applying the same rows is a no-op.
"""

from __future__ import annotations

from dataclasses import dataclass

REJECT_CHECK = "v1_ledger_sync_reject"


@dataclass(frozen=True)
class Spec:
    target: str
    columns: tuple[tuple[str, str], ...]  # (name, staging type)
    key: tuple[str, ...]
    update: tuple[str, ...] = ()  # empty => insert-only (ledger is append-only, R13.5)

    @property
    def names(self) -> list[str]:
        return [c for c, _ in self.columns]

    @property
    def staging(self) -> str:
        return "stg_" + self.target.replace(".", "_")


_T, _U, _D, _N, _B = "text", "uuid", "date", "numeric", "boolean"

SPECS: dict[str, Spec] = {
    "managers": Spec(
        "core.managers",
        (("manager_id", _U), ("legacy_id", _T), ("name", _T), ("firm", _T), ("email", _T), ("is_active", _B)),
        ("manager_id",),
        ("legacy_id", "name", "firm", "email", "is_active"),
    ),
    "clients": Spec(
        "core.clients",
        (("client_id", _U), ("legacy_id", _T), ("manager_id", _U), ("name", _T),
         ("client_code", _T), ("broker", _T), ("status", _T)),
        ("client_id",),
        ("legacy_id", "manager_id", "name", "client_code", "broker", "status"),
    ),
    "uploads": Spec(
        "ledger.uploads",
        (("legacy_id", _T), ("client_id", _U), ("version", "int"), ("file_name", _T), ("file_sha256", "bytea"),
         ("broker_format", _T), ("date_from", _D), ("date_to", _D), ("rows_total", "int"),
         ("rows_imported", "int"), ("rows_duplicate", "int"), ("rows_rejected", "int"), ("status", _T)),
        ("client_id", "file_sha256"),
    ),
    "trades": Spec(
        "ledger.trades",
        (("client_id", _U), ("legacy_id", _T), ("fingerprint", _T), ("symbol", _T), ("isin", _T),
         ("trade_date", _D), ("exchange", _T), ("segment", _T), ("series", _T), ("trade_type", _T),
         ("auction", _B), ("quantity", _N), ("price", _N), ("broker_trade_id", _T), ("broker_order_id", _T),
         ("executed_at", "timestamptz"), ("charges", _N), ("charges_known", _B), ("source", _T),
         ("note", _T), ("extra", "jsonb")),
        ("client_id", "fingerprint"),
    ),
    "corporate_actions": Spec(
        "ledger.corporate_actions",
        (("key", _T), ("isin", _T), ("symbol", _T), ("ex_date", _D), ("type", _T),
         ("qty_multiplier", _N), ("amount_per_share", _N), ("subject", _T), ("source", _T)),
        ("key",),
        ("isin", "symbol", "ex_date", "type", "qty_multiplier", "amount_per_share", "subject", "source"),
    ),
    "dividends": Spec(
        "ledger.dividends",
        (("client_id", _U), ("symbol", _T), ("ex_date", _D), ("amount_per_share", _N),
         ("quantity", _N), ("source", _T)),
        ("client_id", "symbol", "ex_date"),
        ("amount_per_share", "quantity", "source"),
    ),
    "stock_theses": Spec(
        "research.stock_theses",
        (("client_id", _U), ("symbol", _T), ("thesis", "jsonb")),
        ("client_id", "symbol"),
        ("thesis",),
    ),
    "watchlists": Spec(
        "research.watchlists",
        (("watchlist_id", _U), ("owner_type", _T), ("owner_id", _U), ("name", _T), ("is_default", _B)),
        ("watchlist_id",),
    ),
    "watchlist_entries": Spec(
        "research.watchlist_entries",
        (("watchlist_id", _U), ("symbol", _T), ("added_date", _D), ("added_price", _N), ("why", _T),
         ("remarks", _T), ("risks", _T), ("sector", _T), ("alert_price", _N), ("alert_date", _D)),
        ("watchlist_id", "symbol"),
        ("added_date", "added_price", "why", "remarks", "risks", "sector", "alert_price", "alert_date"),
    ),
    "board_items": Spec(
        "research.board_items",
        (("item_id", _U), ("owner_type", _T), ("owner_id", _U), ("symbol", _T), ("lane", _T),
         ("entry_price", _N), ("exit_price", _N), ("why", _T), ("sort_order", "int")),
        ("item_id",),
        ("lane", "entry_price", "exit_price", "why", "sort_order"),
    ),
}
# FK order: parents before children.
APPLY_ORDER = (
    "managers", "clients", "uploads", "trades", "corporate_actions", "dividends",
    "stock_theses", "watchlists", "watchlist_entries", "board_items",
)


def _safe(name: str) -> str:
    if not name.replace("_", "").replace(".", "").isalnum():
        raise ValueError(f"unsafe identifier: {name!r}")
    return name


def staging_ddl(spec: Spec) -> str:
    cols = ", ".join(f"{_safe(c)} {t}" for c, t in spec.columns)
    return f"CREATE TEMP TABLE IF NOT EXISTS {_safe(spec.staging)} ({cols}) ON COMMIT DROP"


def merge_sql(spec: Spec) -> str:
    """MERGE staging into target. Insert-only specs ignore matched rows."""
    t, s = _safe(spec.target), _safe(spec.staging)
    on = " AND ".join(f"t.{_safe(k)} = s.{k}" for k in spec.key)
    cols = ", ".join(_safe(c) for c in spec.names)
    vals = ", ".join(f"s.{c}" for c in spec.names)
    sql = f"MERGE INTO {t} AS t USING {s} AS s ON {on}\n"
    if spec.update:
        changed = " OR ".join(f"t.{_safe(c)} IS DISTINCT FROM s.{c}" for c in spec.update)
        sets = ", ".join(f"{c} = s.{c}" for c in spec.update)
        sql += f"WHEN MATCHED AND ({changed}) THEN UPDATE SET {sets}\n"
    return sql + f"WHEN NOT MATCHED THEN INSERT ({cols}) VALUES ({vals})"


REJECTS_DDL = (
    "CREATE TEMP TABLE IF NOT EXISTS stg_v1_rejects (entity_key text, details jsonb) ON COMMIT DROP"
)
REJECTS_INSERT = (
    "INSERT INTO ops.dq_issues (check_name, severity, entity_key, details) "
    "SELECT $1, 'WARN', r.entity_key, r.details FROM stg_v1_rejects r "
    "WHERE NOT EXISTS (SELECT 1 FROM ops.dq_issues d WHERE d.check_name = $1 "
    "AND d.entity_key = r.entity_key AND NOT d.resolved)"
)
ORPHAN_TRADES_DDL = (
    "CREATE TEMP TABLE IF NOT EXISTS stg_v1_orphan_trades (client_id uuid, fingerprint text) ON COMMIT DROP"
)
# Tombstone, never DELETE (R13.5). Only rows still live are touched.
ORPHAN_TRADES_FLAG = (
    "UPDATE ledger.trades t SET deleted_at = now() FROM stg_v1_orphan_trades s "
    "WHERE t.client_id = s.client_id AND t.fingerprint = s.fingerprint AND t.deleted_at IS NULL"
)
ORPHAN_CLIENTS_FLAG = (
    "UPDATE core.clients SET status = 'INACTIVE' WHERE client_id = ANY($1::uuid[]) AND status <> 'INACTIVE'"
)
ORPHAN_MANAGERS_FLAG = (
    "UPDATE core.managers SET is_active = false WHERE manager_id = ANY($1::uuid[]) AND is_active"
)
ADVISORY_LOCK = "SELECT pg_try_advisory_xact_lock(hashtext('pi_v1_ledger_sync'))"

SNAPSHOT_SQL = {
    "managers": "SELECT manager_id, legacy_id, name, firm, email::text AS email, is_active FROM core.managers",
    "clients": (
        "SELECT c.client_id, c.legacy_id, c.manager_id, c.name, c.client_code, c.broker, c.status, "
        "(SELECT count(*) FROM ledger.trades t WHERE t.client_id = c.client_id AND t.deleted_at IS NULL) "
        "AS active_trades FROM core.clients c"
    ),
    # v1_origin: carried a v1 id, predates the cutover, or was written by this sync.
    "trades": (
        "SELECT client_id, fingerprint, legacy_id, symbol, trade_type, quantity, "
        "deleted_at IS NOT NULL AS deleted, "
        "(legacy_id IS NOT NULL OR created_at < $1::timestamptz OR extra ? 'v1_sync') AS v1_origin "
        "FROM ledger.trades"
    ),
    "uploads": "SELECT legacy_id, client_id, file_sha256 FROM ledger.uploads",
    "corporate_actions": (
        "SELECT key, isin, symbol, ex_date, type, qty_multiplier, amount_per_share, subject, source "
        "FROM ledger.corporate_actions"
    ),
    "dividends": "SELECT client_id, symbol, ex_date, amount_per_share, quantity, source FROM ledger.dividends",
    "theses": "SELECT client_id, symbol, thesis::text AS thesis FROM research.stock_theses",
    "watchlists": "SELECT watchlist_id, owner_type, owner_id, name FROM research.watchlists",
    "watchlist_entries": (
        "SELECT watchlist_id, symbol, added_date, added_price, why, remarks, risks, sector, alert_price, "
        "alert_date FROM research.watchlist_entries"
    ),
    "board_items": (
        "SELECT item_id, owner_type, owner_id, symbol, lane, entry_price, exit_price, why, sort_order "
        "FROM research.board_items"
    ),
    "reject_keys": "SELECT entity_key FROM ops.dq_issues WHERE check_name = $1 AND NOT resolved",
}

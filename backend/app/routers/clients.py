"""Manager routes: manage clients + tradebook upload (no auth in Phase 1)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

import asyncio
from collections import Counter

from starlette.concurrency import run_in_threadpool

from app.models.schemas import ClientCreate, ClientUpdate
from app.routers.portfolio import _actions_for, cached_performance_series
from app.services import analytics, auth, ingestion
from app.services.engine import compute_round_trips, split_intraday
from app.store import get_store

router = APIRouter(prefix="/api", tags=["clients"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _delivery_trades(client_id: str) -> list[dict]:
    """Delivery/swing trades only, matching what every client-level endpoint gets from
    portfolio._trades_or_404.

    The manager routes used to read store.list_trades() raw, so same-day round trips
    (intraday/speculative under Section 43(5)) were folded into the book's invested value,
    holdings and round trips here while the client's own screen excluded them. The same
    client therefore reported different numbers depending on which page you opened it from.
    Intraday P&L is real but it is not investment: the capital comes back the same day and
    is margin-funded, so it belongs in its own report, not in the book's cost basis.
    """
    delivery, _ = split_intraday(await get_store().list_trades(client_id))
    return delivery


@router.get("/managers/{manager_id}/clients")
async def list_clients(manager_id: str, _: auth.Identity = Depends(auth.require_manager_scope)):
    store = get_store()
    clients = await store.list_clients(manager_id)
    for c in clients:
        c["trade_count"] = await store.count_trades(c["id"])
    return {"data": clients}


@router.get("/managers/{manager_id}/metrics")
async def manager_metrics(manager_id: str, _: auth.Identity = Depends(auth.require_manager_scope)):
    """Book-wide metrics aggregated across all of a manager's clients."""
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    clients = await store.list_clients(manager_id)
    # Read every client's trades concurrently — a serial await-per-client loop made this
    # O(clients) round-trips and was a big part of the manager page's load time.
    trades_lists = await asyncio.gather(*(_delivery_trades(c["id"]) for c in clients))
    # The Trades column is the count of trades actually stored — the delivery-only list
    # above is consolidated (same-day round trips collapse to VWAP rows), so len() of it
    # would understate it (one client: 1,456 shown against 4,219 stored).
    raw_counts = await asyncio.gather(*(store.count_trades(c["id"]) for c in clients))
    # Corporate actions per client, so a split/bonus is applied here exactly as it is on the
    # client's own page; client_code/status were never passed before, so the Code column
    # was blank for every client.
    actions_lists = await asyncio.gather(*(_actions_for(t) for t in trades_lists))
    payload = [
        {"id": c["id"], "name": c["name"], "trades": t, "trade_count": n, "actions": a,
         "client_code": c.get("client_code") or "", "status": c.get("status") or "ACTIVE"}
        for c, t, n, a in zip(clients, trades_lists, raw_counts, actions_lists)
    ]
    return {"data": analytics.manager_metrics(payload)}


@router.get("/managers/{manager_id}/performance")
async def manager_performance(manager_id: str, _: auth.Identity = Depends(auth.require_manager_scope)):
    """Manager-level performance, in two parts:
    - "book": the whole book's value summed across every client's own real,
      mark-to-market performance curve, compared against the same 4 benchmark indices
      used on a client's own Performance tab — the manager's overall portfolio vs.
      Nifty/Midcap/Largecap/Smallcap.
    - "clients": each client's own % return over time (NOT absolute ₹ — clients deploy
      wildly different capital, so only a normalized return is fair to plot on one shared
      chart; a client with 10x the capital would otherwise dominate the y-axis with no
      bearing on who's actually performing better).
    Every client's real prices are fetched concurrently so this scales reasonably with
    book size."""
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    clients = await store.list_clients(manager_id)

    async def _one_client(c: dict) -> tuple[list[dict] | None, dict | None]:
        trades = await _delivery_trades(c["id"])
        if not trades:
            return None, None
        actions = await _actions_for(trades)
        series = await cached_performance_series(c["id"], trades, actions)
        # Time-weighted return, so the comparison between clients is fair regardless of
        # when each of them added money. The old formula divided P&L by OPEN COST BASIS,
        # which made a client's line fall simply because they bought more (one real
        # account dropped 11.60% -> 9.09% on a purchase day, having lost nothing), and
        # collapsed to a flat 0% for anyone who closed out entirely, since the guard for
        # a zero denominator returned 0.
        nav = analytics.twr_series(series)
        pct_series = [{"date": n["date"], "return_pct": round(n["nav"] - 100, 2)} for n in nav]
        return series, {"id": c["id"], "name": c["name"], "series": pct_series}

    results = await asyncio.gather(*(_one_client(c) for c in clients))
    client_series = [r[0] for r in results if r[0]]
    client_summaries = [r[1] for r in results if r[1] is not None]

    book = analytics.aggregate_performance_series(client_series)
    return {"data": {"book": book, "clients": client_summaries}}


@router.get("/managers/{manager_id}/holdings/heatmap")
async def manager_holdings_heatmap(
    manager_id: str,
    client_ids: str = None,
    mode: str = Query("day", pattern="^(day|range)$"),
    day: str | None = Query(None, description="YYYY-MM-DD; omitted = live (today's quotes)"),
    start: str | None = Query(None, description="range: common start date; omitted = each stock's tracking day"),
    grain: str = Query("auto", pattern="^(auto|day|week|month)$"),
    _: auth.Identity = Depends(auth.require_manager_scope),
):
    """Returns for every stock the selected clients hold: one day's move (`mode=day`), or
    period-by-period returns from each stock's tracking day (`mode=range`). Decimals.
    Daily closes come from the stored daily candles first, so this makes no broker calls
    for stocks already in the store."""
    from app.services import heatmap, market_data

    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    clients = await store.list_clients(manager_id)
    if client_ids:
        wanted = set(client_ids.split(","))
        clients = [c for c in clients if c["id"] in wanted]
    # Quantities and tracking days only: no live prices here, so a past day or the
    # tracking grid never waits on 40 quote lookups (that made the Day view take ~20 s).
    meta: dict[str, dict] = {}
    for c in clients:
        trades = await _delivery_trades(c["id"])
        if not trades:
            continue
        hold = analytics.build_holdings(trades, with_prices=False, actions=await _actions_for(trades))
        for h in hold["holdings"]:
            if (h.get("quantity") or 0) <= 0:
                continue
            m = meta.setdefault(h["symbol"], {"qty": 0.0, "invested": 0.0, "clients": 0, "entry_date": None})
            m["qty"] += h["quantity"]
            m["invested"] += h.get("invested_value") or 0
            m["clients"] += 1
            ed = (h.get("entry_date") or "")[:10] or None
            if ed and (m["entry_date"] is None or ed < m["entry_date"]):
                m["entry_date"] = ed
    if not meta:
        return {"data": {"mode": mode, "tiles": [], "columns": [], "rows": []}}
    weights = {s: m["invested"] for s, m in meta.items()}

    if mode == "day" and not day:
        quotes = await run_in_threadpool(market_data.get_quote_details, list(weights))
        tiles = []
        for sym in weights:
            q = quotes.get(sym, {})
            price, prev = q.get("price"), q.get("prev_close")
            ret = (price / prev - 1.0) if price and prev else None
            tiles.append({"symbol": sym, "ret": ret, "close": price, "prev_close": prev, **meta[sym]})
        tiles.sort(key=lambda t: (t["ret"] is None, -(t["ret"] or 0)))
        return {"data": {"mode": "day", "day": "live", "tiles": tiles}}

    earliest = min((m["entry_date"] for m in meta.values() if m["entry_date"]), default=None)
    from_date = min(filter(None, [start, day, earliest])) if any([start, day, earliest]) else None
    actions = await _actions_for([{"symbol": s} for s in weights])
    by_sym: dict[str, list[dict]] = {}
    for a in actions:
        by_sym.setdefault(a.get("symbol"), []).append(a)

    async def _series(sym):
        hist = await run_in_threadpool(market_data.get_history, sym, from_date, "1d", "NSE")
        return sym, heatmap.adjusted_closes(hist.get("points", []), by_sym.get(sym))
    series = {s: pts for s, pts in await asyncio.gather(*(_series(s) for s in weights)) if pts}
    # The last date most stocks share, not the newest single bar: a fallback provider can
    # stamp a weekend "bar" for one symbol, which would otherwise end every row there.
    from collections import Counter
    lasts = Counter(pts[-1][0] for pts in series.values())
    latest = max(lasts, key=lambda d: (lasts[d], d)) if lasts else None

    if mode == "day":
        rets = heatmap.day_returns(series, day)
        tiles = [{"symbol": s, **rets.get(s, {"ret": None}), **meta[s]} for s in weights]
        tiles.sort(key=lambda t: (t["ret"] is None, -(t["ret"] or 0)))
        return {"data": {"mode": "day", "day": day, "latest": latest, "tiles": tiles}}

    end = latest or datetime.now(timezone.utc).date().isoformat()
    starts = {s: (start or meta[s]["entry_date"]) for s in series}
    first = min(filter(None, starts.values()), default=end)
    g = heatmap.pick_grain(first, end) if grain == "auto" else grain
    m = heatmap.range_matrix(series, starts, end, g)
    for r in m["rows"]:
        r.update(meta[r["symbol"]])
    m["rows"].sort(key=lambda r: -(weights.get(r["symbol"]) or 0))
    missing = sorted(set(weights) - set(series))
    return {"data": {"mode": "range", "end": end, "no_history": missing, **m}}


@router.get("/managers/{manager_id}/holdings")
async def manager_holdings(manager_id: str, client_ids: str = None, _: auth.Identity = Depends(auth.require_manager_scope)):
    """Aggregated holdings across selected clients for a manager.
    Returns holdings grouped by symbol with client names, quantities, and holding %.

    Args:
        manager_id: The manager's ID
        client_ids: Comma-separated list of client IDs to include (all if not specified)
    """
    from app.services import analytics

    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")

    all_clients = await store.list_clients(manager_id)
    if not all_clients:
        return {"data": {"holdings": [], "totals": {"market_value": 0, "invested_value": 0, "unrealized_pnl": 0}}}

    # Filter clients if specific ones requested
    if client_ids:
        requested = set(client_ids.split(","))
        clients = [c for c in all_clients if c["id"] in requested]
    else:
        clients = all_clients

    if not clients:
        raise HTTPException(400, "no valid clients selected")

    # Aggregate holdings from all selected clients
    aggregated = {}
    totals = {"market_value": 0, "invested_value": 0, "unrealized_pnl": 0}

    for client in clients:
        trades = await _delivery_trades(client["id"])
        if not trades:
            continue

        actions = await _actions_for(trades)
        holdings_data = analytics.build_holdings(trades, with_prices=True, actions=actions)

        for holding in holdings_data.get("holdings", []):
            symbol = holding["symbol"]
            qty = holding.get("quantity") or 0  # Use "quantity" not "qty"; coerce None→0

            if symbol not in aggregated:
                aggregated[symbol] = {
                    "symbol": symbol,
                    "qty": 0,
                    "buy_avg": 0,
                    "buy_value": 0,
                    "ltp": holding.get("ltp", 0),
                    "present_value": 0,
                    "pnl": 0,
                    "pnl_pct": 0,
                    "clients": []
                }

            # Add this client's contribution (coerce None→0: a symbol Angel couldn't price
            # returns market_value/pnl = None, which used to crash the += aggregation).
            aggregated[symbol]["qty"] += qty
            aggregated[symbol]["buy_value"] += holding.get("invested_value") or 0
            aggregated[symbol]["present_value"] += holding.get("market_value") or 0
            aggregated[symbol]["pnl"] += holding.get("unrealized_pnl") or 0
            aggregated[symbol]["ltp"] = holding.get("ltp") or aggregated[symbol]["ltp"]

            # Track which client holds this with full name
            if qty > 0:
                aggregated[symbol]["clients"].append({
                    "name": client["name"],
                    "qty": qty
                })

        # Update totals (coerce None→0)
        _t = holdings_data.get("totals", {})
        totals["market_value"] += _t.get("market_value") or 0
        totals["invested_value"] += _t.get("invested_value") or 0
        totals["unrealized_pnl"] += _t.get("unrealized_pnl") or 0

    # Calculate buy average and percentages
    holdings_list = []
    for symbol, data in aggregated.items():
        # Calculate buy average from invested value and quantity
        if data["qty"] > 0:
            data["buy_avg"] = data["buy_value"] / data["qty"]
        else:
            data["buy_avg"] = 0

        # Calculate P&L percentage
        if data["buy_value"] > 0:
            data["pnl_pct"] = (data["pnl"] / data["buy_value"] * 100)
        else:
            data["pnl_pct"] = 0

        # Calculate holding percentage
        holding_pct = (data["present_value"] / totals["market_value"] * 100) if totals["market_value"] > 0 else 0
        data["holding_pct"] = holding_pct

        holdings_list.append(data)

    # Sort by market value descending
    holdings_list.sort(key=lambda x: x["present_value"], reverse=True)

    return {
        "data": {
            "holdings": holdings_list,
            "totals": totals,
            "client_count": len(clients)
        }
    }


@router.get("/managers/{manager_id}/trade-log")
async def manager_trade_log(manager_id: str, _: auth.Identity = Depends(auth.require_manager_scope)):
    """Flat closed-trade log across every client — one row per FIFO round trip, with the
    client as the 'account' and the buy-trade note as 'reason for buying'. This is the
    spreadsheet-style journal view: Account | Stock | Qty | Buy | Sell | Days | PNL |
    PNL% | Reason. Round trips are computed in-process (no external calls)."""
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    clients = await store.list_clients(manager_id)

    rows: list[dict] = []
    for c in clients:
        trades = await _delivery_trades(c["id"])
        if not trades:
            continue
        rts = await run_in_threadpool(compute_round_trips, trades)
        journal = await store.get_trade_journal(c["id"])

        # Merge every closed cycle of a stock into ONE line per (account, symbol), like the
        # Playbook — quantity-weighted average buy/sell, total P&L, average holding, and a
        # cycle count. The reason attaches to the latest buy lot (edits persist there).
        groups: dict[str, dict] = {}
        for rt in rts:
            sym = rt["symbol"]
            g = groups.get(sym)
            if g is None:
                g = groups[sym] = {"symbol": sym, "qty": 0.0, "buy_val": 0.0, "sell_val": 0.0,
                                   "pnl": 0.0, "days_w": 0.0, "cycles": 0, "last_sell": "",
                                   "last_buy": "", "rep_fp": None, "any_note": ""}
            q = rt["quantity"]
            g["qty"] += q
            g["buy_val"] += q * rt["buy_price"]
            g["sell_val"] += q * rt["sell_price"]
            g["pnl"] += rt["pnl"]
            g["days_w"] += (rt["days"] or 0) * q
            g["cycles"] += 1
            g["last_sell"] = max(g["last_sell"], rt.get("sell_date") or "")
            fp = rt.get("buy_fingerprint")
            if (rt.get("buy_date") or "") >= g["last_buy"]:
                g["last_buy"], g["rep_fp"] = rt.get("buy_date") or "", fp
            note = (journal.get(fp) or {}).get("note", "")
            if note and not g["any_note"]:
                g["any_note"] = note

        for g in groups.values():
            q = g["qty"] or 1
            buy_price = g["buy_val"] / q
            sell_price = g["sell_val"] / q
            rep_note = (journal.get(g["rep_fp"]) or {}).get("note", "")
            rows.append({
                "account": c["name"], "client_id": c["id"], "symbol": g["symbol"],
                "quantity": round(g["qty"], 2),
                "buy_price": round(buy_price, 2), "sell_price": round(sell_price, 2),
                "days": round(g["days_w"] / q), "cycles": g["cycles"],
                "sell_date": g["last_sell"], "pnl": round(g["pnl"], 2),
                "pnl_pct": round(g["pnl"] / g["buy_val"] * 100, 2) if g["buy_val"] else 0.0,
                "reason": rep_note or g["any_note"], "buy_fingerprint": g["rep_fp"],
            })
    rows.sort(key=lambda r: r.get("sell_date") or "", reverse=True)
    return {"data": rows, "meta": {"total": len(rows), "clients": len(clients)}}


@router.get("/clients")
async def list_all_clients(ident: auth.Identity = Depends(auth.get_identity)):
    store = get_store()
    # Admin sees the whole book; a manager sees only their own clients.
    clients = await store.list_clients(None if ident.role == "admin" else ident.manager_id)
    for c in clients:
        c["trade_count"] = await store.count_trades(c["id"])
    return {"data": clients}


@router.post("/clients")
async def create_client(body: ClientCreate, ident: auth.Identity = Depends(auth.get_identity)):
    store = get_store()
    if ident.role != "admin" and ident.manager_id != body.portfolio_manager_id:
        raise HTTPException(403, "you can only add clients under your own account")
    if not await store.get_manager(body.portfolio_manager_id):
        raise HTTPException(404, "portfolio manager not found")
    doc = {
        **body.model_dump(),
        "status": "ACTIVE",
        "onboarded_at": _now(),
        "created_at": _now(),
    }
    return {"data": await store.create_client(doc)}


@router.get("/clients/{client_id}")
async def get_client(client_id: str, _: auth.Identity = Depends(auth.require_client_access)):
    store = get_store()
    c = await store.get_client(client_id)
    if not c:
        raise HTTPException(404, "client not found")
    c["trade_count"] = await store.count_trades(client_id)
    return {"data": c}


@router.patch("/clients/{client_id}")
async def update_client(client_id: str, body: ClientUpdate, _: auth.Identity = Depends(auth.require_client_access)):
    store = get_store()
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = await store.update_client(client_id, patch)
    if not updated:
        raise HTTPException(404, "client not found")
    return {"data": updated}


@router.delete("/clients/{client_id}")
async def delete_client(client_id: str, _: auth.Identity = Depends(auth.require_client_access)):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    # cascades trades + uploads + watchlist in the store
    await store.delete_client(client_id)
    return {"data": {"deleted": client_id}}


@router.post("/clients/{client_id}/tradebooks")
async def upload_tradebook(client_id: str, file: UploadFile = File(...),
                           force: bool = Query(False, description="re-import a file already uploaded; trades are still deduped"),
                           _: auth.Identity = Depends(auth.require_client_access)):
    store = get_store()
    client = await store.get_client(client_id)
    if not client:
        raise HTTPException(404, "client not found")

    content = await file.read()
    fhash = ingestion.file_hash(content)
    if not force and await store.upload_exists(client_id, fhash):
        raise HTTPException(409, "this exact file was already uploaded")

    import io

    parsed = ingestion.parse_tradebook(io.BytesIO(content), client_id_hint=client.get("client_code"))
    if not parsed.trades:
        raise HTTPException(422, f"no valid trades found ({'; '.join(parsed.errors[:3])})")

    # A tradebook belongs to one broker account. If the file names an account and this
    # client already has a different one, it is someone else's file: reject it before a
    # single trade is written (force does not override this — it only re-imports a file).
    stored_code = (client.get("client_code") or "").strip().upper()
    file_code = (parsed.file_client_id or "").strip().upper()
    if stored_code and file_code and file_code != stored_code:
        raise HTTPException(
            422,
            f"this tradebook is for account {file_code}, but this client's account is "
            f"{stored_code}. Upload it to the right client, or correct the client's code first.",
        )
    # A file we cannot tie to an account is never accepted onto an account we know.
    if stored_code and not file_code:
        raise HTTPException(
            422,
            f"this file does not show which account it is for, so it cannot be checked "
            f"against {stored_code}. Upload the broker's original export.",
        )
    # A client without a code yet would adopt the file's code: refuse if another client owns it.
    if file_code and not stored_code:
        owner = next((c for c in await store.list_clients()
                      if c["id"] != client_id and (c.get("client_code") or "").strip().upper() == file_code), None)
        if owner:
            raise HTTPException(
                422,
                f"this tradebook is for account {file_code}, which belongs to another client "
                f"({owner.get('name')}). Upload it there.",
            )

    # tag every trade with our internal client id and the upload that brought it in, so
    # the upload can be deleted later (a deduped trade keeps its first upload's id)
    import uuid
    upload_id = uuid.uuid4().hex
    for t in parsed.trades:
        t["client_id"] = client_id
        t["upload_id"] = upload_id

    version = await store.next_upload_version(client_id)
    inserted, dupes = await store.insert_trades(parsed.trades)

    upload = await store.create_upload(
        {
            "id": upload_id,
            "client_id": client_id,
            "version": version,
            "file_name": file.filename,
            "file_hash": fhash,
            "uploaded_at": _now(),
            "date_from": parsed.date_from,
            "date_to": parsed.date_to,
            "row_count": len(parsed.trades),
            "imported_count": inserted,
            "duplicate_count": dupes,
            "error_count": len(parsed.errors),
            "status": "IMPORTED" if not parsed.errors else "PARTIAL",
        }
    )
    # if the excel carried a client code and the client didn't have one, store it
    if parsed.client_id and not client.get("client_code"):
        await store.update_client(client_id, {"client_code": parsed.client_id})

    return {
        "data": {
            "upload": upload,
            "summary": {
                "parsed": len(parsed.trades),
                "imported": inserted,
                "duplicates": dupes,
                "errors": len(parsed.errors),
            },
        }
    }


@router.get("/clients/{client_id}/tradebooks")
async def list_uploads(client_id: str, _: auth.Identity = Depends(auth.require_client_access)):
    store = get_store()
    ups = await store.list_uploads(client_id)
    linked = Counter(t.get("upload_id") for t in await store.list_trades(client_id))
    for u in ups:
        # trades still in the book from this upload; None for uploads made before trades
        # were linked to their upload (those can only have their record removed)
        n = linked.get(u.get("id"), 0)
        u["trade_count"] = None if (not n and u.get("imported_count") and u.get("status") != "DELETED") else n
    return {"data": ups}


@router.delete("/clients/{client_id}/tradebooks/{upload_id}")
async def delete_upload(client_id: str, upload_id: str, _: auth.Identity = Depends(auth.require_client_access)):
    """Remove an upload and the trades it imported. Manual trades and trades that came in
    through another upload are untouched. The upload stays listed as DELETED."""
    store = get_store()
    removed = await store.delete_upload(client_id, upload_id, _now())
    if removed is None:
        raise HTTPException(404, "upload not found or already deleted")
    return {"data": {"upload_id": upload_id, "trades_removed": removed}}

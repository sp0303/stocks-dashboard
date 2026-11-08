"""Ingest Worker (:8204): Lossless broker tradebook ingestion adhering to Rule R13.

Supports Zerodha Console and Upstox tradebook CSVs.
Extracts every broker column, generates deterministic fingerprints,
stores rejected rows in ledger.upload_rejects, and triggers portfolio.recompute.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator, Dict, List, Optional, Tuple
from uuid import UUID

import asyncpg
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from pi_workers.portfolio_worker import recompute_single_client
from pi_workers.tradebook_store import insert_trades
from pi_workers.tradebook_xlsx import is_xlsx, parse_tradebook_xlsx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pi_workers.ingest")

PORT = int(os.environ.get("PORT", 8204))

_pool: Optional[asyncpg.Pool] = None


async def get_db_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn=os.environ["DATABASE_URL"], min_size=2, max_size=5)
    return _pool


def parse_tradebook_csv(
    file_bytes: bytes, broker_format: str
) -> Tuple[List[Dict], List[Tuple[int, str, dict]]]:
    """Parses broker CSV into valid rows and rejects (Rule R13)."""
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    valid_rows = []
    rejects = []

    for row_no, row in enumerate(reader, start=2):
        try:
            # Handle Zerodha Console layout
            if broker_format == "ZERODHA":
                symbol = row.get("symbol", "").strip().upper()
                trade_date_raw = row.get("trade_date", "").strip()
                t_date = datetime.strptime(trade_date_raw, "%Y-%m-%d").date()
                trade_type = row.get("trade_type", "").strip().lower()
                quantity = float(row.get("quantity", 0))
                price = float(row.get("price", 0))
                trade_id = row.get("trade_id", "").strip() or f"gen_{row_no}"
                order_id = row.get("order_id", "").strip()
                exchange = row.get("exchange", "NSE").strip().upper()
                segment = row.get("segment", "EQ").strip().upper()
                isin = row.get("isin", "").strip()

            # Handle Upstox layout
            elif broker_format == "UPSTOX":
                symbol = row.get("Scrip Name", row.get("Symbol", "")).strip().upper()
                trade_date_raw = row.get("Trade Date", "").strip()
                t_date = datetime.strptime(trade_date_raw, "%d/%m/%Y").date()
                side_raw = row.get("Side", row.get("Type", "")).strip().lower()
                trade_type = "buy" if "buy" in side_raw else "sell"
                quantity = float(row.get("Quantity", row.get("Qty", 0)))
                price = float(row.get("Price", row.get("Rate", 0)))
                trade_id = row.get("Trade No", "").strip() or f"gen_{row_no}"
                order_id = row.get("Order No", "").strip()
                exchange = row.get("Exchange", "NSE").strip().upper()
                segment = "EQ"
                isin = None
            else:
                rejects.append((row_no, f"Unsupported broker format {broker_format}", row))
                continue

            if not symbol or quantity <= 0 or price < 0:
                rejects.append((row_no, "Invalid symbol, quantity, or price", row))
                continue

            valid_rows.append({
                "symbol": symbol,
                "isin": isin,
                "trade_date": t_date,
                "exchange": exchange,
                "segment": segment,
                "trade_type": trade_type,
                "quantity": quantity,
                "price": price,
                "broker_trade_id": trade_id,
                "broker_order_id": order_id,
                "extra": row,
            })
        except Exception as e:
            rejects.append((row_no, f"Parsing exception: {str(e)}", row))

    return valid_rows, rejects


async def ingest_tradebook(
    client_id: UUID,
    file_name: str,
    file_bytes: bytes,
    broker_format: str,
) -> Dict:
    """Stores the raw upload and its trades (R13). Takes Zerodha/Groww .xlsx and broker CSVs."""
    file_code: Optional[str] = None
    if is_xlsx(file_name, file_bytes):
        parsed = parse_tradebook_xlsx(file_bytes)
        valid_rows, rejects, file_code = parsed.rows, parsed.rejects, parsed.file_client_code
        broker_format = "ZERODHA" if parsed.layout == "ZERODHA" else "OTHER"
    else:
        valid_rows, rejects = parse_tradebook_csv(file_bytes, broker_format)
        broker_format = broker_format if broker_format in ("ZERODHA", "UPSTOX") else "OTHER"
    file_sha256 = hashlib.sha256(file_bytes).digest()
    pool = await get_db_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            client = await conn.fetchrow(
                "SELECT client_code FROM core.clients WHERE client_id = $1 AND deleted_at IS NULL;", client_id
            )
            if client is None:
                raise HTTPException(status_code=404, detail="Client not found.")
            code = (client["client_code"] or "").strip().upper()
            if file_code and code and file_code != code:
                raise HTTPException(
                    status_code=400,
                    detail=f"This file is for account {file_code} but the client is {code}. Nothing was imported.",
                )
            existing = await conn.fetchval(
                "SELECT upload_id FROM ledger.uploads WHERE client_id = $1 AND file_sha256 = $2;",
                client_id, file_sha256,
            )
            if existing:
                raise HTTPException(status_code=400, detail="This exact tradebook file was already uploaded for this client.")

            dates = [r["trade_date"] for r in valid_rows]
            upload_id = await conn.fetchval(
                """
                INSERT INTO ledger.uploads (
                    client_id, version, file_name, file_sha256, broker_format, date_from, date_to,
                    rows_total, rows_imported, rows_duplicate, rows_rejected, status
                )
                VALUES ($1, 1, $2, $3, $4, $5, $6, $7, 0, 0, $8, 'IMPORTED')
                RETURNING upload_id;
                """,
                client_id, file_name, file_sha256, broker_format,
                min(dates, default=None), max(dates, default=None),
                len(valid_rows) + len(rejects), len(rejects),
            )
            if rejects:
                await conn.executemany(
                    "INSERT INTO ledger.upload_rejects (upload_id, row_no, reason, raw) VALUES ($1, $2, $3, $4);",
                    [(upload_id, n, why, json.dumps(raw, default=str)) for n, why, raw in rejects],
                )
            inserted = await insert_trades(conn, client_id, upload_id, valid_rows, file_code or code or str(client_id))
            duplicates = len(valid_rows) - inserted
            status = "PARTIAL" if rejects and inserted else ("FAILED" if rejects and not inserted and not duplicates else "IMPORTED")
            await conn.execute(
                "UPDATE ledger.uploads SET rows_imported = $2, rows_duplicate = $3, status = $4 WHERE upload_id = $1;",
                upload_id, inserted, duplicates, status,
            )

        # Best-effort recompute. The ledger write above is already committed; when this runs
        # inside the API (pi_api role is read-only on portfolio.*, AGENTS §3.5) it fails and
        # the scheduled pi-portfolio-recompute worker picks the client up instead.
        try:
            await recompute_single_client(conn, client_id)
        except Exception:
            logger.warning("recompute deferred to the portfolio worker (upload %s)", upload_id)

    return {
        "upload_id": upload_id,
        "rows_total": len(valid_rows) + len(rejects),
        "rows_imported": inserted,
        "rows_duplicate": duplicates,
        "rows_rejected": len(rejects),
        "status": status,
    }


# FastAPI app for ingest worker endpoints (:8204)
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(f"Starting ingest-worker on port {PORT}...")
    await get_db_pool()
    yield
    global _pool
    if _pool:
        await _pool.close()


app = FastAPI(title="Portfolio Intelligence - Ingest Worker", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "worker": "ingest-worker", "port": PORT}


@app.post("/ingest/upload")
async def handle_upload(
    client_id: UUID = Form(...),
    broker_format: str = Form("ZERODHA"),
    file: UploadFile = File(...),
):
    file_bytes = await file.read()
    result = await ingest_tradebook(client_id, file.filename, file_bytes, broker_format)
    return result


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT)

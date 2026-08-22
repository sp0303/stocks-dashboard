"""News pipeline routes: PDF upload + processing status + reads.

OCR is slow (~50s/page, so a 16-page paper is ~13 min) — far too long for a
synchronous request. Upload returns immediately with a PENDING upload id; processing
runs as a FastAPI background task, updating status as it progresses so the frontend
can poll. See docs/06-news-pipeline.md and the news-pipeline plan for the full design.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile

from app.config import settings
from app.services import analytics
from app.services.ingestion import file_hash
from app.services.news import nlp, pdf_extract, pdf_pipeline
from app.store import get_store

router = APIRouter(prefix="/api/news", tags=["news"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _owner_exists(store, scope: str, owner_id: str) -> bool:
    if scope == "manager":
        return bool(await store.get_manager(owner_id))
    if scope == "client":
        return bool(await store.get_client(owner_id))
    return False


@router.post("/pdf")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    scope: str = Query(..., pattern="^(manager|client)$"),
    id: str = Query(...),
    file: UploadFile = File(...),
):
    store = get_store()
    if not await _owner_exists(store, scope, id):
        raise HTTPException(404, f"{scope} not found")

    content = await file.read()
    fhash = file_hash(content)
    if await store.pdf_upload_exists(scope, id, fhash):
        raise HTTPException(409, "this exact file was already uploaded")

    upload = await store.create_pdf_upload(
        {
            "scope": scope,
            "owner_id": id,
            "file_name": file.filename,
            "file_hash": fhash,
            "edition_date": _now()[:10],
            "page_count": 0,
            "status": "PENDING",
            "pages_with_news": 0,
            "items_created": 0,
            "uploaded_at": _now(),
        }
    )

    background_tasks.add_task(_process_pdf_upload, upload["id"], content)
    return {"data": {"upload_id": upload["id"], "status": "PENDING"}}


async def _process_pdf_upload(upload_id: str, content: bytes) -> None:
    store = get_store()
    try:
        await store.update_pdf_upload(upload_id, {"status": "PROCESSING"})
        upload = await store.get_pdf_upload(upload_id)

        result = pdf_extract.extract_pdf(content)
        enricher = nlp.get_enricher(
            settings.news_enricher,
            ollama_url=settings.ollama_url,
            ollama_model=settings.ollama_model,
            anthropic_api_key=settings.anthropic_api_key,
        )
        stories = pdf_pipeline.ingest_pdf(
            result.pages,
            {"pdf_upload_id": upload_id, "published_at": upload.get("edition_date") if upload else None},
            enricher=enricher,
            rss_enabled=settings.news_rss_enrichment,
            rss_max_related=settings.news_rss_max_related,
            min_page_chars=settings.news_pdf_min_page_chars,
        )
        items = [s.item for s in stories]
        links = [lk for s in stories for lk in s.links]
        if items:
            await store.insert_news_items(items)
        if links:
            await store.insert_news_links(links)

        await store.update_pdf_upload(
            upload_id,
            {
                "status": "DONE",
                "page_count": result.page_count,
                "pages_with_news": len({it["page"] for it in items}),
                "items_created": len(items),
            },
        )
    except Exception as e:  # never leave an upload stuck in PROCESSING
        await store.update_pdf_upload(upload_id, {"status": "FAILED", "error": str(e)})


@router.get("/pdf-uploads/{upload_id}")
async def get_pdf_upload(upload_id: str):
    store = get_store()
    upload = await store.get_pdf_upload(upload_id)
    if not upload:
        raise HTTPException(404, "upload not found")
    return {"data": upload}


@router.get("/pdf-uploads")
async def list_pdf_uploads(scope: str = Query(..., pattern="^(manager|client)$"), id: str = Query(...)):
    store = get_store()
    return {"data": await store.list_pdf_uploads(scope, id)}


@router.get("/stock/{symbol}")
async def news_for_stock(symbol: str, limit: int = 20):
    store = get_store()
    return {"data": await store.news_for_symbol(symbol, limit=limit)}


@router.get("/client/{client_id}")
async def news_for_client(client_id: str, limit: int = 50):
    store = get_store()
    client = await store.get_client(client_id)
    if not client:
        raise HTTPException(404, "client not found")
    trades = await store.list_trades(client_id)
    holdings = analytics.build_holdings(trades, with_prices=False)["holdings"]
    symbols = [h["symbol"] for h in holdings]
    if not symbols:
        return {"data": []}
    return {"data": await store.news_for_symbols(symbols, limit=limit)}

"""FastAPI application entrypoint.

No authentication in Phase 1 (by request). Store backend auto-selects Mongo vs JSON.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    admin, broker, clients, corporate_actions, market, portfolio, screener, sectors, watchlists,
)
from app.seed import seed_if_empty
from app.services.alerts import run_alert_loop
from app.store import init_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = await init_store()
    # await seed_if_empty(store)  # Disabled: don't overwrite production data
    app.state.store_backend = "mongo" if settings.use_mongo else "json-file"
    alert_task = asyncio.create_task(run_alert_loop(store))
    # Pre-warm the screener snapshot in the background so the first user doesn't pay the
    # ~1-min cold fetch. Runs off the request path; never blocks startup or serving.
    from app.routers.screener import warm_screener
    warm_task = asyncio.create_task(warm_screener())
    yield
    warm_task.cancel()
    alert_task.cancel()
    await store.close()


app = FastAPI(title="Portfolio Intelligence Platform", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.cors_origins == "*" else settings.cors_origins.split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin.router)
app.include_router(clients.router)
app.include_router(portfolio.router)
app.include_router(watchlists.router)
app.include_router(market.router)
app.include_router(sectors.router)
app.include_router(screener.router)
app.include_router(broker.router)
app.include_router(corporate_actions.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "store": getattr(app.state, "store_backend", "unknown")}

"""FastAPI application entry point for Portfolio Intelligence v2 API."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pi_api.core.db import close_db_pool, init_db_pool
from pi_api.modules.admin.router import router as admin_router
from pi_api.modules.analytics.router import router as analytics_router
from pi_api.modules.auth.router import router as auth_router
from pi_api.modules.heatmap.router import router as heatmap_router
from pi_api.modules.ledger.router import router as ledger_router
from pi_api.modules.market.router import router as market_router
from pi_api.modules.ops.router import router as ops_router
from pi_api.modules.orb.router import router as orb_router
from pi_api.modules.portfolio.router import router as portfolio_router
from pi_api.modules.research.router import router as research_router
from pi_api.settings import settings

logging.basicConfig(level=logging.INFO if not settings.DEBUG else logging.DEBUG)
logger = logging.getLogger("pi_api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: manages asyncpg pool lifecycle."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.VERSION} on port {settings.PORT}...")
    try:
        await init_db_pool()
    except Exception as e:
        logger.warning(f"Database pool initial connection deferred: {e}")
    yield
    logger.info(f"Shutting down {settings.APP_NAME}...")
    await close_db_pool()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Ops & Health probes at root and /api/v1
app.include_router(ops_router)
app.include_router(ops_router, prefix="/api/v1")

# Mount API bounded-context modules under /api/v1
app.include_router(auth_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(portfolio_router, prefix="/api/v1")
app.include_router(heatmap_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(ledger_router, prefix="/api/v1")
app.include_router(market_router, prefix="/api/v1")
app.include_router(research_router, prefix="/api/v1")
app.include_router(orb_router, prefix="/api/v1")


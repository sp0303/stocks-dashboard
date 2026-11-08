"""Scheduler Worker (:8206): Cron job dispatcher using Redis leader lock."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pi_workers.scheduler")

PORT = int(os.environ.get("PORT", 8206))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(f"Starting scheduler worker on port {PORT}...")
    yield
    logger.info("Shutting down scheduler worker...")


app = FastAPI(title="Portfolio Intelligence - Scheduler", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "worker": "scheduler", "port": PORT}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT)

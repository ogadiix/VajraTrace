"""FastAPI application with CORS, lifespan events, and v1 router."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.database import engine, neo4j_driver
from app.models import Base
from app.api.v1.router import v1_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create Postgres tables & verify Neo4j. Shutdown: close connections."""
    # ── Startup ──
    logger.info("Installing Postgres extensions...")
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pg_trgm"'))
    logger.info("Extensions ready.")

    logger.info("Creating Postgres tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Postgres tables ready.")

    # Verify Neo4j
    try:
        await neo4j_driver.verify_connectivity()
        logger.info("Neo4j connection verified.")
    except Exception as e:
        logger.warning(f"Neo4j not reachable (non-fatal): {e}")

    yield

    # ── Shutdown ──
    await engine.dispose()
    await neo4j_driver.close()
    logger.info("Connections closed.")


app = FastAPI(
    title="VajraTrace API",
    description="Real-time cryptocurrency fraud-exchange identification",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow the Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API v1
app.include_router(v1_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "vajratrace-api"}

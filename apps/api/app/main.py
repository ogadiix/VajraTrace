"""FastAPI application with CORS, WebSocket support, request logging,
structured error handling, lifespan events, and v1 router."""

import logging
import time
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import engine, neo4j_driver
from app.models import Base
from app.api.v1.router import v1_router

logger = logging.getLogger(__name__)

# Configure root logger for structured output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)


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


# ---------------------------------------------------------------------------
# CORS — allow the Next.js frontend + deployed domain
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://vajratrace.vercel.app",
        "https://vajratrace.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request logging middleware  (log every request method + path + duration)
# ---------------------------------------------------------------------------


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s → %d  (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# ---------------------------------------------------------------------------
# Global exception handlers — never leak raw tracebacks to the client
# ---------------------------------------------------------------------------


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Structured JSON for all HTTP errors (404, 422, 500, etc.)."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "status_code": exc.status_code,
            "detail": exc.detail,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Structured JSON for Pydantic validation failures."""
    return JSONResponse(
        status_code=422,
        content={
            "error": True,
            "status_code": 422,
            "detail": "Validation error",
            "errors": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all: log the full traceback but return a safe message."""
    logger.error(
        "Unhandled exception on %s %s:\n%s",
        request.method,
        request.url.path,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "status_code": 500,
            "detail": "Internal server error",
        },
    )


# ---------------------------------------------------------------------------
# Mount API v1 (includes WebSocket routes via trace.router)
# ---------------------------------------------------------------------------

app.include_router(v1_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "vajratrace-api"}

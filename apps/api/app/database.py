"""Async SQLAlchemy engine + Neo4j driver setup."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from neo4j import AsyncGraphDatabase

from app.config import settings

# ── Postgres (async) ──
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency — yields an async DB session."""
    async with async_session() as session:
        yield session


# ── Neo4j ──
neo4j_driver = AsyncGraphDatabase.driver(
    settings.NEO4J_URI,
    auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
)


async def get_neo4j():
    """FastAPI dependency — yields a Neo4j async session."""
    async with neo4j_driver.session() as session:
        yield session

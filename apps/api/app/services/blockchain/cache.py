"""Caching layer for blockchain API responses.

Every API call in the system goes through this layer.  The flow is:

1. **Check cache** — look up ``raw_transactions`` for a row matching
   ``(address, chain, api_source, endpoint)`` where ``fetched_at`` is within
   the TTL window (default 10 minutes).
2. **Cache hit (fresh)** — deserialise and return the cached ``response_body``.
3. **Cache miss / stale** — call the real API, write the result to
   ``raw_transactions``, and return fresh data.
4. **API failure** — if the remote call raises or returns a non-2xx status,
   return the *most recent* cached row (even if stale) with ``stale=True``.
   The system **never** raises an exception that would crash the UI.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChainEnum, RawTransaction

logger = logging.getLogger(__name__)

# Maps the chain strings used in this service to the DB enum values.
_CHAIN_MAP: dict[str, ChainEnum] = {
    "bitcoin": ChainEnum.BTC,
    "ethereum": ChainEnum.ETH,
    "tron": ChainEnum.TRON,
}

# Default cache time-to-live.
CACHE_TTL = timedelta(minutes=10)


class CachedResponse:
    """Wrapper returned by :func:`get_or_fetch`.

    Attributes:
        data:  The parsed JSON response body.
        stale: ``True`` when the data came from an expired cache entry
               because the live API was unreachable.
    """

    __slots__ = ("data", "stale")

    def __init__(self, data: Any, stale: bool = False) -> None:
        self.data = data
        self.stale = stale


async def _lookup_cache(
    session: AsyncSession,
    address: str,
    chain: str,
    api_source: str,
    endpoint: str,
) -> RawTransaction | None:
    """Return the most recent cached row for this request, or ``None``.

    The query is intentionally *not* filtered by TTL so that the caller can
    decide whether to treat a stale row as acceptable fallback.
    """
    chain_enum = _CHAIN_MAP.get(chain)
    if chain_enum is None:
        return None

    stmt = (
        select(RawTransaction)
        .where(
            RawTransaction.address == address,
            RawTransaction.chain == chain_enum,
            RawTransaction.api_source == api_source,
            RawTransaction.endpoint == endpoint,
        )
        .order_by(RawTransaction.fetched_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _write_cache(
    session: AsyncSession,
    address: str,
    chain: str,
    api_source: str,
    endpoint: str,
    response_body: Any,
    http_status: int = 200,
) -> None:
    """Upsert a cache row using Postgres ``ON CONFLICT … DO UPDATE``.

    This uses the unique constraint ``uq_raw_cache`` on
    ``(address, chain, api_source, endpoint)`` so that repeated fetches for
    the same request simply overwrite the previous cached value.
    """
    chain_enum = _CHAIN_MAP[chain]
    now = datetime.now(timezone.utc)

    stmt = pg_insert(RawTransaction).values(
        address=address,
        chain=chain_enum,
        api_source=api_source,
        endpoint=endpoint,
        response_body=response_body,
        fetched_at=now,
        expires_at=now + CACHE_TTL,
        http_status=http_status,
    )
    stmt = stmt.on_conflict_on_constraint("uq_raw_cache").do_update(
        set_={
            "response_body": stmt.excluded.response_body,
            "fetched_at": stmt.excluded.fetched_at,
            "expires_at": stmt.excluded.expires_at,
            "http_status": stmt.excluded.http_status,
        }
    )
    await session.execute(stmt)
    await session.commit()
    logger.info(
        "Cache written: address=%s chain=%s source=%s endpoint=%s",
        address, chain, api_source, endpoint,
    )


async def get_or_fetch(
    session: AsyncSession,
    address: str,
    chain: str,
    api_source: str,
    endpoint: str,
    fetch_fn: Any,  # Callable[[], Awaitable[Any]]
) -> CachedResponse:
    """Main entry point — return cached data or call *fetch_fn*.

    Args:
        session:    An active async SQLAlchemy session.
        address:    The blockchain address being queried.
        chain:      ``"bitcoin"`` | ``"ethereum"`` | ``"tron"``.
        api_source: Identifier for the API provider (e.g. ``"etherscan"``).
        endpoint:   The specific endpoint/action (e.g. ``"txlist"``).
        fetch_fn:   An ``async`` callable with no arguments that performs the
                    real HTTP request and returns parsed JSON.

    Returns:
        A :class:`CachedResponse` wrapping the data and a ``stale`` flag.

    Raises:
        Never — on API failure it falls back to stale cache, or returns an
        empty dict if no cache exists at all.
    """
    # 1. Check cache
    cached = await _lookup_cache(session, address, chain, api_source, endpoint)
    if cached is not None:
        age = datetime.now(timezone.utc) - cached.fetched_at.replace(tzinfo=timezone.utc)
        if age < CACHE_TTL:
            logger.info(
                "Cache HIT (fresh, age=%ds): %s/%s/%s",
                int(age.total_seconds()), api_source, endpoint, address,
            )
            return CachedResponse(data=cached.response_body, stale=False)
        logger.info(
            "Cache STALE (age=%ds): %s/%s/%s",
            int(age.total_seconds()), api_source, endpoint, address,
        )

    # 2. Fetch from API
    try:
        data = await fetch_fn()
        await _write_cache(session, address, chain, api_source, endpoint, data)
        return CachedResponse(data=data, stale=False)
    except Exception as exc:
        logger.warning(
            "API fetch failed for %s/%s/%s — %s: %s. Falling back to cache.",
            api_source, endpoint, address, type(exc).__name__, exc,
        )
        # 3. Fall back to stale cache
        if cached is not None:
            return CachedResponse(data=cached.response_body, stale=True)

        # 4. No cache at all — return empty, never crash
        logger.error(
            "No cached data available for %s/%s/%s and API is down.",
            api_source, endpoint, address,
        )
        return CachedResponse(data={}, stale=True)

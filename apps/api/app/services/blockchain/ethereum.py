"""Ethereum transaction fetcher using the Etherscan V2 API.

Fetches three categories of transactions for a given address:
- **Normal** external transactions (``action=txlist``)
- **Internal** transactions (``action=txlistinternal``)
- **ERC-20** token transfers (``action=tokentx``)

All results are normalised into :class:`TransactionRecord` objects.

Rate limiting:  Etherscan free tier allows 5 req/s.  An
``asyncio.Semaphore(5)`` gates concurrent requests, and exponential
backoff handles 429 responses gracefully.

API docs: https://docs.etherscan.io/etherscan-v2
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.blockchain.cache import CachedResponse, get_or_fetch
from app.services.blockchain.models import TransactionRecord

logger = logging.getLogger(__name__)

# Etherscan V2 base URL
_BASE_URL = "https://api.etherscan.io/v2/api"

# Concurrency gate — max 5 in-flight requests to Etherscan at once.
_semaphore = asyncio.Semaphore(5)

# Backoff parameters
_BACKOFF_BASE = 2       # seconds
_BACKOFF_MAX = 30       # seconds
_MAX_RETRIES = 3


async def _request_etherscan(
    client: httpx.AsyncClient,
    params: dict[str, str],
) -> dict[str, Any]:
    """Make a single request to Etherscan with rate-limiting and backoff.

    Args:
        client: A shared ``httpx.AsyncClient`` instance.
        params: Query parameters (``module``, ``action``, etc.).

    Returns:
        The parsed JSON response body.

    Raises:
        httpx.HTTPStatusError: After exhausting retries on persistent 429/5xx.
        httpx.TimeoutException: If every attempt times out.
    """
    params["apikey"] = settings.ETHERSCAN_API_KEY

    for attempt in range(1, _MAX_RETRIES + 1):
        async with _semaphore:
            logger.info(
                "Etherscan request (attempt %d/%d): action=%s address=%s",
                attempt, _MAX_RETRIES, params.get("action"), params.get("address"),
            )
            response = await client.get(_BASE_URL, params=params, timeout=45.0)

        if response.status_code == 429:
            wait = min(_BACKOFF_BASE * (2 ** (attempt - 1)), _BACKOFF_MAX)
            logger.warning("Etherscan 429 — backing off %ds (attempt %d)", wait, attempt)
            await asyncio.sleep(wait)
            continue

        if response.status_code >= 500:
            wait = min(_BACKOFF_BASE * (2 ** (attempt - 1)), _BACKOFF_MAX)
            logger.warning(
                "Etherscan %d — backing off %ds (attempt %d)",
                response.status_code, wait, attempt,
            )
            await asyncio.sleep(wait)
            continue

        response.raise_for_status()
        return response.json()

    # All retries exhausted — raise so cache layer can fall back
    response.raise_for_status()
    return response.json()  # unreachable but keeps type-checker happy


def _wei_to_ether(wei_str: str) -> Decimal:
    """Convert a wei string to Ether as a Decimal.

    Args:
        wei_str: Wei amount as a string from the Etherscan response.

    Returns:
        The equivalent Ether value.
    """
    try:
        return Decimal(wei_str) / Decimal("1000000000000000000")
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _parse_token_decimals(decimals_str: str) -> int:
    """Safely parse token decimals, defaulting to 18.

    Args:
        decimals_str: The ``tokenDecimal`` field from Etherscan.

    Returns:
        An integer number of decimals.
    """
    try:
        return int(decimals_str)
    except (ValueError, TypeError):
        return 18


def _normalize_txns(
    raw_txns: list[dict[str, Any]],
    address: str,
    category: str,
) -> list[TransactionRecord]:
    """Convert raw Etherscan transaction dicts into TransactionRecords.

    Args:
        raw_txns:  List of transaction dicts from the API.
        address:   The queried address (used to determine direction).
        category:  ``"normal"`` | ``"internal"`` | ``"erc20"`` — controls
                   how the value field is interpreted.

    Returns:
        A list of normalised :class:`TransactionRecord` objects.
    """
    records: list[TransactionRecord] = []
    addr_lower = address.lower()

    for tx in raw_txns:
        from_addr = tx.get("from", "").lower()
        to_addr = tx.get("to", "").lower()

        # Skip failed transactions
        if tx.get("isError") == "1" and category == "normal":
            continue

        # Determine direction
        direction = "out" if from_addr == addr_lower else "in"

        # Determine value & token
        if category == "erc20":
            decimals = _parse_token_decimals(tx.get("tokenDecimal", "18"))
            try:
                value = Decimal(tx.get("value", "0")) / (Decimal(10) ** decimals)
            except (InvalidOperation, ValueError):
                value = Decimal("0")
            token = tx.get("tokenSymbol", "UNKNOWN")
        else:
            value = _wei_to_ether(tx.get("value", "0"))
            token = "ETH"

        # Parse timestamp
        try:
            ts = datetime.fromtimestamp(int(tx.get("timeStamp", "0")), tz=timezone.utc)
        except (ValueError, TypeError, OSError):
            ts = datetime(2000, 1, 1, tzinfo=timezone.utc)

        # Parse block number
        try:
            block_num = int(tx.get("blockNumber", "0"))
        except (ValueError, TypeError):
            block_num = 0

        records.append(
            TransactionRecord(
                tx_hash=tx.get("hash", tx.get("transactionHash", "")),
                from_address=from_addr,
                to_address=to_addr,
                value=value,
                token=token,
                chain="ethereum",
                timestamp=ts,
                block_number=block_num,
                direction=direction,
            )
        )

    return records


async def fetch_ethereum_transactions(
    address: str,
    session: AsyncSession,
) -> tuple[list[TransactionRecord], bool]:
    """Fetch all Ethereum transaction categories for *address*.

    Queries Etherscan V2 for normal, internal, and ERC-20 transactions.
    Each sub-request goes through the caching layer; on API failure the
    cache provides stale data so the UI never crashes.

    Args:
        address: A valid Ethereum address (``0x…``).
        session: An active async SQLAlchemy session (for the cache).

    Returns:
        A tuple of ``(records, stale)`` where *records* is the unified
        transaction list and *stale* is ``True`` if any sub-request had
        to fall back to stale cached data.
    """
    all_records: list[TransactionRecord] = []
    any_stale = False

    actions = [
        ("txlist", "normal"),
        ("txlistinternal", "internal"),
        ("tokentx", "erc20"),
    ]

    async with httpx.AsyncClient() as client:
        for action, category in actions:
            params: dict[str, str] = {
                "chainid": "1",
                "module": "account",
                "action": action,
                "address": address,
                "startblock": "0",
                "endblock": "99999999",
                "page": "1",
                "offset": "10000",
                "sort": "desc",
            }

            cached_resp: CachedResponse = await get_or_fetch(
                session=session,
                address=address,
                chain="ethereum",
                api_source="etherscan",
                endpoint=action,
                fetch_fn=lambda p=params, c=client: _request_etherscan(c, dict(p)),
            )

            if cached_resp.stale:
                any_stale = True

            # Etherscan wraps results in {"status": "1", "result": [...]}
            data = cached_resp.data
            result_list = data.get("result") if isinstance(data, dict) else None
            if not isinstance(result_list, list):
                logger.warning(
                    "Etherscan %s returned non-list result for %s: %s",
                    action, address, type(result_list),
                )
                continue

            records = _normalize_txns(result_list, address, category)
            all_records.extend(records)
            logger.info(
                "Etherscan %s: %d records for %s (stale=%s)",
                action, len(records), address, cached_resp.stale,
            )

    return all_records, any_stale

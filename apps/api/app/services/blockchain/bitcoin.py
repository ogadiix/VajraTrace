"""Bitcoin transaction fetcher.

Primary source:  **mempool.space** ``GET /api/address/{address}/txs``
Fallback:        **Blockchair** ``GET /bitcoin/dashboards/address/{address}``

Bitcoin uses the UTXO model — a single transaction can have multiple inputs
and multiple outputs.  This module maps each (input → output) pair that
involves the traced address into a unified :class:`TransactionRecord`.

Neither API requires an API key.

API docs:
- https://mempool.space/docs/api
- https://api.blockchair.com
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.blockchain.cache import CachedResponse, get_or_fetch
from app.services.blockchain.models import TransactionRecord

logger = logging.getLogger(__name__)

_MEMPOOL_BASE = "https://mempool.space/api"
_BLOCKCHAIR_BASE = "https://api.blockchair.com"

# Backoff parameters (shared with all fetchers)
_BACKOFF_BASE = 2
_BACKOFF_MAX = 30
_MAX_RETRIES = 3


def _satoshi_to_btc(satoshis: int | str) -> Decimal:
    """Convert satoshis to BTC as a Decimal.

    Args:
        satoshis: Amount in satoshis (integer or string).

    Returns:
        The equivalent BTC value.
    """
    try:
        return Decimal(str(satoshis)) / Decimal("100000000")
    except (InvalidOperation, ValueError):
        return Decimal("0")


async def _request_with_backoff(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> Any:
    """HTTP GET with exponential backoff on 429 / 5xx.

    Args:
        client:  An ``httpx.AsyncClient``.
        url:     The full URL to request.
        params:  Optional query parameters.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON response.

    Raises:
        httpx.HTTPStatusError: After exhausting retries.
        httpx.TimeoutException: If every attempt times out.
    """
    for attempt in range(1, _MAX_RETRIES + 1):
        logger.info("Bitcoin API request (attempt %d/%d): %s", attempt, _MAX_RETRIES, url)
        response = await client.get(url, params=params, timeout=timeout)

        if response.status_code in (429, 503) or response.status_code >= 500:
            wait = min(_BACKOFF_BASE * (2 ** (attempt - 1)), _BACKOFF_MAX)
            logger.warning(
                "Bitcoin API %d — backing off %ds (attempt %d)",
                response.status_code, wait, attempt,
            )
            await asyncio.sleep(wait)
            continue

        response.raise_for_status()
        return response.json()

    response.raise_for_status()
    return response.json()


def _parse_mempool_txns(
    txns: list[dict[str, Any]],
    address: str,
) -> list[TransactionRecord]:
    """Normalise mempool.space transaction list into TransactionRecords.

    The mempool.space response structure per transaction:
    ```json
    {
      "txid": "...",
      "status": {"confirmed": true, "block_height": 800000, "block_time": 1690000000},
      "vin": [{"prevout": {"scriptpubkey_address": "...", "value": 50000}}],
      "vout": [{"scriptpubkey_address": "...", "value": 30000}]
    }
    ```

    For each transaction we create a record per (input, output) pair that
    references our traced address.  This gives the graph builder full
    resolution of the money flow.

    Args:
        txns:    Raw transaction dicts from mempool.space.
        address: The traced Bitcoin address.

    Returns:
        Normalised records.
    """
    records: list[TransactionRecord] = []

    for tx in txns:
        txid = tx.get("txid", "")
        status = tx.get("status", {})
        confirmed = status.get("confirmed", False)
        block_height = status.get("block_height", 0) or 0

        try:
            block_time = int(status.get("block_time", 0) or 0)
            ts = datetime.fromtimestamp(block_time, tz=timezone.utc) if block_time else datetime(2000, 1, 1, tzinfo=timezone.utc)
        except (ValueError, TypeError, OSError):
            ts = datetime(2000, 1, 1, tzinfo=timezone.utc)

        # Collect input addresses and their values
        input_addrs: list[tuple[str, int]] = []
        for vin in tx.get("vin", []):
            prevout = vin.get("prevout", {})
            if prevout:
                in_addr = prevout.get("scriptpubkey_address", "")
                in_val = prevout.get("value", 0)
                if in_addr:
                    input_addrs.append((in_addr, in_val))

        # Collect output addresses and their values
        output_addrs: list[tuple[str, int]] = []
        for vout in tx.get("vout", []):
            out_addr = vout.get("scriptpubkey_address", "")
            out_val = vout.get("value", 0)
            if out_addr:
                output_addrs.append((out_addr, out_val))

        # Check if our address is in inputs (sending) or outputs (receiving)
        addr_is_input = any(a == address for a, _ in input_addrs)
        addr_is_output = any(a == address for a, _ in output_addrs)

        if addr_is_input:
            # Address is sending — create an "out" record for each output
            # that is NOT our own address (skip change outputs back to self)
            for out_addr, out_val in output_addrs:
                if out_addr == address:
                    continue  # change back to self
                records.append(
                    TransactionRecord(
                        tx_hash=txid,
                        from_address=address,
                        to_address=out_addr,
                        value=_satoshi_to_btc(out_val),
                        token="BTC",
                        chain="bitcoin",
                        timestamp=ts,
                        block_number=block_height,
                        direction="out",
                    )
                )

        if addr_is_output:
            # Address is receiving — create an "in" record from each input
            received = sum(v for a, v in output_addrs if a == address)
            # Use the first input address as the "from" (simplification)
            from_addr = input_addrs[0][0] if input_addrs else "coinbase"
            records.append(
                TransactionRecord(
                    tx_hash=txid,
                    from_address=from_addr,
                    to_address=address,
                    value=_satoshi_to_btc(received),
                    token="BTC",
                    chain="bitcoin",
                    timestamp=ts,
                    block_number=block_height,
                    direction="in",
                )
            )

    return records


def _parse_blockchair_txns(
    data: dict[str, Any],
    address: str,
) -> list[TransactionRecord]:
    """Normalise a Blockchair dashboard response into TransactionRecords.

    Blockchair returns a nested structure:
    ```json
    {
      "data": {
        "<address>": {
          "transactions": ["txid1", "txid2", ...],
          "address": {"received": 100000, "spent": 50000, ...}
        }
      }
    }
    ```

    The dashboard endpoint doesn't return full vin/vout details per
    transaction, so we create summary records based on the address
    statistics.  This is a degraded fallback — mempool.space gives much
    richer data.

    Args:
        data:    The full Blockchair API response.
        address: The traced Bitcoin address.

    Returns:
        Simplified records (one per txid with aggregated values).
    """
    records: list[TransactionRecord] = []

    addr_data = data.get("data", {}).get(address, {})
    if not addr_data:
        return records

    txids = addr_data.get("transactions", [])
    addr_info = addr_data.get("address", {})
    total_received = _satoshi_to_btc(addr_info.get("received", 0))
    total_spent = _satoshi_to_btc(addr_info.get("spent", 0))
    first_seen = addr_info.get("first_seen_receiving")

    try:
        ts = datetime.fromisoformat(first_seen) if first_seen else datetime(2000, 1, 1, tzinfo=timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        ts = datetime(2000, 1, 1, tzinfo=timezone.utc)

    # Create one summary record per txid (limited information from Blockchair dashboard)
    for txid in txids[:100]:  # Cap at 100 to avoid huge responses
        records.append(
            TransactionRecord(
                tx_hash=txid,
                from_address="unknown",
                to_address=address,
                value=total_received / max(len(txids), 1),  # rough approximation
                token="BTC",
                chain="bitcoin",
                timestamp=ts,
                block_number=0,
                direction="in",
            )
        )

    return records


async def _fetch_mempool(
    client: httpx.AsyncClient,
    address: str,
) -> list[dict[str, Any]]:
    """Fetch from mempool.space API.

    The endpoint paginates using ``after_txid``.  We follow pagination to
    collect all transactions (mempool.space returns 25 per page).

    Args:
        client:  An ``httpx.AsyncClient``.
        address: A Bitcoin address.

    Returns:
        A flat list of all transaction dicts.
    """
    all_txns: list[dict[str, Any]] = []
    url = f"{_MEMPOOL_BASE}/address/{address}/txs"

    # First page
    txns = await _request_with_backoff(client, url)
    if not isinstance(txns, list):
        return all_txns
    all_txns.extend(txns)

    # Follow pagination (mempool.space returns 25 per page)
    while len(txns) == 25:
        last_txid = txns[-1].get("txid", "")
        if not last_txid:
            break
        url_paged = f"{_MEMPOOL_BASE}/address/{address}/txs/chain/{last_txid}"
        txns = await _request_with_backoff(client, url_paged)
        if not isinstance(txns, list) or not txns:
            break
        all_txns.extend(txns)
        # Safety cap — don't fetch more than 500 txns for a single address
        if len(all_txns) >= 500:
            logger.info("Bitcoin: capping at 500 txns for %s", address)
            break

    return all_txns


async def _fetch_blockchair(
    client: httpx.AsyncClient,
    address: str,
) -> dict[str, Any]:
    """Fetch from Blockchair dashboard API (fallback).

    Args:
        client:  An ``httpx.AsyncClient``.
        address: A Bitcoin address.

    Returns:
        The full dashboard response dict.
    """
    url = f"{_BLOCKCHAIR_BASE}/bitcoin/dashboards/address/{address}"
    return await _request_with_backoff(client, url)


async def fetch_bitcoin_transactions(
    address: str,
    session: AsyncSession,
) -> tuple[list[TransactionRecord], bool]:
    """Fetch Bitcoin transactions for *address*.

    Tries mempool.space first; falls back to Blockchair on failure.
    Both paths go through the caching layer.

    Args:
        address: A valid Bitcoin address.
        session: An active async SQLAlchemy session (for the cache).

    Returns:
        A tuple of ``(records, stale)`` where *stale* is ``True`` if
        data came from a stale cache fallback.
    """
    any_stale = False

    async with httpx.AsyncClient() as client:
        # Try mempool.space (primary)
        cached_resp: CachedResponse = await get_or_fetch(
            session=session,
            address=address,
            chain="bitcoin",
            api_source="mempool",
            endpoint="address_txs",
            fetch_fn=lambda: _fetch_mempool(client, address),
        )

        if cached_resp.stale:
            any_stale = True

        data = cached_resp.data

        # mempool.space returns a list; Blockchair returns a dict
        if isinstance(data, list) and data:
            records = _parse_mempool_txns(data, address)
            logger.info("Bitcoin mempool.space: %d records for %s", len(records), address)
            return records, any_stale

        # Fallback to Blockchair
        logger.info("Falling back to Blockchair for %s", address)
        cached_resp = await get_or_fetch(
            session=session,
            address=address,
            chain="bitcoin",
            api_source="blockchair",
            endpoint="dashboard",
            fetch_fn=lambda: _fetch_blockchair(client, address),
        )

        if cached_resp.stale:
            any_stale = True

        bc_data = cached_resp.data
        if isinstance(bc_data, dict):
            records = _parse_blockchair_txns(bc_data, address)
            logger.info("Bitcoin Blockchair: %d records for %s", len(records), address)
            return records, any_stale

    logger.warning("No Bitcoin data available for %s", address)
    return [], any_stale

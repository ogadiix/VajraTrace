"""TRON transaction fetcher using the TronGrid API.

Fetches two categories:
- **All transactions**: ``/v1/accounts/{address}/transactions``
- **TRC-20 transfers**: ``/v1/accounts/{address}/transactions/trc20``

TRC-20 USDT transfers are the dominant fraud rail in India, so this module
pays special attention to extracting token metadata from TRC-20 events.

API docs: https://developers.tron.network/reference/get-transactions-by-account-address
Rate limiting: TronGrid allows ~15 req/s on the free tier; we use a
semaphore of 5 plus exponential backoff to stay well within limits.
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

_TRONGRID_BASE = "https://api.trongrid.io"

# Concurrency gate
_semaphore = asyncio.Semaphore(5)

# Backoff parameters
_BACKOFF_BASE = 2
_BACKOFF_MAX = 30
_MAX_RETRIES = 3


def _sun_to_trx(sun: int | str) -> Decimal:
    """Convert SUN (the smallest TRX unit) to TRX.

    1 TRX = 1,000,000 SUN.

    Args:
        sun: Amount in SUN.

    Returns:
        Equivalent TRX value as Decimal.
    """
    try:
        return Decimal(str(sun)) / Decimal("1000000")
    except (InvalidOperation, ValueError):
        return Decimal("0")


async def _request_trongrid(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Make a single request to TronGrid with rate-limiting and backoff.

    Args:
        client: A shared ``httpx.AsyncClient``.
        url:    Full URL to request.
        params: Optional query parameters.

    Returns:
        Parsed JSON response body.

    Raises:
        httpx.HTTPStatusError: After exhausting retries on persistent errors.
    """
    headers: dict[str, str] = {}
    if settings.TRONGRID_API_KEY:
        headers["TRON-PRO-API-KEY"] = settings.TRONGRID_API_KEY

    for attempt in range(1, _MAX_RETRIES + 1):
        async with _semaphore:
            logger.info(
                "TronGrid request (attempt %d/%d): %s",
                attempt, _MAX_RETRIES, url,
            )
            response = await client.get(
                url, params=params, headers=headers, timeout=20.0,
            )

        if response.status_code == 429:
            wait = min(_BACKOFF_BASE * (2 ** (attempt - 1)), _BACKOFF_MAX)
            logger.warning("TronGrid 429 — backing off %ds (attempt %d)", wait, attempt)
            await asyncio.sleep(wait)
            continue

        if response.status_code >= 500:
            wait = min(_BACKOFF_BASE * (2 ** (attempt - 1)), _BACKOFF_MAX)
            logger.warning(
                "TronGrid %d — backing off %ds (attempt %d)",
                response.status_code, wait, attempt,
            )
            await asyncio.sleep(wait)
            continue

        response.raise_for_status()
        return response.json()

    response.raise_for_status()
    return response.json()


def _parse_normal_txns(
    data: dict[str, Any],
    address: str,
) -> list[TransactionRecord]:
    """Parse TronGrid normal transaction response.

    TronGrid ``/v1/accounts/{addr}/transactions`` returns:
    ```json
    {
      "data": [
        {
          "txID": "...",
          "block_timestamp": 1690000000000,
          "raw_data": {
            "contract": [{
              "parameter": {
                "value": {
                  "amount": 1000000,
                  "owner_address": "41...",
                  "to_address": "41..."
                }
              },
              "type": "TransferContract"
            }]
          },
          "ret": [{"contractRet": "SUCCESS"}]
        }
      ]
    }
    ```

    Args:
        data:    Full API response.
        address: The traced TRON address (T-format).

    Returns:
        Normalised transaction records.
    """
    records: list[TransactionRecord] = []
    txns = data.get("data", [])
    if not isinstance(txns, list):
        return records

    for tx in txns:
        txid = tx.get("txID", "")

        # Skip failed transactions
        ret_list = tx.get("ret", [])
        if ret_list and ret_list[0].get("contractRet") != "SUCCESS":
            continue

        # Parse timestamp (TronGrid uses milliseconds)
        try:
            ts_ms = int(tx.get("block_timestamp", 0))
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        except (ValueError, TypeError, OSError):
            ts = datetime(2000, 1, 1, tzinfo=timezone.utc)

        # Parse block number
        try:
            block_num = int(tx.get("blockNumber", 0))
        except (ValueError, TypeError):
            block_num = 0

        # Extract transfer details from raw_data.contract
        raw_data = tx.get("raw_data", {})
        contracts = raw_data.get("contract", [])
        if not contracts:
            continue

        contract = contracts[0]
        contract_type = contract.get("type", "")
        param_value = contract.get("parameter", {}).get("value", {})

        if contract_type == "TransferContract":
            # Native TRX transfer
            from_addr = _hex_to_tron_address(param_value.get("owner_address", ""))
            to_addr = _hex_to_tron_address(param_value.get("to_address", ""))
            amount = _sun_to_trx(param_value.get("amount", 0))
            token = "TRX"
        elif contract_type == "TriggerSmartContract":
            # Could be a TRC-20 transfer — but these are better parsed
            # from the dedicated TRC-20 endpoint, so skip here.
            continue
        else:
            continue

        direction = "out" if from_addr == address else "in"

        records.append(
            TransactionRecord(
                tx_hash=txid,
                from_address=from_addr,
                to_address=to_addr,
                value=amount,
                token=token,
                chain="tron",
                timestamp=ts,
                block_number=block_num,
                direction=direction,
            )
        )

    return records


def _parse_trc20_txns(
    data: dict[str, Any],
    address: str,
) -> list[TransactionRecord]:
    """Parse TronGrid TRC-20 transfer response.

    TronGrid ``/v1/accounts/{addr}/transactions/trc20`` returns:
    ```json
    {
      "data": [
        {
          "transaction_id": "...",
          "block_timestamp": 1690000000000,
          "from": "T...",
          "to": "T...",
          "value": "1000000",
          "token_info": {
            "symbol": "USDT",
            "decimals": 6,
            "address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
          }
        }
      ]
    }
    ```

    Args:
        data:    Full API response.
        address: The traced TRON address.

    Returns:
        Normalised transaction records, with particular attention to USDT.
    """
    records: list[TransactionRecord] = []
    txns = data.get("data", [])
    if not isinstance(txns, list):
        return records

    for tx in txns:
        txid = tx.get("transaction_id", "")
        from_addr = tx.get("from", "")
        to_addr = tx.get("to", "")

        # Token info
        token_info = tx.get("token_info", {})
        token_symbol = token_info.get("symbol", "UNKNOWN")
        decimals = token_info.get("decimals", 6)

        # Parse value with correct decimals
        try:
            raw_value = Decimal(tx.get("value", "0"))
            value = raw_value / (Decimal(10) ** int(decimals))
        except (InvalidOperation, ValueError, TypeError):
            value = Decimal("0")

        # Parse timestamp
        try:
            ts_ms = int(tx.get("block_timestamp", 0))
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        except (ValueError, TypeError, OSError):
            ts = datetime(2000, 1, 1, tzinfo=timezone.utc)

        direction = "out" if from_addr == address else "in"

        records.append(
            TransactionRecord(
                tx_hash=txid,
                from_address=from_addr,
                to_address=to_addr,
                value=value,
                token=token_symbol,
                chain="tron",
                timestamp=ts,
                block_number=0,  # TRC-20 endpoint doesn't always return block number
                direction=direction,
            )
        )

    return records


def _hex_to_tron_address(hex_addr: str) -> str:
    """Convert a hex-encoded TRON address to base58check T-format.

    TronGrid internal responses often use the hex format (``41…``).
    If the input is already in T-format, return it as-is.

    Args:
        hex_addr: Address in hex (``41…``) or T-format.

    Returns:
        Address in T-format, or the original string if conversion fails.
    """
    if not hex_addr or hex_addr.startswith("T"):
        return hex_addr

    try:
        import hashlib
        import base64

        # Ensure hex prefix
        if hex_addr.startswith("0x"):
            hex_addr = "41" + hex_addr[2:]
        elif not hex_addr.startswith("41"):
            return hex_addr

        addr_bytes = bytes.fromhex(hex_addr)
        # Double SHA-256 for checksum
        h1 = hashlib.sha256(addr_bytes).digest()
        h2 = hashlib.sha256(h1).digest()
        checksum = h2[:4]
        full = addr_bytes + checksum

        # Base58 encode
        return _base58_encode(full)
    except Exception:
        return hex_addr


def _base58_encode(data: bytes) -> str:
    """Base58 encode a byte string.

    Args:
        data: Raw bytes to encode.

    Returns:
        Base58-encoded string.
    """
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    n = int.from_bytes(data, "big")
    result = ""
    while n > 0:
        n, remainder = divmod(n, 58)
        result = alphabet[remainder] + result
    # Preserve leading zero bytes
    for byte in data:
        if byte == 0:
            result = "1" + result
        else:
            break
    return result


async def _fetch_all_tron_txns(
    client: httpx.AsyncClient,
    address: str,
    endpoint: str,
) -> dict[str, Any]:
    """Fetch a paginated TronGrid endpoint, collecting all pages.

    TronGrid paginates with a ``fingerprint`` field; if present in the
    response, pass it as ``?fingerprint=…`` to get the next page.

    Args:
        client:   An ``httpx.AsyncClient``.
        address:  The TRON address.
        endpoint: ``"transactions"`` or ``"transactions/trc20"``.

    Returns:
        A dict with a ``"data"`` key containing all collected transactions.
    """
    url = f"{_TRONGRID_BASE}/v1/accounts/{address}/{endpoint}"
    all_data: list[dict[str, Any]] = []
    params: dict[str, str] = {"limit": "200", "order_by": "block_timestamp,desc"}

    page_count = 0
    max_pages = 10  # Safety cap: 10 pages × 200 = 2000 txns max

    while page_count < max_pages:
        resp = await _request_trongrid(client, url, params=params)
        page_data = resp.get("data", [])
        if not isinstance(page_data, list):
            break
        all_data.extend(page_data)

        # Check for next page
        meta = resp.get("meta", {})
        fingerprint = meta.get("fingerprint")
        if not fingerprint:
            break

        params["fingerprint"] = fingerprint
        page_count += 1

    return {"data": all_data}


async def fetch_tron_transactions(
    address: str,
    session: AsyncSession,
) -> tuple[list[TransactionRecord], bool]:
    """Fetch all TRON transactions for *address*.

    Queries TronGrid for both normal transactions and TRC-20 token
    transfers (with special focus on USDT — the dominant fraud rail
    in India).  Both sub-requests go through the caching layer.

    Args:
        address: A valid TRON address (``T…``).
        session: An active async SQLAlchemy session (for the cache).

    Returns:
        A tuple of ``(records, stale)`` where *stale* is ``True`` if
        data came from a stale cache fallback.
    """
    all_records: list[TransactionRecord] = []
    any_stale = False

    async with httpx.AsyncClient() as client:
        # 1. Normal transactions
        cached_resp: CachedResponse = await get_or_fetch(
            session=session,
            address=address,
            chain="tron",
            api_source="trongrid",
            endpoint="transactions",
            fetch_fn=lambda: _fetch_all_tron_txns(client, address, "transactions"),
        )
        if cached_resp.stale:
            any_stale = True

        if isinstance(cached_resp.data, dict):
            normal_records = _parse_normal_txns(cached_resp.data, address)
            all_records.extend(normal_records)
            logger.info(
                "TronGrid normal: %d records for %s (stale=%s)",
                len(normal_records), address, cached_resp.stale,
            )

        # 2. TRC-20 transfers (USDT focus)
        cached_resp = await get_or_fetch(
            session=session,
            address=address,
            chain="tron",
            api_source="trongrid",
            endpoint="transactions_trc20",
            fetch_fn=lambda: _fetch_all_tron_txns(client, address, "transactions/trc20"),
        )
        if cached_resp.stale:
            any_stale = True

        if isinstance(cached_resp.data, dict):
            trc20_records = _parse_trc20_txns(cached_resp.data, address)
            all_records.extend(trc20_records)
            logger.info(
                "TronGrid TRC-20: %d records for %s (stale=%s)",
                len(trc20_records), address, cached_resp.stale,
            )

    return all_records, any_stale

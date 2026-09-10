"""Chain detection — determines which blockchain an address belongs to.

Supports:
- **Bitcoin**: Legacy (``1…``), P2SH (``3…``), and Bech32 / Bech32m (``bc1…``)
- **Ethereum / EVM**: ``0x`` prefix, exactly 42 hex characters
- **TRON**: ``T`` prefix, exactly 34 Base58Check characters

Raises ``InvalidAddress`` for anything that doesn't match a known pattern.
"""

from __future__ import annotations

import re
import logging
import string

logger = logging.getLogger(__name__)

# Characters allowed in Bitcoin Base58Check addresses
_BASE58_ALPHABET = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")

# Characters allowed in Bech32 / Bech32m (lowercase only, no 1/b/i/o)
_BECH32_ALPHABET = set("qpzry9x8gf2tvdw0s3jn54khce6mua7l")


class InvalidAddress(ValueError):
    """Raised when an address does not match any supported chain format."""


def _is_valid_bech32_structure(address: str) -> bool:
    """Check structural validity of a bc1 (bech32 / bech32m) Bitcoin address.

    This performs a *format* check — it does NOT verify the checksum polynomial
    (which would require a full Bech32 decoder).  The format rules are:
    - Must start with ``bc1``
    - The remainder (after ``bc1``) must be 1–71 Bech32 characters
    - Total length for SegWit v0 is 42 (P2WPKH) or 62 (P2WSH)
    - SegWit v1+ (Taproot) is 62 characters

    Returns:
        ``True`` if the address *could* be a valid bc1 address.
    """
    lower = address.lower()
    if not lower.startswith("bc1"):
        return False
    data_part = lower[3:]
    if not data_part:
        return False
    if not all(ch in _BECH32_ALPHABET for ch in data_part):
        return False
    # SegWit v0: 42 (P2WPKH) or 62 (P2WSH)
    # SegWit v1 Taproot: 62
    # Allow a reasonable range
    if len(address) < 14 or len(address) > 74:
        return False
    return True


def _is_valid_base58(address: str) -> bool:
    """Return ``True`` if every character is in the Base58 alphabet."""
    return all(ch in _BASE58_ALPHABET for ch in address)


def detect_chain(address: str) -> str:
    """Detect which blockchain *address* belongs to.

    Args:
        address: A raw blockchain address string (untrimmed is fine).

    Returns:
        One of ``"bitcoin"``, ``"ethereum"``, or ``"tron"``.

    Raises:
        InvalidAddress: If the address doesn't match any supported format.

    Examples:
        >>> detect_chain("0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18")
        'ethereum'
        >>> detect_chain("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4")
        'bitcoin'
        >>> detect_chain("TN2YqTv2LkR4F4bqz8NPhv4r5KnGz1UmqM")
        'tron'
    """
    addr = address.strip()
    if not addr:
        raise InvalidAddress("Empty address")

    # ── EVM / Ethereum ──
    # 0x + 40 hex digits = 42 chars total
    if addr.startswith("0x") or addr.startswith("0X"):
        if len(addr) == 42 and re.fullmatch(r"0[xX][0-9a-fA-F]{40}", addr):
            logger.info("Detected Ethereum address: %s", addr)
            return "ethereum"
        raise InvalidAddress(
            f"Address starts with 0x but is not a valid 42-char hex EVM address: {addr}"
        )

    # ── Bitcoin: Bech32 / Bech32m (bc1…) ──
    if addr.lower().startswith("bc1"):
        if _is_valid_bech32_structure(addr):
            logger.info("Detected Bitcoin bech32 address: %s", addr)
            return "bitcoin"
        raise InvalidAddress(
            f"Address starts with bc1 but fails bech32 structure check: {addr}"
        )

    # ── Bitcoin: Legacy (1…) or P2SH (3…) ──
    if addr[0] in ("1", "3"):
        if 25 <= len(addr) <= 34 and _is_valid_base58(addr):
            logger.info("Detected Bitcoin base58 address: %s", addr)
            return "bitcoin"
        raise InvalidAddress(
            f"Address starts with {addr[0]} but fails Base58Check length/charset: {addr}"
        )

    # ── TRON ──
    if addr.startswith("T"):
        if len(addr) == 34 and _is_valid_base58(addr):
            logger.info("Detected TRON address: %s", addr)
            return "tron"
        raise InvalidAddress(
            f"Address starts with T but is not a valid 34-char Base58Check TRON address: {addr}"
        )

    raise InvalidAddress(
        f"Address does not match any supported chain (BTC, ETH, TRON): {addr}"
    )

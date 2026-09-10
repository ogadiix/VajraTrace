"""Multi-chain blockchain data fetch service for VajraTrace.

This package provides a unified interface for tracing cryptocurrency
transactions across Bitcoin, Ethereum, and TRON blockchains.

Quick start::

    from app.services.blockchain import trace_address

    result = await trace_address(address, session, depth=3)

Exports:
    - :func:`trace_address` — Main orchestrator (BFS multi-hop tracer).
    - :func:`detect_chain` — Auto-detect which chain an address belongs to.
    - :class:`InvalidAddress` — Raised when an address format is unrecognised.
    - :class:`TransactionRecord` — Unified normalised transaction.
    - :class:`Node` — Graph node (one per address).
    - :class:`Edge` — Graph edge (one per transaction flow).
    - :class:`TraceGraphResult` — Complete trace output.
"""

from app.services.blockchain.detector import InvalidAddress, detect_chain
from app.services.blockchain.models import (
    Edge,
    Node,
    TraceGraphResult,
    TransactionRecord,
)
from app.services.blockchain.orchestrator import trace_address

__all__ = [
    "trace_address",
    "detect_chain",
    "InvalidAddress",
    "TransactionRecord",
    "Node",
    "Edge",
    "TraceGraphResult",
]

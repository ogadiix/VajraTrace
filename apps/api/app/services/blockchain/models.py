"""Pydantic V2 data models for the multi-chain blockchain tracing service.

These models form the unified schema that all chain-specific fetchers produce,
allowing the orchestrator to work with a single set of types regardless of
whether the underlying data came from Etherscan, mempool.space, or TronGrid.

Naming note:  The Pydantic result model is called ``TraceGraphResult`` (not
``TraceResult``) to avoid a name collision with the SQLAlchemy ORM model
``app.models.TraceResult`` that already exists in this project.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class TransactionRecord(BaseModel):
    """A single normalised transaction, regardless of source chain.

    Every chain-specific fetcher maps its raw API response into a list of
    these records so that all downstream logic (graph building, risk scoring,
    reporting) can work with one unified schema.

    Attributes:
        tx_hash:      The transaction hash / txid.
        from_address: Sender address (normalised to lowercase for EVM).
        to_address:   Receiver address (normalised to lowercase for EVM).
        value:        Amount transferred — always ``Decimal``, never float.
        token:        Symbol of the token moved (``"ETH"``, ``"BTC"``, ``"USDT"`` …).
        chain:        Which blockchain: ``"bitcoin"`` | ``"ethereum"`` | ``"tron"``.
        timestamp:    Block timestamp in UTC.
        block_number: Block height.
        direction:    ``"in"`` if the traced address received, ``"out"`` if it sent.
    """

    tx_hash: str
    from_address: str
    to_address: str
    value: Decimal = Field(description="Transferred amount — never use float for money")
    token: str
    chain: str
    timestamp: datetime
    block_number: int
    direction: str  # "in" | "out"


class Node(BaseModel):
    """A node in the trace graph — represents one on-chain address.

    Attributes:
        address:        The blockchain address.
        chain:          Which blockchain this address lives on.
        label:          Optional human-readable label (e.g. ``"Binance Hot Wallet"``).
        risk_score:     Optional risk score in [0, 1] assigned by downstream ML.
        total_received: Sum of incoming value across all traced transactions.
        total_sent:     Sum of outgoing value across all traced transactions.
        tx_count:       Number of traced transactions touching this address.
        first_seen:     Earliest block timestamp observed.
        last_seen:      Latest block timestamp observed.
    """

    address: str
    chain: str
    label: str | None = None
    risk_score: float | None = None
    total_received: Decimal = Decimal("0")
    total_sent: Decimal = Decimal("0")
    tx_count: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class Edge(BaseModel):
    """A directed edge in the trace graph — represents one transaction flow.

    Attributes:
        from_address: Sender.
        to_address:   Receiver.
        tx_hash:      Transaction hash for provenance.
        value:        Amount transferred (``Decimal``).
        token:        Token symbol.
        chain:        Which blockchain.
        timestamp:    Block timestamp.
        block_number: Block height.
    """

    from_address: str
    to_address: str
    tx_hash: str
    value: Decimal
    token: str
    chain: str
    timestamp: datetime
    block_number: int


class TraceGraphResult(BaseModel):
    """Complete output of a multi-hop trace operation.

    Contains the full graph (nodes + edges), metadata about the trace run,
    and a flag indicating whether any cached data was stale.

    Attributes:
        source_address:    The root address the trace started from.
        chain:             The auto-detected chain of the source address.
        nodes:             All unique addresses encountered.
        edges:             All transaction flows discovered.
        depth_reached:     How many hops the BFS actually explored.
        chains_involved:   Deduplicated list of chains touched.
        total_value_moved: Grand total of all edge values.
        stale_data:        ``True`` if any API call fell back to stale cache.
        trace_duration_ms: Wall-clock time of the trace in milliseconds.
    """

    source_address: str
    chain: str
    nodes: list[Node]
    edges: list[Edge]
    depth_reached: int
    chains_involved: list[str]
    total_value_moved: Decimal
    stale_data: bool = False
    trace_duration_ms: int

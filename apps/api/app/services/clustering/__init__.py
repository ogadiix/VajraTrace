"""Wallet Clustering service for VajraTrace.

Exports:
    - :class:`UnionFind` — Generic DSU data structure.
    - :class:`CoinJoinDetector` — CoinJoin / mixing detection guard.
    - :class:`MultiInputCoSpendHeuristic` — UTXO multi-input heuristic.
    - :class:`ChangeAddressHeuristic` — UTXO change-address heuristic.
    - :class:`AccountModelClusterHeuristic` — Ethereum/TRON behavioural heuristics.
    - :class:`ClusterAssignment` — Record of a single cluster-link decision.
    - :class:`ClusteringEngine` — Master orchestrator.
    - :class:`ClusterInfo` — Cluster metadata.
    - :class:`ClusteringResult` — Full clustering output.
"""

from app.services.clustering.heuristics import (
    AccountModelClusterHeuristic,
    ChangeAddressHeuristic,
    ClusterAssignment,
    CoinJoinDetector,
    CoinJoinResult,
    MultiInputCoSpendHeuristic,
    UnionFind,
)
from app.services.clustering.engine import (
    ClusterInfo,
    ClusteringEngine,
    ClusteringResult,
)

__all__ = [
    "UnionFind",
    "CoinJoinDetector",
    "CoinJoinResult",
    "ClusterAssignment",
    "MultiInputCoSpendHeuristic",
    "ChangeAddressHeuristic",
    "AccountModelClusterHeuristic",
    "ClusteringEngine",
    "ClusterInfo",
    "ClusteringResult",
]

"""Master Clustering Engine for VajraTrace blockchain forensics.

Orchestrates all clustering heuristics, merges results using Union-Find,
and persists clusters to both Postgres (``clusters`` / ``cluster_members``
tables) and Neo4j (``BELONGS_TO_CLUSTER`` relationships).

Usage::

    engine = ClusteringEngine()
    result = await engine.run(trace_graph_result, raw_transactions=raw_btc_txns)
    await engine.persist_to_postgres(result, chain="bitcoin")
    await engine.persist_to_neo4j(result)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, neo4j_driver
from app.models import (
    Address,
    ChainEnum,
    Cluster,
    ClusterMember,
    HeuristicEnum,
)
from app.services.blockchain.models import Edge, Node, TraceGraphResult
from app.services.clustering.heuristics import (
    AccountModelClusterHeuristic,
    ChangeAddressHeuristic,
    ClusterAssignment,
    CoinJoinDetector,
    MultiInputCoSpendHeuristic,
    UnionFind,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Heuristic name → HeuristicEnum mapping
# ---------------------------------------------------------------------------

_HEURISTIC_MAP: Dict[str, HeuristicEnum] = {
    "multi_input_cospend": HeuristicEnum.MULTI_INPUT,
    "change_address": HeuristicEnum.CHANGE_ADDRESS,
    "funded_by_same_parent": HeuristicEnum.DEPOSIT_REUSE,
    "counterparty_overlap": HeuristicEnum.TIMING_AMOUNT_BRIDGE,
    "temporal_cluster": HeuristicEnum.TIMING_AMOUNT_BRIDGE,
    "peeling_chain": HeuristicEnum.PEELING_CHAIN,
    "manual": HeuristicEnum.MANUAL,
}

# Chain string → ChainEnum mapping
_CHAIN_MAP: Dict[str, ChainEnum] = {
    "bitcoin": ChainEnum.BTC,
    "btc": ChainEnum.BTC,
    "ethereum": ChainEnum.ETH,
    "eth": ChainEnum.ETH,
    "tron": ChainEnum.TRON,
}


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class ClusterInfo(BaseModel):
    """Information about a single identified cluster of addresses.

    Attributes:
        cluster_id:     UUID string identifying this cluster.
        addresses:      All addresses belonging to this cluster.
        heuristic_used: Comma-separated heuristic names that formed this cluster.
        confidence:     Maximum confidence from contributing assignments (0–1).
        explanation:    Human-readable summary for the evidence panel.
        size:           Number of addresses in the cluster.
        label:          Optional human-readable label (e.g. 'Binance cluster').
    """

    cluster_id: str
    addresses: List[str]
    heuristic_used: str
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str
    size: int
    label: Optional[str] = None


class ClusteringResult(BaseModel):
    """Complete output of the clustering engine.

    Attributes:
        address_to_cluster:       Mapping of each clustered address to its ClusterInfo.
        clusters:                 All identified clusters.
        excluded_transactions:    CoinJoin / mixing transactions excluded from clustering.
        total_addresses_clustered: Count of addresses assigned to a cluster.
        heuristics_applied:       List of heuristic names that were executed.
    """

    address_to_cluster: Dict[str, ClusterInfo]
    clusters: List[ClusterInfo]
    excluded_transactions: List[Dict[str, Any]]
    total_addresses_clustered: int
    heuristics_applied: List[str]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ClusteringEngine:
    """Master Clustering Engine — runs all applicable heuristics and merges results.

    The engine determines which heuristics to apply based on the chain type
    of the trace, merges all cluster assignments into a single Union-Find
    structure, builds ``ClusterInfo`` objects, and provides methods to persist
    to both Postgres and Neo4j.
    """

    def __init__(self) -> None:
        """Initialise the engine with all available heuristics."""
        logger.info("Initializing ClusteringEngine with all heuristics.")
        self._multi_input = MultiInputCoSpendHeuristic()
        self._change_addr = ChangeAddressHeuristic()
        self._account_model = AccountModelClusterHeuristic()

    async def run(
        self,
        trace_result: TraceGraphResult,
        raw_transactions: Optional[List[Dict[str, Any]]] = None,
    ) -> ClusteringResult:
        """Run clustering heuristics on a trace graph result.

        Determines the chain type from ``trace_result.chain`` and applies
        the appropriate heuristics:

        - **Bitcoin**: Multi-input co-spend + change-address (requires ``raw_transactions``).
        - **Ethereum / TRON**: Account-model heuristics (funded-by-parent, counterparty
          overlap, temporal clustering).

        Args:
            trace_result:     The ``TraceGraphResult`` from the blockchain tracing engine.
            raw_transactions: Optional list of raw transaction dicts (mempool.space format).
                              Required for Bitcoin UTXO heuristics.

        Returns:
            A ``ClusteringResult`` with all clusters, assignments, and exclusions.
        """
        chain = trace_result.chain.lower() if trace_result.chain else "unknown"
        logger.info(
            "Running clustering engine: chain=%s nodes=%d edges=%d",
            chain, len(trace_result.nodes), len(trace_result.edges),
        )

        all_assignments: List[ClusterAssignment] = []
        heuristics_applied: List[str] = []

        if chain == "bitcoin":
            if not raw_transactions:
                logger.warning(
                    "No raw transactions provided for Bitcoin clustering. "
                    "UTXO heuristics require raw transaction data with vin/vout."
                )
                raw_transactions = []

            # Shared UnionFind for both UTXO heuristics
            uf: UnionFind[str] = UnionFind()

            cospend_assignments = self._multi_input.apply(raw_transactions, uf)
            change_assignments = self._change_addr.apply(raw_transactions, uf)

            all_assignments.extend(cospend_assignments)
            all_assignments.extend(change_assignments)
            heuristics_applied.extend(["multi_input_cospend", "change_address"])

        elif chain in ("ethereum", "tron"):
            account_assignments = self._account_model.apply(
                trace_result.nodes, trace_result.edges,
            )
            all_assignments.extend(account_assignments)
            heuristics_applied.append("account_model")
        else:
            logger.warning(
                "Unsupported chain '%s' for clustering. Returning empty result.", chain,
            )

        # Merge all non-excluded assignments into a master UnionFind
        master_uf, excluded_list = self._merge_assignments(all_assignments)

        # Build cluster objects from connected components
        clusters = self._build_clusters(master_uf, all_assignments)

        # Build address → cluster mapping
        address_to_cluster: Dict[str, ClusterInfo] = {}
        for cluster in clusters:
            for addr in cluster.addresses:
                address_to_cluster[addr] = cluster

        result = ClusteringResult(
            address_to_cluster=address_to_cluster,
            clusters=clusters,
            excluded_transactions=excluded_list,
            total_addresses_clustered=len(address_to_cluster),
            heuristics_applied=heuristics_applied,
        )

        logger.info(
            "Clustering complete: %d clusters containing %d addresses, "
            "%d transactions excluded (mixing).",
            len(clusters), result.total_addresses_clustered, len(excluded_list),
        )
        return result

    # ------------------------------------------------------------------
    # Persistence: Postgres
    # ------------------------------------------------------------------

    async def persist_to_postgres(self, result: ClusteringResult, chain: str) -> None:
        """Persist clustering results to the Postgres ``clusters`` and ``cluster_members`` tables.

        Creates ``Cluster`` and ``ClusterMember`` ORM rows inside a single
        transaction.  Address rows are upserted as needed.

        Args:
            result: The ``ClusteringResult`` to persist.
            chain:  Chain name (e.g. ``'bitcoin'``, ``'ethereum'``).
        """
        logger.info("Persisting %d clusters to Postgres...", len(result.clusters))

        chain_enum = _CHAIN_MAP.get(chain.lower())
        if chain_enum is None:
            logger.warning("Chain '%s' not in ChainEnum — defaulting to BTC.", chain)
            chain_enum = ChainEnum.BTC

        async with async_session() as session:
            async with session.begin():
                for cluster_info in result.clusters:
                    # Map heuristic string to HeuristicEnum
                    primary_heuristic = cluster_info.heuristic_used.split(",")[0].strip()
                    heuristic_enum = _HEURISTIC_MAP.get(
                        primary_heuristic, HeuristicEnum.MANUAL,
                    )

                    # Create Cluster ORM row
                    cluster_uuid = uuid.UUID(cluster_info.cluster_id)
                    db_cluster = Cluster(
                        cluster_id=cluster_uuid,
                        label=cluster_info.label,
                        heuristic_used=heuristic_enum,
                        confidence=cluster_info.confidence,
                        size=cluster_info.size,
                    )
                    session.add(db_cluster)
                    await session.flush()  # ensure cluster_id is available

                    # Create ClusterMember rows
                    for addr_str in cluster_info.addresses:
                        # Upsert address
                        stmt = select(Address).where(
                            Address.address == addr_str,
                            Address.chain == chain_enum,
                        )
                        db_addr = (await session.execute(stmt)).scalar_one_or_none()

                        if db_addr is None:
                            db_addr = Address(
                                address=addr_str,
                                chain=chain_enum,
                            )
                            session.add(db_addr)
                            await session.flush()

                        member = ClusterMember(
                            cluster_id=cluster_uuid,
                            address_id=db_addr.id,
                            joined_via=heuristic_enum,
                            confidence=cluster_info.confidence,
                        )
                        session.add(member)

        logger.info("Successfully persisted %d clusters to Postgres.", len(result.clusters))

    # ------------------------------------------------------------------
    # Persistence: Neo4j
    # ------------------------------------------------------------------

    async def persist_to_neo4j(self, result: ClusteringResult) -> None:
        """Persist clustering results to Neo4j as graph relationships.

        Creates ``(:Cluster)`` nodes and ``(:Address)-[:BELONGS_TO_CLUSTER]->(:Cluster)``
        relationships using ``MERGE`` for idempotency.

        Args:
            result: The ``ClusteringResult`` to persist.
        """
        if not result.clusters:
            logger.info("No clusters to persist to Neo4j.")
            return

        logger.info("Persisting %d clusters to Neo4j...", len(result.clusters))

        cypher = """
        UNWIND $clusters AS cluster
        MERGE (c:Cluster {cluster_id: cluster.cluster_id})
        SET c.label = cluster.label,
            c.confidence = cluster.confidence,
            c.heuristic_used = cluster.heuristic_used,
            c.size = cluster.size
        WITH c, cluster
        UNWIND cluster.addresses AS addr
        MERGE (a:Address {address: addr})
        MERGE (a)-[:BELONGS_TO_CLUSTER]->(c)
        """

        cluster_data = [
            {
                "cluster_id": c.cluster_id,
                "label": c.label or "",
                "confidence": c.confidence,
                "heuristic_used": c.heuristic_used,
                "size": c.size,
                "addresses": c.addresses,
            }
            for c in result.clusters
        ]

        try:
            async with neo4j_driver.session() as session:
                await session.run(cypher, clusters=cluster_data)
            logger.info("Successfully persisted %d clusters to Neo4j.", len(result.clusters))
        except Exception:
            logger.exception("Failed to persist clusters to Neo4j.")
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _merge_assignments(
        self,
        assignments: List[ClusterAssignment],
    ) -> Tuple[UnionFind[str], List[Dict[str, Any]]]:
        """Merge all non-excluded assignments into a master Union-Find.

        Args:
            assignments: All ``ClusterAssignment`` records from all heuristics.

        Returns:
            Tuple of ``(union_find, excluded_transactions)`` where
            ``excluded_transactions`` is a list of dicts describing CoinJoin /
            mixing transactions that were excluded from clustering.
        """
        uf: UnionFind[str] = UnionFind()
        excluded: List[Dict[str, Any]] = []

        for assignment in assignments:
            if assignment.excluded:
                excluded.append({
                    "address_a": assignment.address_a,
                    "address_b": assignment.address_b,
                    "tx_hash": assignment.tx_hash,
                    "heuristic": assignment.heuristic,
                    "exclusion_reason": assignment.exclusion_reason,
                    "explanation": assignment.explanation,
                })
                continue

            # Merge the two addresses into the same component
            uf.union(assignment.address_a, assignment.address_b)

        return uf, excluded

    def _build_clusters(
        self,
        uf: UnionFind[str],
        assignments: List[ClusterAssignment],
    ) -> List[ClusterInfo]:
        """Build ``ClusterInfo`` objects from Union-Find components.

        Each connected component with ≥ 2 addresses becomes a cluster.
        The cluster's confidence is the *maximum* confidence from all
        contributing (non-excluded) assignments.

        Args:
            uf:          The merged Union-Find containing all address groups.
            assignments: All cluster assignments (used for metadata extraction).

        Returns:
            List of ``ClusterInfo`` objects, one per cluster.
        """
        components = uf.get_components()

        # Index: address → contributing assignments
        addr_assignments: Dict[str, List[ClusterAssignment]] = {}
        for asn in assignments:
            if asn.excluded:
                continue
            for addr in (asn.address_a, asn.address_b):
                addr_assignments.setdefault(addr, []).append(asn)

        clusters: List[ClusterInfo] = []

        for _root, members in components.items():
            if len(members) < 2:
                continue  # singleton — not a meaningful cluster

            # Collect metadata from contributing assignments
            contributing: List[ClusterAssignment] = []
            for addr in members:
                contributing.extend(addr_assignments.get(addr, []))

            if not contributing:
                continue

            # Deduplicate heuristics and explanations
            heuristics: set[str] = set()
            explanations: List[str] = []
            max_confidence: float = 0.0
            seen_explanations: set[str] = set()

            for ca in contributing:
                heuristics.add(ca.heuristic)
                if ca.confidence > max_confidence:
                    max_confidence = ca.confidence
                if ca.explanation not in seen_explanations:
                    seen_explanations.add(ca.explanation)
                    explanations.append(ca.explanation)

            cluster_id = str(uuid.uuid4())
            heuristic_str = ", ".join(sorted(heuristics))

            # Limit explanation length (join first few, cap at 5)
            if len(explanations) > 5:
                explanation = " | ".join(explanations[:5]) + f" | ... and {len(explanations) - 5} more."
            else:
                explanation = " | ".join(explanations)

            clusters.append(ClusterInfo(
                cluster_id=cluster_id,
                addresses=sorted(members),
                heuristic_used=heuristic_str,
                confidence=max_confidence,
                explanation=explanation,
                size=len(members),
                label=None,
            ))

        logger.info("Built %d clusters from %d components.", len(clusters), len(components))
        return clusters

import logging
import statistics
from typing import Dict, List, Optional, Set
from pydantic import BaseModel

# Imports for types mentioned in instructions
# Note: These paths reflect the expected structure in VajraTrace.
from app.services.blockchain.models import TraceGraphResult
from app.services.clustering.engine import ClusteringResult
from app.services.attribution.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


class AttributionMatch(BaseModel):
    """
    Represents a match made by the attribution engine for a specific address.
    """
    address: str
    entity_name: Optional[str] = None
    entity_type: str
    confidence: float
    match_method: str  # e.g., 'direct_tag', 'cluster_tag', 'behavioral_exchange', 'behavioral_defi', 'unresolved'
    explanation: str
    is_sanctioned: bool = False
    cluster_id: Optional[str] = None
    matched_via_address: Optional[str] = None


class AttributionResult(BaseModel):
    """
    The final output of the VASP matcher for a given trace.
    """
    matches: List[AttributionMatch]
    address_to_match: Dict[str, AttributionMatch]
    sanctions_hits: List[AttributionMatch]
    total_attributed: int
    total_unresolved: int
    highest_confidence_match: Optional[AttributionMatch] = None


class VASPMatcher:
    """
    VASP ATTRIBUTION ALGORITHM for VajraTrace blockchain forensics.
    Given a traced graph and cluster results, attributes addresses to known entities.
    """
    def __init__(self, knowledge_base: KnowledgeBase):
        self.knowledge_base = knowledge_base
        logger.info("VASPMatcher initialized with KnowledgeBase.")

    async def attribute(self, trace_result: TraceGraphResult, clustering_result: Optional[ClusteringResult] = None) -> AttributionResult:
        """
        Main entry point for attribution. Runs 4 steps in priority order.
        """
        logger.info(f"Starting attribution for {len(trace_result.nodes)} nodes.")
        addresses = [node.address for node in trace_result.nodes]
        already_matched: Set[str] = set()
        matches: List[AttributionMatch] = []
        address_to_match: Dict[str, AttributionMatch] = {}

        # Step 1: Direct Tag Match
        try:
            direct_matches = self._direct_tag_match(addresses)
            for addr, match in direct_matches.items():
                if addr not in already_matched:
                    matches.append(match)
                    address_to_match[addr] = match
                    already_matched.add(addr)
        except Exception as e:
            logger.error(f"Error in _direct_tag_match: {e}", exc_info=True)

        # Step 2: Cluster Tag Match
        if clustering_result:
            try:
                unmatched_addresses = [addr for addr in addresses if addr not in already_matched]
                cluster_matches = self._cluster_tag_match(unmatched_addresses, clustering_result)
                for addr, match in cluster_matches.items():
                    if addr not in already_matched:
                        matches.append(match)
                        address_to_match[addr] = match
                        already_matched.add(addr)
            except Exception as e:
                logger.error(f"Error in _cluster_tag_match: {e}", exc_info=True)

        # Step 3: Behavioral Analysis Match
        try:
            behavioral_matches = self._behavioral_exchange_detection(trace_result, already_matched)
            for addr, match in behavioral_matches.items():
                if addr not in already_matched:
                    matches.append(match)
                    address_to_match[addr] = match
                    already_matched.add(addr)
        except Exception as e:
            logger.error(f"Error in _behavioral_exchange_detection: {e}", exc_info=True)

        # Step 4: Unresolved Match
        try:
            unresolved_matches = self._unresolved(addresses, already_matched)
            for addr, match in unresolved_matches.items():
                if addr not in already_matched:
                    matches.append(match)
                    address_to_match[addr] = match
                    already_matched.add(addr)
        except Exception as e:
            logger.error(f"Error in _unresolved: {e}", exc_info=True)

        sanctions_hits = [m for m in matches if m.is_sanctioned]
        total_attributed = sum(1 for m in matches if m.match_method != 'unresolved')
        total_unresolved = len(matches) - total_attributed
        highest_confidence_match = max(matches, key=lambda m: m.confidence, default=None) if matches else None

        result = AttributionResult(
            matches=matches,
            address_to_match=address_to_match,
            sanctions_hits=sanctions_hits,
            total_attributed=total_attributed,
            total_unresolved=total_unresolved,
            highest_confidence_match=highest_confidence_match
        )
        logger.info(f"Attribution completed. Attributed: {total_attributed}, Unresolved: {total_unresolved}")
        return result

    def _direct_tag_match(self, addresses: List[str]) -> Dict[str, AttributionMatch]:
        """Step 1: Check if any address in the graph has a direct tag in the knowledge base.

        Direct tag matches are the highest confidence attribution method (0.95)
        — the address itself appears in our curated VASP tag database.

        Args:
            addresses: All addresses from the trace graph.

        Returns:
            Mapping of matched address → ``AttributionMatch``.
        """
        matches: Dict[str, AttributionMatch] = {}
        tags_found = self.knowledge_base.lookup_many(addresses)

        for addr, tag in tags_found.items():
            is_sanc = tag.is_sanctioned
            matches[addr] = AttributionMatch(
                address=addr,
                entity_name=tag.entity_name,
                entity_type=tag.entity_type,
                confidence=0.95,
                match_method="direct_tag",
                explanation=(
                    f"Address {addr} directly matches known entity "
                    f"'{tag.entity_name}' ({tag.entity_type}) from source "
                    f"'{tag.source}'."
                ),
                is_sanctioned=is_sanc,
                cluster_id=None,
                matched_via_address=addr,
            )
        return matches

    def _cluster_tag_match(
        self, addresses: List[str], clustering_result: ClusteringResult,
    ) -> Dict[str, AttributionMatch]:
        """Step 2: For unattributed addresses, check if a cluster-mate has a tag.

        If address A is in the same cluster as address B, and B has a known
        entity tag, then A is attributed to the same entity with reduced
        confidence (0.80).

        Args:
            addresses:         Unattributed addresses to check.
            clustering_result: Output from the clustering engine.

        Returns:
            Mapping of matched address → ``AttributionMatch``.
        """
        matches: Dict[str, AttributionMatch] = {}
        for addr in addresses:
            cluster_info = clustering_result.address_to_cluster.get(addr)
            if cluster_info is None:
                continue

            other_addrs = [a for a in cluster_info.addresses if a != addr]
            if not other_addrs:
                continue

            tags_found = self.knowledge_base.lookup_many(other_addrs)
            for tagged_addr, tag in tags_found.items():
                is_sanc = tag.is_sanctioned
                matches[addr] = AttributionMatch(
                    address=addr,
                    entity_name=tag.entity_name,
                    entity_type=tag.entity_type,
                    confidence=0.80,
                    match_method="cluster_tag",
                    explanation=(
                        f"Address {addr} belongs to cluster "
                        f"{cluster_info.cluster_id} which also contains "
                        f"tagged address {tagged_addr} "
                        f"('{tag.entity_name}'). Linked via "
                        f"{cluster_info.heuristic_used} heuristic."
                    ),
                    is_sanctioned=is_sanc,
                    cluster_id=cluster_info.cluster_id,
                    matched_via_address=tagged_addr,
                )
                break  # First match wins
        return matches

    def _behavioral_exchange_detection(
        self, trace_result: TraceGraphResult, already_matched: Set[str],
    ) -> Dict[str, AttributionMatch]:
        """Step 3: Detect exchange/mixer/DeFi behavior from graph topology.

        Analyses endpoint nodes (leaf nodes) in the trace graph for
        behavioural patterns that indicate specific entity types:

        - High fan-in (>100 incoming) → likely exchange hot wallet
        - Regular withdrawal patterns → likely custodial service
        - Known contract interaction → DeFi protocol
        - High fan-out with similar amounts → possible mixer

        Args:
            trace_result:   The full trace graph.
            already_matched: Set of addresses already attributed.

        Returns:
            Mapping of matched address → ``AttributionMatch``.
        """
        matches: Dict[str, AttributionMatch] = {}

        # Build edge lookups
        incoming_edges: Dict[str, List] = {}
        outgoing_edges: Dict[str, List] = {}
        for edge in trace_result.edges:
            incoming_edges.setdefault(edge.to_address, []).append(edge)
            outgoing_edges.setdefault(edge.from_address, []).append(edge)

        for node in trace_result.nodes:
            addr = node.address
            if addr in already_matched:
                continue

            in_edges = incoming_edges.get(addr, [])
            out_edges = outgoing_edges.get(addr, [])

            # Known DEX router / contract interaction
            is_contract = getattr(node, "is_contract", False)
            if is_contract:
                matches[addr] = AttributionMatch(
                    address=addr,
                    entity_name="DeFi Protocol",
                    entity_type="defi",
                    confidence=0.65,
                    match_method="behavioral_defi",
                    explanation=f"Address {addr} interacts with known DeFi protocol router.",
                    is_sanctioned=False,
                )
                continue

            # High fan-in → exchange hot wallet
            if len(in_edges) > 100:
                unique_senders = len({e.from_address for e in in_edges})
                matches[addr] = AttributionMatch(
                    address=addr,
                    entity_name="Potential Exchange",
                    entity_type="exchange",
                    confidence=0.60,
                    match_method="behavioral_exchange",
                    explanation=(
                        f"Address {addr} exhibits exchange-like behavior: "
                        f"{len(in_edges)} incoming transactions from "
                        f"{unique_senders} unique senders."
                    ),
                    is_sanctioned=False,
                )
                continue

            # Regular withdrawal patterns → custodial service
            if len(out_edges) > 5:
                out_sorted = sorted(out_edges, key=lambda e: e.timestamp)
                time_gaps_sec: List[float] = []
                for i in range(1, len(out_sorted)):
                    delta = out_sorted[i].timestamp - out_sorted[i - 1].timestamp
                    time_gaps_sec.append(delta.total_seconds())

                if len(time_gaps_sec) > 1:
                    mean_gap = statistics.mean(time_gaps_sec)
                    std_gap = statistics.stdev(time_gaps_sec)
                    if mean_gap > 0 and std_gap < (mean_gap * 0.3):
                        avg_min = mean_gap / 60.0
                        std_min = std_gap / 60.0
                        matches[addr] = AttributionMatch(
                            address=addr,
                            entity_name="Custodial Service",
                            entity_type="exchange",
                            confidence=0.55,
                            match_method="behavioral_exchange",
                            explanation=(
                                f"Address {addr} shows regular withdrawal patterns "
                                f"(avg interval: {avg_min:.1f}min, σ: {std_min:.1f}min), "
                                f"suggesting a custodial service or automated system."
                            ),
                            is_sanctioned=False,
                        )
                        continue

            # High fan-out with similar amounts → possible mixer
            if len(out_edges) > 50:
                unique_receivers = len({e.to_address for e in out_edges})
                values = [float(e.value) for e in out_edges if e.value]
                if len(values) > 1:
                    mean_val = statistics.mean(values)
                    std_val = statistics.stdev(values)
                    if mean_val > 0 and std_val < (mean_val * 0.1):
                        matches[addr] = AttributionMatch(
                            address=addr,
                            entity_name="Potential Mixer",
                            entity_type="mixer",
                            confidence=0.50,
                            match_method="behavioral_exchange",
                            explanation=(
                                f"Address {addr} shows mixer-like behavior: "
                                f"{len(out_edges)} outgoing transactions of similar "
                                f"size to {unique_receivers} unique receivers."
                            ),
                            is_sanctioned=False,
                        )
                        continue

        return matches

    def _unresolved(self, addresses: List[str], already_matched: Set[str]) -> Dict[str, AttributionMatch]:
        matches = {}
        for addr in addresses:
            if addr not in already_matched:
                matches[addr] = AttributionMatch(
                    address=addr,
                    entity_name=None,
                    entity_type='unknown',
                    confidence=0.0,
                    match_method='unresolved',
                    explanation=f"No attribution data available for address {addr}. This address could not be linked to any known entity, cluster tag, or behavioral pattern.",
                    is_sanctioned=False
                )
        return matches

"""Core Clustering Heuristics for VajraTrace blockchain forensics.

This module implements the foundational address-clustering algorithms that
separate VajraTrace from a simple blockchain explorer. Each heuristic links
addresses to the same real-world entity based on on-chain evidence.

Heuristics implemented:
    1. Multi-Input Co-Spend (UTXO model — Bitcoin)
    2. Change Address Detection (UTXO model — Bitcoin)
    3. Account-Model Clustering (Ethereum / TRON)
    4. CoinJoin / Mixing Detection (critical false-positive guard)

Data structures:
    - ``UnionFind[T]``: Generic Disjoint Set Union with path compression and
      union by rank — O(α(n)) amortized per operation.
    - ``ClusterAssignment``: Structured record of every cluster-link decision,
      carrying a human-readable ``explanation`` for the evidence panel.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Generic, List, Optional, Set, Tuple, TypeVar

from app.services.blockchain.models import Edge, Node

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Union-Find (Disjoint Set Union)
# ---------------------------------------------------------------------------


class UnionFind(Generic[T]):
    """Generic Disjoint Set Union with path compression and union by rank.

    Provides amortized O(α(n)) per ``find`` and ``union`` operation, where
    α is the inverse Ackermann function — effectively constant for all
    practical input sizes.

    Example::

        uf: UnionFind[str] = UnionFind()
        uf.union("addr_A", "addr_B")
        assert uf.connected("addr_A", "addr_B")
        components = uf.get_components()  # {root: {members}}
    """

    def __init__(self) -> None:
        self._parent: Dict[T, T] = {}
        self._rank: Dict[T, int] = {}

    def _ensure(self, x: T) -> None:
        """Lazily initialise an element if it has never been seen."""
        if x not in self._parent:
            self._parent[x] = x
            self._rank[x] = 0

    def find(self, x: T) -> T:
        """Return the root representative of the set containing *x*.

        Uses **path compression**: every node on the path from *x* to the
        root is re-pointed directly to the root, flattening the tree.

        Args:
            x: An element (auto-initialised if new).

        Returns:
            The root representative of *x*'s set.
        """
        self._ensure(x)
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, x: T, y: T) -> None:
        """Merge the sets containing *x* and *y* using **union by rank**.

        The smaller tree is attached under the root of the larger tree,
        keeping the overall height logarithmic.

        Args:
            x: First element.
            y: Second element.
        """
        root_x = self.find(x)
        root_y = self.find(y)

        if root_x == root_y:
            return

        if self._rank[root_x] < self._rank[root_y]:
            self._parent[root_x] = root_y
        elif self._rank[root_x] > self._rank[root_y]:
            self._parent[root_y] = root_x
        else:
            self._parent[root_y] = root_x
            self._rank[root_x] += 1

    def connected(self, x: T, y: T) -> bool:
        """Return ``True`` if *x* and *y* are in the same set.

        Args:
            x: First element.
            y: Second element.

        Returns:
            ``True`` if they share a root representative.
        """
        return self.find(x) == self.find(y)

    def get_components(self) -> Dict[T, Set[T]]:
        """Return every connected component as ``{root: {members}}``.

        Calling ``find`` on each element guarantees path compression is
        complete, so the returned roots are canonical.

        Returns:
            Mapping from each root representative to the set of all members
            in its component.
        """
        components: Dict[T, Set[T]] = defaultdict(set)
        for element in list(self._parent.keys()):
            root = self.find(element)
            components[root].add(element)
        return dict(components)


# ---------------------------------------------------------------------------
# CoinJoin / Mixing Detection
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CoinJoinResult:
    """Outcome of a CoinJoin detection check.

    Attributes:
        is_coinjoin: ``True`` if the transaction matches mixing heuristics.
        confidence:  Detection confidence in [0, 1].
        reason:      Human-readable explanation of the detection logic.
    """

    is_coinjoin: bool
    confidence: float
    reason: str


class CoinJoinDetector:
    """Detects CoinJoin / mixing transactions to prevent false-positive clustering.

    **Algorithm**: A CoinJoin transaction is characterised by many inputs of
    roughly equal value being combined and then split into many outputs of
    roughly equal value (the "equal-output" pattern).

    This detector counts the largest group of outputs whose values are within
    1 % of each other.  If that group represents ≥ ``threshold`` of all
    outputs, the transaction is flagged.

    Why this matters:
        In a CoinJoin, multiple *unrelated* users pool their UTXOs.  The
        multi-input co-spend heuristic would incorrectly cluster all of them
        as the same entity — potentially putting innocent people in a fraud
        cluster.  Detecting CoinJoins lets us *exclude* them from clustering.
    """

    @staticmethod
    def is_coinjoin(
        tx_inputs: List[Tuple[str, Decimal]],
        tx_outputs: List[Tuple[str, Decimal]],
        threshold: float = 0.7,
    ) -> CoinJoinResult:
        """Determine whether a transaction exhibits CoinJoin characteristics.

        Args:
            tx_inputs:  List of ``(address, value_satoshis)`` for each input.
            tx_outputs: List of ``(address, value_satoshis)`` for each output.
            threshold:  Minimum ratio of equal-sized outputs to flag as mixing.

        Returns:
            A ``CoinJoinResult`` with detection outcome and explanation.
        """
        if not tx_outputs or not tx_inputs:
            return CoinJoinResult(False, 0.0, "Transaction lacks inputs or outputs.")

        if len(tx_inputs) < 3 or len(tx_outputs) < 3:
            return CoinJoinResult(
                False, 0.0,
                "Not enough inputs or outputs for a CoinJoin pattern "
                f"(need ≥3 each, got {len(tx_inputs)} inputs, {len(tx_outputs)} outputs).",
            )

        # Sort output values and find the largest group of "equal" values
        sorted_values = sorted(val for _, val in tx_outputs)
        best_group_size = 1
        current_group_size = 1

        for i in range(1, len(sorted_values)):
            prev, curr = sorted_values[i - 1], sorted_values[i]
            # "Equal" means within 1 % of each other
            if prev > 0 and abs(curr - prev) / prev <= Decimal("0.01"):
                current_group_size += 1
            else:
                best_group_size = max(best_group_size, current_group_size)
                current_group_size = 1

        best_group_size = max(best_group_size, current_group_size)
        ratio = best_group_size / len(tx_outputs)

        if ratio >= threshold:
            return CoinJoinResult(
                is_coinjoin=True,
                confidence=min(ratio, 1.0),
                reason=(
                    f"Detected {best_group_size} similarly-sized outputs out of "
                    f"{len(tx_outputs)} total ({ratio * 100:.1f}% equal-value ratio). "
                    f"This strongly resembles a CoinJoin mixing pattern."
                ),
            )

        return CoinJoinResult(False, 0.0, "Does not match CoinJoin heuristics.")


# ---------------------------------------------------------------------------
# Cluster Assignment record
# ---------------------------------------------------------------------------


@dataclass
class ClusterAssignment:
    """Record of a single cluster-link decision between two addresses.

    The ``explanation`` field is designed to be displayed directly in the
    VajraTrace evidence panel — it must be detailed enough for a law
    enforcement analyst to understand *why* two addresses were linked.

    Attributes:
        address_a:        First address in the link.
        address_b:        Second address in the link.
        heuristic:        Heuristic identifier string.
        confidence:       Confidence of this link (0–1).
        explanation:      Human-readable evidence narrative.
        tx_hash:          Transaction hash that evidences the link (if any).
        excluded:         ``True`` if clustering was rejected (CoinJoin).
        exclusion_reason: Why clustering was excluded (e.g. ``'mixing_detected'``).
    """

    address_a: str
    address_b: str
    heuristic: str  # 'multi_input_cospend' | 'change_address' | 'funded_by_same_parent' | ...
    confidence: float
    explanation: str
    tx_hash: Optional[str] = None
    excluded: bool = False
    exclusion_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Heuristic 1: Multi-Input Co-Spend (Bitcoin UTXO)
# ---------------------------------------------------------------------------


class MultiInputCoSpendHeuristic:
    """Multi-Input Common Ownership Heuristic for UTXO blockchains.

    **Principle**: If multiple addresses appear as *inputs* in the same
    Bitcoin transaction, the owner must have held the private keys for
    *all* of them to sign the transaction.  Therefore they are controlled
    by the same entity.

    **CoinJoin guard**: Before clustering, the detector checks whether the
    transaction is a CoinJoin.  If so, the addresses are *not* clustered
    and a ``ClusterAssignment`` with ``excluded=True`` is emitted so the
    exclusion is recorded in the evidence trail.

    Reference:
        Meiklejohn et al., "A Fistful of Bitcoins" (IMC 2013), §3.1.
    """

    def __init__(self) -> None:
        self._cj_detector = CoinJoinDetector()

    def apply(
        self,
        transactions: List[dict],
        uf: UnionFind[str],
    ) -> List[ClusterAssignment]:
        """Run the multi-input heuristic on raw mempool.space transactions.

        Args:
            transactions: Raw transaction dicts with ``vin[].prevout.scriptpubkey_address``
                          and ``vout[].scriptpubkey_address`` / ``vout[].value``.
            uf:           A shared ``UnionFind`` to accumulate cluster links.

        Returns:
            List of ``ClusterAssignment`` records (including excluded CoinJoins).
        """
        assignments: List[ClusterAssignment] = []

        for tx in transactions:
            tx_hash: str = tx.get("txid") or tx.get("hash", "unknown_tx")

            # --- Extract inputs ---
            inputs: List[Tuple[str, Decimal]] = []
            for vin in tx.get("vin", []):
                prevout = vin.get("prevout", {})
                if prevout and "scriptpubkey_address" in prevout:
                    addr = prevout["scriptpubkey_address"]
                    val = Decimal(str(prevout.get("value", 0)))
                    inputs.append((addr, val))

            # --- Extract outputs ---
            outputs: List[Tuple[str, Decimal]] = []
            for vout in tx.get("vout", []):
                if "scriptpubkey_address" in vout:
                    addr = vout["scriptpubkey_address"]
                    val = Decimal(str(vout.get("value", 0)))
                    outputs.append((addr, val))

            # Need at least 2 distinct input addresses
            unique_input_addrs = list({addr for addr, _ in inputs})
            if len(unique_input_addrs) < 2:
                continue

            # --- CoinJoin check (CRITICAL) ---
            cj_result = self._cj_detector.is_coinjoin(inputs, outputs)

            if cj_result.is_coinjoin:
                logger.info(
                    "CoinJoin detected in tx %s — excluding %d input addresses from clustering.",
                    tx_hash, len(unique_input_addrs),
                )
                for i in range(len(unique_input_addrs) - 1):
                    assignments.append(ClusterAssignment(
                        address_a=unique_input_addrs[i],
                        address_b=unique_input_addrs[i + 1],
                        heuristic="multi_input_cospend",
                        confidence=0.0,
                        explanation=(
                            f"Clustering EXCLUDED for addresses in transaction {tx_hash}. "
                            f"{cj_result.reason} "
                            f"Inputs were NOT clustered to avoid linking unrelated CoinJoin participants."
                        ),
                        tx_hash=tx_hash,
                        excluded=True,
                        exclusion_reason="mixing_detected, clustering_excluded",
                    ))
                continue

            # --- Cluster all input addresses together ---
            primary = unique_input_addrs[0]
            for other in unique_input_addrs[1:]:
                if not uf.connected(primary, other):
                    uf.union(primary, other)
                    assignments.append(ClusterAssignment(
                        address_a=primary,
                        address_b=other,
                        heuristic="multi_input_cospend",
                        confidence=0.99,
                        explanation=(
                            f"Addresses {primary} and {other} were both spent as inputs "
                            f"in transaction {tx_hash}. Spending multiple inputs requires "
                            f"the private keys for ALL input addresses, proving common "
                            f"ownership by the same entity."
                        ),
                        tx_hash=tx_hash,
                    ))

        logger.info("Multi-input co-spend: produced %d assignments.", len(assignments))
        return assignments


# ---------------------------------------------------------------------------
# Heuristic 2: Change Address Detection (Bitcoin UTXO)
# ---------------------------------------------------------------------------


class ChangeAddressHeuristic:
    """Change Address Detection for UTXO blockchains.

    **Principle**: In a Bitcoin transaction, typically one output is the
    *payment* and the other is *change* returned to the sender.  If we can
    identify which output is the change address, we can cluster it with the
    sender's input address.

    Three sub-heuristics (applied in priority order):

    1. **Round-number detection** (confidence 0.65):
       If one output is a round number (divisible by 10 000 satoshis) and the
       other is not, the non-round output is likely change.

    2. **Address-type matching** (confidence 0.70):
       Wallets typically generate change addresses of the same script type as
       the sender (P2PKH→P2PKH, P2WPKH→P2WPKH, etc.).

    3. **Fresh-address detection** (confidence 0.55):
       If one output goes to a never-before-seen address, it was likely
       freshly generated as a change address.

    Reference:
        Meiklejohn et al., "A Fistful of Bitcoins" (IMC 2013), §3.2.
    """

    @staticmethod
    def _get_address_type(address: str) -> str:
        """Classify a Bitcoin address by its script type prefix.

        Returns:
            One of ``'P2PKH'``, ``'P2SH'``, ``'P2WPKH'``, ``'P2TR'``, or ``'unknown'``.
        """
        if address.startswith("1"):
            return "P2PKH"
        if address.startswith("3"):
            return "P2SH"
        if address.lower().startswith("bc1q"):
            return "P2WPKH"
        if address.lower().startswith("bc1p"):
            return "P2TR"
        return "unknown"

    def apply(
        self,
        transactions: List[dict],
        uf: UnionFind[str],
    ) -> List[ClusterAssignment]:
        """Run change-address heuristics on raw mempool.space transactions.

        Args:
            transactions: Raw transaction dicts.
            uf:           A shared ``UnionFind`` to accumulate cluster links.

        Returns:
            List of ``ClusterAssignment`` records.
        """
        assignments: List[ClusterAssignment] = []

        # Pre-scan: collect all addresses we've ever seen (for fresh-address check)
        seen_addresses: Set[str] = set()
        for tx in transactions:
            for vin in tx.get("vin", []):
                prevout = vin.get("prevout", {})
                if prevout and "scriptpubkey_address" in prevout:
                    seen_addresses.add(prevout["scriptpubkey_address"])
            for vout in tx.get("vout", []):
                if "scriptpubkey_address" in vout:
                    seen_addresses.add(vout["scriptpubkey_address"])

        for tx in transactions:
            tx_hash: str = tx.get("txid") or tx.get("hash", "unknown_tx")

            # Get sender (first input address)
            input_addresses: List[str] = []
            for vin in tx.get("vin", []):
                prevout = vin.get("prevout", {})
                if prevout and "scriptpubkey_address" in prevout:
                    input_addresses.append(prevout["scriptpubkey_address"])

            if not input_addresses:
                continue

            sender_address = input_addresses[0]
            sender_type = self._get_address_type(sender_address)

            # Get outputs — this heuristic works best with exactly 2 outputs
            outputs: List[dict] = []
            for vout in tx.get("vout", []):
                if "scriptpubkey_address" in vout:
                    outputs.append({
                        "address": vout["scriptpubkey_address"],
                        "value": int(vout.get("value", 0)),
                    })

            if len(outputs) != 2:
                continue

            out1, out2 = outputs[0], outputs[1]

            # Skip if either output is back to the sender (self-change already handled)
            if out1["address"] in input_addresses and out2["address"] in input_addresses:
                continue

            # --- Sub-heuristic 1: Round-number detection ---
            out1_round = out1["value"] > 0 and out1["value"] % 10_000 == 0
            out2_round = out2["value"] > 0 and out2["value"] % 10_000 == 0

            if out1_round and not out2_round:
                # out2 is likely change (non-round)
                if out2["address"] not in input_addresses:
                    uf.union(sender_address, out2["address"])
                    assignments.append(ClusterAssignment(
                        address_a=sender_address,
                        address_b=out2["address"],
                        heuristic="change_address",
                        confidence=0.65,
                        explanation=(
                            f"In transaction {tx_hash}, output to {out1['address']} "
                            f"is a round amount ({out1['value']} satoshis), suggesting it "
                            f"is the intended payment. The non-round output "
                            f"({out2['value']} satoshis) to {out2['address']} is likely "
                            f"change returning to the sender's wallet."
                        ),
                        tx_hash=tx_hash,
                    ))
                continue
            elif out2_round and not out1_round:
                if out1["address"] not in input_addresses:
                    uf.union(sender_address, out1["address"])
                    assignments.append(ClusterAssignment(
                        address_a=sender_address,
                        address_b=out1["address"],
                        heuristic="change_address",
                        confidence=0.65,
                        explanation=(
                            f"In transaction {tx_hash}, output to {out2['address']} "
                            f"is a round amount ({out2['value']} satoshis), suggesting it "
                            f"is the intended payment. The non-round output "
                            f"({out1['value']} satoshis) to {out1['address']} is likely "
                            f"change returning to the sender's wallet."
                        ),
                        tx_hash=tx_hash,
                    ))
                continue

            # --- Sub-heuristic 2: Address-type matching ---
            out1_type = self._get_address_type(out1["address"])
            out2_type = self._get_address_type(out2["address"])

            if sender_type != "unknown":
                if out1_type == sender_type and out2_type != sender_type:
                    if out1["address"] not in input_addresses:
                        uf.union(sender_address, out1["address"])
                        assignments.append(ClusterAssignment(
                            address_a=sender_address,
                            address_b=out1["address"],
                            heuristic="change_address",
                            confidence=0.70,
                            explanation=(
                                f"In transaction {tx_hash}, address {out1['address']} "
                                f"matches the script type ({sender_type}) of sender "
                                f"{sender_address}. The payment output {out2['address']} "
                                f"uses a different type ({out2_type}). Standard wallets "
                                f"generate change addresses of the same type as the sender."
                            ),
                            tx_hash=tx_hash,
                        ))
                    continue
                elif out2_type == sender_type and out1_type != sender_type:
                    if out2["address"] not in input_addresses:
                        uf.union(sender_address, out2["address"])
                        assignments.append(ClusterAssignment(
                            address_a=sender_address,
                            address_b=out2["address"],
                            heuristic="change_address",
                            confidence=0.70,
                            explanation=(
                                f"In transaction {tx_hash}, address {out2['address']} "
                                f"matches the script type ({sender_type}) of sender "
                                f"{sender_address}. The payment output {out1['address']} "
                                f"uses a different type ({out1_type}). Standard wallets "
                                f"generate change addresses of the same type as the sender."
                            ),
                            tx_hash=tx_hash,
                        ))
                    continue

            # --- Sub-heuristic 3: Fresh-address detection ---
            out1_new = out1["address"] not in seen_addresses
            out2_new = out2["address"] not in seen_addresses

            if out1_new and not out2_new:
                if out1["address"] not in input_addresses:
                    uf.union(sender_address, out1["address"])
                    assignments.append(ClusterAssignment(
                        address_a=sender_address,
                        address_b=out1["address"],
                        heuristic="change_address",
                        confidence=0.55,
                        explanation=(
                            f"In transaction {tx_hash}, address {out1['address']} was "
                            f"never seen on-chain before this transaction, while "
                            f"{out2['address']} has prior transaction history. Freshly "
                            f"generated addresses are typically change outputs created by "
                            f"the sender's wallet software."
                        ),
                        tx_hash=tx_hash,
                    ))
            elif out2_new and not out1_new:
                if out2["address"] not in input_addresses:
                    uf.union(sender_address, out2["address"])
                    assignments.append(ClusterAssignment(
                        address_a=sender_address,
                        address_b=out2["address"],
                        heuristic="change_address",
                        confidence=0.55,
                        explanation=(
                            f"In transaction {tx_hash}, address {out2['address']} was "
                            f"never seen on-chain before this transaction, while "
                            f"{out1['address']} has prior transaction history. Freshly "
                            f"generated addresses are typically change outputs created by "
                            f"the sender's wallet software."
                        ),
                        tx_hash=tx_hash,
                    ))

            # Update seen addresses for subsequent transactions
            seen_addresses.add(out1["address"])
            seen_addresses.add(out2["address"])

        logger.info("Change-address heuristic: produced %d assignments.", len(assignments))
        return assignments


# ---------------------------------------------------------------------------
# Heuristic 3: Account-Model Clustering (Ethereum / TRON)
# ---------------------------------------------------------------------------


class AccountModelClusterHeuristic:
    """Clustering heuristics for account-model blockchains (Ethereum, TRON).

    Unlike UTXO chains, account-model chains don't have the multi-input
    co-spend signal.  Instead we use three weaker but still valuable
    behavioural heuristics:

    A. **Funded-by-same-parent** (confidence 0.60):
       If multiple addresses received their *first* incoming transaction from
       the same parent address, they were likely created and funded by the
       same entity (common in exchange hot-wallet / operational-wallet setups).

    B. **Counterparty overlap** (confidence 0.55):
       If two addresses consistently transact with the same set of
       counterparties (Jaccard similarity > 0.7), they are likely operated
       by the same entity.

    C. **Temporal clustering** (confidence 0.50):
       If two addresses repeatedly initiate transactions in the same narrow
       time windows (same 1-hour bucket, ≥ 3 co-occurrences), this suggests
       automated or scripted control from a common operator.
    """

    def apply(
        self,
        nodes: List[Node],
        edges: List[Edge],
    ) -> List[ClusterAssignment]:
        """Run account-model clustering on trace graph nodes and edges.

        Args:
            nodes: All unique addresses from the trace graph.
            edges: All transaction flows from the trace graph.

        Returns:
            List of ``ClusterAssignment`` records.
        """
        uf: UnionFind[str] = UnionFind()
        assignments: List[ClusterAssignment] = []

        # Build edge lookup maps
        in_edges_map: Dict[str, List[Edge]] = defaultdict(list)
        out_edges_map: Dict[str, List[Edge]] = defaultdict(list)

        for edge in edges:
            in_edges_map[edge.to_address].append(edge)
            out_edges_map[edge.from_address].append(edge)

        addresses: Set[str] = {node.address for node in nodes}

        # ── Heuristic A: Funded-by-same-parent ──
        parent_children: Dict[str, Set[str]] = defaultdict(set)

        for addr in addresses:
            incoming = in_edges_map.get(addr, [])
            if incoming:
                # Sort by timestamp to find the *first* funder
                sorted_in = sorted(incoming, key=lambda e: e.timestamp)
                parent_addr = sorted_in[0].from_address
                parent_children[parent_addr].add(addr)

        for parent, children in parent_children.items():
            # Only cluster small groups (2–10) to avoid false positives
            # with large exchange deposit aggregators
            if 2 <= len(children) <= 10:
                children_list = sorted(children)
                primary = children_list[0]
                for child in children_list[1:]:
                    if not uf.connected(primary, child):
                        uf.union(primary, child)
                        assignments.append(ClusterAssignment(
                            address_a=primary,
                            address_b=child,
                            heuristic="funded_by_same_parent",
                            confidence=0.60,
                            explanation=(
                                f"Addresses {primary} and {child} were both initially "
                                f"funded by the same parent address {parent}. In "
                                f"account-model networks, bulk wallet generation often "
                                f"involves funding multiple controlled addresses from a "
                                f"central source (e.g. an exchange creating operational "
                                f"wallets)."
                            ),
                            tx_hash=None,
                        ))

        # ── Heuristic B: Counterparty overlap (Jaccard similarity) ──
        counterparties: Dict[str, Set[str]] = defaultdict(set)
        for edge in edges:
            counterparties[edge.from_address].add(edge.to_address)
            counterparties[edge.to_address].add(edge.from_address)

        addr_list = sorted(addresses)
        for i in range(len(addr_list)):
            for j in range(i + 1, len(addr_list)):
                a1, a2 = addr_list[i], addr_list[j]
                cp1, cp2 = counterparties.get(a1, set()), counterparties.get(a2, set())

                # Require minimum 3 counterparties each to avoid noise
                if len(cp1) < 3 or len(cp2) < 3:
                    continue

                intersection = len(cp1 & cp2)
                union_size = len(cp1 | cp2)

                if union_size > 0:
                    jaccard = intersection / union_size
                    if jaccard > 0.7 and not uf.connected(a1, a2):
                        uf.union(a1, a2)
                        assignments.append(ClusterAssignment(
                            address_a=a1,
                            address_b=a2,
                            heuristic="counterparty_overlap",
                            confidence=0.55,
                            explanation=(
                                f"Addresses {a1} and {a2} share {intersection} of "
                                f"{union_size} unique counterparties (Jaccard similarity "
                                f"{jaccard * 100:.1f}%). Consistently interacting with the "
                                f"same set of third parties indicates likely common control."
                            ),
                            tx_hash=None,
                        ))

        # ── Heuristic C: Temporal clustering ──
        time_buckets: Dict[int, Set[str]] = defaultdict(set)
        for edge in edges:
            if edge.timestamp:
                # 1-hour buckets based on Unix epoch
                bucket = int(edge.timestamp.timestamp()) // 3600
                time_buckets[bucket].add(edge.from_address)

        # Count how often pairs of addresses appear in the same time bucket
        pair_counts: Dict[Tuple[str, str], int] = defaultdict(int)
        for _bucket, bucket_addrs in time_buckets.items():
            if 2 <= len(bucket_addrs) <= 5:
                sorted_bucket = sorted(bucket_addrs)
                for i in range(len(sorted_bucket)):
                    for j in range(i + 1, len(sorted_bucket)):
                        pair_counts[(sorted_bucket[i], sorted_bucket[j])] += 1

        for (a1, a2), count in pair_counts.items():
            if count >= 3 and not uf.connected(a1, a2):
                uf.union(a1, a2)
                assignments.append(ClusterAssignment(
                    address_a=a1,
                    address_b=a2,
                    heuristic="temporal_cluster",
                    confidence=0.50,
                    explanation=(
                        f"Addresses {a1} and {a2} initiated transactions within the "
                        f"same 1-hour time window on {count} separate occasions. This "
                        f"synchronous activity pattern often indicates automated or "
                        f"scripted control from a common operator."
                    ),
                    tx_hash=None,
                ))

        logger.info("Account-model heuristic: produced %d assignments.", len(assignments))
        return assignments

"""Evidence Trail Generator — tamper-evident chain-of-custody for VajraTrace.

This module builds and persists a **linked evidence chain** for every
investigation case.  Each evidence entry records one forensic action (e.g.
fetching transaction history, clustering an address, looking up a tag,
checking sanctions, or scoring risk) along with its result, confidence,
and raw payload.

Integrity guarantees
--------------------
When the chain is persisted to Postgres, every row receives a SHA-256
``integrity_hash`` that includes the hash of its predecessor:

    hash_n = SHA-256( step_number || action || description || prev_hash_{n-1} )

This creates a **hash chain** analogous to a mini-blockchain: tampering with
any earlier entry invalidates the hashes of all subsequent entries, giving
investigators a cryptographic audit trail.

The builder pattern (``EvidenceChainBuilder``) is intentionally mutable and
synchronous for the *collection* phase, but ``persist()`` is async and
transactional — a single ``AsyncSession.commit()`` writes the full chain or
rolls back on failure.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models import EvidenceActionEnum, EvidenceChain
from app.services.blockchain.models import Edge

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schema
# ---------------------------------------------------------------------------

class EvidenceEntry(BaseModel):
    """A single step in the evidence trail, serialisable to JSON.

    This is the *in-memory* representation used while building the chain.
    The ``EvidenceChainBuilder.persist`` method maps each entry to a
    ``EvidenceChain`` ORM row.

    Attributes:
        step:        1-based ordinal position in the chain.
        hop:         Human-readable flow notation, e.g. ``'0xABC… → 0xDEF…'``.
        tx_hash:     The on-chain transaction hash (empty string for non-tx steps).
        value:       Formatted value string, e.g. ``'2.5 ETH'``.
        timestamp:   ISO 8601 timestamp string.
        heuristic:   Name of the heuristic applied (if any).
        action:      The ``EvidenceActionEnum`` value as a string.
        explanation: Investigator-facing narrative for this step.
        confidence:  Step-level confidence in [0, 1].
        raw_data:    Optional payload for deep-dive inspection.
    """

    step: int = Field(
        ...,
        ge=1,
        description="1-based step number in the evidence chain.",
    )
    hop: str = Field(
        "",
        description="Directional address flow, e.g. '0xABC… → 0xDEF…'.",
    )
    tx_hash: str = Field(
        "",
        description="On-chain transaction hash for this evidence step.",
    )
    value: str = Field(
        "",
        description="Formatted value string, e.g. '2.5 ETH'.",
    )
    timestamp: str = Field(
        "",
        description="ISO 8601 timestamp of the on-chain event or action.",
    )
    heuristic: Optional[str] = Field(
        None,
        description="Heuristic name if a clustering heuristic was applied.",
    )
    action: str = Field(
        ...,
        description="Evidence action type from EvidenceActionEnum.",
    )
    explanation: str = Field(
        "",
        description="Investigator-facing narrative for this evidence step.",
    )
    confidence: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for this evidence step.",
    )
    raw_data: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional raw payload for deep-dive inspection.",
    )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class EvidenceChainBuilder:
    """Fluent builder for constructing a linked evidence chain.

    Usage::

        builder = EvidenceChainBuilder()
        builder.add_transaction_hop(edge, explanation="Initial outflow detected.")
        builder.add_tag_lookup("0xABC", "Binance", "EXCHANGE", 0.95,
                               "Matched against GraphSense tagpack.")
        chain = builder.build()

        # Persist to Postgres with hash-chain integrity
        await builder.persist(case_id="...")
    """

    def __init__(self) -> None:
        """Initialise an empty evidence chain builder."""
        self._entries: List[EvidenceEntry] = []
        self._step_counter: int = 0

    # ------------------------------------------------------------------
    # Transaction hop
    # ------------------------------------------------------------------

    def add_transaction_hop(
        self,
        edge: Edge,
        explanation: str = "",
    ) -> EvidenceEntry:
        """Record a ``FETCH_TX_HISTORY`` evidence entry for a transaction hop.

        If no ``explanation`` is provided, a sensible default is generated
        from the edge metadata.

        Args:
            edge:        A ``Edge`` from the trace graph.
            explanation: Optional investigator-facing narrative.

        Returns:
            The newly created ``EvidenceEntry``.
        """
        self._step_counter += 1
        hop: str = f"{edge.from_address} → {edge.to_address}"
        value_str: str = f"{edge.value} {edge.token}"
        ts_str: str = edge.timestamp.isoformat() if edge.timestamp else ""

        if not explanation:
            explanation = (
                f"Transaction {edge.tx_hash} transferred {value_str} "
                f"from {edge.from_address} to {edge.to_address} "
                f"on {edge.chain} at block {edge.block_number}."
            )

        entry = EvidenceEntry(
            step=self._step_counter,
            hop=hop,
            tx_hash=edge.tx_hash,
            value=value_str,
            timestamp=ts_str,
            heuristic=None,
            action=EvidenceActionEnum.FETCH_TX_HISTORY.value,
            explanation=explanation,
            confidence=1.0,  # on-chain data is deterministic
            raw_data={
                "from_address": edge.from_address,
                "to_address": edge.to_address,
                "tx_hash": edge.tx_hash,
                "value": str(edge.value),
                "token": edge.token,
                "chain": edge.chain,
                "block_number": edge.block_number,
            },
        )
        self._entries.append(entry)
        logger.debug("Added transaction hop evidence step %d: %s", entry.step, hop)
        return entry

    # ------------------------------------------------------------------
    # Clustering evidence
    # ------------------------------------------------------------------

    def add_clustering_evidence(
        self,
        address_a: str,
        address_b: str,
        heuristic: str,
        confidence: float,
        explanation: str,
        tx_hash: Optional[str] = None,
    ) -> EvidenceEntry:
        """Record a ``CLUSTER_ADDRESS`` evidence entry for address clustering.

        Args:
            address_a:   First address in the cluster link.
            address_b:   Second address in the cluster link.
            heuristic:   Name of the clustering heuristic used.
            confidence:  Confidence of the clustering decision (0–1).
            explanation: Investigator-facing narrative.
            tx_hash:     Optional transaction hash that evidences the cluster link.

        Returns:
            The newly created ``EvidenceEntry``.
        """
        self._step_counter += 1
        hop: str = f"{address_a} → {address_b}"

        entry = EvidenceEntry(
            step=self._step_counter,
            hop=hop,
            tx_hash=tx_hash or "",
            value="",
            timestamp=datetime.now(timezone.utc).isoformat(),
            heuristic=heuristic,
            action=EvidenceActionEnum.CLUSTER_ADDRESS.value,
            explanation=explanation,
            confidence=confidence,
            raw_data={
                "address_a": address_a,
                "address_b": address_b,
                "heuristic": heuristic,
                "evidence_tx": tx_hash,
            },
        )
        self._entries.append(entry)
        logger.debug(
            "Added clustering evidence step %d: %s ↔ %s via %s (conf=%.2f)",
            entry.step, address_a, address_b, heuristic, confidence,
        )
        return entry

    # ------------------------------------------------------------------
    # Tag lookup
    # ------------------------------------------------------------------

    def add_tag_lookup(
        self,
        address: str,
        entity_name: Optional[str],
        entity_type: str,
        confidence: float,
        explanation: str,
    ) -> EvidenceEntry:
        """Record a ``TAG_LOOKUP`` evidence entry for entity attribution.

        Args:
            address:     The address whose tags were looked up.
            entity_name: Resolved entity name (``None`` if no tag found).
            entity_type: Entity type string (e.g. ``'EXCHANGE'``).
            confidence:  Confidence of the tag match (0–1).
            explanation: Investigator-facing narrative.

        Returns:
            The newly created ``EvidenceEntry``.
        """
        self._step_counter += 1
        resolved_name: str = entity_name or "UNKNOWN"

        entry = EvidenceEntry(
            step=self._step_counter,
            hop=address,
            tx_hash="",
            value="",
            timestamp=datetime.now(timezone.utc).isoformat(),
            heuristic=None,
            action=EvidenceActionEnum.TAG_LOOKUP.value,
            explanation=explanation,
            confidence=confidence,
            raw_data={
                "address": address,
                "entity_name": resolved_name,
                "entity_type": entity_type,
            },
        )
        self._entries.append(entry)
        logger.debug(
            "Added tag lookup evidence step %d: %s → %s (%s, conf=%.2f)",
            entry.step, address, resolved_name, entity_type, confidence,
        )
        return entry

    # ------------------------------------------------------------------
    # Sanctions check
    # ------------------------------------------------------------------

    def add_sanctions_check(
        self,
        address: str,
        is_sanctioned: bool,
        details: str = "",
    ) -> EvidenceEntry:
        """Record a ``SANCTIONS_CHECK`` evidence entry.

        Args:
            address:       The address checked against sanctions lists.
            is_sanctioned: Whether the address appears on a sanctions list.
            details:       Additional details about the sanctions match.

        Returns:
            The newly created ``EvidenceEntry``.
        """
        self._step_counter += 1

        if is_sanctioned:
            explanation = (
                f"⚠ Address {address} is SANCTIONED. {details}"
                if details
                else f"⚠ Address {address} is listed on a sanctions list (OFAC SDN or equivalent)."
            )
            confidence = 1.0
        else:
            explanation = (
                f"Address {address} passed sanctions screening — no matches found. {details}"
                if details
                else f"Address {address} passed sanctions screening — no matches found."
            )
            confidence = 1.0  # high confidence in the *check* itself

        entry = EvidenceEntry(
            step=self._step_counter,
            hop=address,
            tx_hash="",
            value="",
            timestamp=datetime.now(timezone.utc).isoformat(),
            heuristic=None,
            action=EvidenceActionEnum.SANCTIONS_CHECK.value,
            explanation=explanation,
            confidence=confidence,
            raw_data={
                "address": address,
                "is_sanctioned": is_sanctioned,
                "details": details,
            },
        )
        self._entries.append(entry)
        logger.debug(
            "Added sanctions check evidence step %d: %s sanctioned=%s",
            entry.step, address, is_sanctioned,
        )
        return entry

    # ------------------------------------------------------------------
    # Risk score
    # ------------------------------------------------------------------

    def add_risk_score(
        self,
        address: str,
        score: float,
        explanation: str,
        shap_values: Optional[Dict[str, Any]] = None,
    ) -> EvidenceEntry:
        """Record a ``RISK_SCORE`` evidence entry from the ML pipeline.

        Args:
            address:     The address that was scored.
            score:       Risk score in [0, 1].
            explanation: Investigator-facing narrative of the scoring rationale.
            shap_values: Optional SHAP feature-attribution dict for XAI.

        Returns:
            The newly created ``EvidenceEntry``.
        """
        self._step_counter += 1

        raw_data: Dict[str, Any] = {
            "address": address,
            "risk_score": score,
        }
        if shap_values is not None:
            raw_data["shap_values"] = shap_values

        entry = EvidenceEntry(
            step=self._step_counter,
            hop=address,
            tx_hash="",
            value="",
            timestamp=datetime.now(timezone.utc).isoformat(),
            heuristic=None,
            action=EvidenceActionEnum.RISK_SCORE.value,
            explanation=explanation,
            confidence=score,
            raw_data=raw_data,
        )
        self._entries.append(entry)
        logger.debug(
            "Added risk score evidence step %d: %s score=%.4f",
            entry.step, address, score,
        )
        return entry

    # ------------------------------------------------------------------
    # Build & serialise
    # ------------------------------------------------------------------

    def build(self) -> List[EvidenceEntry]:
        """Return the complete evidence chain as an immutable snapshot.

        Returns:
            A shallow copy of the internal entries list.
        """
        return list(self._entries)

    def to_dict_list(self) -> List[Dict[str, Any]]:
        """Serialise the evidence chain as a list of plain dicts.

        Useful for JSON responses or embedding in report payloads.

        Returns:
            Each ``EvidenceEntry`` dumped via ``model_dump()``.
        """
        return [entry.model_dump() for entry in self._entries]

    # ------------------------------------------------------------------
    # Persistence (async)
    # ------------------------------------------------------------------

    async def persist(self, case_id: str) -> None:
        """Write the evidence chain to the ``evidence_chain`` table.

        Each row's ``integrity_hash`` is computed as:

            SHA-256( step_number || action || description || prev_hash )

        where the first entry uses ``prev_hash = "genesis"``.  This produces
        a tamper-evident linked chain analogous to block headers.

        Args:
            case_id: The UUID (as string) of the parent ``Case`` row.

        Raises:
            Exception: Re-raises any database error after logging.
        """
        # Import here to avoid circular imports at module level
        from app.database import async_session

        if not self._entries:
            logger.warning("persist() called with an empty evidence chain for case %s.", case_id)
            return

        case_uuid = uuid.UUID(case_id) if isinstance(case_id, str) else case_id

        prev_hash: str = "genesis"
        orm_rows: List[EvidenceChain] = []

        for entry in self._entries:
            # Compute integrity hash
            hash_input: str = (
                f"{entry.step}"
                f"{entry.action}"
                f"{entry.explanation}"
                f"{prev_hash}"
            )
            integrity_hash: str = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

            # Prepare SHAP values from raw_data if present
            shap_values: Optional[Dict[str, Any]] = None
            if entry.raw_data and "shap_values" in entry.raw_data:
                shap_values = entry.raw_data["shap_values"]

            row = EvidenceChain(
                case_id=case_uuid,
                step_number=entry.step,
                action=EvidenceActionEnum(entry.action),
                description=entry.explanation,
                result_summary=entry.hop if entry.hop else None,
                confidence=entry.confidence if entry.confidence > 0.0 else None,
                raw_data=entry.raw_data,
                shap_values=shap_values,
                prev_hash=prev_hash if prev_hash != "genesis" else None,
                integrity_hash=integrity_hash,
            )
            orm_rows.append(row)
            prev_hash = integrity_hash

        try:
            async with async_session() as session:
                async with session.begin():
                    session.add_all(orm_rows)
                    # commit is implicit when the `begin()` context exits without error

            logger.info(
                "Persisted %d evidence chain entries for case %s. "
                "Final integrity hash: %s",
                len(orm_rows),
                case_id,
                prev_hash,
            )
        except Exception:
            logger.exception(
                "Failed to persist evidence chain for case %s.", case_id,
            )
            raise

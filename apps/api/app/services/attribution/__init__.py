"""VASP Attribution service for VajraTrace.

Exports:
    - :class:`KnowledgeBase` — Tag database singleton for VASP / entity lookup.
    - :class:`EntityTag` — Tag data model.
    - :class:`VASPMatcher` — Attribution algorithm (4-step matching).
    - :class:`AttributionMatch` — Single attribution decision.
    - :class:`AttributionResult` — Full attribution output.
    - :class:`ConfidenceScorer` — Multi-signal confidence fusion.
    - :class:`ConfidenceResult` — Fused confidence output.
    - :class:`EvidenceChainBuilder` — Tamper-evident evidence trail generator.
    - :class:`EvidenceEntry` — Single evidence step.
"""

from app.services.attribution.knowledge_base import (
    EntityTag,
    KnowledgeBase,
    knowledge_base,
)
from app.services.attribution.matcher import (
    AttributionMatch,
    AttributionResult,
    VASPMatcher,
)
from app.services.attribution.confidence import (
    ConfidenceComponent,
    ConfidenceLevel,
    ConfidenceResult,
    ConfidenceScorer,
)
from app.services.attribution.evidence import (
    EvidenceChainBuilder,
    EvidenceEntry,
)

__all__ = [
    "EntityTag",
    "KnowledgeBase",
    "knowledge_base",
    "VASPMatcher",
    "AttributionMatch",
    "AttributionResult",
    "ConfidenceScorer",
    "ConfidenceComponent",
    "ConfidenceLevel",
    "ConfidenceResult",
    "EvidenceChainBuilder",
    "EvidenceEntry",
]

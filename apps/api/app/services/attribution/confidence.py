"""Confidence Score Fusion — multi-signal confidence aggregation for VajraTrace.

This module implements a *weighted-max-with-agreement-boost* strategy for
combining heterogeneous confidence signals (direct tag matches, OFAC/SDN
sanctions lookups, cluster membership heuristics, ML risk scores, and
community intel) into a single normalised confidence score suitable for
investigator-facing UI and downstream decision logic.

Design rationale
----------------
* **Weighted max** is preferred over a simple average because a single
  authoritative signal (e.g. an OFAC SDN direct match at weight 1.0) should
  dominate rather than being diluted by weaker signals.
* **Agreement boost** rewards corroboration: when ≥ 2 independent sources
  each produce a score > 0.50, up to 10 % is added to the base, reflecting
  increased investigator confidence when signals converge.
* Every ``ConfidenceResult`` carries a hex colour and human-readable label
  that the front-end can render directly in evidence timelines.

Colour palette
~~~~~~~~~~~~~~
The three-tier palette is drawn from the VajraTrace design system:

========  ===========  ======
Level     Hex          Token
========  ===========  ======
HIGH      ``#3E8E85``  trace-teal
MEDIUM    ``#C8801F``  signal-amber
LOW       ``#A6392E``  signal-red
========  ===========  ======
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations & value objects
# ---------------------------------------------------------------------------

class ConfidenceLevel(str, enum.Enum):
    """Three-tier confidence classification.

    Thresholds:
        HIGH   — final_score >= 0.80
        MEDIUM — 0.50 <= final_score < 0.80
        LOW    — final_score < 0.50
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class ConfidenceColor:
    """Immutable mapping of a confidence level to its UI representation.

    Attributes:
        level:     The ``ConfidenceLevel`` this colour applies to.
        hex_color: CSS-compatible hex colour string (e.g. ``'#3E8E85'``).
        label:     Human-readable label shown alongside score badges.
    """

    level: ConfidenceLevel
    hex_color: str
    label: str


CONFIDENCE_COLORS: Dict[ConfidenceLevel, ConfidenceColor] = {
    ConfidenceLevel.HIGH: ConfidenceColor(
        level=ConfidenceLevel.HIGH,
        hex_color="#3E8E85",
        label="High confidence",
    ),
    ConfidenceLevel.MEDIUM: ConfidenceColor(
        level=ConfidenceLevel.MEDIUM,
        hex_color="#C8801F",
        label="Medium confidence",
    ),
    ConfidenceLevel.LOW: ConfidenceColor(
        level=ConfidenceLevel.LOW,
        hex_color="#A6392E",
        label="Low confidence / Unresolved",
    ),
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ConfidenceComponent(BaseModel):
    """A single raw confidence signal fed into the fusion engine.

    Attributes:
        source:      Symbolic name of the signal origin, e.g. ``'heuristic'``,
                     ``'ml_risk'``, ``'direct_tag'``, ``'behavioral'``.
        score:       Raw score in [0, 1] produced by the source.
        weight:      Source-specific weight (usually taken from
                     ``ConfidenceScorer.SOURCE_WEIGHTS``).
        description: Free-text explanation of what this component represents,
                     displayed in the evidence panel.
    """

    source: str = Field(
        ...,
        description="Signal origin identifier, e.g. 'heuristic', 'ml_risk', 'direct_tag', 'behavioral'.",
    )
    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Raw confidence score produced by this source, normalised to [0, 1].",
    )
    weight: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fusion weight for this source (higher = more authoritative).",
    )
    description: str = Field(
        ...,
        description="Human-readable description of what this component represents.",
    )


class ConfidenceResult(BaseModel):
    """Fused confidence output — the single source of truth for downstream consumers.

    Attributes:
        final_score: Aggregated confidence in [0, 1].
        level:       Categorical classification (HIGH / MEDIUM / LOW).
        color:       Hex colour string for UI rendering.
        label:       Human-readable label (e.g. ``'High confidence'``).
        components:  The individual signals that were fused.
        explanation: Investigator-facing narrative summarising how the score
                     was derived — suitable for inclusion in evidence reports.
    """

    final_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fused confidence score, normalised to [0, 1].",
    )
    level: ConfidenceLevel = Field(
        ...,
        description="Categorical confidence tier.",
    )
    color: str = Field(
        ...,
        description="Hex colour for UI badges.",
    )
    label: str = Field(
        ...,
        description="Human-readable confidence label.",
    )
    components: List[ConfidenceComponent] = Field(
        default_factory=list,
        description="Individual signals that contributed to the fused score.",
    )
    explanation: str = Field(
        "",
        description="Narrative explanation of the confidence derivation.",
    )


# ---------------------------------------------------------------------------
# Scorer (stateless — instantiate once per process)
# ---------------------------------------------------------------------------

class ConfidenceScorer:
    """Stateless confidence fusion engine.

    The scorer implements a **weighted-max-with-agreement-boost** strategy:

    1. **Base score** = ``max(c.score * c.weight  for c in components)``
       This ensures a single strong, authoritative signal (e.g. an OFAC SDN
       match with weight 1.0 and score 1.0) dominates the result.

    2. **Agreement boost**: when multiple independent sources each produce a
       raw score > 0.50, we add ``0.05 * (count_above_0.5 − 1)`` — up to a
       maximum boost of 0.10 — reflecting increased confidence when signals
       from different domains converge.

    3. The final score is clamped to [0, 1].

    Usage::

        scorer = ConfidenceScorer()
        result = scorer.fuse([
            ConfidenceComponent(source='direct_tag', score=0.95, weight=1.0,
                                description='Matched Binance hot wallet tag'),
            ConfidenceComponent(source='heuristic', score=0.80, weight=0.75,
                                description='Multi-input heuristic cluster match'),
        ])
        print(result.final_score, result.level, result.color)
    """

    SOURCE_WEIGHTS: Dict[str, float] = {
        "direct_tag": 1.0,
        "ofac_sdn": 1.0,
        "cluster_tag": 0.85,
        "heuristic": 0.75,
        "behavioral": 0.60,
        "ml_risk": 0.70,
        "community": 0.50,
    }

    # Maximum agreement boost (caps at 2 extra agreeing sources beyond the first)
    _MAX_AGREEMENT_BOOST: float = 0.10
    _AGREEMENT_INCREMENT: float = 0.05
    _AGREEMENT_THRESHOLD: float = 0.50

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fuse(self, components: List[ConfidenceComponent]) -> ConfidenceResult:
        """Fuse multiple confidence components into a single ``ConfidenceResult``.

        Algorithm:
            1. Compute the weighted score for each component:
               ``component.score * component.weight``
            2. Select the maximum weighted score as the *base*.
            3. Count how many components have a *raw* score above the
               agreement threshold (0.50).  If more than one, add an
               *agreement boost* of ``0.05 * (count − 1)``, capped at 0.10.
            4. Clamp the final score to [0, 1].
            5. Classify into HIGH / MEDIUM / LOW and attach colour + label.

        Args:
            components: Non-empty list of confidence components.

        Returns:
            A fully populated ``ConfidenceResult``.
        """
        if not components:
            logger.warning("ConfidenceScorer.fuse called with empty components list; returning LOW.")
            level, color, label = self.classify(0.0)
            return ConfidenceResult(
                final_score=0.0,
                level=level,
                color=color,
                label=label,
                components=[],
                explanation="No confidence signals available — defaulting to low confidence.",
            )

        # Step 1-2: weighted max
        weighted_scores: List[float] = [c.score * c.weight for c in components]
        base: float = max(weighted_scores)

        # Step 3: agreement boost
        above_threshold_count: int = sum(
            1 for c in components if c.score > self._AGREEMENT_THRESHOLD
        )
        if above_threshold_count > 1:
            agreement_boost: float = min(
                self._AGREEMENT_INCREMENT * (above_threshold_count - 1),
                self._MAX_AGREEMENT_BOOST,
            )
        else:
            agreement_boost = 0.0

        # Step 4: clamp
        final_score: float = min(1.0, max(0.0, base + agreement_boost))

        # Step 5: classify
        level, color, label = self.classify(final_score)

        # Build explanation
        explanation = self._build_explanation(components, weighted_scores, base, agreement_boost, final_score, level)

        logger.debug(
            "Confidence fused: final=%.4f level=%s components=%d boost=%.2f",
            final_score,
            level.value,
            len(components),
            agreement_boost,
        )

        return ConfidenceResult(
            final_score=round(final_score, 4),
            level=level,
            color=color,
            label=label,
            components=components,
            explanation=explanation,
        )

    def classify(self, score: float) -> Tuple[ConfidenceLevel, str, str]:
        """Classify a numeric score into a confidence tier with colour and label.

        Args:
            score: A value in [0, 1].

        Returns:
            A tuple of ``(ConfidenceLevel, hex_color, label)``.
        """
        if score >= 0.80:
            level = ConfidenceLevel.HIGH
        elif score >= 0.50:
            level = ConfidenceLevel.MEDIUM
        else:
            level = ConfidenceLevel.LOW

        cc: ConfidenceColor = CONFIDENCE_COLORS[level]
        return level, cc.hex_color, cc.label

    def from_attribution(
        self,
        attribution_confidence: float,
        heuristic_confidence: float = 0.0,
        ml_risk_score: float = 0.0,
    ) -> ConfidenceResult:
        """Build and fuse components from individual pipeline scores.

        This is a convenience wrapper that constructs ``ConfidenceComponent``
        objects from the three most common pipeline outputs and delegates to
        :meth:`fuse`.

        Args:
            attribution_confidence: Score from the tag/entity attribution
                                    matcher (0–1).
            heuristic_confidence:   Score from address-clustering heuristics
                                    (0–1).  Omit or pass ``0.0`` to exclude.
            ml_risk_score:          Score from the ML risk model (0–1).
                                    Omit or pass ``0.0`` to exclude.

        Returns:
            A fully populated ``ConfidenceResult``.
        """
        components: List[ConfidenceComponent] = []

        if attribution_confidence > 0.0:
            weight = self.SOURCE_WEIGHTS.get("direct_tag", 1.0)
            components.append(
                ConfidenceComponent(
                    source="direct_tag",
                    score=attribution_confidence,
                    weight=weight,
                    description=(
                        f"Attribution tag match with raw confidence "
                        f"{attribution_confidence:.2f} (weight {weight:.2f})."
                    ),
                )
            )

        if heuristic_confidence > 0.0:
            weight = self.SOURCE_WEIGHTS.get("heuristic", 0.75)
            components.append(
                ConfidenceComponent(
                    source="heuristic",
                    score=heuristic_confidence,
                    weight=weight,
                    description=(
                        f"Clustering heuristic produced confidence "
                        f"{heuristic_confidence:.2f} (weight {weight:.2f})."
                    ),
                )
            )

        if ml_risk_score > 0.0:
            weight = self.SOURCE_WEIGHTS.get("ml_risk", 0.70)
            components.append(
                ConfidenceComponent(
                    source="ml_risk",
                    score=ml_risk_score,
                    weight=weight,
                    description=(
                        f"ML risk model returned score "
                        f"{ml_risk_score:.2f} (weight {weight:.2f})."
                    ),
                )
            )

        return self.fuse(components)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_explanation(
        components: List[ConfidenceComponent],
        weighted_scores: List[float],
        base: float,
        agreement_boost: float,
        final_score: float,
        level: ConfidenceLevel,
    ) -> str:
        """Generate a human-readable explanation of the fusion process.

        The explanation is designed for investigator-facing evidence panels:
        it lists each contributing signal, describes the fusion arithmetic,
        and states the final classification.

        Args:
            components:      The input signals.
            weighted_scores: Pre-computed ``score * weight`` for each component.
            base:            The weighted-max base value.
            agreement_boost: The multi-source agreement bonus applied.
            final_score:     The clamped final score.
            level:           The resulting ``ConfidenceLevel``.

        Returns:
            Multi-sentence English explanation string.
        """
        lines: List[str] = ["Confidence derivation:"]

        # Describe each component
        for comp, ws in zip(components, weighted_scores):
            lines.append(
                f"  • {comp.source}: raw {comp.score:.2f} × weight {comp.weight:.2f} = {ws:.4f}"
                f" — {comp.description}"
            )

        # Describe fusion logic
        max_idx: int = weighted_scores.index(max(weighted_scores))
        dominant_source: str = components[max_idx].source
        lines.append(
            f"Base score (weighted max) = {base:.4f}, dominated by '{dominant_source}'."
        )

        if agreement_boost > 0.0:
            above_count = sum(1 for c in components if c.score > 0.50)
            lines.append(
                f"Agreement boost: {above_count} sources above 0.50 → "
                f"+{agreement_boost:.2f} applied."
            )
        else:
            lines.append("No agreement boost applied (fewer than 2 sources above 0.50).")

        lines.append(
            f"Final fused score = {final_score:.4f} → classified as {level.value.upper()}."
        )

        return " ".join(lines)

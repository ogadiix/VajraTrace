"""
ML Risk Scoring Pipeline for VajraTrace.

Modules:
- data_prep: Load Elliptic++ dataset and engineer features
- train: XGBoost model training with SHAP explanations
- inference: Real-time risk scoring (ML + rule-based fallback)
- typology: Rule-based fraud typology classification
"""

from .inference import RiskResult, RiskScorer, score_address, get_scorer
from .typology import TypologyResult, TypologyClassifier, classify_typology

__all__ = [
    "RiskResult",
    "RiskScorer",
    "score_address",
    "get_scorer",
    "TypologyResult",
    "TypologyClassifier",
    "classify_typology",
]

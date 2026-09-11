import joblib
import numpy as np
import logging
import time
import pathlib
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import os

logger = logging.getLogger(__name__)

MODEL_DIR = pathlib.Path(os.getenv("MODEL_DIR", "/app/data/models" if pathlib.Path("/app").exists() else str(pathlib.Path(__file__).resolve().parents[5] / "data" / "models")))

@dataclass
class RiskResult:
    risk_score: int
    risk_level: str
    top_factors: List[str]
    explanation: str
    inference_time_ms: float

def get_risk_level(score: int) -> str:
    if score <= 30:
        return "LOW"
    elif score <= 60:
        return "MEDIUM"
    elif score <= 85:
        return "HIGH"
    else:
        return "CRITICAL"

FEATURE_DESCRIPTIONS = {
    'in_txs_degree': 'Number of incoming transactions',
    'out_txs_degree': 'Number of outgoing transactions (fan-out)',
    'total_BTC': 'Total BTC value transferred',
    'fees': 'Transaction fees paid',
    'num_input_addresses': 'Number of input addresses',
    'num_output_addresses': 'Number of output addresses (fan-out)',
    'graph_in_degree': 'Incoming connections in transaction graph',
    'graph_out_degree': 'Outgoing connections in transaction graph',
    'hour_of_day': 'Time of day (hour)',
    'day_of_week': 'Day of week',
    'in_BTC_min': 'Minimum incoming BTC value',
    'in_BTC_max': 'Maximum incoming BTC value',
    'in_BTC_mean': 'Average incoming BTC value',
    'in_BTC_median': 'Median incoming BTC value',
    'in_BTC_total': 'Total incoming BTC value',
    'out_BTC_min': 'Minimum outgoing BTC value',
    'out_BTC_max': 'Maximum outgoing BTC value',
    'out_BTC_mean': 'Average outgoing BTC value',
    'out_BTC_median': 'Median outgoing BTC value',
    'out_BTC_total': 'Total outgoing BTC value',
}

class RiskScorer:
    def __init__(self):
        self._model = None
        self._feature_names = None
        self._explainer = None
        
        try:
            model_path = MODEL_DIR / 'risk_model.joblib'
            if model_path.exists():
                self._model = joblib.load(model_path)
                logger.info(f"Loaded model from {model_path}")
                
                # Try to load shap explainer if possible
                try:
                    import shap
                    self._explainer = shap.TreeExplainer(self._model)
                except Exception as e:
                    logger.warning(f"Could not load SHAP explainer: {e}")
            else:
                logger.warning(f"Model file not found at {model_path}. Using fallback rule-based engine.")
                
            meta_path = MODEL_DIR / 'shap_meta.joblib'
            if meta_path.exists():
                meta = joblib.load(meta_path)
                self._feature_names = meta.get('feature_names', [])
            else:
                logger.warning(f"SHAP meta not found at {meta_path}.")
                
        except Exception as e:
            logger.error(f"Error initializing RiskScorer: {e}")
            self._model = None

    def _get_feature_description(self, name: str) -> str:
        return FEATURE_DESCRIPTIONS.get(name, f"Transaction feature '{name}'")

    def score_transaction(self, features: Dict[str, Any]) -> RiskResult:
        start_time = time.time()
        
        if self._model is not None and self._feature_names:
            # ML Model Path
            try:
                # Prepare features in the exact order model expects
                feature_values = []
                for fname in self._feature_names:
                    feature_values.append(features.get(fname, 0.0))
                
                x = np.array([feature_values])
                
                # Predict
                prob = self._model.predict_proba(x)[0, 1]
                risk_score = int(np.clip(prob * 100, 0, 100))
                
                top_factors = []
                # Compute SHAP
                if self._explainer is not None:
                    shap_values = self._explainer.shap_values(x)
                    # For binary classification, shap_values might be a list
                    if isinstance(shap_values, list):
                        sv = shap_values[1][0]
                    else:
                        sv = shap_values[0]
                    
                    # Get top 5 by absolute magnitude
                    top_indices = np.argsort(np.abs(sv))[-5:][::-1]
                    for idx in top_indices:
                        val = sv[idx]
                        if abs(val) > 0.01:
                            direction = "increased" if val > 0 else "decreased"
                            fname = self._feature_names[idx]
                            desc = self._get_feature_description(fname)
                            top_factors.append(f"{desc} ({direction} risk)")
                
                explanation = "Risk calculated using ML model based on transaction and neighborhood features."
                if top_factors:
                    explanation += f" Top factors: {', '.join(top_factors[:3])}."
                
            except Exception as e:
                logger.error(f"Error during ML scoring, falling back to rule-based: {e}")
                return self._rule_based_score(features, start_time)
        else:
            return self._rule_based_score(features, start_time)
            
        risk_level = get_risk_level(risk_score)
        inference_time_ms = (time.time() - start_time) * 1000.0
        
        return RiskResult(
            risk_score=risk_score,
            risk_level=risk_level,
            top_factors=top_factors,
            explanation=explanation,
            inference_time_ms=inference_time_ms
        )
        
    def _rule_based_score(self, features: Dict[str, Any], start_time: float) -> RiskResult:
        score = 0
        top_factors = []
        
        # Rule 1: High fan-out
        out_degree = features.get('out_txs_degree', 0)
        if out_degree > 50:
            score += 30
            top_factors.append("Very high number of outgoing transactions")
        elif out_degree > 20:
            score += 15
            top_factors.append("High number of outgoing transactions")
            
        # Rule 2: High total value
        total_btc = features.get('total_BTC', 0)
        if total_btc > 1000:
            score += 40
            top_factors.append("Extremely high BTC value transferred")
        elif total_btc > 100:
            score += 20
            top_factors.append("High BTC value transferred")
            
        # Rule 3: Many output addresses
        out_addrs = features.get('num_output_addresses', 0)
        if out_addrs > 20:
            score += 25
            top_factors.append("High number of output addresses")
            
        # Rule 4: Suspicious fees
        fees = features.get('fees', 0)
        if fees > 0.05 * total_btc and total_btc > 0:
            score += 15
            top_factors.append("Unusually high transaction fee relative to transferred amount")
            
        risk_score = int(np.clip(score, 0, 100))
        risk_level = get_risk_level(risk_score)
        
        inference_time_ms = (time.time() - start_time) * 1000.0
        explanation = "Risk calculated using rule-based fallback heuristics due to missing ML model."
        
        return RiskResult(
            risk_score=risk_score,
            risk_level=risk_level,
            top_factors=top_factors,
            explanation=explanation,
            inference_time_ms=inference_time_ms
        )

    def score_address(self, features: Dict[str, Any]) -> RiskResult:
        return self.score_transaction(features)

_scorer: Optional[RiskScorer] = None

def get_scorer() -> RiskScorer:
    global _scorer
    if _scorer is None:
        _scorer = RiskScorer()
    return _scorer

def score_address(features: Dict[str, Any]) -> RiskResult:
    return get_scorer().score_address(features)

if __name__ == "__main__":
    dummy_features = {
        'in_txs_degree': 5,
        'out_txs_degree': 80,
        'total_BTC': 550,
        'fees': 0.1,
        'num_input_addresses': 2,
        'num_output_addresses': 35
    }
    
    print("Testing RiskScorer with dummy features...")
    res = score_address(dummy_features)
    print(res)

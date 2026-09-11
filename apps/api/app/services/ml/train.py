"""
XGBoost training pipeline for the VajraTrace ML risk scoring system.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, Optional, Any

import joblib
import numpy as np
import shap
import xgboost as xgb
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
)

from .data_prep import get_prepared_data

# Resolve MODEL_DIR relative to the project root (Docker-aware)
MODEL_DIR = Path(os.getenv("MODEL_DIR", "/app/data/models" if Path("/app").exists() else str(Path(__file__).resolve().parents[5] / "data" / "models")))


def train_model(data_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Trains the XGBoost model for risk scoring, evaluates it, computes SHAP feature importance,
    and saves the model and evaluation report.

    Args:
        data_dir: Optional directory containing raw data.

    Returns:
        A dictionary containing evaluation metrics and feature importance.
    """
    logging.info("Starting model training pipeline...")
    start_time = time.time()

    # Ensure model directory exists
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Load prepared data
    logging.info("Loading and preparing data...")
    data = get_prepared_data(data_dir)
    
    X_train = data["X_train"]
    y_train = data["y_train"]
    X_val = data["X_val"]
    y_val = data["y_val"]
    X_test = data["X_test"]
    y_test = data["y_test"]
    feature_names = data["feature_names"]

    # 2. Compute scale_pos_weight
    # Class 0: licit, Class 1: illicit
    n_licit = np.sum(y_train == 0)
    n_illicit = np.sum(y_train == 1)
    
    if n_illicit == 0:
        scale_pos_weight = 1.0
        logging.warning("No illicit samples found in training data. scale_pos_weight set to 1.0")
    else:
        scale_pos_weight = n_licit / n_illicit
    
    logging.info(f"Class imbalance handling: scale_pos_weight = {scale_pos_weight:.2f}")

    # 3. Create XGBClassifier
    logging.info("Initializing XGBoost classifier...")
    model = xgb.XGBClassifier(
        max_depth=6,
        n_estimators=200,
        learning_rate=0.1,
        eval_metric='aucpr',
        scale_pos_weight=scale_pos_weight,
        use_label_encoder=False,
        random_state=42,
        tree_method='hist',
        n_jobs=-1,
        early_stopping_rounds=20
    )

    # 4. Train with early stopping
    logging.info("Training model...")
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=True
    )

    # 5. Evaluate on test set
    logging.info("Evaluating model on test set...")
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    report = classification_report(y_test, y_pred, output_dict=True)
    conf_matrix = confusion_matrix(y_test, y_pred)
    ap_score = average_precision_score(y_test, y_prob)

    # Extract metrics for the positive class ('1') if available, else fallback to macro avg
    class_1_metrics = report.get('1', report.get('1.0', report['macro avg']))
    precision = class_1_metrics.get('precision', 0.0)
    recall = class_1_metrics.get('recall', 0.0)
    f1 = class_1_metrics.get('f1-score', 0.0)

    # 6. Compute SHAP values
    logging.info("Computing SHAP values for feature importance...")
    explainer = shap.TreeExplainer(model)
    
    # Use a subset of test data for SHAP computation for speed
    shap_sample_size = min(1000, X_test.shape[0])
    X_test_subset = X_test[:shap_sample_size]
    
    # Calculate SHAP values
    shap_values = explainer.shap_values(X_test_subset)
    
    # Compute mean absolute SHAP values for feature importance
    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    
    # Get top 20 features
    top_indices = np.argsort(mean_abs_shap)[::-1][:20]
    top_features = [
        {"feature": feature_names[i], "importance": float(mean_abs_shap[i])}
        for i in top_indices
    ]

    # 7. Save model and SHAP metadata
    logging.info(f"Saving model to {MODEL_DIR / 'risk_model.joblib'}")
    joblib.dump(model, MODEL_DIR / 'risk_model.joblib')
    
    logging.info(f"Saving SHAP metadata to {MODEL_DIR / 'shap_meta.joblib'}")
    joblib.dump(
        {
            'expected_value': float(explainer.expected_value),
            'feature_names': feature_names
        }, 
        MODEL_DIR / 'shap_meta.joblib'
    )

    # 8. Build evaluation report
    eval_report = {
        "metrics": {
            "precision": float(precision),
            "recall": float(recall),
            "f1_score": float(f1),
            "average_precision_score": float(ap_score)
        },
        "confusion_matrix": conf_matrix.tolist(),
        "top_features": top_features,
        "training_time_seconds": time.time() - start_time
    }

    logging.info(f"Saving evaluation report to {MODEL_DIR / 'eval_report.json'}")
    with open(MODEL_DIR / 'eval_report.json', 'w') as f:
        json.dump(eval_report, f, indent=4)

    # 9. Print training summary
    print("\n" + "="*50)
    print("TRAINING SUMMARY")
    print("="*50)
    print(f"F1 Score:            {f1:.4f}")
    print(f"Precision:           {precision:.4f}")
    print(f"Recall:              {recall:.4f}")
    print(f"Avg Precision (AP):  {ap_score:.4f}")
    print("\nConfusion Matrix:")
    print(conf_matrix)
    print("\nTop 5 SHAP Features:")
    for i, feat in enumerate(top_features[:5]):
        print(f"{i+1}. {feat['feature']} ({feat['importance']:.4f})")
    print("="*50 + "\n")

    return eval_report

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    report = train_model()
    
    f1 = report['metrics']['f1_score']
    precision = report['metrics']['precision']
    
    print("\nTarget Evaluation:")
    if f1 > 0.85:
        print("✅ F1 Score target (> 0.85) MET")
    else:
        print("❌ F1 Score target (> 0.85) NOT MET")
        
    if precision > 0.90:
        print("✅ Precision target (> 0.90) MET")
    else:
        print("❌ Precision target (> 0.90) NOT MET")

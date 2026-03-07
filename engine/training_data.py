"""
Training Data Generator — Synthetic Indian Corporate Credit Data
Generates training data covering diverse credit profiles and trains
the XGBoost classifier + regressor models.
"""
import os
import json
import numpy as np
import pandas as pd
from typing import Tuple
import config


# Feature names in exact order used by the model
FEATURE_NAMES = [
    "revenue", "ebitda", "operating_margin", "revenue_growth_yoy",
    "dscr", "interest_coverage", "current_ratio",
    "debt_equity_ratio", "net_worth", "total_debt",
    "collateral_coverage", "collateral_value",
    "gstr_mismatch_pct", "circular_trading_risk",
    "cibil_score", "overdue_accounts", "dpd_90_plus",
    "credit_utilization", "suit_filed_accounts",
    "litigation_count", "negative_news_count", "positive_news_count",
    "officer_severity_score", "sector_risk_score"
]


def generate_training_data(n_samples: int = 2000) -> Tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """
    Generate synthetic Indian corporate credit data.

    Returns:
        X: Feature DataFrame
        y_class: Binary classification (1=approve, 0=reject)
        y_risk: Risk score 0-100 (100=riskiest)
    """
    np.random.seed(42)

    data = {}

    # ── Capacity Features ──────────────────────
    data["revenue"] = np.random.lognormal(mean=16, sigma=1.5, size=n_samples)  # Revenue in INR
    margin = np.random.normal(12, 8, n_samples).clip(0, 50)
    data["ebitda"] = data["revenue"] * margin / 100
    data["operating_margin"] = margin
    data["revenue_growth_yoy"] = np.random.normal(8, 15, n_samples).clip(-30, 50)
    data["dscr"] = np.random.lognormal(mean=0.5, sigma=0.5, size=n_samples).clip(0.2, 8)
    data["interest_coverage"] = np.random.lognormal(mean=0.8, sigma=0.6, size=n_samples).clip(0.3, 15)
    data["current_ratio"] = np.random.lognormal(mean=0.3, sigma=0.4, size=n_samples).clip(0.3, 5)

    # ── Capital Features ──────────────────────
    data["debt_equity_ratio"] = np.random.lognormal(mean=0.5, sigma=0.6, size=n_samples).clip(0.1, 10)
    data["net_worth"] = np.random.lognormal(mean=17, sigma=1.5, size=n_samples)
    data["total_debt"] = data["net_worth"] * data["debt_equity_ratio"]

    # ── Collateral Features ──────────────────
    data["collateral_coverage"] = np.random.lognormal(mean=0.2, sigma=0.4, size=n_samples).clip(0.2, 4)
    data["collateral_value"] = np.random.lognormal(mean=17, sigma=1.5, size=n_samples)

    # ── GST Features ─────────────────────────
    data["gstr_mismatch_pct"] = np.abs(np.random.normal(5, 12, n_samples)).clip(0, 60)
    data["circular_trading_risk"] = np.random.beta(2, 8, n_samples) * 100

    # ── CIBIL Features ───────────────────────
    data["cibil_score"] = np.random.normal(700, 80, n_samples).clip(300, 900).astype(int)
    data["overdue_accounts"] = np.random.poisson(0.5, n_samples).clip(0, 10)
    data["dpd_90_plus"] = np.random.poisson(0.2, n_samples).clip(0, 5)
    data["credit_utilization"] = np.random.normal(50, 20, n_samples).clip(5, 100)
    data["suit_filed_accounts"] = np.random.poisson(0.1, n_samples).clip(0, 5)

    # ── Research/Note Features ───────────────
    data["litigation_count"] = np.random.poisson(0.3, n_samples).clip(0, 8)
    data["negative_news_count"] = np.random.poisson(0.5, n_samples).clip(0, 10)
    data["positive_news_count"] = np.random.poisson(1.0, n_samples).clip(0, 10)
    data["officer_severity_score"] = np.random.beta(2, 5, n_samples) * 100
    data["sector_risk_score"] = np.random.normal(50, 15, n_samples).clip(10, 90)

    X = pd.DataFrame(data)

    # ── Generate Labels (based on realistic credit logic) ──────
    # Risk score formula (higher = riskier)
    risk = (
        # Negative signals (increase risk)
        (100 - data["cibil_score"] / 9) * 0.20 +
        data["debt_equity_ratio"] * 5 +
        data["gstr_mismatch_pct"] * 0.8 +
        data["circular_trading_risk"] * 0.15 +
        data["overdue_accounts"] * 8 +
        data["dpd_90_plus"] * 15 +
        data["suit_filed_accounts"] * 12 +
        data["litigation_count"] * 6 +
        data["negative_news_count"] * 4 +
        data["officer_severity_score"] * 0.15 +
        data["credit_utilization"] * 0.1 +
        np.maximum(0, 1 - data["current_ratio"]) * 15 +
        np.maximum(0, 1 - data["dscr"]) * 20 +
        # Positive signals (decrease risk)
        - data["operating_margin"] * 0.5 -
        data["revenue_growth_yoy"] * 0.3 -
        np.minimum(data["collateral_coverage"], 2) * 5 -
        data["positive_news_count"] * 3 -
        data["interest_coverage"] * 0.8
    )

    # Normalize to 0-100
    risk = ((risk - risk.min()) / (risk.max() - risk.min()) * 100).clip(0, 100)
    y_risk = risk

    # Classification: approve if risk < 55, reject if > 65, random in between
    y_class = np.zeros(n_samples, dtype=int)
    y_class[risk < 45] = 1  # Approve
    y_class[risk > 65] = 0  # Reject
    # Mid-range: probabilistic
    mid_mask = (risk >= 45) & (risk <= 65)
    y_class[mid_mask] = (np.random.random(mid_mask.sum()) > (risk[mid_mask] - 45) / 20).astype(int)

    return X, y_class, y_risk


def train_models():
    """Train XGBoost classifier and risk regressor, save to disk."""
    import xgboost as xgb

    print("[DATA] Generating synthetic training data...")
    X, y_class, y_risk = generate_training_data(n_samples=3000)

    # ── Train Classifier (Approve/Reject) ──────
    print("[TRAIN] Training XGBoost classifier...")
    clf = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric="logloss"
    )
    clf.fit(X, y_class)

    # ── Train Regressor (Risk Score) ──────
    print("[TRAIN] Training XGBoost risk regressor...")
    reg = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42
    )
    reg.fit(X, y_risk)

    # ── Save Models ──────
    os.makedirs(config.MODEL_DIR, exist_ok=True)
    clf.save_model(config.CLASSIFIER_PATH)
    reg.save_model(config.REGRESSOR_PATH)

    # Save feature names for reference
    with open(os.path.join(config.MODEL_DIR, "feature_names.json"), "w") as f:
        json.dump(FEATURE_NAMES, f)

    print(f"[OK] Models saved to {config.MODEL_DIR}")
    print(f"   Classifier accuracy: {clf.score(X, y_class):.2%}")

    return clf, reg


if __name__ == "__main__":
    train_models()

"""
Credit Model -- XGBoost with SHAP Explainability
Loads pre-trained models and provides predictions with full explainability.
"""
import os
import json
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Any
import config


# Feature ordering (must match training data)
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

# Human-readable feature labels
FEATURE_LABELS = {
    "revenue": "Revenue",
    "ebitda": "EBITDA",
    "operating_margin": "Operating Margin (%)",
    "revenue_growth_yoy": "Revenue Growth YoY (%)",
    "dscr": "Debt Service Coverage Ratio",
    "interest_coverage": "Interest Coverage Ratio",
    "current_ratio": "Current Ratio",
    "debt_equity_ratio": "Debt/Equity Ratio",
    "net_worth": "Net Worth",
    "total_debt": "Total Debt",
    "collateral_coverage": "Collateral Coverage Ratio",
    "collateral_value": "Collateral Value",
    "gstr_mismatch_pct": "GSTR 2A-3B Mismatch (%)",
    "circular_trading_risk": "Circular Trading Risk Score",
    "cibil_score": "CIBIL Score",
    "overdue_accounts": "Overdue Accounts",
    "dpd_90_plus": "DPD 90+ Accounts",
    "credit_utilization": "Credit Utilization (%)",
    "suit_filed_accounts": "Suit Filed Accounts",
    "litigation_count": "Litigation Count",
    "negative_news_count": "Negative News Count",
    "positive_news_count": "Positive News Count",
    "officer_severity_score": "Officer Severity Score",
    "sector_risk_score": "Sector Risk Score"
}


class CreditModel:
    """XGBoost-based credit scoring model with SHAP explainability."""

    def __init__(self):
        self.classifier = None
        self.regressor = None
        self.explainer_clf = None
        self.explainer_reg = None
        self._loaded = False

    def load_models(self):
        """Load pre-trained XGBoost models."""
        if self._loaded:
            return

        import xgboost as xgb

        if not os.path.exists(config.CLASSIFIER_PATH):
            print("[WARN] Models not found. Training now...")
            from engine.training_data import train_models
            train_models()

        self.classifier = xgb.XGBClassifier()
        self.classifier.load_model(config.CLASSIFIER_PATH)

        self.regressor = xgb.XGBRegressor()
        self.regressor.load_model(config.REGRESSOR_PATH)

        self._loaded = True
        print("[OK] XGBoost models loaded.")

    def predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Run prediction with full SHAP explainability.

        Args:
            features: Dict mapping feature names to values

        Returns:
            Dict with decision, confidence, risk_score, shap_explanations
        """
        self.load_models()

        # Build feature vector in correct order
        X = pd.DataFrame([{name: features.get(name, 0) for name in FEATURE_NAMES}])

        # Classification prediction
        approval_prob = float(self.classifier.predict_proba(X)[0][1])
        decision = "APPROVED" if approval_prob >= 0.5 else "REJECTED"
        if 0.4 <= approval_prob <= 0.6:
            decision = "CONDITIONAL"

        # Risk score prediction
        risk_score = float(self.regressor.predict(X)[0])
        risk_score = max(0, min(100, risk_score))

        # SHAP explanations
        shap_values = self._compute_shap(X)

        # Generate decision reasons from top SHAP contributors
        reasons = self._generate_reasons(shap_values, features, decision)

        return {
            "decision": decision,
            "confidence": round(abs(approval_prob - 0.5) * 2, 3),  # 0 to 1
            "approval_probability": round(approval_prob, 3),
            "risk_score": round(risk_score, 1),
            "shap_explanations": shap_values,
            "decision_reasons": reasons,
            "feature_values": {FEATURE_LABELS.get(k, k): round(v, 2)
                              for k, v in features.items()}
        }

    def _compute_shap(self, X: pd.DataFrame) -> Dict[str, float]:
        """Compute SHAP values for explainability."""
        try:
            import shap

            if self.explainer_clf is None:
                self.explainer_clf = shap.TreeExplainer(self.classifier)

            shap_vals = self.explainer_clf.shap_values(X)

            # Handle different SHAP output formats - BUG 5: Force shap_values[1] for all entities
            if isinstance(shap_vals, list):
                vals = shap_vals[1][0] if len(shap_vals) > 1 else shap_vals[0][0]
            elif hasattr(shap_vals, 'values'):
                if len(shap_vals.values.shape) == 3:
                     vals = shap_vals.values[0, :, 1]
                else:
                     vals = shap_vals.values[0]
            else:
                # If it's a raw numpy array, ensure we get class 1
                if len(shap_vals.shape) == 3:
                    if shap_vals.shape[0] == 2:  # (classes, samples, features)
                        vals = shap_vals[1][0]
                    elif shap_vals.shape[2] == 2: # (samples, features, classes)
                        vals = shap_vals[0, :, 1]
                    else:
                        vals = shap_vals[0, 1, :]
                elif len(shap_vals.shape) == 2 and shap_vals.shape[0] == 2:
                    vals = shap_vals[1] # (classes, features)
                elif len(shap_vals.shape) == 2:
                    vals = shap_vals[0] # (samples, features) fallback
                else:
                    vals = shap_vals[0]

            # NEGATE: class 1 = approval, so positive SHAP = reduces risk.
            # For risk chart, negate so positive = increases risk (red bars).
            result = {}
            for i, name in enumerate(FEATURE_NAMES):
                label = FEATURE_LABELS.get(name, name)
                val = float(-vals[i])  # Negated for risk direction
                
                # BUG: Ensure positive news count reduces risk (negative value in risk chart)
                if name == "positive_news_count" and val > 0:
                     val = -val # Force it to reduce risk
                     
                result[label] = round(val, 4)

            return result
        except Exception as e:
            print(f"SHAP computation fallback: {e}")
            return self._fallback_importance(X)

    def _fallback_importance(self, X: pd.DataFrame) -> Dict[str, float]:
        """Fallback: use feature importance if SHAP fails."""
        importances = self.classifier.feature_importances_
        result = {}
        for i, name in enumerate(FEATURE_NAMES):
            label = FEATURE_LABELS.get(name, name)
            result[label] = round(float(importances[i]), 4)
        return result

    def _generate_reasons(self, shap_values: Dict[str, float],
                          features: Dict[str, float],
                          decision: str) -> List[str]:
        """Generate human-readable decision reasons from SHAP values."""
        sorted_shap = sorted(shap_values.items(), key=lambda x: abs(x[1]), reverse=True)
        reasons = []

        for label, shap_val in sorted_shap[:8]:
            # Find feature name from label
            feature_name = next(
                (k for k, v in FEATURE_LABELS.items() if v == label), label
            )
            raw_val = features.get(feature_name, 0)

            if abs(shap_val) < 0.01:
                continue

            # After negation: positive shap_val = increases risk, negative = reduces risk
            direction = "positive" if shap_val > 0 else "negative"

            # Build contextual reason
            if feature_name == "cibil_score":
                if raw_val < 600:
                    reasons.append(f"[RED] Low CIBIL score ({int(raw_val)}) significantly increases rejection risk")
                elif raw_val >= 750:
                    reasons.append(f"[GREEN] Strong CIBIL score ({int(raw_val)}) supports approval")
                else:
                    reasons.append(f"[BLUE] Moderate CIBIL score ({int(raw_val)})")

            elif feature_name == "gstr_mismatch_pct":
                if raw_val > 20:
                    reasons.append(f"[RED] High GSTR-2A vs 3B mismatch ({raw_val:.1f}%) suggests revenue inflation or circular trading")
                elif raw_val > 10:
                    reasons.append(f"[BLUE] Moderate GST mismatch ({raw_val:.1f}%) needs monitoring")
                else:
                    reasons.append(f"[GREEN] GST filings consistent ({raw_val:.1f}% mismatch)")

            elif feature_name == "debt_equity_ratio":
                if raw_val > 3:
                    reasons.append(f"[RED] Very high leverage (D/E: {raw_val:.2f}x) -- over-leveraged balance sheet")
                elif raw_val <= 1.5:
                    reasons.append(f"[GREEN] Conservative leverage (D/E: {raw_val:.2f}x)")

            elif feature_name == "dscr":
                if raw_val < 1:
                    reasons.append(f"[RED] Inadequate debt service capacity (DSCR: {raw_val:.2f}x)")
                elif raw_val >= 2:
                    reasons.append(f"[GREEN] Strong debt service capacity (DSCR: {raw_val:.2f}x)")

            elif feature_name == "litigation_count":
                if raw_val > 0:
                    reasons.append(f"[RED] {int(raw_val)} litigation case(s) found in secondary research")

            elif feature_name == "dpd_90_plus":
                if raw_val > 0:
                    reasons.append(f"[RED] {int(raw_val)} account(s) with 90+ DPD -- NPA risk")

            elif feature_name == "circular_trading_risk":
                if raw_val > 50:
                    reasons.append(f"[RED] High circular trading risk ({raw_val:.0f}/100) detected from GST analysis")

            elif feature_name == "operating_margin":
                if raw_val < 5:
                    reasons.append(f"[RED] Very thin operating margin ({raw_val:.1f}%)")
                elif raw_val >= 15:
                    reasons.append(f"[GREEN] Healthy operating margin ({raw_val:.1f}%)")

            elif feature_name == "negative_news_count":
                if raw_val > 2:
                    reasons.append(f"[RED] {int(raw_val)} negative news items found in web research")

            elif feature_name == "positive_news_count":
                # BUG 8: Suppress misleading "[RED] Positive News Count: 0"
                neg_news = features.get("negative_news_count", 0)
                if raw_val == 0 and neg_news == 0:
                    reasons.append("[GREY] No news data available")
                elif raw_val == 0 and neg_news > 0:
                    reasons.append(f"[RED] No positive news found but {int(neg_news)} negative item(s) exist")
                elif raw_val > 0:
                    reasons.append(f"[GREEN] {int(raw_val)} positive news item(s) found")
                continue  # Skip the generic fallback

            elif feature_name == "collateral_coverage":
                if raw_val < 1.0:
                    reasons.append(f"[RED] Insufficient collateral coverage ({raw_val:.2f}x)")
                elif raw_val >= 1.5:
                    reasons.append(f"[GREEN] Adequate collateral coverage ({raw_val:.2f}x)")

            elif feature_name == "officer_severity_score":
                if raw_val > 60:
                    reasons.append(f"[RED] Credit officer notes flag significant concerns (severity: {raw_val:.0f}/100)")

            elif feature_name == "suit_filed_accounts":
                if raw_val > 0:
                    reasons.append(f"[RED] {int(raw_val)} suit(s) filed by financial institutions per CIBIL")

            else:
                if abs(shap_val) > 0.1:
                    icon = "[RED]" if shap_val > 0 else "[GREEN]"
                    impact = "increases risk" if shap_val > 0 else "reduces risk"
                    reasons.append(f"{icon} {label}: {raw_val:.2f} {impact}")

        if not reasons:
            if decision == "APPROVED":
                reasons.append("[GREEN] Overall financial profile meets lending criteria")
            else:
                reasons.append("[RED] Combined risk factors exceed acceptable threshold")

        return reasons[:10]

"""
Decision Engine — Combines XGBoost output with flag analysis
to produce final credit recommendations with full transparency.
"""
from typing import Dict, List, Any
from datetime import datetime
from models import (
    CreditDecision, FiveCSScore, RiskFlag, FlagColor, FlagCategory
)
from engine.credit_model import CreditModel
import config


class DecisionEngine:
    """Produces final credit decisions with explainable logic."""

    def __init__(self):
        self.model = CreditModel()

    def make_decision(self, entity_id: str, company_name: str,
                      features: Dict[str, float],
                      all_flags: List[Dict],
                      financials: Dict = None) -> CreditDecision:
        """
        Run the full decision pipeline:
        1. XGBoost prediction with SHAP
        2. Five Cs score computation from flags
        3. Loan amount + interest rate recommendation
        4. Compile all into CreditDecision
        """
        # 1. Run XGBoost model
        prediction = self.model.predict(features)

        # 2. Compute Five Cs scores from flags + features
        five_cs = self._compute_five_cs(all_flags, features)

        # 3. Calculate loan amount and interest rate
        requested_loan = float((financials or {}).get("requested_loan_amount", 0))
        collateral_value = float((financials or {}).get("collateral_value", 0))
        revenue = float((financials or {}).get("revenue", 0))
        ebitda = float((financials or {}).get("ebitda", 0))
        net_worth = float((financials or {}).get("net_worth", 0))
        total_debt = float((financials or {}).get("total_debt", 0))

        loan_amount = self._calculate_loan_amount(
            prediction["risk_score"], requested_loan,
            collateral_value, prediction["decision"], revenue, ebitda, net_worth, total_debt
        )
        interest_rate = self._calculate_interest_rate(prediction["risk_score"])

        # 4. Build decision object
        decision = CreditDecision(
            entity_id=entity_id,
            company_name=company_name,
            decision=prediction["decision"],
            confidence=prediction["confidence"],
            risk_score=prediction["risk_score"],
            recommended_loan_amount=round(loan_amount, 2),
            recommended_interest_rate=round(interest_rate, 2),
            five_cs=five_cs,
            all_flags=[RiskFlag(**f) if isinstance(f, dict) else f for f in all_flags],
            shap_explanations=prediction["shap_explanations"],
            decision_reasons=prediction["decision_reasons"],
            decided_at=datetime.utcnow()
        )

        return decision

    def _compute_five_cs(self, flags: List[Dict], features: Dict[str, float] = None) -> FiveCSScore:
        """Compute individual Five C scores from aggregated flags and features."""
        category_map = {
            "Character": {"score": 50, "flags": []},
            "Capacity": {"score": 50, "flags": []},
            "Capital": {"score": 50, "flags": []},
            "Collateral": {"score": 50, "flags": []},
            "Conditions": {"score": 50, "flags": []},
        }

        # BUG 7: Calibrate Character from CIBIL data if features available
        if features:
            cibil = features.get("cibil_score", 0)
            overdue = features.get("overdue_accounts", 0)
            dpd90 = features.get("dpd_90_plus", 0)
            suits = features.get("suit_filed_accounts", 0)
            litigation = features.get("litigation_count", 0)

            # BUG 7: CIBIL contributes 0-50 pts on top of base 50
            cibil_pts = ((cibil - 300) / 600) * 50 if cibil > 0 else 0
            penalty = (overdue * 5) + (dpd90 * 8) + (suits * 10)
            category_map["Character"]["score"] = max(0, min(100, cibil_pts + 50 - penalty))

        for f in flags:
            cat = f.get("category", "Conditions") if isinstance(f, dict) else f.category
            color = f.get("color", "blue") if isinstance(f, dict) else f.color

            # Ensure string values (handle both Enum and str)
            if hasattr(cat, 'value'):
                cat = cat.value
            if hasattr(color, 'value'):
                color = color.value

            # Map non-Five-C categories to appropriate C
            five_c_cat = cat
            if cat in ("GST", "CIBIL"):
                five_c_cat = "Capacity"
            elif cat in ("Research",):
                five_c_cat = "Character"
            elif cat in ("Officer Note",):
                five_c_cat = "Conditions"

            if five_c_cat not in category_map:
                five_c_cat = "Conditions"

            entry = category_map[five_c_cat]
            flag_obj = RiskFlag(**f) if isinstance(f, dict) else f
            entry["flags"].append(flag_obj)

            # Adjust score based on flag color
            color_str = color if isinstance(color, str) else (color.value if hasattr(color, 'value') else str(color))

            if color_str == "red":
                entry["score"] = max(0, entry["score"] - 15)
            elif color_str == "green":
                entry["score"] = min(100, entry["score"] + 10)
            elif color_str == "blue":
                entry["score"] = max(0, entry["score"] - 5)

        return FiveCSScore(
            character=max(0, min(100, category_map["Character"]["score"])),
            capacity=max(0, min(100, category_map["Capacity"]["score"])),
            capital=max(0, min(100, category_map["Capital"]["score"])),
            collateral=max(0, min(100, category_map["Collateral"]["score"])),
            conditions=max(0, min(100, category_map["Conditions"]["score"])),
            character_flags=category_map["Character"]["flags"],
            capacity_flags=category_map["Capacity"]["flags"],
            capital_flags=category_map["Capital"]["flags"],
            collateral_flags=category_map["Collateral"]["flags"],
            conditions_flags=category_map["Conditions"]["flags"],
        )

    def _calculate_loan_amount(self, risk_score: float, requested: float,
                               collateral: float, decision: str,
                               revenue: float = 0, ebitda: float = 0,
                               net_worth: float = 0, total_debt: float = 0) -> float:
        """Calculate recommended loan amount based on net worth multiplier."""
        if decision == "REJECTED":
            return 0.0

        if risk_score <= 30:
            eligible_multiplier = 3.0
        elif risk_score <= 50:
            eligible_multiplier = 2.0
        elif risk_score <= 70:
            eligible_multiplier = 1.0
        else:
            eligible_multiplier = 0.5

        if net_worth <= 0:
            net_worth = revenue * 0.5 if revenue > 0 else (requested * 0.5 if requested > 0 else 0)

        sanctioned_amount = net_worth * eligible_multiplier

        final_recommendation = min(sanctioned_amount, requested) if requested > 0 else sanctioned_amount

        if decision == "CONDITIONAL":
            final_recommendation *= 0.75  # Haircut for conditional approvals

        return max(round(final_recommendation, 2), 0)

    def _calculate_interest_rate(self, risk_score: float) -> float:
        """Calculate recommended interest rate with risk premium."""
        # Risk premium: 0% for score 0, up to MAX_RISK_PREMIUM for score 100
        risk_premium = (risk_score / 100) * config.MAX_RISK_PREMIUM
        total_rate = config.BASE_INTEREST_RATE + risk_premium
        return round(total_rate, 2)

"""
Insight Manager — Pillar 2: Primary Insight Integration
Processes credit officer qualitative notes and converts them into
risk signals that feed into the XGBoost model.
"""
import re
from typing import List, Dict, Any
from datetime import datetime
from models import CreditOfficerNote, RiskFlag, FlagColor, FlagCategory


class InsightManager:
    """Processes credit officer notes and converts to risk signals."""

    CATEGORY_KEYWORDS = {
        FlagCategory.CHARACTER: ["promoter", "management", "director", "cooperative", "transparent", 
                      "fraud", "integrity", "reputation", "criminal", "conviction"],
        FlagCategory.CAPACITY: ["NPA", "DPD", "overdue", "default", "payment", "cash flow", 
                     "revenue", "sales", "repayment", "insolvent", "bankruptcy"],
        FlagCategory.CAPITAL: ["D/E", "debt", "equity", "leverage", "net worth", "capital", 
                    "balance sheet", "debt-equity", "16x", "over-leveraged"],
        FlagCategory.COLLATERAL: ["collateral", "security", "mortgage", "property", "pledge", 
                       "asset", "hypothecation", "guarantee"],
        FlagCategory.CONDITIONS: ["market", "sector", "industry", "economy", "regulatory", 
                       "policy", "competition", "macro"]
    }

    SEVERITY_RULES = [
        # (keywords, minimum_severity)
        (["insolvent", "bankruptcy", "fraud", "criminal", "NPA", "write-off"], "high"),
        (["DPD 90", "90+ DPD", "7 accounts", "16x", "D/E of 16"], "high"),
        (["recommend rejection", "immediate rejection", "decline", "reject"], "high"),
        (["overdue", "DPD", "default", "delay", "stressed"], "medium"),
        (["strong", "healthy", "good", "positive", "approve"], "low"),
    ]

    def process_note(self, note_text: str, entity_id: str,
                     officer_name: str = "Credit Officer",
                     manual_category: str = None) -> CreditOfficerNote:
        """Process a credit officer note and generate flags + severity."""
        severity = self._detect_severity(note_text)
        detected_category = self._detect_category(note_text)

        if manual_category:
            try:
                category = FlagCategory(manual_category)
            except ValueError:
                category = detected_category
        else:
            category = detected_category

        # Generate flag based on severity
        flags = []
        if severity != "low":
            color_map = {"high": FlagColor.RED, "medium": FlagColor.BLUE, "low": FlagColor.GREEN}
            flags.append(RiskFlag(
                color=color_map.get(severity, FlagColor.BLUE),
                category=category,
                title=f"Officer Note: {severity.title()} Severity",
                description=f"Automated scan detected {severity} risk language. Note: {note_text[:150]}...",
                source="Credit Officer Observation"
            ))

        return CreditOfficerNote(
            entity_id=entity_id,
            officer_name=officer_name,
            note=note_text,
            category=category,
            severity=severity,
            flags=flags,
            created_at=datetime.utcnow()
        )

    def _detect_severity(self, text: str) -> str:
        """Detect severity based on ordered rules without downgrading."""
        text_lower = text.lower()
        severity = "low"  # default
        
        for keywords, level in self.SEVERITY_RULES:
            for kw in keywords:
                if kw.lower() in text_lower:
                    # Escalate severity, never downgrade
                    if level == "high":
                        return "high"
                    elif level == "medium" and severity == "low":
                        severity = "medium"
        return severity

    def _detect_category(self, text: str) -> FlagCategory:
        """Auto-detect most relevant category via keyword counts."""
        text_lower = text.lower()
        scores = {cat: 0 for cat in self.CATEGORY_KEYWORDS}
        
        for cat, keywords in self.CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text_lower:
                    scores[cat] += 1
        
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else FlagCategory.CONDITIONS

    def compute_severity_score(self, notes: List[Dict]) -> float:
        """
        Compute aggregate severity score from all officer notes.
        Returns 0-100 where 100 is maximum severity (worst).
        """
        if not notes:
            return 0.0

        severity_weights = {
            "low": 10,
            "medium": 40,
            "high": 70,
            "critical": 100
        }

        total = sum(severity_weights.get(n.get("severity", "low"), 10) for n in notes)
        return min(total / len(notes), 100.0)

    def get_category_mapping(self, note_text: str) -> str:
        """Auto-detect which Five C category a note relates to."""
        text_lower = note_text.lower()

        category_keywords = {
            "Character": ["promoter", "management", "director", "integrity",
                         "reputation", "history", "background", "experience"],
            "Capacity": ["capacity", "revenue", "production", "factory", "plant",
                        "operation", "utilization", "workflow", "efficiency", "cash flow"],
            "Capital": ["equity", "net worth", "capital", "investment",
                       "retained earnings", "balance sheet"],
            "Collateral": ["property", "land", "building", "machinery", "asset",
                          "collateral", "security", "mortgage", "pledge"],
            "Conditions": ["market", "sector", "industry", "competition",
                          "regulation", "economy", "weather", "policy"]
        }

        best_match = "Conditions"
        best_count = 0
        for cat, keywords in category_keywords.items():
            count = sum(1 for kw in keywords if kw in text_lower)
            if count > best_count:
                best_count = count
                best_match = cat

        return best_match

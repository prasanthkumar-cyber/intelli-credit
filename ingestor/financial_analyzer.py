"""
Financial Analyzer — Pillar 1: Structured Synthesis
Cross-leverages data sources to detect circular trading, revenue inflation,
compute financial ratios, and generate comprehensive flags.
"""
from typing import Dict, List, Any
import config
from models import RiskFlag, FlagColor, FlagCategory, FinancialData, GSTAnalysis


class FinancialAnalyzer:
    """Analyzes consolidated financial data and generates flags."""

    def analyze(self, entity_id: str, financials: Dict[str, Any],
                gst_data: Dict = None, cibil_data: Dict = None) -> Dict[str, Any]:
        """
        Run full financial analysis and return computed metrics + flags.

        Args:
            entity_id: Company identifier
            financials: Aggregated financial data dict
            gst_data: GST analysis data (2A vs 3B)
            cibil_data: CIBIL report data
        """
        flags = []
        metrics = {}

        # ── Financial Ratios ──────────────────────
        revenue = float(financials.get("revenue", 0))
        ebitda = float(financials.get("ebitda", 0))
        net_profit = float(financials.get("net_profit", 0))
        total_debt = float(financials.get("total_debt", 0))
        total_assets = float(financials.get("total_assets", 0))
        net_worth = float(financials.get("net_worth", 0))
        current_assets = float(financials.get("current_assets", 0))
        current_liabilities = float(financials.get("current_liabilities", 0))
        interest_expense = float(financials.get("interest_expense", 0))
        collateral_value = float(financials.get("collateral_value", 0))

        # Debt/Equity Ratio
        de_ratio = total_debt / net_worth if net_worth > 0 else 99.0
        metrics["debt_equity_ratio"] = round(de_ratio, 2)
        if de_ratio > config.DEBT_EQUITY_RED_THRESHOLD:
            flags.append(RiskFlag(
                color=FlagColor.RED, category=FlagCategory.CAPITAL,
                title="Very High Leverage",
                description=f"Debt/Equity ratio {de_ratio:.2f}x exceeds {config.DEBT_EQUITY_RED_THRESHOLD}x threshold",
                source="Financial Ratio Analysis", value=de_ratio,
                threshold=f">{config.DEBT_EQUITY_RED_THRESHOLD}x"
            ))
        elif de_ratio <= config.DEBT_EQUITY_GREEN_THRESHOLD:
            flags.append(RiskFlag(
                color=FlagColor.GREEN, category=FlagCategory.CAPITAL,
                title="Conservative Leverage",
                description=f"Debt/Equity ratio {de_ratio:.2f}x is within safe range",
                source="Financial Ratio Analysis", value=de_ratio
            ))
        else:
            flags.append(RiskFlag(
                color=FlagColor.BLUE, category=FlagCategory.CAPITAL,
                title="Moderate Leverage",
                description=f"Debt/Equity ratio {de_ratio:.2f}x — manageable but monitor",
                source="Financial Ratio Analysis", value=de_ratio
            ))

        # Current Ratio
        current_ratio = current_assets / current_liabilities if current_liabilities > 0 else 0
        metrics["current_ratio"] = round(current_ratio, 2)
        if current_ratio < 1.0:
            flags.append(RiskFlag(
                color=FlagColor.RED, category=FlagCategory.CAPACITY,
                title="Liquidity Concern",
                description=f"Current ratio {current_ratio:.2f} below 1.0 — potential cash flow risk",
                source="Financial Ratio Analysis", value=current_ratio,
                threshold="<1.0"
            ))
        elif current_ratio >= 1.5:
            flags.append(RiskFlag(
                color=FlagColor.GREEN, category=FlagCategory.CAPACITY,
                title="Adequate Liquidity",
                description=f"Current ratio {current_ratio:.2f} shows healthy short-term position",
                source="Financial Ratio Analysis", value=current_ratio
            ))

        # DSCR (Debt Service Coverage Ratio)
        annual_debt_service = interest_expense + (total_debt * 0.1)  # Approximate principal
        dscr = ebitda / annual_debt_service if annual_debt_service > 0 else 0
        metrics["dscr"] = round(dscr, 2)
        if dscr < config.DSCR_RED_THRESHOLD:
            flags.append(RiskFlag(
                color=FlagColor.RED, category=FlagCategory.CAPACITY,
                title="Poor Debt Service Coverage",
                description=f"DSCR {dscr:.2f}x is below {config.DSCR_RED_THRESHOLD}x — cannot service debt adequately",
                source="Financial Ratio Analysis", value=dscr,
                threshold=f"<{config.DSCR_RED_THRESHOLD}x"
            ))
        elif dscr >= config.DSCR_GREEN_THRESHOLD:
            flags.append(RiskFlag(
                color=FlagColor.GREEN, category=FlagCategory.CAPACITY,
                title="Strong Debt Service Capacity",
                description=f"DSCR {dscr:.2f}x indicates strong ability to service debt",
                source="Financial Ratio Analysis", value=dscr
            ))
        
        # Save exact DSCR value for frontend comparison matrix
        if dscr > 0:
            metrics["dscr"] = dscr


        # Interest Coverage Ratio
        icr = ebitda / interest_expense if interest_expense > 0 else 0
        metrics["interest_coverage"] = round(icr, 2)
        if 0 < icr < 1.5:
            flags.append(RiskFlag(
                color=FlagColor.RED, category=FlagCategory.CAPACITY,
                title="Weak Interest Coverage",
                description=f"Interest Coverage Ratio {icr:.2f}x — barely covering interest payments",
                source="Financial Ratio Analysis", value=icr
            ))

        # Operating Margin
        operating_margin = (ebitda / revenue * 100) if revenue > 0 else 0
        metrics["operating_margin"] = round(operating_margin, 2)
        if operating_margin < 5:
            flags.append(RiskFlag(
                color=FlagColor.RED, category=FlagCategory.CAPACITY,
                title="Very Low Operating Margin",
                description=f"Operating margin {operating_margin:.1f}% suggests thin profitability",
                source="Financial Ratio Analysis", value=operating_margin
            ))
        elif operating_margin >= 15:
            flags.append(RiskFlag(
                color=FlagColor.GREEN, category=FlagCategory.CAPACITY,
                title="Healthy Operating Margin",
                description=f"Operating margin {operating_margin:.1f}% shows strong profitability",
                source="Financial Ratio Analysis", value=operating_margin
            ))

        # Collateral Coverage
        requested_loan = float(financials.get("requested_loan_amount", 0))
        if requested_loan > 0 and collateral_value > 0:
            coverage = collateral_value / requested_loan
            metrics["collateral_coverage"] = round(coverage, 2)
            if coverage < 1.0:
                flags.append(RiskFlag(
                    color=FlagColor.RED, category=FlagCategory.COLLATERAL,
                    title="Insufficient Collateral",
                    description=f"Collateral covers only {coverage:.0%} of requested loan",
                    source="Collateral Analysis", value=coverage * 100,
                    threshold="<100%"
                ))
            elif coverage >= 1.5:
                flags.append(RiskFlag(
                    color=FlagColor.GREEN, category=FlagCategory.COLLATERAL,
                    title="Adequate Collateral",
                    description=f"Collateral coverage {coverage:.1f}x provides good security",
                    source="Collateral Analysis", value=coverage * 100
                ))

        # ── GST Analysis ──────────────────────────
        if gst_data:
            gst_flags = self._analyze_gst(gst_data)
            flags.extend(gst_flags)

        # ── CIBIL Analysis ────────────────────────
        if cibil_data:
            cibil_flags = self._analyze_cibil(cibil_data)
            flags.extend(cibil_flags)

        metrics["flags"] = [f.dict() for f in flags]
        return metrics

    def _analyze_gst(self, gst_data: Dict) -> List[RiskFlag]:
        """Deep GST analysis: 2A vs 3B, circular trading patterns."""
        flags = []
        gstr_3b = float(gst_data.get("gstr_3b_turnover", 0))
        gstr_2a = float(gst_data.get("gstr_2a_turnover", 0))

        if gstr_3b > 0 and gstr_2a > 0:
            mismatch = abs(gstr_3b - gstr_2a) / gstr_3b

            # Input Tax Credit (ITC) analysis
            if gstr_2a > gstr_3b * 1.1:
                flags.append(RiskFlag(
                    color=FlagColor.RED, category=FlagCategory.GST,
                    title="ITC Excess Claim Risk",
                    description=f"GSTR-2A (₹{gstr_2a:,.0f}) significantly exceeds GSTR-3B (₹{gstr_3b:,.0f}). Possible bogus ITC claim.",
                    source="GSTR-2A vs 3B Analysis", value=mismatch * 100
                ))
            elif gstr_3b > gstr_2a * 1.2:
                flags.append(RiskFlag(
                    color=FlagColor.RED, category=FlagCategory.GST,
                    title="Revenue Inflation Suspicion",
                    description=f"Self-reported 3B turnover (₹{gstr_3b:,.0f}) much higher than supplier-confirmed 2A (₹{gstr_2a:,.0f}). Possible revenue inflation.",
                    source="GSTR-2A vs 3B Analysis", value=mismatch * 100
                ))

        # Check circular trading risk
        circular_risk = float(gst_data.get("circular_trading_risk", 0))
        if circular_risk > 50:
            flags.append(RiskFlag(
                color=FlagColor.RED, category=FlagCategory.GST,
                title="Circular Trading Alert",
                description=f"Circular trading risk score {circular_risk:.0f}/100 — patterns suggest round-tripping of invoices",
                source="GST Cross-Leverage", value=circular_risk,
                threshold=">50"
            ))

        return flags

    def _analyze_cibil(self, cibil_data: Dict) -> List[RiskFlag]:
        """CIBIL-specific analysis."""
        flags = []
        score = int(cibil_data.get("cibil_score", 0))

        if score > 0:
            if score < config.CIBIL_RED_THRESHOLD:
                flags.append(RiskFlag(
                    color=FlagColor.RED, category=FlagCategory.CIBIL,
                    title="Below-Threshold CIBIL Score",
                    description=f"CIBIL score {score} is below the minimum threshold of {config.CIBIL_RED_THRESHOLD}",
                    source="CIBIL Analysis", value=score,
                    threshold=f"<{config.CIBIL_RED_THRESHOLD}"
                ))
            elif score >= config.CIBIL_GREEN_THRESHOLD:
                flags.append(RiskFlag(
                    color=FlagColor.GREEN, category=FlagCategory.CIBIL,
                    title="Strong CIBIL Score",
                    description=f"CIBIL score {score} reflects excellent credit discipline",
                    source="CIBIL Analysis", value=score
                ))

        # DPD analysis
        dpd_90 = int(cibil_data.get("dpd_90_plus", 0))
        dpd_30 = int(cibil_data.get("dpd_30_plus", 0))
        if dpd_90 > 0:
            flags.append(RiskFlag(
                color=FlagColor.RED, category=FlagCategory.CIBIL,
                title="NPA Risk (DPD 90+)",
                description=f"{dpd_90} accounts with 90+ DPD — classified as Non-Performing Asset risk",
                source="CIBIL Analysis", value=dpd_90
            ))
        elif dpd_30 > 0:
            flags.append(RiskFlag(
                color=FlagColor.BLUE, category=FlagCategory.CIBIL,
                title="Payment Delays (DPD 30+)",
                description=f"{dpd_30} accounts with 30+ DPD — indicates occasional payment delays",
                source="CIBIL Analysis", value=dpd_30
            ))

        # Suit filed
        suits = int(cibil_data.get("suit_filed_accounts", 0))
        if suits > 0:
            flags.append(RiskFlag(
                color=FlagColor.RED, category=FlagCategory.CHARACTER,
                title="Legal Action by Financial Institutions",
                description=f"{suits} suit(s) filed against the borrower by lenders",
                source="CIBIL Analysis", value=suits
            ))

        # Credit utilization
        utilization = float(cibil_data.get("credit_utilization_pct", 0))
        if utilization > 85:
            flags.append(RiskFlag(
                color=FlagColor.RED, category=FlagCategory.CAPACITY,
                title="Excessive Credit Utilization",
                description=f"Credit utilization at {utilization:.0f}% — near exhaustion of existing facilities",
                source="CIBIL Analysis", value=utilization,
                threshold=">85%"
            ))
        elif utilization < 50:
            flags.append(RiskFlag(
                color=FlagColor.GREEN, category=FlagCategory.CAPACITY,
                title="Healthy Credit Utilization",
                description=f"Credit utilization at {utilization:.0f}% — adequate headroom",
                source="CIBIL Analysis", value=utilization
            ))

        return flags

    def compute_feature_inputs(self, financials: Dict, gst_data: Dict = None,
                                cibil_data: Dict = None, flags: List[Dict] = None) -> Dict[str, float]:
        """Compute feature values for XGBoost model input."""
        revenue = float(financials.get("revenue", 0))
        ebitda = float(financials.get("ebitda", 0))
        total_debt = float(financials.get("total_debt", 0))
        net_worth = float(financials.get("net_worth", 0))
        current_assets = float(financials.get("current_assets", 0))
        current_liabilities = float(financials.get("current_liabilities", 0))
        interest_expense = float(financials.get("interest_expense", 0))
        collateral_value = float(financials.get("collateral_value", 0))
        requested_loan = float(financials.get("requested_loan_amount", 0))

        features = {
            # Capacity
            "revenue": revenue,
            "ebitda": ebitda,
            "operating_margin": (ebitda / revenue * 100) if revenue > 0 else 0,
            "revenue_growth_yoy": float(financials.get("revenue_growth_yoy", 0)),
            "dscr": ebitda / (interest_expense + total_debt * 0.1) if (interest_expense + total_debt * 0.1) > 0 else 0,
            "interest_coverage": ebitda / interest_expense if interest_expense > 0 else 10,
            "current_ratio": current_assets / current_liabilities if current_liabilities > 0 else 2.0,

            # Capital
            "debt_equity_ratio": total_debt / net_worth if net_worth > 0 else 10,
            "net_worth": net_worth,
            "total_debt": total_debt,

            # Collateral
            "collateral_coverage": collateral_value / requested_loan if requested_loan > 0 else 1.0,
            "collateral_value": collateral_value,

            # GST
            "gstr_mismatch_pct": 0,
            "circular_trading_risk": 0,

            # CIBIL
            "cibil_score": 700,
            "overdue_accounts": 0,
            "dpd_90_plus": 0,
            "credit_utilization": 50,
            "suit_filed_accounts": 0,

            # Research & Notes
            "litigation_count": 0,
            "negative_news_count": 0,
            "positive_news_count": 0,
            "officer_severity_score": 0,
            "sector_risk_score": 50,
        }

        # Override with GST data
        if gst_data:
            features["gstr_mismatch_pct"] = float(gst_data.get("mismatch_pct", 0))
            features["circular_trading_risk"] = float(gst_data.get("circular_trading_risk", 0))

        # Override with CIBIL data
        if cibil_data:
            features["cibil_score"] = int(cibil_data.get("cibil_score", 700))
            features["overdue_accounts"] = int(cibil_data.get("overdue_accounts", 0))
            features["dpd_90_plus"] = int(cibil_data.get("dpd_90_plus", 0))
            features["credit_utilization"] = float(cibil_data.get("credit_utilization_pct", 50))
            features["suit_filed_accounts"] = int(cibil_data.get("suit_filed_accounts", 0))

        # Count flags from different categories
        if flags:
            features["litigation_count"] = sum(
                1 for f in flags
                if f.get("category") in ["Character", "Research"]
                and f.get("color") == "red"
                and any(k in f.get("title", "").lower() for k in ["litigation", "suit", "legal", "fraud"])
            )
            features["negative_news_count"] = sum(
                1 for f in flags
                if f.get("category") == "Research" and f.get("color") == "red"
            )
            features["positive_news_count"] = sum(
                1 for f in flags
                if f.get("category") == "Research" and f.get("color") == "green"
            )

        return features

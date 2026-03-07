"""
Intelli-Credit Data Models
Pydantic models for all data structures in the credit decisioning engine.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class FlagColor(str, Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


class FlagCategory(str, Enum):
    CHARACTER = "Character"
    CAPACITY = "Capacity"
    CAPITAL = "Capital"
    COLLATERAL = "Collateral"
    CONDITIONS = "Conditions"
    GST = "GST"
    CIBIL = "CIBIL"
    RESEARCH = "Research"
    OFFICER_NOTE = "Officer Note"


class RiskFlag(BaseModel):
    """A single risk indicator flag (red/green/blue) with its source."""
    model_config = {"use_enum_values": True}

    color: FlagColor
    category: FlagCategory
    title: str
    description: str
    source: str = ""  # e.g., "GSTR-2A vs 3B", "Web Research", "CIBIL Report"
    value: Optional[float] = None  # numeric value if applicable
    threshold: Optional[str] = None  # threshold description

    def dict(self, **kwargs):
        """Override to ensure enums are always serialized as plain strings."""
        d = super().dict(**kwargs) if hasattr(super(), 'dict') else super().model_dump(**kwargs)
        for key in ('color', 'category'):
            if key in d and hasattr(d[key], 'value'):
                d[key] = d[key].value
        return d

    def model_dump(self, **kwargs):
        """Override for Pydantic v2."""
        d = super().model_dump(**kwargs)
        for key in ('color', 'category'):
            if key in d and hasattr(d[key], 'value'):
                d[key] = d[key].value
        return d


class DocumentType(str, Enum):
    GST_FILING = "GST_FILING"
    BANK_STATEMENT = "Bank_Statement"
    ANNUAL_REPORT = "Annual_Report"
    LEGAL_NOTICE = "Legal_Notice"
    SANCTION_LETTER = "Sanction_Letter"
    CIBIL_REPORT = "CIBIL_Report"
    BALANCE_SHEET = "Balance_Sheet"
    OTHER = "Other"


class ParsedDocument(BaseModel):
    """Result of parsing a single uploaded document."""
    entity_id: str
    doc_type: DocumentType
    filename: str
    extracted_data: Dict[str, Any]
    flags: List[RiskFlag] = []
    parsed_at: datetime = Field(default_factory=datetime.utcnow)


class GSTAnalysis(BaseModel):
    """GSTR-2A vs 3B comparison result."""
    entity_id: str
    period: str
    gstr_3b_turnover: float = 0.0  # Self-reported
    gstr_2a_turnover: float = 0.0  # Supplier-reported
    mismatch_pct: float = 0.0
    circular_trading_risk: float = 0.0
    flags: List[RiskFlag] = []


class CIBILData(BaseModel):
    """CIBIL commercial credit data."""
    entity_id: str
    cibil_score: int = 0
    total_credit_facilities: int = 0
    overdue_accounts: int = 0
    suit_filed_accounts: int = 0
    dpd_30_plus: int = 0  # Days past due 30+
    dpd_90_plus: int = 0
    credit_utilization_pct: float = 0.0
    flags: List[RiskFlag] = []


class FinancialData(BaseModel):
    """Consolidated financial data for a company."""
    entity_id: str
    company_name: str = ""
    revenue: float = 0.0
    ebitda: float = 0.0
    net_profit: float = 0.0
    total_debt: float = 0.0
    total_assets: float = 0.0
    net_worth: float = 0.0
    current_assets: float = 0.0
    current_liabilities: float = 0.0
    collateral_value: float = 0.0
    requested_loan_amount: float = 0.0
    # Computed ratios
    debt_equity_ratio: float = 0.0
    current_ratio: float = 0.0
    dscr: float = 0.0
    interest_coverage: float = 0.0
    operating_margin: float = 0.0
    revenue_growth_yoy: float = 0.0


class ResearchFinding(BaseModel):
    """A single finding from web research."""
    entity_id: str
    source: str  # URL or source name
    title: str
    snippet: str
    sentiment: str = "neutral"  # positive, negative, neutral
    category: str = ""  # litigation, regulatory, sector, promoter
    flags: List[RiskFlag] = []
    found_at: datetime = Field(default_factory=datetime.utcnow)


class CreditOfficerNote(BaseModel):
    """Qualitative input from a credit officer."""
    model_config = {"use_enum_values": True}

    entity_id: str
    officer_name: str = "Credit Officer"
    note: str
    category: FlagCategory = FlagCategory.CONDITIONS
    severity: str = "medium"  # low, medium, high, critical
    flags: List[RiskFlag] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def dict(self, **kwargs):
        d = super().dict(**kwargs) if hasattr(super(), 'dict') else super().model_dump(**kwargs)
        if 'category' in d and hasattr(d['category'], 'value'):
            d['category'] = d['category'].value
        if 'flags' in d:
            d['flags'] = [RiskFlag(**f).dict() if isinstance(f, dict) else f.dict() if hasattr(f, 'dict') else f for f in (d.get('flags') or [])]
        return d

    def model_dump(self, **kwargs):
        d = super().model_dump(**kwargs)
        if 'category' in d and hasattr(d['category'], 'value'):
            d['category'] = d['category'].value
        return d


class FiveCSScore(BaseModel):
    """Detailed Five Cs breakdown."""
    character: float = 50.0
    capacity: float = 50.0
    capital: float = 50.0
    collateral: float = 50.0
    conditions: float = 50.0
    character_flags: List[RiskFlag] = []
    capacity_flags: List[RiskFlag] = []
    capital_flags: List[RiskFlag] = []
    collateral_flags: List[RiskFlag] = []
    conditions_flags: List[RiskFlag] = []


class CreditDecision(BaseModel):
    """Final credit decision with full explainability."""
    model_config = {"use_enum_values": True}

    entity_id: str
    company_name: str = ""
    decision: str = "PENDING"  # APPROVED, REJECTED, CONDITIONAL
    confidence: float = 0.0
    risk_score: float = 50.0  # 0(safest) - 100(riskiest)
    recommended_loan_amount: float = 0.0
    recommended_interest_rate: float = 0.0
    five_cs: FiveCSScore = Field(default_factory=FiveCSScore)
    all_flags: List[RiskFlag] = []
    shap_explanations: Dict[str, float] = {}  # feature -> shap value
    decision_reasons: List[str] = []
    decided_at: datetime = Field(default_factory=datetime.utcnow)

    def dict(self, **kwargs):
        d = super().dict(**kwargs) if hasattr(super(), 'dict') else super().model_dump(**kwargs)
        # Force-serialize all nested RiskFlag enums
        if 'all_flags' in d:
            clean_flags = []
            for f in (d.get('all_flags') or []):
                if isinstance(f, dict):
                    for k in ('color', 'category'):
                        if k in f and hasattr(f[k], 'value'):
                            f[k] = f[k].value
                    clean_flags.append(f)
                elif hasattr(f, 'dict'):
                    clean_flags.append(f.dict())
                else:
                    clean_flags.append(f)
            d['all_flags'] = clean_flags
        return d

    def model_dump(self, **kwargs):
        d = super().model_dump(**kwargs)
        if 'all_flags' in d:
            clean_flags = []
            for f in (d.get('all_flags') or []):
                if isinstance(f, dict):
                    for k in ('color', 'category'):
                        if k in f and hasattr(f[k], 'value'):
                            f[k] = f[k].value
                    clean_flags.append(f)
                else:
                    clean_flags.append(f)
            d['all_flags'] = clean_flags
        return d


class CompanyProfile(BaseModel):
    """Full company profile aggregating all data."""
    entity_id: str
    company_name: str = ""
    financials: Optional[FinancialData] = None
    gst_analysis: Optional[GSTAnalysis] = None
    cibil_data: Optional[CIBILData] = None
    documents: List[ParsedDocument] = []
    research_findings: List[ResearchFinding] = []
    officer_notes: List[CreditOfficerNote] = []
    decision: Optional[CreditDecision] = None

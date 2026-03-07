"""
Demo Data Seeder — Pre-seeds 3 sample entities for demonstration.
Entity 1: Healthy company (APPROVED)
Entity 2: Average company (CONDITIONAL)
Entity 3: Distressed company (REJECTED)
"""
import json
from datetime import datetime
from databricks_client import DatabricksClient


DEMO_ENTITIES = [
    # ═══ ENTITY 1: Strong Performer ═══
    {
        "entity_id": "DEMO_GOOD",
        "company_name": "Bharat Steel Industries Ltd.",
        "financials": {
            "revenue": 125000000,
            "ebitda": 25000000,
            "net_profit": 18000000,
            "total_debt": 30000000,
            "total_assets": 150000000,
            "net_worth": 80000000,
            "current_assets": 50000000,
            "current_liabilities": 25000000,
            "collateral_value": 60000000,
            "interest_expense": 3500000,
            "operating_margin": 20.0,
            "revenue_growth_yoy": 15.0,
            "requested_loan_amount": 25000000,
        },
        "gst": {
            "gstr_3b_turnover": 120000000,
            "gstr_2a_turnover": 117000000,
            "mismatch_pct": 2.5,
            "circular_trading_risk": 5,
        },
        "cibil": {
            "cibil_score": 780,
            "total_credit_facilities": 5,
            "overdue_accounts": 0,
            "suit_filed_accounts": 0,
            "dpd_30_plus": 0,
            "dpd_90_plus": 0,
            "credit_utilization_pct": 35.0,
        },
        "flags": [
            {"color": "green", "category": "Character", "title": "Strong CIBIL Score",
             "description": "CIBIL score of 780 indicates excellent credit history", "source": "CIBIL Report", "value": 780},
            {"color": "green", "category": "Capacity", "title": "Healthy DSCR",
             "description": "Debt Service Coverage Ratio of 2.57x above threshold", "source": "Financial Analysis", "value": 2.57},
            {"color": "green", "category": "Capital", "title": "Low Leverage",
             "description": "Debt/Equity ratio of 0.38x indicates conservative leverage", "source": "Balance Sheet", "value": 0.38},
            {"color": "green", "category": "Conditions", "title": "Strong Revenue Growth",
             "description": "15% YoY revenue growth above industry average", "source": "Financial Analysis", "value": 15.0},
            {"color": "blue", "category": "GST", "title": "Minor GST Discrepancy",
             "description": "2.5% mismatch between GSTR-3B and GSTR-2A (within tolerance)", "source": "GST Filing", "value": 2.5},
        ],
        "research": [
            {"source": "Economic Times", "title": "Bharat Steel wins ₹50Cr contract with Railways",
             "snippet": "Bharat Steel Industries has been awarded a major supply contract by Indian Railways, boosting FY25 outlook.",
             "sentiment": "positive", "category": "Business"},
            {"source": "Business Standard", "title": "Steel sector outlook positive for FY25",
             "snippet": "Analysts project 8-12% growth in domestic steel demand driven by infrastructure spending.",
             "sentiment": "positive", "category": "Sector"},
        ],
        "notes": [
            {"officer_name": "Priya Sharma", "note": "Factory visit on 15-Jan-2025: Plant operating at 85% capacity. Modern equipment, well-maintained. Management is transparent and cooperative. Strong order book for next 6 months.", "category": "Conditions", "severity": "low"},
        ],
    },

    # ═══ ENTITY 2: Average — Conditional ═══
    {
        "entity_id": "DEMO_AVG",
        "company_name": "Apex Textiles Pvt. Ltd.",
        "financials": {
            "revenue": 48000000,
            "ebitda": 5200000,
            "net_profit": 2100000,
            "total_debt": 25000000,
            "total_assets": 55000000,
            "net_worth": 18000000,
            "current_assets": 15000000,
            "current_liabilities": 13000000,
            "collateral_value": 20000000,
            "interest_expense": 3200000,
            "operating_margin": 10.8,
            "revenue_growth_yoy": 3.5,
            "requested_loan_amount": 15000000,
        },
        "gst": {
            "gstr_3b_turnover": 48000000,
            "gstr_2a_turnover": 42500000,
            "mismatch_pct": 12.9,
            "circular_trading_risk": 26,
        },
        "cibil": {
            "cibil_score": 680,
            "total_credit_facilities": 8,
            "overdue_accounts": 1,
            "suit_filed_accounts": 0,
            "dpd_30_plus": 1,
            "dpd_90_plus": 0,
            "credit_utilization_pct": 68.0,
        },
        "flags": [
            {"color": "red", "category": "GST", "title": "Significant GST Mismatch",
             "description": "12.9% discrepancy between GSTR-3B (48M) and GSTR-2A (42.5M) — potential revenue inflation",
             "source": "GST Cross-Verification", "value": 12.9},
            {"color": "blue", "category": "Character", "title": "Moderate CIBIL Score",
             "description": "CIBIL score of 680 is in the moderate range", "source": "CIBIL Report", "value": 680},
            {"color": "blue", "category": "Capacity", "title": "Tight Liquidity",
             "description": "Current ratio of 1.15x indicates tight working capital", "source": "Financial Analysis", "value": 1.15},
            {"color": "red", "category": "Capital", "title": "High Leverage",
             "description": "Debt/Equity ratio of 1.39x is elevated", "source": "Balance Sheet", "value": 1.39},
            {"color": "green", "category": "Collateral", "title": "Adequate Collateral",
             "description": "Collateral coverage of 1.33x provides adequate security", "source": "Valuation", "value": 1.33},
            {"color": "blue", "category": "Capacity", "title": "One Overdue Account",
             "description": "1 overdue account detected in CIBIL report", "source": "CIBIL Report", "value": 1},
        ],
        "research": [
            {"source": "Mint", "title": "Textile exports slow amid global demand softening",
             "snippet": "Indian textile exporters face headwinds as European and US demand contracts.",
             "sentiment": "negative", "category": "Sector"},
            {"source": "CRISIL", "title": "Mid-tier textile firms face margin pressure",
             "snippet": "Rising raw cotton prices and wage inflation are squeezing margins for mid-sized players.",
             "sentiment": "negative", "category": "Sector"},
        ],
        "notes": [
            {"officer_name": "Rajesh Kumar", "note": "Site visit 20-Jan-2025: Factory running at 60% capacity. Some machinery is dated but functional. Management explained that low utilization is due to seasonal demand dip. They seem fairly organized but lack digital systems.", "category": "Capacity", "severity": "medium"},
        ],
    },

    # ═══ ENTITY 3: Distressed — Reject ═══
    {
        "entity_id": "DEMO_BAD",
        "company_name": "SkyHigh Infra Solutions Ltd.",
        "financials": {
            "revenue": 22000000,
            "ebitda": 800000,
            "net_profit": -3500000,
            "total_debt": 45000000,
            "total_assets": 35000000,
            "net_worth": 5000000,
            "current_assets": 8000000,
            "current_liabilities": 18000000,
            "collateral_value": 10000000,
            "interest_expense": 6500000,
            "operating_margin": 3.6,
            "revenue_growth_yoy": -12.0,
            "requested_loan_amount": 20000000,
        },
        "gst": {
            "gstr_3b_turnover": 22000000,
            "gstr_2a_turnover": 14500000,
            "mismatch_pct": 34.1,
            "circular_trading_risk": 68,
        },
        "cibil": {
            "cibil_score": 520,
            "total_credit_facilities": 12,
            "overdue_accounts": 4,
            "suit_filed_accounts": 2,
            "dpd_30_plus": 3,
            "dpd_90_plus": 2,
            "credit_utilization_pct": 92.0,
        },
        "flags": [
            {"color": "red", "category": "Character", "title": "Very Low CIBIL Score",
             "description": "CIBIL score of 520 indicates significant credit risk", "source": "CIBIL Report", "value": 520},
            {"color": "red", "category": "Character", "title": "Suit Filed Accounts",
             "description": "2 suit-filed accounts — indicates legal action by creditors", "source": "CIBIL Report", "value": 2},
            {"color": "red", "category": "GST", "title": "Severe GST Mismatch",
             "description": "34.1% discrepancy between GSTR-3B (22M) and GSTR-2A (14.5M) — high risk of circular trading",
             "source": "GST Cross-Verification", "value": 34.1},
            {"color": "red", "category": "Capital", "title": "Extreme Leverage",
             "description": "Debt/Equity ratio of 9.0x — company is severely over-leveraged", "source": "Balance Sheet", "value": 9.0},
            {"color": "red", "category": "Capacity", "title": "Net Loss",
             "description": "Company posted net loss of -3.5M indicating operational distress", "source": "P&L Statement", "value": -3500000},
            {"color": "red", "category": "Capacity", "title": "Negative Revenue Growth",
             "description": "-12% YoY revenue decline signals business contraction", "source": "Financial Analysis", "value": -12.0},
            {"color": "red", "category": "Capacity", "title": "Multiple DPD 90+ Accounts",
             "description": "2 accounts with 90+ days past due — severe repayment stress", "source": "CIBIL Report", "value": 2},
            {"color": "red", "category": "Collateral", "title": "Inadequate Collateral",
             "description": "Collateral coverage of 0.22x — loan far exceeds security value", "source": "Valuation", "value": 0.22},
        ],
        "research": [
            {"source": "LiveLaw.in", "title": "SkyHigh Infra facing NCLT proceedings from creditors",
             "snippet": "Two operational creditors have filed insolvency petitions against SkyHigh Infrastructure.",
             "sentiment": "negative", "category": "Legal"},
            {"source": "Money Control", "title": "Infra firm promoter under ED lens for fund diversion",
             "snippet": "Enforcement Directorate investigating the promoter group for alleged siphoning of bank funds.",
             "sentiment": "negative", "category": "Legal"},
            {"source": "Construction World", "title": "Multiple infra projects stalled in Western India",
             "snippet": "Several mid-sized infra firms are struggling to complete projects amid cash flow constraints.",
             "sentiment": "negative", "category": "Sector"},
        ],
        "notes": [
            {"officer_name": "Amit Deshmukh", "note": "Site visit 25-Jan-2025: Office appeared largely empty. Could not meet the promoter — was told he is 'travelling'. Staff seemed evasive about project progress. Equipment at construction site appears idle and some looks damaged. Serious concerns about operational continuity.", "category": "Character", "severity": "critical"},
            {"officer_name": "Amit Deshmukh", "note": "Follow-up call 28-Jan-2025: Promoter finally available. When asked about ED investigation, gave vague responses. Financial records provided were incomplete. Strong recommendation for caution.", "category": "Character", "severity": "high"},
        ],
    },
]


def seed_demo_data(use_databricks: bool = True):
    """Seed the 3 demo entities into the system."""
    db = None
    if use_databricks:
        try:
            db = DatabricksClient()
            db.initialize_schema()
        except Exception as e:
            print(f"[WARN] Databricks unavailable, using in-memory only: {e}")
            db = None

    seeded = []
    for entity in DEMO_ENTITIES:
        eid = entity["entity_id"]
        name = entity["company_name"]
        fin = entity["financials"]

        if db:
            try:
                db.upsert_financials(eid, name, "Demo_Data", fin)

                gst = entity["gst"]
                db.save_gst_analysis(eid, "FY24",
                    gst["gstr_3b_turnover"], gst["gstr_2a_turnover"],
                    gst["mismatch_pct"], gst["circular_trading_risk"])

                db.save_cibil(eid, entity["cibil"])
                db.save_flags(eid, entity["flags"])
                db.save_research(eid, entity["research"])
                for note in entity["notes"]:
                    db.save_note(eid, note)
            except Exception as e:
                print(f"[WARN] DB seed for {eid}: {e}")

        seeded.append({"entity_id": eid, "company_name": name})
        print(f"[OK] Seeded: {name} ({eid})")

    return seeded


def get_demo_entities():
    """Return demo entity data without DB dependency (in-memory)."""
    return DEMO_ENTITIES


if __name__ == "__main__":
    seed_demo_data()

"""
Intelli-Credit: Enhanced Databricks Client
Manages all Delta Table operations for the credit decisioning engine.
"""
import os
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List, Optional
from databricks import sql
import config


class DatabricksClient:
    """Handles all Databricks SQL Warehouse interactions."""

    def __init__(self):
        self.server_hostname = config.DATABRICKS_SERVER_HOSTNAME
        self.http_path = config.DATABRICKS_HTTP_PATH
        self.access_token = config.DATABRICKS_TOKEN
        self.catalog = config.DATABRICKS_CATALOG
        self.schema = config.DATABRICKS_SCHEMA

    def get_connection(self):
        return sql.connect(
            server_hostname=self.server_hostname,
            http_path=self.http_path,
            access_token=self.access_token
        )

    def _execute(self, query: str, fetch: bool = False):
        """Execute a SQL query, optionally fetching results."""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                for stmt in query.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        cursor.execute(stmt)
                if fetch:
                    return cursor.fetchall()

    def _table(self, name: str) -> str:
        return f"{self.catalog}.{self.schema}.{name}"

    # ──────────── Schema Initialization ────────────

    def initialize_schema(self):
        """Creates all Delta Tables for Intelli-Credit."""
        tables = [
            f"""CREATE TABLE IF NOT EXISTS {self._table('corporate_financials')} (
                entity_id STRING,
                company_name STRING,
                document_type STRING,
                filing_period STRING,
                revenue DOUBLE,
                ebitda DOUBLE,
                net_profit DOUBLE,
                total_debt DOUBLE,
                total_assets DOUBLE,
                net_worth DOUBLE,
                current_assets DOUBLE,
                current_liabilities DOUBLE,
                collateral_value DOUBLE,
                gst_turnover DOUBLE,
                interest_expense DOUBLE,
                operating_margin DOUBLE,
                revenue_growth_yoy DOUBLE,
                processed_at TIMESTAMP
            ) USING DELTA""",

            f"""CREATE TABLE IF NOT EXISTS {self._table('gst_analysis')} (
                entity_id STRING,
                period STRING,
                gstr_3b_turnover DOUBLE,
                gstr_2a_turnover DOUBLE,
                mismatch_pct DOUBLE,
                circular_trading_risk DOUBLE,
                analyzed_at TIMESTAMP
            ) USING DELTA""",

            f"""CREATE TABLE IF NOT EXISTS {self._table('cibil_data')} (
                entity_id STRING,
                cibil_score INT,
                total_credit_facilities INT,
                overdue_accounts INT,
                suit_filed_accounts INT,
                dpd_30_plus INT,
                dpd_90_plus INT,
                credit_utilization_pct DOUBLE,
                updated_at TIMESTAMP
            ) USING DELTA""",

            f"""CREATE TABLE IF NOT EXISTS {self._table('risk_flags')} (
                entity_id STRING,
                color STRING,
                category STRING,
                title STRING,
                description STRING,
                source STRING,
                value DOUBLE,
                threshold STRING,
                created_at TIMESTAMP
            ) USING DELTA""",

            f"""CREATE TABLE IF NOT EXISTS {self._table('research_findings')} (
                entity_id STRING,
                source STRING,
                title STRING,
                snippet STRING,
                sentiment STRING,
                category STRING,
                found_at TIMESTAMP
            ) USING DELTA""",

            f"""CREATE TABLE IF NOT EXISTS {self._table('officer_notes')} (
                entity_id STRING,
                officer_name STRING,
                note STRING,
                category STRING,
                severity STRING,
                created_at TIMESTAMP
            ) USING DELTA""",

            f"""CREATE TABLE IF NOT EXISTS {self._table('credit_decisions')} (
                entity_id STRING,
                company_name STRING,
                decision STRING,
                confidence DOUBLE,
                risk_score DOUBLE,
                recommended_loan_amount DOUBLE,
                recommended_interest_rate DOUBLE,
                character_score DOUBLE,
                capacity_score DOUBLE,
                capital_score DOUBLE,
                collateral_score DOUBLE,
                conditions_score DOUBLE,
                shap_explanations STRING,
                decision_reasons STRING,
                decided_at TIMESTAMP
            ) USING DELTA"""
        ]

        create_schema = f"CREATE SCHEMA IF NOT EXISTS {self.catalog}.{self.schema}"
        self._execute(create_schema)
        for t in tables:
            self._execute(t)
        print("[OK] All Delta tables initialized.")

    # ──────────── Corporate Financials ────────────

    def upsert_financials(self, entity_id: str, company_name: str, doc_type: str,
                          data: Dict[str, Any]):
        """Insert or update financial data for an entity."""
        now = datetime.utcnow().isoformat()
        q = f"""INSERT INTO {self._table('corporate_financials')} VALUES (
            '{entity_id}', '{company_name}', '{doc_type}',
            '{data.get("period", "FY24")}',
            {float(data.get("revenue", 0))},
            {float(data.get("ebitda", 0))},
            {float(data.get("net_profit", 0))},
            {float(data.get("total_debt", 0))},
            {float(data.get("total_assets", 0))},
            {float(data.get("net_worth", 0))},
            {float(data.get("current_assets", 0))},
            {float(data.get("current_liabilities", 0))},
            {float(data.get("collateral_value", 0))},
            {float(data.get("gst_turnover", 0))},
            {float(data.get("interest_expense", 0))},
            {float(data.get("operating_margin", 0))},
            {float(data.get("revenue_growth_yoy", 0))},
            '{now}'
        )"""
        self._execute(q)

    def get_financials(self, entity_id: str) -> List[Dict]:
        """Fetch all financial records for an entity."""
        q = f"""SELECT * FROM {self._table('corporate_financials')}
                WHERE entity_id = '{entity_id}' ORDER BY processed_at DESC"""
        rows = self._execute(q, fetch=True)
        if not rows:
            return []
        cols = ["entity_id", "company_name", "document_type", "filing_period",
                "revenue", "ebitda", "net_profit", "total_debt", "total_assets",
                "net_worth", "current_assets", "current_liabilities",
                "collateral_value", "gst_turnover", "interest_expense",
                "operating_margin", "revenue_growth_yoy", "processed_at"]
        return [dict(zip(cols, row)) for row in rows]

    # ──────────── GST Analysis ────────────

    def save_gst_analysis(self, entity_id: str, period: str, gstr_3b: float,
                          gstr_2a: float, mismatch_pct: float,
                          circular_risk: float):
        now = datetime.utcnow().isoformat()
        q = f"""INSERT INTO {self._table('gst_analysis')} VALUES (
            '{entity_id}', '{period}', {gstr_3b}, {gstr_2a},
            {mismatch_pct}, {circular_risk}, '{now}'
        )"""
        self._execute(q)

    def get_gst_analysis(self, entity_id: str) -> List[Dict]:
        q = f"""SELECT * FROM {self._table('gst_analysis')}
                WHERE entity_id = '{entity_id}'"""
        rows = self._execute(q, fetch=True)
        if not rows:
            return []
        cols = ["entity_id", "period", "gstr_3b_turnover", "gstr_2a_turnover",
                "mismatch_pct", "circular_trading_risk", "analyzed_at"]
        return [dict(zip(cols, row)) for row in rows]

    # ──────────── CIBIL Data ────────────

    def save_cibil(self, entity_id: str, data: Dict[str, Any]):
        now = datetime.utcnow().isoformat()
        q = f"""INSERT INTO {self._table('cibil_data')} VALUES (
            '{entity_id}', {int(data.get("cibil_score", 0))},
            {int(data.get("total_credit_facilities", 0))},
            {int(data.get("overdue_accounts", 0))},
            {int(data.get("suit_filed_accounts", 0))},
            {int(data.get("dpd_30_plus", 0))},
            {int(data.get("dpd_90_plus", 0))},
            {float(data.get("credit_utilization_pct", 0))},
            '{now}'
        )"""
        self._execute(q)

    def get_cibil(self, entity_id: str) -> Optional[Dict]:
        q = f"""SELECT * FROM {self._table('cibil_data')}
                WHERE entity_id = '{entity_id}' ORDER BY updated_at DESC LIMIT 1"""
        rows = self._execute(q, fetch=True)
        if not rows:
            return None
        cols = ["entity_id", "cibil_score", "total_credit_facilities",
                "overdue_accounts", "suit_filed_accounts", "dpd_30_plus",
                "dpd_90_plus", "credit_utilization_pct", "updated_at"]
        return dict(zip(cols, rows[0]))

    # ──────────── Risk Flags ────────────

    def save_flags(self, entity_id: str, flags: List[Dict]):
        now = datetime.utcnow().isoformat()
        for f in flags:
            val = f.get("value")
            val_str = str(val) if val is not None else "NULL"
            thresh = f.get("threshold", "")
            desc = str(f.get("description", "")).replace("'", "''")
            title = str(f.get("title", "")).replace("'", "''")
            q = f"""INSERT INTO {self._table('risk_flags')} VALUES (
                '{entity_id}', '{f["color"]}', '{f["category"]}',
                '{title}', '{desc}',
                '{f.get("source", "")}', {val_str}, '{thresh}', '{now}'
            )"""
            self._execute(q)

    def get_flags(self, entity_id: str) -> List[Dict]:
        q = f"""SELECT * FROM {self._table('risk_flags')}
                WHERE entity_id = '{entity_id}' ORDER BY created_at DESC"""
        rows = self._execute(q, fetch=True)
        if not rows:
            return []
        cols = ["entity_id", "color", "category", "title", "description",
                "source", "value", "threshold", "created_at"]
        return [dict(zip(cols, row)) for row in rows]

    # ──────────── Research Findings ────────────

    def save_research(self, entity_id: str, findings: List[Dict]):
        now = datetime.utcnow().isoformat()
        for f in findings:
            snippet = str(f.get("snippet", "")).replace("'", "''")
            title = str(f.get("title", "")).replace("'", "''")
            q = f"""INSERT INTO {self._table('research_findings')} VALUES (
                '{entity_id}', '{f.get("source", "")}',
                '{title}', '{snippet}',
                '{f.get("sentiment", "neutral")}',
                '{f.get("category", "")}', '{now}'
            )"""
            self._execute(q)

    def get_research(self, entity_id: str) -> List[Dict]:
        q = f"""SELECT * FROM {self._table('research_findings')}
                WHERE entity_id = '{entity_id}'"""
        rows = self._execute(q, fetch=True)
        if not rows:
            return []
        cols = ["entity_id", "source", "title", "snippet", "sentiment",
                "category", "found_at"]
        return [dict(zip(cols, row)) for row in rows]

    # ──────────── Officer Notes ────────────

    def save_note(self, entity_id: str, note: Dict):
        now = datetime.utcnow().isoformat()
        note_text = str(note.get("note", "")).replace("'", "''")
        q = f"""INSERT INTO {self._table('officer_notes')} VALUES (
            '{entity_id}', '{note.get("officer_name", "Credit Officer")}',
            '{note_text}', '{note.get("category", "Conditions")}',
            '{note.get("severity", "medium")}', '{now}'
        )"""
        self._execute(q)

    def get_notes(self, entity_id: str) -> List[Dict]:
        q = f"""SELECT * FROM {self._table('officer_notes')}
                WHERE entity_id = '{entity_id}'"""
        rows = self._execute(q, fetch=True)
        if not rows:
            return []
        cols = ["entity_id", "officer_name", "note", "category",
                "severity", "created_at"]
        return [dict(zip(cols, row)) for row in rows]

    # ──────────── Credit Decisions ────────────

    def save_decision(self, decision: Dict):
        import json
        now = datetime.utcnow().isoformat()
        shap_str = json.dumps(decision.get("shap_explanations", {})).replace("'", "''")
        reasons_str = json.dumps(decision.get("decision_reasons", [])).replace("'", "''")
        company = str(decision.get("company_name", "")).replace("'", "''")
        q = f"""INSERT INTO {self._table('credit_decisions')} VALUES (
            '{decision["entity_id"]}', '{company}',
            '{decision["decision"]}', {decision.get("confidence", 0)},
            {decision.get("risk_score", 50)},
            {decision.get("recommended_loan_amount", 0)},
            {decision.get("recommended_interest_rate", 0)},
            {decision.get("character_score", 50)},
            {decision.get("capacity_score", 50)},
            {decision.get("capital_score", 50)},
            {decision.get("collateral_score", 50)},
            {decision.get("conditions_score", 50)},
            '{shap_str}', '{reasons_str}', '{now}'
        )"""
        self._execute(q)

    def get_decision(self, entity_id: str) -> Optional[Dict]:
        q = f"""SELECT * FROM {self._table('credit_decisions')}
                WHERE entity_id = '{entity_id}' ORDER BY decided_at DESC LIMIT 1"""
        rows = self._execute(q, fetch=True)
        if not rows:
            return None
        cols = ["entity_id", "company_name", "decision", "confidence",
                "risk_score", "recommended_loan_amount",
                "recommended_interest_rate", "character_score",
                "capacity_score", "capital_score", "collateral_score",
                "conditions_score", "shap_explanations", "decision_reasons",
                "decided_at"]
        return dict(zip(cols, rows[0]))

    # ──────────── Circular Trading Detection ────────────

    def detect_circular_trading(self, entity_id: str) -> Dict[str, Any]:
        """Cross-leverage GST returns against bank statements."""
        financials = self.get_financials(entity_id)
        if not financials:
            return {"risk": 0, "flags": []}

        gst_records = [f for f in financials if "GST" in f.get("document_type", "")]
        bank_records = [f for f in financials if "Bank" in f.get("document_type", "")]

        if not gst_records or not bank_records:
            return {"risk": 0, "flags": []}

        total_gst = sum(f.get("gst_turnover", 0) for f in gst_records)
        total_bank_credit = sum(f.get("revenue", 0) for f in bank_records)

        flags = []
        risk = 0.0

        if total_bank_credit > 0:
            ratio = abs(total_gst - total_bank_credit) / total_bank_credit
            if ratio > config.GST_MISMATCH_RED_THRESHOLD:
                risk = min(ratio * 100, 100)
                flags.append({
                    "color": "red",
                    "category": "GST",
                    "title": "Revenue Inflation Risk",
                    "description": f"GST turnover (₹{total_gst:,.0f}) vs Bank credits (₹{total_bank_credit:,.0f}) mismatch: {ratio:.1%}",
                    "source": "GST vs Bank Statement Cross-leverage",
                    "value": ratio * 100,
                    "threshold": f">{config.GST_MISMATCH_RED_THRESHOLD:.0%}"
                })
            elif ratio > config.GST_MISMATCH_BLUE_THRESHOLD:
                risk = ratio * 50
                flags.append({
                    "color": "blue",
                    "category": "GST",
                    "title": "Minor Revenue Discrepancy",
                    "description": f"Moderate GST vs Bank mismatch: {ratio:.1%}",
                    "source": "GST vs Bank Statement Cross-leverage",
                    "value": ratio * 100,
                    "threshold": f">{config.GST_MISMATCH_BLUE_THRESHOLD:.0%}"
                })
            else:
                flags.append({
                    "color": "green",
                    "category": "GST",
                    "title": "Consistent Revenue Reporting",
                    "description": f"GST and Bank statements align within {ratio:.1%}",
                    "source": "GST vs Bank Statement Cross-leverage",
                    "value": ratio * 100
                })

        return {"risk": risk, "flags": flags}

    # ──────────── Entity Listing ────────────

    def list_entities(self) -> List[Dict]:
        """List all unique entities with their latest data."""
        q = f"""SELECT DISTINCT entity_id, company_name
                FROM {self._table('corporate_financials')}
                ORDER BY entity_id"""
        rows = self._execute(q, fetch=True)
        if not rows:
            return []
        return [{"entity_id": r[0], "company_name": r[1] or r[0]} for r in rows]


# Backward-compatible alias
DatabricksIngestor = DatabricksClient